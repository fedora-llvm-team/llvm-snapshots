#!/bin/bash

set -e

# Prints whatever tag is currently assigned to rawhide in koji (e.g. f45).
function get_rawhide_tag {
    local rawhide_tag=$(koji list-targets --name=rawhide --quiet | grep -oP "f[0-9]+" | head -n1)

    echo "INFO: rawhide tag: ${rawhide_tag}" 1>&2
    echo "$rawhide_tag"
}

# Prints the latest NVR (e.g. llvm-22.1.6-1.fc45) of the llvm package for the
# given rawhide tag (e.g. f45). If no rawhide tag is provided, it will be
# determined automatically.
function get_nvr {
    local rawhide_tag=${1:-$(get_rawhide_tag)}
    local nvr

    nvr=$(koji latest-build --quiet "${rawhide_tag}" llvm | cut -d ' ' -f1)

    echo "INFO: NVR: ${nvr}" 1>&2
    echo "$nvr"
}

# Downloads the RPMs for a given NVR and architecture into a target directory.
function download_rpms {
    local nvr=${1:-$(get_nvr)}
    local arch=${2:-x86_64}
    local target_dir=${3:-./$PWD/${arch}}

    echo "INFO: Downloading RPMS for ${nvr} and arch ${arch} to ${target_dir}"
    mkdir -p "${target_dir}"
    pushd "${target_dir}"
    koji download-build --arch="${arch}" "${nvr}"
    popd
}

# Downloads the SRPM for the given NVR so we can extract the llvm.spec file
# later.
function download_srpm {
    local nvr=${1:-$(get_nvr)}
    local target_dir=${2:-$PWD}
    local srpm="${nvr}.src.rpm"

    echo "INFO: Downloading ${srpm} to ${target_dir}"
    mkdir -p "${target_dir}"
    pushd "$target_dir"
    koji download-build --rpm "$srpm"
    popd
}

function main {
    # TODO(kwk): Add refresh option
    local rawhide_tag
    local nvr
    local arch=x86_64
    local base_dir
    local final_dir
    local rhel_version=${1:-9}

    rawhide_tag=$(get_rawhide_tag)
    nvr=$(get_nvr "${rawhide_tag}")
    base_dir=/home/kkleine/src/llvm-snapshots/main #$(mktemp -d)
    final_dir=/home/kkleine/src/llvm-snapshots/main #$(mktemp -d)

    echo "INFO: Architecture: ${arch}"
    echo "INFO: Artifacts: ${final_dir}"
    echo "INFO: Target RHEL version: ${rhel_version}"

    download_rpms "${nvr}" "${arch}" "${base_dir}"
    download_srpm "${nvr}" "${base_dir}"

    echo "STEPS:"
    echo "* [DONE] Download all RPMs for a particular NVR for a given architecutre (e.g. x86_64)"
    echo "* [DONE] Download SRPM for a given NVR to get access to the spec file used in that version".
    echo "* Extract the SRPM (NOT only the llvm.spec) to some directory."
    echo "* Parse the spec file for /usr/share/man files"
    echo "  * rpmspec --undefine=fedora --define='rhel 9' -P llvm.spec | grep -P '^/usr/share/man'"
    echo "* Extract the downloaded RPMS (e.g. using cpio) and copy only the man pages"
    echo "  (How to respect ownership and file mods or links?)"
    echo "* Create a docs tarball of man pages"
    echo "* Create sha512sum of docs tarball"
    echo "* Sign docs tarball"
    echo "* Add signature of all signers to keyring (one time?)"
    echo "* Copy docs signature and tarball itself to centos repo in the correct version"
    echo "* Add signature and tarball checksums to sources file in centos repo."
    echo "  Use the following procedure:"
    echo "    * Download existing sources first: centpkg sources"
    echo "    * Upload signature and tarball together with everything already"
    echo "      in the sources file to the lookaside cache:"
    echo "      centpkg new-sources \$(grep -oP '\(\K[^)]+' sources) docs.tar.xz docs.sig"
    echo "* Commit the changes made to the sources file"


    # local srpm=
    # echo "INFO: Download SRPM
}

main
