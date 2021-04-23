#!/bin/bash

# To build the SRPMs with koji use:
# koji -p koji-clang build f35-llvm-snapshot out/srpms/llvm-13.0.0~pre20210422.gf6d8cf7798440f-1.fc35.src.rpm

set -eux

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

projects=${projects:-"llvm clang lld compiler-rt"}

# Clean submodules and remove untracked files and reset back to content from upstream
git submodule init
keep_submodules=${KEEP_SUBMODULES:-0}
if [ "$keep_submodules" == "1" ]; then
    echo "Keep submodules uncleaned"
else
    git submodule update --force
    git submodule foreach --recursive git clean -f
    git submodule foreach --recursive git clean -f -d
    git submodule foreach --recursive git reset --hard HEAD
fi

new_snapshot_spec_file() {
    local orig_file=$1
    local out_file=$2
    local llvm_snapshot_version=$3
    local llvm_snapshot_git_revision=$4

    cat <<EOF > ${out_file}
################################################################################
# BEGIN SNAPSHOT PREFIX
################################################################################

%global _with_snapshot_build 1
# Optionally enable snapshot build with \`--with=snapshot_build\` or \`--define
# "_with_snapshot_build 1"\`.
%bcond_with snapshot_build

%if %{with snapshot_build}
%global llvm_snapshot_yyyymmdd %{lua: print(os.date("%Y%m%d"))}
%global llvm_snapshot_version ${llvm_snapshot_version}
%global llvm_snapshot_git_revision ${llvm_snapshot_git_revision}

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

yyyymmdd=$(date +%Y%m%d)
llvm_snapshot_version=$(curl -sL https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-release-${yyyymmdd}.txt)
llvm_snapshot_git_revision=$(curl -sL https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-git-revision-${yyyymmdd}.txt)

# temp_file=$(mktemp)
# new_snapshot_spec_file "/home/kkleine/dev/rpms/llvm/llvm.spec" ${temp_file} ${llvm_snapshot_version} ${llvm_snapshot_git_revision}
# rpmspec -q ${temp_file}

cur_dir=$(pwd)
projects_dir=${cur_dir}/projects
spec_files_dir=${cur_dir}/spec-files
out_dir=${cur_dir}/out
tmp_dir=${out_dir}/tmp
rpms_dir=${out_dir}/rpms
srpms_dir=${out_dir}/srpms
mkdir -pv ${out_dir}/{rpms,srpms,tmp}

# # Create a local repo in order to install build RPMs in a chain of RPMs
repo_dir=$cur_dir/${yyyymmdd}.${llvm_snapshot_git_revision}
mkdir -pv $repo_dir
# createrepo $repo_dir --update
# envsubst '$repo_dir ' < ${cur_dir}/rawhide-mock.cfg.in > ${cur_dir}/rawhide-mock.cfg

# Extract for which Fedora Core version (e.g. fc34) we build packages.
# This is like the ongoing version number for the rolling Fedora "rawhide" release.
fc_version=$(grep -ioP "config_opts\['releasever'\] = '\K[0-9]+" /etc/mock/templates/fedora-rawhide.tpl)

# # Create a changelog entry for all packages
# # changelog_date=$(date --date='TZ="UTC"' +'%a %b %d %Y')
# changelog_date=$(date --date="$yyyymmdd" +'%a %b %d %Y')
# cat <<EOF > ${out_dir}/changelog_entry.txt
# * ${changelog_date} Konrad Kleine <kkleine@redhat.com>
# - Daily build of ${llvm_version_major}.${llvm_version_minor}.${llvm_version_patch}~${yyyymmdd}.g${llvm_snapshot_git_revision}
# EOF

# # Get and extract the tarball of the latest LLVM version
# # -R is for preserving the upstream timestamp (https://docs.fedoraproject.org/en-US/packaging-guidelines/#_timestamps)
# # NOTE: DO NOT MAKE THIS AN ABSOLUTE PATH!!!
# llvm_src_dir=llvm-project

# Remove the chroot and start fresh
keep_chroot=${KEEP_CHROOT:-0}
if [ "$keep_chroot" == "1" ]; then
    echo "Keeping mock directory uncleaned."
else
    mock -r ${cur_dir}/rawhide-mock.cfg --clean
fi

# # Scrub mock build root every Monday
# #[[ `date +%A` == "Monday" ]] && mock -r ${cur_dir}/rawhide-mock.cfg --scrub all

# # Install LLVM 11 compat packages
# #packages=""
# #for pkg in "" libs- static-; do
# #    url="https://kojipkgs.fedoraproject.org//packages/llvm11.0/11.1.0/0.1.rc2.fc34/x86_64/llvm11.0-${pkg}11.1.0-0.1.rc2.fc34.x86_64.rpm"
# #    packages+=" $url"
# #done
# #mock -r ${cur_dir}/rawhide-mock.cfg --dnf-cmd install ${packages}


for proj in $projects; do
    tarball_name=${proj}-${yyyymmdd}.src.tar.xz
    # wget -O $projects_dir/$proj/$tarball_name https://github.com/kwk/llvm-project/releases/download/source-snapshot/${tarball_name}

    pushd $projects_dir/$proj

    new_spec_file=$(mktemp --suffix=.spec)
    new_snapshot_spec_file "$projects_dir/$proj/$proj.spec" ${new_spec_file} ${llvm_snapshot_version} ${llvm_snapshot_git_revision}
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
        --nocheck \
        --isolation=simple

    koji --config=${cur_dir}/koji.conf -p koji-clang build ${fc_version}-llvm-snapshot ${out_dir}/srpms/${proj}-${llvm_snapshot_version}~pre${yyyymmdd}.g*.src.rpm

#     # Build RPM
#     time mock -r ${cur_dir}/rawhide-mock.cfg \
#         --rebuild $srpms_dir/${proj}-${llvm_version}-0.${snapshot_name}.fc${fc_version}.src.rpm \
#         --resultdir=$rpms_dir \
#         --no-cleanup-after \
#         --no-clean \
#         --nocheck \
#         --isolation=simple \
#         --postinstall
    
#     # Link RPMs to repo dir and update the repository
#     pushd $repo_dir
#     ln -sfv $rpms_dir/*.rpm .
#     createrepo . --update
#     popd

#     # TODO(kwk): Remove --nocheck once ready?

    popd
done

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