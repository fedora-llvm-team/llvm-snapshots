#!/bin/bash

set -e

# Prints whatever tag is currently assigned to rawhide in koji (e.g. f45).
function get_rawhide_tag {
    local rawhide_tag

    rawhide_tag=$(koji list-targets --name=rawhide --quiet | grep -oP "f[0-9]+" | head -n1)
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
    local rawhide_tag
    local nvr
    local arch=x86_64
    local base_dir="${PWD}/package-rhel-docs"
    local final_dir="${base_dir}/final"
    local rhel_version=${1:-9}

    rawhide_tag=$(get_rawhide_tag)
    nvr=$(get_nvr "${rawhide_tag}")
    mkdir -p "${base_dir}"
    mkdir -p "${final_dir}"

    echo "INFO: Architecture: ${arch}"
    echo "INFO: Artifacts: ${final_dir}"
    echo "INFO: Target RHEL version: ${rhel_version}"

    download_rpms "${nvr}" "${arch}" "${base_dir}"
    download_srpm "${nvr}" "${base_dir}"
}

main
