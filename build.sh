#!/bin/bash

set -eu

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

# Setup some directories for later use
cur_dir=$(pwd)
out_dir=$(pwd)/out
projects_dir=
rpms_dir=
srpms_dir=

bootstrap() {
    out_dir=$(realpath $out_dir)
    projects_dir=$out_dir/projects
    rpms_dir=$out_dir/rpms
    [[ -z "$srpms_dir" ]] && srpms_dir=$out_dir/srpms
    srpms_dir=$(realpath $srpms_dir)
    mkdir -pv $out_dir $rpms_dir $srpms_dir $projects_dir

    # Write a fresh mock config
    # TODO(kwk): Find a better place to do this...
    createrepo --update $rpms_dir
    export REPO_DIR=$rpms_dir
    cat $cur_dir/mock.cfg.in | envsubst '$REPO_DIR' > $out_dir/mock.cfg
    unset REPO_DIR
}

#############################################################################
# These vars can be adjusted with the options passing to this script:
#############################################################################

# This defines the order in which to build packages.
#
# NOTE: When overwriting this from the outside, only shorten the list of
# projects to build or add to it but do not pick out individual projects to
# build. This is not tested.
projects="python-lit llvm clang lld compiler-rt mlir lldb libomp"

# The current date (e.g. 20210427) is used to determine from which tarball a
# snapshot of LLVM is being built.
yyyymmdd="$(date +%Y%m%d)"

mock_build_rpm=""
mock_check_option="--nocheck"
mock_config_path="${cur_dir}/rawhide-mock.cfg"
mock_install_compat_packages=""
koji_build_rpm=""
koji_wait_for_build_option="--nowait"
koji_config_path="koji.conf"
koji_config_profile="koji-clang"

build_compat_packages=""

opt_skip_srpm_generation=""

#############################################################################
#############################################################################

# To be filled out by get_llvm_version() below.
llvm_version=""
llvm_git_revision=""
llvm_version_major=""
llvm_version_minor=""
llvm_version_patch=""

get_llvm_version() {
    local url="https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-release-${yyyymmdd}.txt"
    llvm_version=$(curl -sfL "$url")
    local ret=$?
    if [[ $ret -ne 0 ]]; then
        echo "ERROR: failed to get llvm version from $url"
        exit 1
    fi
    
    url="https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-git-revision-${yyyymmdd}.txt"
    llvm_git_revision=$(curl -sfL "$url")
    ret=$?
    if [[ $ret -ne 0 ]]; then
        echo "ERROR: failed to get llvm git revision from $url"
        exit 1
    fi
    llvm_version_major=$(echo $llvm_version | grep -ioP '^[0-9]+')
    llvm_version_minor=$(echo $llvm_version | grep -ioP '\.\K[0-9]+' | head -n1)
    llvm_version_patch=$(echo $llvm_version | grep -ioP '\.\K[0-9]+$')
}

show_llvm_version() {
    cat <<EOF
Date:               ${yyyymmdd}
LLVM Version:       ${llvm_version}
LLVM Git Revision:  ${llvm_git_revision}
LLVM Major Version: ${llvm_version_major}
LLVM Minor Version: ${llvm_version_minor}
LLVM Patch Version: ${llvm_version_patch}
EOF
}

usage() {
local script=$(basename $0)
cat <<EOF
Build LLVM snapshot SRPMs using mock and optionally RPMs using mock and/or koji.

Usage: ${script}
            [--yyyymmdd <YYYYMMDD>]
            [--projects "llvm clang lld compiler-rt"]
            [--out-dir "out"]
            [--srpms-dir "out/srpms"]
            [--skip-srpm-generation]
            [--mock-wipe]
            [--mock-build-rpm]
            [--mock-check-rpm]
            [--mock-config-path "/path/to/mock.cfg"]
            [--koji-build-rpm]
            [--koji-wait-for-build]
            [--koji-config-path "/path/to/koji.conf"]
            [--koji-config-profile "profile"]
            [--update-projects]
            [--clean-projects]
            [--verbose]
            [--generate-spec-files]
            

OPTIONS
-------

  --yyyymmdd "<YYYYMMDD>"                   The date digits in reverse form of for which to build the snapshot (defaults to today, e.g. "$(date +%Y%m%d)").
  --projects "<X Y Z>"                      LLVM sub-projects to build (defaults to "python-lit llvm clang lld compiler-rt libomp mlir lldb").
                                            Please note that the order is important and packages depend on each other.
                                            Only tweak if you know what you're doing.
  --out-dir "out"                           Directory in which to store all the artifacts (defaults to "${cur_dir}/out").
                                            The directory will be created if it doesn't exist.
  --srpms-dir "out/srpms"                   Directory in which to store srpms. Usually this is in "out/srpms". But in case you want
                                            to reuse existing SRPMs, you can store them elsewhere. The directory will be created if it doesn't exist. 
  --skip-srpm-generation                    By default, an SRPM is being build. But if you pass this option, it won't build one.
                                            This makes most sense if you have pre-built them and you tell with --srpms-dir where
                                            they exist
  Mock related:

  --mock-build-rpm                          Build RPMs (also) using mock. (Please note that SRPMs are always built with mock.)
                                            Please note that --koji-build-rpm and --mock-build-rpm are not mutually exclusive.
  --mock-check-rpm                          Omit the "--nocheck" option from any mock call.
  --mock-wipe                               Remove mock chroot and cache and exit.
  --mock-config-path                        Path to mock configuration file (defaults to "${out_dir}/mock.cfg").
                                            NOTE: When this option is given, no snapshot package will be built. Just invoke the script a second time.

  Koji related:

  --koji-build-rpm                          Build RPMs (also) using koji.
                                            Please note that --koji-build-rpm and --mock-build-rpm are not mutually exclusive.
  --koji-wait-for-build                     Wait for koji build to finish (default: no).
  --koji-config-path "/path/to/koji.conf"   Path to koji.conf (defaults to "koji.conf").
  --koji-config-profile "profile"           Koji configuration profile (defaults to "koji-clang").
  
  Misc:

  --build-compat-packages                   Will build the compatibility packages of the given projects (by having a spec file
                                            that activates the compat_build build condition).
  --reset-projects                          Remove projects and fetch them again.
  --clean-projects                          Removes untracked files in each project and resets it back to HEAD.
  --verbose                                 Toggle on output from "set -x".
  --show-llvm-version                       Prints the version for the given date (see --yyyymmdd) and exits.
  --generate-spec-files                     Generates snapshot spec files for the given date (see --yyyymmdd)
                                            and projects (see --projects), then exits. When --build-compat-packages is given
                                            the spec file is not snapshot specific.

EXAMPLE VALUES FOR PLACEHOLDERS
-------------------------------

  * "<X Y Z>"    -> "llvm clang lld compiler-rt mlir lldb"
  * "<YYYYMMDD>" -> "20210414"

EXAMPLES
--------

    Show the LLVM version for a May 6th 2021 date. Depending on the retention time
    for source snapshots, this might not work for a given date.

        ${script} --show-llvm-version --yyyymmdd 20210505

        Date:               20210505
        LLVM Version:       13.0.0
        LLVM Git Revision:  88ec05b654758fecfe7147064dce84a09e2e20a8
        LLVM Major Version: 13
        LLVM Minor Version: 0
        LLVM Patch Version: 0

    Build SRPMs for llvm and clang. No RPMs will be build because no method (mock or koji was selected).

        ${script} --projects "llvm clang"

    Build SRPMs and RPMs for llvm and clang using mock.

        ${script} --projects "llvm clang" --mock-build-rpm

    Build SRPMs and RPMs for llvm and clang using mock and also in koji. 

        ${script} --projects "llvm clang" --mock-build-rpm --koji-build-rpm

    Clean the mock environment.

        ${script} --mock-wipe
EOF
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

new_compat_spec_file() {
    local orig_file=$1
    local out_file=$2

    cat <<EOF > ${out_file}
################################################################################
# BEGIN COMPAT PREFIX
################################################################################

%global _with_compat_build 1

################################################################################
# END COMPAT PREFIX
################################################################################

EOF
    
    cat ${orig_file} >> ${out_file}
}



build_snapshot() {
    reset_projects
    
    # Checkout rawhide branch from upstream if building compat package
    if [ "${build_compat_packages}" != "" ]; then    
        for proj in $projects; do
            git -C ${projects_dir}/$proj reset --hard upstream/rawhide
        done
    else
        for proj in $projects; do
            git -C ${projects_dir}/$proj reset --hard kkleine/snapshot-build
        done
    fi

    clean_projects

    get_llvm_version
    show_llvm_version
    generate_spec_files
    
    # Extract for which Fedora Core version (e.g. fc34) we build packages.
    # This is like the ongoing version number for the rolling Fedora "rawhide" release.
    local fc_version=$(grep -ioP "config_opts\['releasever'\] = '\K[0-9]+" /etc/mock/templates/fedora-rawhide.tpl)

    for proj in $projects; do
        pushd $projects_dir/$proj

        # Clean mock before building.
        mock -r ${out_dir}/mock.cfg --clean
        
        local spec_file=$projects_dir/$proj/$proj.snapshot.spec

        local with_compat=""
        if [ "${build_compat_packages}" != "" ]; then
            spec_file="$projects_dir/$proj/$proj.compat.spec"
            with_compat="--with=compat_build"
        fi

        # Show which packages will be build with this spec file
        rpmspec -q ${with_compat} ${spec_file}  
        
        # Download files from the specfile into the project directory
        rpmdev-spectool --force -g -a -C . $spec_file

        # Build SRPM
        if [ "${opt_skip_srpm_generation}" == "" ]; then
            time mock -r ${out_dir}/mock.cfg \
                --spec=$spec_file \
                --sources=$PWD \
                --buildsrpm \
                --resultdir=$srpms_dir \
                --isolation=simple ${mock_check_option} ${with_compat}
        fi
        popd
        
        local srpm="${srpms_dir}/${proj}-${llvm_version}~pre${yyyymmdd}.g*.src.rpm"
        if [[ "${with_compat}" != "" ]]; then
            srpm=$(find ${srpms_dir} -regex ".*${proj}[0-9]+-.*")
        fi

        if [ "${koji_build_rpm}" != "" ]; then
            pushd $cur_dir
            koji \
                --config=${koji_config_path} \
                -p ${koji_config_profile} \
                build ${koji_wait_for_build_option} \
                f${fc_version}-llvm-snapshot ${srpm}
            popd
        fi

        if [ "${mock_build_rpm}" != "" ]; then
            # Let's create or update the snapshot repo directory with whatever
            # packages are currently in there.
            createrepo --update $rpms_dir

            pushd $projects_dir/$proj
            time mock -r ${out_dir}/mock.cfg \
                --rebuild ${srpm} \
                --resultdir=${rpms_dir} \
                --isolation=simple \
                --no-cleanup-after \
                ${mock_check_option} ${with_compat}
            popd

            createrepo --update $rpms_dir
        fi     
    done
}

generate_spec_files() {
    if [[ "${llvm_version}" == "" ]]; then
        get_llvm_version
    fi
    for proj in $projects; do
        if [ "${build_compat_packages}" != "" ]; then
            spec_file=$projects_dir/$proj/$proj.compat.spec
            new_compat_spec_file "$projects_dir/$proj/$proj.spec" ${spec_file}
        else
            spec_file=$projects_dir/$proj/$proj.snapshot.spec
            new_snapshot_spec_file "$projects_dir/$proj/$proj.spec" ${spec_file} ${llvm_version} ${llvm_git_revision} ${yyyymmdd}
        fi
    done
}

# Clean projects and remove untracked files and reset back to content from
# HEAD. 
clean_projects() {
    for proj in $projects; do
        if [ -d $projects_dir/$proj ]; then
            git -C ${projects_dir}/$proj clean -f
            git -C ${projects_dir}/$proj clean -f -d
            git -C ${projects_dir}/$proj reset --hard HEAD
        fi
    done
}

# Updates the LLVM projects with the latest version of the tracked branch.
reset_projects() {
    rm -rf $projects_dir
    for proj in $projects; do
        git clone --origin kkleine --branch snapshot-build https://src.fedoraproject.org/forks/kkleine/rpms/$proj.git ${projects_dir}/$proj
        # TODO(kwk): Once upstream does work, change back to: https://src.fedoraproject.org/rpms/$proj.git
        git -C ${projects_dir}/$proj remote add upstream https://src.fedoraproject.org/forks/kkleine/rpms/$proj.git
        git -C ${projects_dir}/$proj fetch upstream
    done
}


exit_right_away=""
opt_mock_wipe=""
opt_verbose=""
opt_clean_projects=""
opt_reset_projects=""
opt_show_llvm_version=""
opt_generate_spec_files=""

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
        --mock-wipe )
            opt_mock_wipe="1"
            exit_right_away=1
            ;;
        --mock-build-rpm )
            mock_build_rpm="1"
            exit_right_away=""
            ;;
        --mock-check-rpm )
            mock_check_option=""
            ;;
        --mock-config-path )
            shift
            mock_config_path="$1"
            ;;
        --build-compat-packages )
            build_compat_packages="1"
            ;;
        --koji-build-rpm )
            koji_build_rpm="1"
            exit_right_away=""
            ;;
        --reset-projects )
            opt_reset_projects="1"
            exit_right_away=1
            ;;
        --clean-projects )
            opt_clean_projects="1"
            exit_right_away=1
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
        --show-llvm-version )
            opt_show_llvm_version="1"
            exit_right_away=1
            ;;
        --verbose )
            opt_verbose="1"
            ;;
        --generate-spec-files )
            opt_generate_spec_files="1"
            exit_right_away=1
            ;;
        --out-dir )
            shift
            out_dir="$1"
            ;;
        --srpms-dir )
            shift
            srpms_dir="$1"
            ;;
        --skip-srpm-generation )
            opt_skip_srpm_generation="1"
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

[[ "${opt_verbose}" != "" ]] && set -x

bootstrap

[[ "${opt_show_llvm_version}" != "" ]] && get_llvm_version && show_llvm_version
[[ "${opt_mock_wipe}" != "" ]] && mock -r ${out_dir}/mock.cfg --scrub all
[[ "${opt_clean_projects}" != "" ]] && clean_projects
[[ "${opt_reset_projects}" != "" ]] && reset_projects
[[ "${opt_generate_spec_files}" != "" ]] && generate_spec_files
[[ "${exit_right_away}" != "" ]] && exit 0

build_snapshot

exit 0