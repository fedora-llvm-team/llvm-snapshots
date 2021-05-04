#!/bin/bash

set -eux

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

# Setup some directories for later use
cur_dir=$(pwd)
projects_dir=${cur_dir}/projects
out_dir=${cur_dir}/out
rpms_dir=${out_dir}/rpms
srpms_dir=${out_dir}/srpms
mkdir -pv ${out_dir}/{rpms,srpms,tmp}

# This defines the order in which to build packages.
#
# NOTE: When overwriting this from the outside, only shorten the list of
# projects to build or add to it but do not pick out individual projects to
# build. This is not tested.
projects=${projects:-"llvm clang lld compiler-rt"}

# The current date (e.g. 20210427) is used to determine from which tarball a
# snapshot of LLVM is being built.
yyyymmdd=${yyyymmdd:-$(date +%Y%m%d)}

# Get the current snapshot version and git revision for today
llvm_version=$(curl -sL https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-release-${yyyymmdd}.txt)
llvm_git_revision=$(curl -sL https://github.com/kwk/llvm-project/releases/download/source-snapshot/llvm-git-revision-${yyyymmdd}.txt)
llvm_version_major=$(echo $llvm_version | grep -ioP '^[0-9]+')
llvm_version_minor=$(echo $llvm_version | grep -ioP '\.\K[0-9]+' | head -n1)
llvm_version_patch=$(echo $llvm_version | grep -ioP '\.\K[0-9]+$')

# Extract for which Fedora Core version (e.g. fc34) we build packages.
# This is like the ongoing version number for the rolling Fedora "rawhide" release.
fc_version=$(grep -ioP "config_opts\['releasever'\] = '\K[0-9]+" /etc/mock/templates/fedora-rawhide.tpl)

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

clean_submodules

# Takes an original spec file and prefixes snapshot information to it. Then it
# writes the generated spec file to a new location.
#
# @param orig_file Path to the original spec file.
# @param out_file Path to the spec file that's generated
# @param llvm_snapshot_revision The "<major>.<minor>.<patch>" version string.
# @param llvm_snapshot_git_revision The sha1 of the snapshot that's being built.
new_snapshot_spec_file() {
    local orig_file=$1
    local out_file=$2
    local llvm_version=$3
    local llvm_git_revision=$4

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

# # Create a local repo in order to install build RPMs in a chain of RPMs
repo_dir=$out_dir/repo-${yyyymmdd}.${llvm_git_revision}
mkdir -pv $repo_dir
# createrepo $repo_dir --update
# envsubst '$repo_dir ' < ${cur_dir}/rawhide-mock.cfg.in > ${cur_dir}/rawhide-mock.cfg

# Remove the chroot and start fresh
noclean=${noclean:-""}
[[ "${noclean}" == "" ]] && mock -r ${cur_dir}/rawhide-mock.cfg --clean

# # Scrub mock build root every Monday
# [[ `date +%A` == "Monday" ]] && mock -r ${cur_dir}/rawhide-mock.cfg --scrub all

# # Install LLVM n-1 compat packages
# #packages=""
# #for pkg in "" libs- static-; do
# #    url="https://kojipkgs.fedoraproject.org//packages/llvm11.0/11.1.0/0.1.rc2.fc34/x86_64/llvm11.0-${pkg}11.1.0-0.1.rc2.fc34.x86_64.rpm"
# #    packages+=" $url"
# #done
# #mock -r ${cur_dir}/rawhide-mock.cfg --dnf-cmd install ${packages}

for proj in $projects; do
    tarball_name=${proj}-${yyyymmdd}.src.tar.xz
  
    pushd $projects_dir/$proj

    new_spec_file=$(mktemp --suffix=.spec)
    new_snapshot_spec_file "$projects_dir/$proj/$proj.spec" ${new_spec_file} ${llvm_version} ${llvm_git_revision}
    
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
        --nocheck \
        --isolation=simple

    # koji \
    #     --config=koji.conf \
    #     -p koji-clang \
    #     build \
    #     f${fc_version}-llvm-snapshot ${srpms_dir}/${proj}-${llvm_snapshot_version}~pre${yyyymmdd}.g*.src.rpm

    # Build RPM
    time mock -r ${cur_dir}/rawhide-mock.cfg \
        --rebuild ${srpms_dir}/${proj}-${llvm_version}~pre${yyyymmdd}.g*.src.rpm \
        --resultdir=$rpms_dir \
        --no-cleanup-after \
        --no-clean \
        --nocheck \
        --isolation=simple \
        --postinstall
    
    popd

#     # Link RPMs to repo dir and update the repository
#     pushd $repo_dir
#     ln -sfv $rpms_dir/*.rpm .
#     createrepo . --update
#     popd

#     # TODO(kwk): Remove --nocheck once ready?
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