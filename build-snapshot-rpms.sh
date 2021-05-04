#!/bin/bash

set -eu

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

#############################################################################
# These vars can be adjusted with the options passing to this script:
#############################################################################

# This defines the order in which to build packages.
#
# NOTE: When overwriting this from the outside, only shorten the list of
# projects to build or add to it but do not pick out individual projects to
# build. This is not tested.
projects="llvm clang lld compiler-rt"

# The current date (e.g. 20210427) is used to determine from which tarball a
# snapshot of LLVM is being built.
yyyymmdd="$(date +%Y%m%d)"

mock_clean_before=""
mock_scrub=""
mock_build_rpm=""
mock_check_option="--nocheck"
koji_build_rpm=""
update_projects=""
koji_wait_for_build_option="--nowait"
koji_config_path="koji.conf"
koji_config_profile=""

#############################################################################
#############################################################################

# Setup some directories for later use
cur_dir=$(pwd)
projects_dir=${cur_dir}/projects
out_dir=${cur_dir}/out
rpms_dir=${out_dir}/rpms
srpms_dir=${out_dir}/srpms
mkdir -pv ${out_dir}/{rpms,srpms,tmp}


usage() {
cat <<EOF
Build LLVM snapshot SRPMs using mock and optionally RPMs using mock and/or koji.

Usage: $(basename $0) 
            [--yyyymmdd <YYYYMMDD>]
            [--mock-no-clean-before]
            [--mock-scrub]
            [--mock-build-rpm]
            [--mock-check-rpm]
            [--koji-build-rpm]
            [--koji-wait-for-build]
            [--koji-config-path "/path/to/koji.conf"]
            [--koji-config-profile "profile"]
            [--update-projects]
            [--projects "llvm clang lld compiler-rt"] 

OPTIONS
-------

  --yyyymmdd "<YYYYMMDD>"                   The date digits in reverse form of for which to build the snapshot (defaults to today, e.g. "$(date +%Y%m%d)").
  --projects "<X Y Z>"                      LLVM sub-projects to build (defaults to "llvm clang lld compiler-rt").
                                            Please note that the order is important and packages depend on each other.
                                            Only tweak if you know what you're doing.
  
  Mock related:

  --mock-build-rpm                          Build RPMs (also) using mock. (Please note that SRPMs are always built with mock.)
                                            Please note that --koji-build-rpm and --mock-build-rpm are not mutually exclusive.
  --mock-check-rpm                          Omit the "--nocheck" option from any mock call. (Reasoning: for snapshots we don't want to run "make check".)
  --mock-no-clean-before                    Don't clean the mock environment upon each new script invocation.
  --mock-scrub                              Wipe away the entire mock environment upon each script invocation.

  Koji related:

  --koji-build-rpm                          Build RPMs (also) using koji.
                                            Please note that --koji-build-rpm and --mock-build-rpm are not mutually exclusive.
  --koji-wait-for-build                     Wait for koji build to finish (default: no).
  --koji-config-path "/path/to/koji.conf"   Path to koji.conf (defaults to "koji.conf").
  --koji-config-profile "profile"           Koji configuration profile (defaults to "koji-clang").
  
  Misc:

  --update-projects                         Fetch the latest updates for each LLVM sub-project before building.

EXAMPLE VALUES FOR PLACEHOLDERS
-------------------------------

  * "<X,Y,Z>"    -> "llvm clang lld compiler-rt"
  * "<YYYYMMDD>" -> "20210414"

EXAMPLES
--------

  $0

  Will build SRPMs for "llvm clang lld compiler-rt". No RPM will be build.

  $0 --projects "llvm clang"

  Will build SRPMs for llvm and clang. No RPMs will be build

  $0 --projects "llvm clang" --mock-build-rpm

  Will build SRPMs and RPMs for llvm and clang using mock.

  $0 --projects "llvm clang" --mock-build-rpm --koji-build-rpm

  Will build SRPMs and RPMs for llvm and clang using mock and also in koji. 

EOF
}


# Clean submodules and remove untracked files and reset back to content from
# upstream. If you need to update a submodule to the latest version, please do
# git submodule update --remote projects/<YOURPROJECT>. 
clean_submodules() {
    pushd $cur_dir
    git submodule init
    git submodule update --force
    git submodule foreach --recursive git clean -f
    git submodule foreach --recursive git clean -f -d
    git submodule foreach --recursive git reset --hard HEAD
    popd
}

# Updates the LLVM sub-project submodules with the latest version of the tracked
# branch.
update_submodules() {
    pushd $cur_dir
    git submodule update --remote
    popd
}


# Takes an original spec file and prefixes snapshot information to it. Then it
# writes the generated spec file to a new location.
#
# @param orig_file Path to the original spec file.
# @param out_file Path to the spec file that's generated
# @param llvm_snapshot_revision The "<major>.<minor>.<patch>" version string.
# @param llvm_snapshot_git_revision The sha1 of the snapshot that's being built.
# @param yyyymmdd Reversed date for which to build the snapshot
new_snapshot_spec_file() {
    local orig_file=$1
    local out_file=$2
    local llvm_version=$3
    local llvm_git_revision=$4
    local yyyymmdd=$5

    cat <<EOF > ${out_file}
################################################################################
# BEGIN SNAPSHOT PREFIX
################################################################################

%global _with_snapshot_build 1
# Optionally enable snapshot build with \`--with=snapshot_build\` or \`--define
# "_with_snapshot_build 1"\`.
%bcond_with snapshot_build

%if %{with snapshot_build}
%global llvm_snapshot_yyyymmdd ${yyyymmdd}
%global llvm_snapshot_version ${llvm_version}
%global llvm_snapshot_git_revision ${llvm_git_revision}

# Split version
%global llvm_snapshot_version_major %{lua: print(string.match(rpm.expand("%{llvm_snapshot_version}"), "[0-9]+"));}
%global llvm_snapshot_version_minor %{lua: print(string.match(rpm.expand("%{llvm_snapshot_version}"), "%p([0-9]+)%p"));}
%global llvm_snapshot_version_patch %{lua: print(string.match(rpm.expand("%{llvm_snapshot_version}"), "%p([0-9]+)$"));}

# Shorten git revision
%global llvm_snapshot_git_revision_short %{lua: print(string.sub(rpm.expand("%llvm_snapshot_git_revision"), 0, 14));}
%endif

################################################################################
# END SNAPSHOT PREFIX
################################################################################

EOF
    
    cat ${orig_file} >> ${out_file}
}


build_snapshot() {
    # Get the current snapshot version and git revision for today
    llvm_version=$(curl -sL https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-release-${yyyymmdd}.txt)
    llvm_git_revision=$(curl -sL https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-git-revision-${yyyymmdd}.txt)
    llvm_version_major=$(echo $llvm_version | grep -ioP '^[0-9]+')
    llvm_version_minor=$(echo $llvm_version | grep -ioP '\.\K[0-9]+' | head -n1)
    llvm_version_patch=$(echo $llvm_version | grep -ioP '\.\K[0-9]+$')

    # Extract for which Fedora Core version (e.g. fc34) we build packages.
    # This is like the ongoing version number for the rolling Fedora "rawhide" release.
    fc_version=$(grep -ioP "config_opts\['releasever'\] = '\K[0-9]+" /etc/mock/templates/fedora-rawhide.tpl)

    clean_submodules

    [[ "${update_projects}" != "" ]] && update_submodules
    [[ "${mock_clean}" != "" ]] && mock -r ${cur_dir}/rawhide-mock.cfg --clean
    [[ "${mock_scrub}" != "" ]] && mock -r ${cur_dir}/rawhide-mock.cfg --scrub all

    for proj in $projects; do
        pushd $projects_dir/$proj

        new_spec_file=$(mktemp --suffix=.spec)
        new_snapshot_spec_file "$projects_dir/$proj/$proj.spec" ${new_spec_file} ${llvm_version} ${llvm_git_revision} ${yyyymmdd}
        
        # Show which packages will be build with this spec file
        rpmspec -q ${new_spec_file}

        # Download files from the specfile into the project directory
        rpmdev-spectool -g -a -C . $new_spec_file

        # Build SRPM
        time mock -r ${cur_dir}/rawhide-mock.cfg \
            --spec=$new_spec_file \
            --sources=$PWD \
            --buildsrpm \
            --resultdir=$srpms_dir \
            --no-cleanup-after \
            --no-clean \
            --isolation=simple ${mock_check_option}
        popd
        
        if [ "${koji_build_rpm}" != "" ]; then
            pushd $cur_dir
            koji \
                --config=${koji_config_path} \
                -p ${koji_config_profile} \
                build ${koji_wait_for_build_option} \
                f${fc_version}-llvm-snapshot ${srpms_dir}/${proj}-${llvm_version}~pre${yyyymmdd}.g*.src.rpm
            popd
        fi

        if [ "${mock_build_rpm}" != "" ]; then
            pushd $projects_dir/$proj
            time mock -r ${cur_dir}/rawhide-mock.cfg \
                --rebuild ${srpms_dir}/${proj}-${llvm_version}~pre${yyyymmdd}.g*.src.rpm \
                --resultdir=${rpms_dir} \
                --no-cleanup-after \
                --no-clean \
                --isolation=simple \
                --postinstall ${mock_check_option}
            popd
        fi
    done
}



while [ $# -gt 0 ]; do
    case $1 in
        --yyyymmdd )
            shift
            yyyymmdd="$1"
            ;;
        --projects )
            shift
            projects="$1"
            ;;
        --mock-no-clean )
            mock_clean=""
            ;;
        --mock-scrub )
            mock_scrub="1"
            ;;
        --mock-build-rpm )
            mock_build_rpm="1"
            ;;
        --mock-check-rpm )
            mock_check_option=""
            ;;
        --koji-build-rpm )
            koji_build_rpm="1"
            ;;
        --update-projects )
            update_projects="1"
            ;;
        --koji-wait-for-build )
            koji_wait_for_build_option=""
            ;;
        --koji-config-path )
            shift
            koji_config_path="$1"
            ;;
        --koji-config-profile )
            shift
            koji_config_profile="$1"
            ;;
        -h | -help | --help )
            usage
            exit 0
            ;;
        * )
            echo "unknown option: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

build_snapshot
exit 0


# Go to end of file to see logging
# (

# NOTES TO MYSELF(kwk):
# ---------------------
# Login to build host (e.g. tofan)
#  
#       ssh tofan
#
# Start of recover a previous session:
#
#       screen or screen -dr
#
# Work on non-NFS drive:
#
#       cd /opt/notnfs/$USER
#
# Clone this repo:
#
#       git clone --recurse-submodules https://github.com/kwk/llvm-daily-fedora-rpms.git
#
# Ensure %{_sourcdir} points to a writable location
#
#       mkdir -p /opt/notnfs/$USER/rpmbuild/SOURCES
#       echo '%_topdir /opt/notnfs/$USER/rpmbuild' >> ~/.rpmmacros
#
# The following should show /opt/notnfs/$USER/rpmbuild/SOURCES
#
#       rpm --eval '%{_sourcedir}'
#

# # # Create dnf/yum repo
# # mkdir -pv $out_dir/repo/fedora/$fc_version/$(arch)/base
# # mv -v $rpms_dir/*.rpm $out_dir/repo/fedora/$fc_version/$(arch)/base
# # createrepo $out_dir/repo/fedora/$fc_version/$(arch)/base

# # cat <<EOF > /etc/yum.repos.d/llvm-snapshots.repo
# # [llvm-snapshots]
# # name=LLVM Snapshots
# # failovermethod=priority
# # baseurl=http://tofan.yyz.redhat.com:33229/fedora/$releasever/$basearch/base
# # enabled=1
# # gpgcheck=0
# # EOF
# # yum update

# # Build compat packages
# # git clone -b rawhide https://src.fedoraproject.org/rpms/llvm.git
# # cd llvm
# # fedpkg mockbuild --with compat_build

# # ) |& tee combined.$(date --iso-8601=seconds).log