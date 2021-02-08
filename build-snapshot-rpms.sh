#!/bin/bash

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

# Define for which projects we want to build RPMS.
# See https://github.com/tstellar/llvm-project/blob/release-automation/llvm/utils/release/export.sh#L16
# projects=${projects:-"llvm clang test-suite compiler-rt libcxx libcxxabi clang-tools-extra polly lldb lld openmp libunwind"}
projects=${projects:-"llvm"}
# TODO(kwk): Projects not covered yet: clang-tools-extra and openmp

cur_dir=$(pwd)
out_dir=${cur_dir}/out
tmp_dir=${out_dir}/tmp
mkdir -pv $out_dir/{rpms,srpms,tmp}

# Get LLVM's latest git version and shorten it for the snapshot name
# NOTE(kwk): By specifying latest_git_sha=<git_sha> on the cli, this can be overwritten.  
latest_git_sha=${latest_git_sha:-}
if [ -z "${latest_git_sha}"]; then
    latest_git_sha=$(curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/repos/llvm/llvm-project/commits | jq -r '.[].sha' | head -1)
fi
latest_git_sha_short=${latest_git_sha:0:8}

# In case we need to do a rebuild, let's save the latest git sha that we've build by appending it to a log 
echo $latest_git_sha >> ${out_dir}/latest_git_sha.log

# Get the UTC date in yyyymmdd format
yyyymmdd=$(date --date='TZ="UTC"' +'%Y%m%d')

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
changelog_date=$(date --date='TZ="UTC"' +'%a %b %d %Y')
cat <<EOF > ${out_dir}/changelog_entry
* ${changelog_date} Konrad Kleine <kkleine@redhat.com> ${llvm_version_major}.${llvm_version_minor}.${llvm_version_patch}-0.${snapshot_name}
- Daily build of ${llvm_version_major}.${llvm_version_minor}.${llvm_version_patch}-0.${snapshot_name}
EOF

# Get and extract the tarball of the latest LLVM version
# -R is for preserving the upstream timestamp (https://docs.fedoraproject.org/en-US/packaging-guidelines/#_timestamps)
llvm_src_dir=${out_dir}/llvm-project
# Create a fresh llvm-project directory
rm -rf ${llvm_src_dir}
mkdir -pv ${llvm_src_dir}
curl -R -L https://github.com/llvm/llvm-project/archive/${latest_git_sha}.tar.gz \
  | tar -C ${llvm_src_dir} --strip-components=1 -xzf -

for proj in $projects; do
    tarball_path=${out_dir}/$proj-${snapshot_name}.src.tar.xz
    project_src_dir=${llvm_src_dir}/$proj-${snapshot_name}.src
    echo "Creating tarball for $proj in $tarball_path from $project_src_dir ..."
    mv $llvm_src_dir/$proj $project_src_dir
    tar -C $llvm_src_dir -cJf $tarball_path $project_src_dir

    # For envsubst to work below, we need to export variables as environment variables.
    export project_src_dir=$(basename $project_src_dir)
    export latest_git_sha
    export llvm_version_major
    export llvm_version_minor
    export llvm_version_patch
    export project_archive_url=$(basename $tarball_path)
    export changelog_entry=$(cat ${out_dir}/changelog_entry)
    # TODO(kwk): Does this work for all LLVM sub-projects?
    export release="%{?rc_ver:0.}%{baserelease}%{?rc_ver:.rc%{rc_ver}}.${snapshot_name}%{?dist}"

    envsubst '${project_src_dir} \
        ${latest_git_sha} \
        ${llvm_version_major} \
        ${llvm_version_minor} \
        ${llvm_version_patch} \
        ${project_archive_url} \
        ${changelog_entry} \ 
        ${snapshot_name}' < "spec-files/$proj.spec" > rpms/$proj/$proj.spec

    # Download files from the specfile into the project directory
    spectool -R -g -A -C rpms/$proj/ rpms/$proj/$proj.spec

    # Build SRPM
    time mock -r rawhide-mock.cfg \
        --spec=$proj.spec \
        --sources=rpms/$proj/ \
        --buildsrpm \
        --resultdir=$out_dir/srpms \
        --no-cleanup-after \
        --isolation=simple

    # Build RPM
    time mock -r rawhide-mock.cfg \
        --rebuild $out_dir/srpms/${proj}-${llvm_version}-0.${snapshot_name}.fc${fc_version}.src.rpm \
        --resultdir=$out_dir/rpms \
        --no-cleanup-after \
        --isolation=simple
done