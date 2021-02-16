#!/bin/bash

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

set -eux

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

# Clean submodules and remove untracked files and reset back to content from upstream
git submodule init
git submodule update --force
git submodule foreach --recursive git clean -f
git submodule foreach --recursive git clean -f -d
git submodule foreach --recursive git reset --hard HEAD

# Define which projects we build.
projects=${projects:-"llvm clang lld"}

# Get LLVM's latest git version and shorten it for the snapshot name
# NOTE(kwk): By specifying latest_git_sha=<git_sha> on the cli, this can be overwritten.  
latest_git_sha=${latest_git_sha:-}
if [ -z "${latest_git_sha}"]; then
    latest_git_sha=$(curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/repos/llvm/llvm-project/commits | jq -r '.[].sha' | head -1)
fi
latest_git_sha_short=${latest_git_sha:0:8}

# Get the UTC date in yyyymmdd format
#yyyymmdd=$(date --date='TZ="UTC"' +'%Y%m%d')
yyyymmdd=$(date +'%Y%m%d')

cur_dir=$(pwd)
projects_dir=${cur_dir}/projects
spec_files_dir=${cur_dir}/spec-files
out_dir=${cur_dir}/out/${yyyymmdd}.${latest_git_sha_short}
tmp_dir=${out_dir}/tmp
rpms_dir=${out_dir}/rpms
srpms_dir=${out_dir}/srpms
mkdir -pv ${out_dir}/{rpms,srpms,tmp}

# In case we need to do a rebuild, let's save the latest git sha that we've build by appending it to a log 
echo $latest_git_sha >> ${out_dir}/latest_git_sha.log

# For snapshot naming, see https://docs.fedoraproject.org/en-US/packaging-guidelines/Versioning/#_snapshots 
snapshot_name="${yyyymmdd}.${latest_git_sha_short}"

# Get LLVM version from CMakeLists.txt
wget -O ${tmp_dir}/CMakeLists.txt https://raw.githubusercontent.com/llvm/llvm-project/${latest_git_sha}/llvm/CMakeLists.txt
llvm_version_major=$(grep --regexp="set(\s*LLVM_VERSION_MAJOR" ${tmp_dir}/CMakeLists.txt | tr -d -c '[0-9]')
llvm_version_minor=$(grep --regexp="set(\s*LLVM_VERSION_MINOR" ${tmp_dir}/CMakeLists.txt | tr -d -c '[0-9]')
llvm_version_patch=$(grep --regexp="set(\s*LLVM_VERSION_PATCH" ${tmp_dir}/CMakeLists.txt | tr -d -c '[0-9]')
llvm_version="${llvm_version_major}.${llvm_version_minor}.${llvm_version_patch}"

# Extract for which Fedora Core version (e.g. fc34) we build packages.
# This is like the ongoing version number for the rolling Fedora "rawhide" release.
fc_version=$(grep -F "config_opts['releasever'] = " /etc/mock/templates/fedora-rawhide.tpl | tr -d -c '0-9')

# Create a changelog entry for all packages
# changelog_date=$(date --date='TZ="UTC"' +'%a %b %d %Y')
changelog_date=$(date +'%a %b %d %Y')
cat <<EOF > ${out_dir}/changelog_entry.txt
* ${changelog_date} Konrad Kleine <kkleine@redhat.com> ${llvm_version_major}.${llvm_version_minor}.${llvm_version_patch}-0.${snapshot_name}
- Daily build of ${llvm_version_major}.${llvm_version_minor}.${llvm_version_patch}-0.${snapshot_name}
EOF

# Get and extract the tarball of the latest LLVM version
# -R is for preserving the upstream timestamp (https://docs.fedoraproject.org/en-US/packaging-guidelines/#_timestamps)
# NOTE: DO NOT MAKE THIS AN ABSOLUTE PATH!!!
llvm_src_dir=llvm-project
# Create a fresh llvm-project directory
rm -rf ${out_dir}/llvm-project
mkdir -pv ${out_dir}/llvm-project
curl -R -L https://github.com/llvm/llvm-project/archive/${latest_git_sha}.tar.gz \
  | tar -C ${out_dir}/llvm-project --strip-components=1 -xzf -

# Firstly, create tarballs for all projects.
# This is needed because for example clang requires clang-tools-extra as well to be present.
for proj in llvm clang clang-tools-extra; do
    tarball_name=$proj-$snapshot_name.src.tar.xz
    mv ${out_dir}/llvm-project/$proj ${out_dir}/llvm-project/$proj-$snapshot_name.src
    tar -C ${out_dir}/llvm-project -cJf ${out_dir}/llvm-project/$tarball_name $proj-$snapshot_name.src
    
    if [ "$proj" == "clang-tools-extra" ]; then
        mv -v ${out_dir}/llvm-project/$tarball_name $projects_dir/clang/$tarball_name
    else
        mv -v ${out_dir}/llvm-project/$tarball_name $projects_dir/$proj/$tarball_name
    fi
done

# Remove the chroot and start fresh
mock -r ${cur_dir}/rawhide-mock.cfg --clean

# Scrub every Monday
[[ `date +%A` == "Monday" ]] && mock -r ${cur_dir}/rawhide-mock.cfg --scub all

# Install LLVM 11 compat packages
packages=""
for pkg in "" libs- static-; do
    url="https://kojipkgs.fedoraproject.org//packages/llvm11.0/11.1.0/0.1.rc2.fc34/x86_64/llvm11.0-${pkg}11.1.0-0.1.rc2.fc34.x86_64.rpm"
    packages+=" $url"
done
mock -r ${cur_dir}/rawhide-mock.cfg --dnf-cmd install ${packages}

for proj in $projects; do
    # tarball_name=$proj-$snapshot_name.src.tar.xz
    # mv ${out_dir}/llvm-project/$proj ${out_dir}/llvm-project/$proj-$snapshot_name.src
    # tar -C ${out_dir}/llvm-project -cJf ${out_dir}/llvm-project/$tarball_name $proj-$snapshot_name.src
    # mv -v ${out_dir}/llvm-project/$tarball_name $projects_dir/$proj/$tarball_name

    # For envsubst to work below, we need to export variables as environment variables.
    export latest_git_sha
    export llvm_version_major
    export llvm_version_minor
    export llvm_version_patch
    export snapshot_name
    export changelog_entry=$(cat $out_dir/changelog_entry.txt)
    # TODO(kwk): Does this work for all LLVM sub-projects?
    export release="%{?rc_ver:0.}%{baserelease}%{?rc_ver:.rc%{rc_ver}}.${snapshot_name}%{?dist}"

    cp $projects_dir/$proj/$proj.spec $tmp_dir/$proj.spec.in
    envsubst ' \
        $latest_git_sha \
        $llvm_version_major \
        $llvm_version_minor \
        $llvm_version_patch \
        $changelog_entry \
        $release \
        $snapshot_name' < $tmp_dir/$proj.spec.in > $projects_dir/$proj/$proj.spec

    pushd $projects_dir/$proj

    # TODO(kwk): If project==clang => fix patch 0001-Make-funwind-tables-the-default-for-all-archs.patch

    # Download files from the specfile into the project directory
    spectool -R -g -A -C . $proj.spec

    # Build SRPM
    time mock -r ${cur_dir}/rawhide-mock.cfg \
        --spec=$proj.spec \
        --sources=$PWD \
        --buildsrpm \
        --resultdir=$srpms_dir \
        --no-cleanup-after \
        --no-clean \
        --nocheck \
        --isolation=simple

    # Build RPM
    time mock -r ${cur_dir}/rawhide-mock.cfg \
        --rebuild $srpms_dir/${proj}-${llvm_version}-0.${snapshot_name}.fc${fc_version}.src.rpm \
        --resultdir=$rpms_dir \
        --no-cleanup-after \
        --no-clean \
        --nocheck \
        --isolation=simple \
        --postinstall
    
    # TODO(kwk): Remove --nocheck once ready

    popd
done

# Build compat packages
# git clone -b rawhide https://src.fedoraproject.org/rpms/llvm.git
# cd llvm
# fedpkg mockbuild --with compat_build

# ) |& tee combined.$(date --iso-8601=seconds).log