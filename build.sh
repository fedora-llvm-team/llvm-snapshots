#!/bin/bash

# To call this script directly from copr, do this:
#
# curl --compressed -s -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/kwk/llvm-daily-fedora-rpms/main/build.sh?$(uuidgen) | bash -s -- \
#     --verbose \
#     --reset-project \
#     --generate-spec-file \
#     --build-in-one-dir /workdir/buildroot \
#     --project compat-clang \
#     --yyyymmdd "$(date +%Y%m%d)"
#
# And then select "buildroot" as the "Result directory" in the Web-UI.
#
# You might wonder about the "--compressed" and caching options or even about
# the UUID being attached to the URL at the very end. These are all ways to
# ensure we get the freshest of all versions of the file on github. I noticed
# that curl sometimes queries an older version of the content than currently is
# on github. I got the inspiration for this from here:
# https://stackoverflow.com/questions/31653271/how-to-call-curl-without-using-server-side-cache?noredirect=1&lq=1
 

set -eu

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

# Setup some directories for later use
home_dir=${HOME:-~}
proj=
cfg_dir=${home_dir}/cfg
specs_dir=${home_dir}/rpmbuild/SPECS
sources_dir=${home_dir}/rpmbuild/SOURCES
rpms_dir=${home_dir}/rpmbuild/RPMS
srpms_dir=${home_dir}/rpmbuild/SRPMS
spec_file=${specs_dir}/$proj.spec
snapshot_url_prefix=https://github.com/kwk/llvm-daily-fedora-rpms/releases/download/source-snapshot/

#############################################################################
# These vars can be adjusted with the options passing to this script:
#############################################################################

# projects="python-lit llvm clang lld compiler-rt mlir lldb libomp"

# The current date (e.g. 20210427) is used to determine from which tarball a
# snapshot of LLVM is being built.
yyyymmdd="$(date +%Y%m%d)"

#############################################################################
#############################################################################

info() {
    echo "$(date --rfc-email) INFO $1" 1>&2
    ${@:2}
}

# info_timed() {
#     local title="$1"
#     local start=$(date +%s)
#     echo -n "$(date --rfc-email) INFO ${title}..."
#     ${@:2}
#     local end=$(date +%s)
#     echo "DONE. ($(expr $end - $start)s)"
# }

usage() {
local script=$(basename $0)
cat <<EOF
Build LLVM snapshots...

Usage: ${script} [Options TBD]
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
%global llvm_snapshot_yyyymmdd           ${yyyymmdd}
%global llvm_snapshot_version            ${llvm_version}
%global llvm_snapshot_version_major      ${llvm_version_major}
%global llvm_snapshot_version_minor      ${llvm_version_minor}
%global llvm_snapshot_version_patch      ${llvm_version_patch}
%global llvm_snapshot_git_revision       ${llvm_git_revision}
%global llvm_snapshot_git_revision_short ${llvm_git_revision_short}

%global llvm_snapshot_version_suffix     pre%{llvm_snapshot_yyyymmdd}.g%{llvm_snapshot_git_revision_short}

%global llvm_snapshot_source_prefix      ${snapshot_url_prefix}

# Check if we're building with copr
%if 0%{?copr_projectname:1}

# Remove the .copr prefix that is added here infront the build ID
# see https://pagure.io/copr/copr/blob/main/f/rpmbuild/mock.cfg.j2#_22-25
%global copr_build_id %{lua: print(string.sub(rpm.expand("%buildtag"), 6))}

%global llvm_snapshot_build_link https://copr.fedorainfracloud.org/coprs/build/%{copr_build_id}/
%else
%endif

# This prints a multiline string for the changelog entry
%{lua: function _llvm_snapshot_changelog_entry()
    print("* ")
    print(os.date("%a %b %d %Y"))
    print(" LLVM snapshot - ")
    print(rpm.expand("%version"))
    print("\n")
    print("- This is an automated snapshot build ")
    if rpm.expand("%llvm_snapshot_build_link") ~= "%llvm_snapshot_build_link" then
        print(" (")
        print(rpm.expand("%llvm_snapshot_build_link"))
        print(")")
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


llvm_version=""
llvm_git_revision=""
llvm_git_revision_short=""
llvm_version_major=""
llvm_version_minor=""
llvm_version_patch=""

build_snapshot() {
    if [ "${opt_build_in_one_dir}" == "" ]; then
        info 'Set up build tree'
        HOME=${home_dir} DEBUG=1 rpmdev-setuptree
    fi

    [[ "${opt_verbose}" != "" ]] && set -x

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
    
    info "Show LLVM version"
    cat <<EOF
Date:                          ${yyyymmdd}
LLVM Version:                  ${llvm_version}
LLVM Major Version:            ${llvm_version_major}
LLVM Minor Version:            ${llvm_version_minor}
LLVM Patch Version:            ${llvm_version_patch}
LLVM Git Revision:             ${llvm_git_revision}
LLVM Git Revision (shortened): ${llvm_git_revision_short}

EOF

    [[ "$opt_show_build_tree_on_enter" != "" ]] && show_build_tree "Build tree on enter:"
    [[ "$opt_show_build_tree_on_exit" != "" ]] && trap 'show_build_tree "Build tree on exit:"' EXIT

    if [[ "${proj}" == "" ]]; then
        echo "Please specify which project to build (see --project <proj>)!"
        usage
        exit 1
    fi
    
    if [[ "${opt_reset_project}" != "" ]]; then
        info "Reset project $proj"
        # Updates the LLVM projects with the latest version of the tracked branch.
        rm -rf $sources_dir
        if [ "${opt_build_in_one_dir}" == "" ]; then
            HOME=${home_dir} DEBUG=1 rpmdev-setuptree
        fi
        git clone --quiet --origin kkleine --branch snapshot-build https://src.fedoraproject.org/forks/kkleine/rpms/$proj.git ${sources_dir}
        # TODO(kwk): Once upstream does work, change back to: https://src.fedoraproject.org/rpms/$proj.git
        git -C ${sources_dir} remote add upstream https://src.fedoraproject.org/forks/kkleine/rpms/$proj.git
        git -C ${sources_dir} fetch --quiet upstream
    fi

    # Checkout OS-dependent branch from upstream if building compat package
    if [ "${opt_build_compat_packages}" != "" ]; then
        local branch=""
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
            *)
                echo "ERROR: package name '$orig_package_name' is an unknown compatibility package"
                exit -1;
                ;;
        esac

        info "Reset to ${branch} for compatibility build"
        git -C $sources_dir reset --hard ${branch}
        unset branch
    else
        info "Reset to kkleine/snapshot-build for snapshot build"
        git -C $sources_dir reset --hard kkleine/snapshot-build
    fi

    if [[ "${opt_clean_project}" != "" ]]; then
        info "Clean project $proj"
        # Clean projects and remove untracked files and reset back to content
        # from HEAD. 
        git -C ${sources_dir} clean --quiet -f
        git -C ${sources_dir} clean --quiet -f -d
        git -C ${sources_dir} reset --quiet --hard HEAD
    fi

    if [[ "${opt_generate_spec_file}" != "" ]]; then
        info "Generate spec file in ${specs_dir}/$proj.spec"
        mv -v ${sources_dir}/$proj.spec ${sources_dir}/$proj.spec.old
        if [ "${opt_build_compat_packages}" != "" ]; then
            new_compat_spec_file "${sources_dir}/$proj.spec.old" ${specs_dir}/$proj.spec
        else
            new_snapshot_spec_file "${sources_dir}/$proj.spec.old" ${specs_dir}/$proj.spec
        fi
    fi
    
    # Optionally enable local repos to find snapshot packages
    info "Enabling DNF repos (if any)..."
    for repo_dir in "${opt_enabled_dnf_repos[@]}"; do
        if [ -n "${repo_dir}" ]; then
            repo_name=$(echo $repo_dir | tr '/' '_')
            info "Create repo ${repo_name}.repo and move to /etc/yum.repos.d"
            cat <<EOF > ${repo_name}.repo
[${repo_name}]
name=${repo_name}
baseurl=${repo_dir}
enabled=1
gpgcheck=0
EOF
            sudo mv -f ${repo_name}.repo /etc/yum.repos.d/${repo_name}.repo
        fi
    done

    if [[ "${opt_install_build_dependencies}" != "" ]]; then
        info "Install build dependencies from ${specs_dir}/$proj.spec"
        sudo dnf builddep --assumeyes ${specs_dir}/$proj.spec
    fi  
           
    local with_compat=""
    if [ "${opt_build_compat_packages}" != "" ]; then
        with_compat="--with=compat_build"
    fi

    # Build SRPM
    if [ "${opt_build_srpm}" != "" ]; then
        local spec_file=${specs_dir}/$proj.spec

        # Show which packages will be build with this spec file
        info "RPMs to be built with the spec file ${spec_file}:"
        rpmspec -q ${with_compat} ${spec_file}
        
        info "Download files from the specfile into ${sources_dir}"
        rpmdev-spectool --force -g -a -C ${sources_dir} ${spec_file}
        
        info "Build SRPM"
        rpmbuild --noclean ${with_compat} -bs ${spec_file}
    fi

    if [ "${opt_build_rpm}" != "" ]; then
        info "Build RPM"
        rpmbuild --noclean ${with_compat} -rb SRPMS/*.src.rpm
    fi

    if [ "${opt_generate_dnf_repo}" != "" ]; then
        info "Generate DNF repository"
        createrepo --update --verbose ${rpms_dir}
    fi

    local srpm="${srpms_dir}/${proj}-${llvm_version}~pre${yyyymmdd}.g*.src.rpm"
    if [[ "${with_compat}" != "" ]]; then
        srpm=$(find ${srpms_dir} -regex ".*${proj}[0-9]+-.*")
    fi   
}


opt_verbose=""
opt_clean_project=""
opt_reset_project=""
opt_generate_spec_file=""
opt_show_build_tree_on_enter=""
opt_show_build_tree_on_exit=""
opt_install_build_dependencies=""
opt_build_srpm=""
opt_build_rpm=""
opt_generate_dnf_repo=""
opt_shell=""
opt_enabled_dnf_repos=""
opt_build_compat_packages=""
opt_koji_build_rpm=""
opt_koji_wait_for_build_option="--nowait"
opt_build_in_one_dir=""
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
        --build-in-one-dir )
            shift
            opt_build_in_one_dir="$1"
            if [ "${opt_build_in_one_dir}" != "" ]; then
                cfg_dir=${opt_build_in_one_dir}
                specs_dir=${opt_build_in_one_dir}
                sources_dir=${opt_build_in_one_dir}
                rpms_dir=${opt_build_in_one_dir}
                srpms_dir=${opt_build_in_one_dir}
            fi
            ;;
        --install-build-dependencies )
            opt_install_build_dependencies="1"
            ;;
        --reset-project )
            opt_reset_project="1"
            ;;
        --clean-project )
            opt_clean_project="1"
            ;;
        -v | --verbose )
            opt_verbose="1"
            ;;
        --generate-spec-file )
            opt_generate_spec_file="1"
            ;;
        --build-srpm )
            opt_build_srpm="1"
            ;;
        --build-rpm )
            opt_build_rpm="1"
            ;;
        --generate-dnf-repo )
            opt_generate_dnf_repo="1"
            ;;
        --enable-dnf-repo )
            shift
            opt_enabled_dnf_repos+=("$1")
            ;;
        --show-build-tree-on-enter )
            opt_show_build_tree_on_enter="1"
            ;;
        --show-build-tree-on-exit )
            opt_show_build_tree_on_exit="1"
            ;;
        --show-build-tree )
            opt_show_build_tree_on_enter="1"
            opt_show_build_tree_on_exit="1"
            ;;
        --shell )
            opt_shell="1"
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

function show_build_tree() { 
    echo ""
    echo "$@"
    echo "--------------------------------------------"
    echo ""
    # TODO(kwk): This is only useful when building in containers where we have
    # files stored in this location.
    tree -guph --du ~/rpmbuild
    echo ""
}

build_snapshot

if [ "${opt_shell}" != "" ]; then
    info "Enter bash shell"
    bash
fi

exit 0
