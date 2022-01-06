#!/bin/bash

# To call this script directly from copr, do this:
#
# curl \
#   --compressed \
#   -s \
#   -H 'Cache-Control: no-cache' \
#   https://raw.githubusercontent.com/kwk/llvm-daily-fedora-rpms/main/fedora-copr/create-spec-file.sh?$(uuidgen) \
#   | bash -s -- \
#       --project {} \
#       --yyyymmdd "{}"
#
# And then select "buildroot" as the "Result directory" in the Web-UI.
#
# You might wonder about the "--compressed" and caching options or even about
# the UUID being attached to the URL at the very end. These are all ways to
# ensure we get the freshest of all versions of the file on github. I noticed
# that curl sometimes queries an older version of the content than currently is
# on github. I got the inspiration for this from here:
# https://stackoverflow.com/questions/31653271/how-to-call-curl-without-using-server-side-cache?noredirect=1&lq=1
 
set -x

set -eu

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

proj=
yyyymmdd="$(date +%Y%m%d)"
cfg_dir=/workdir/buildroot
specs_dir=/workdir/buildroot
sources_dir=/workdir/buildroot
spec_file=${specs_dir}/$proj.spec
snapshot_url_prefix=https://github.com/kwk/llvm-daily-fedora-rpms/releases/download/source-snapshot/

#############################################################################
#############################################################################

info() {
    echo "$(date --rfc-email) INFO $1" 1>&2
    ${@:2}
}

usage() {
local script=$(basename $0)
cat <<EOF
Build LLVM snapshots...

Usage: ${script} --project <project> [--yyyymmdd <YYYYMMDD>]
EOF
}

# Takes an original spec file and prefixes snapshot information to it. Then it
# writes the generated spec file to a new location.
#
# @param orig_file Path to the original spec file.
# @param out_file Path to the spec file that's generated
new_snapshot_spec_file() {
    local orig_file=$1
    local out_file=$2

    cat <<EOF > ${out_file}
################################################################################
# BEGIN SNAPSHOT PREFIX
################################################################################

# FIXME: Disable running checks for the time being 
%global _without_check 1

%bcond_without snapshot_build

%if %{with snapshot_build}

# Check if we're building with copr
%if 0%{?copr_projectname:1}

# Remove the .copr prefix that is added here infront the build ID
# see https://pagure.io/copr/copr/blob/main/f/rpmbuild/mock.cfg.j2#_22-25
%global copr_build_id %{lua: print(string.sub(rpm.expand("%buildtag"), 6))}

%global copr_build_link https://copr.fedorainfracloud.org/coprs/build/%{copr_build_id}/
%endif

%global llvm_snapshot_yyyymmdd           ${yyyymmdd}
%global llvm_snapshot_version            ${llvm_version}
%global llvm_snapshot_version_major      ${llvm_version_major}
%global llvm_snapshot_version_minor      ${llvm_version_minor}
%global llvm_snapshot_version_patch      ${llvm_version_patch}
%global llvm_snapshot_git_revision       ${llvm_git_revision}
%global llvm_snapshot_git_revision_short ${llvm_git_revision_short}

%global llvm_snapshot_version_suffix     pre%{llvm_snapshot_yyyymmdd}.g%{llvm_snapshot_git_revision_short}

%global llvm_snapshot_source_prefix      ${snapshot_url_prefix}

# This prints a multiline string for the changelog entry
%{lua: function _llvm_snapshot_changelog_entry()
    assert(os.setlocale('C'))
    print(string.format("* %s LLVM snapshot - %s\n", os.date("%a %b %d %Y"), rpm.expand("%version")))
    print("- This is an automated snapshot build")
    -- TODO(kkleine): Switch to rpm.isdefined() once it is available on copr builders
    if rpm.expand("%copr_build_link") ~= "%copr_build_link" then
        print(string.format(" (%s)", rpm.expand("%copr_build_link")))
    end
    print("\n\n")
end}

%global llvm_snapshot_changelog_entry %{lua: _llvm_snapshot_changelog_entry()}

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


# These will be set by create_spec_file
llvm_version=""
llvm_git_revision=""
llvm_git_revision_short=""
llvm_version_major=""
llvm_version_minor=""
llvm_version_patch=""

create_spec_file() {
    info "Get LLVM version"
    local url="${snapshot_url_prefix}llvm-release-${yyyymmdd}.txt"
    llvm_version=$(curl -sfL "$url")
    local ret=$?
    if [[ $ret -ne 0 ]]; then
        echo "ERROR: failed to get llvm version from $url"
        exit 1
    fi
    
    url="${snapshot_url_prefix}llvm-git-revision-${yyyymmdd}.txt"
    llvm_git_revision=$(curl -sfL "$url")
    llvm_git_revision_short=${llvm_git_revision:0:14}
    ret=$?
    if [[ $ret -ne 0 ]]; then
        echo "ERROR: failed to get llvm git revision from $url"
        exit 1
    fi
    llvm_version_major=$(echo $llvm_version | grep -ioP '^[0-9]+')
    llvm_version_minor=$(echo $llvm_version | grep -ioP '\.\K[0-9]+' | head -n1)
    llvm_version_patch=$(echo $llvm_version | grep -ioP '\.\K[0-9]+$')
     
    info "Reset project $proj"
    # Updates the LLVM projects with the latest version of the tracked branch.
    rm -rf $sources_dir

    git clone --quiet --origin kkleine --branch snapshot-build https://src.fedoraproject.org/forks/kkleine/rpms/$proj.git ${sources_dir}
    # TODO(kwk): Once upstream does work, change back to: https://src.fedoraproject.org/rpms/$proj.git
    git -C ${sources_dir} remote add upstream https://src.fedoraproject.org/forks/kkleine/rpms/$proj.git
    git -C ${sources_dir} fetch --quiet upstream
    
    # Checkout OS-dependent branch from upstream if building compat package
    local branch="kkleine/snapshot-build"
    case $orig_package_name in
        "compat-llvm-fedora-34" | "compat-clang-fedora-34")
            branch="upstream/f34"
            ;;
        "compat-llvm-fedora-35" | "compat-clang-fedora-35")
            branch="upstream/f35"
            ;;
        "compat-llvm-fedora-rawhide" | "compat-clang-fedora-rawhide")
            branch="upstream/rawhide"
            ;;
    esac
    info "Reset to ${branch}"
    git -C $sources_dir reset --hard ${branch}
    unset branch

    info "Generate spec file in ${specs_dir}/$proj.spec"
    mv -v ${sources_dir}/$proj.spec ${sources_dir}/$proj.spec.old
    if [ "${opt_build_compat_packages}" != "" ]; then
        new_compat_spec_file "${sources_dir}/$proj.spec.old" ${specs_dir}/$proj.spec
    else
        new_snapshot_spec_file "${sources_dir}/$proj.spec.old" ${specs_dir}/$proj.spec
    fi
}

opt_build_compat_packages=""
orig_package_name=""

while [ $# -gt 0 ]; do
    case $1 in
        --yyyymmdd )
            shift
            yyyymmdd="$1"
            ;;
        --project )
            shift
            proj="$1"
            orig_package_name="$proj"
            # NOTE: Implicitly enabling a compatibility build when the project's
            # name begins with "compat-". The project's name is manually
            # cleaned from the "compat-" prefix and the "-fedora-XX" suffix.
            case "$proj" in
                "compat-llvm-fedora-34" | "compat-llvm-fedora-35" | "compat-llvm-fedora-rawhide")
                    proj="llvm"
                    opt_build_compat_packages="1"
                    ;;
                "compat-clang-fedora-34" | "compat-clang-fedora-35" | "compat-clang-fedora-rawhide")
                    proj="clang"
                    opt_build_compat_packages="1"
                    ;;
            esac
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

if [[ "${proj}" == "" ]]; then
    echo "Please specify which project to build (see --project <proj>)!"
    usage
    exit 1
fi

create_spec_file

exit 0
