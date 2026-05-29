#!/bin/bash

set -e

# This function ensures that all tools are installed.
function check_tools {
    echo "INFO: Checking that all required tools are installed" 1>&2
    which cpio koji bsdtar rpmspec rpm2cpio grep sed find tar gpg centpkg
}

# Prints whatever tag is currently assigned to rawhide in koji (e.g. f45).
function get_rawhide_tag {
    local rawhide_tag

    # We fetch the targets because the output contains a "Buildroot" column that
    # gives us the current tag assigned to rawhide:
    #
    #   Name                           Buildroot                      Destination
    #   ---------------------------------------------------------------------------------------------
    #   rawhide                        f45-build                      f45-updates-candidate
    #
    rawhide_tag=$(koji list-targets --name=rawhide --quiet | grep -oP "\s+\Kf[0-9]+" | head -n1)
    echo "INFO: rawhide tag: ${rawhide_tag}" 1>&2
    echo "$rawhide_tag"
}

# Prints the latest NVR (e.g. llvm-22.1.6-1.fc45) of the llvm package for the
# given tag (e.g. f45). If no tag is provided, it will be determined
# automatically from whatever tag is assigned to rawhide atm.
function get_nvr {
    local tag="${1:-$(get_rawhide_tag)}"
    local nvr

    nvr=$(koji latest-build --quiet "${tag}" llvm | cut -d ' ' -f1)
    echo "INFO: NVR: ${nvr}" 1>&2
    echo "$nvr"
}

# Downloads the RPMs for a given NVR and architecture into a target directory.
function download_rpms {
    local nvr="${1:-$(get_nvr)}"
    local arch="${2:-x86_64}"
    local target_dir="${3:-./$PWD/${arch}}"

    echo "INFO: Downloading RPMS for ${nvr} and arch ${arch} to ${target_dir}" 1>&2
    mkdir -p "${target_dir}"
    pushd "${target_dir}"
    koji download-build --arch="${arch}" "${nvr}"
    popd
}

# Downloads the SRPM for the given NVR so we can extract the llvm.spec file
# later.
function download_srpm {
    local nvr="${1:-$(get_nvr)}"
    local target_dir="${2:-$PWD}"
    local srpm="${nvr}.src.rpm"

    echo "INFO: Downloading ${srpm} to ${target_dir}" 1>&2
    mkdir -p "${target_dir}"
    pushd "$target_dir"
    koji download-build --rpm "$srpm"
    popd
}

# Extracts a given SRPM file to a given target directory.
function extract_srpm {
    local srpm="${1:-$(get_nvr).src.rpm}"
    local target_dir="${2:-${PWD}/srpm}"

    echo "INFO: Extracting SRPM ${srpm} to ${target_dir}" 1>&2
    mkdir -p "${target_dir}"
    pushd "${target_dir}"
    bsdtar xf "${srpm}"
    popd
}

# Writes all files belonging to man page documentation from the given spec file
# in alphabetic order for a given RHEL version to the given destination file
# list.
function parse_spec_file_for_doc_files {
    local spec_file="${1:-${PWD}/srpm/llvm.spec}"
    local rhel_version="${2:-UNDEFINED_RHEL_VERSION}"
    local spec_dir
    local dest_file_list="${3}"

    echo "INFO: Parsing spec file ${spec_file} for doc files" 1>&2
    spec_dir=$(dirname "${spec_file}")
    pushd "${spec_dir}"
    rpmspec \
        --undefine=fedora \
        --define="rhel ${rhel_version}" \
        -P llvm.spec 2>/dev/null \
    | grep -P '^/usr/share/man' | sort > "${dest_file_list}"
    popd
}

# Extracts all files from the given rpm that are in the files list to the given
# target directory.
function extract_files_from_rpm {
    local rpm="${1}"
    local target_dir="${2}"
    local files_list="${3:-doc-files.txt}"

    echo "INFO: Extracting files from ${rpm} in ${target_dir}" 1>&2
    mkdir -p "${target_dir}"
    pushd "${target_dir}"
    # We actually do want files_list to split here.
    # shellcheck disable=SC2046
    rpm2cpio "${rpm}" | cpio -idm $(cat "${files_list}" | tr '\n' ' ')
    popd
}

# Verifies that the extracted files match those expected from the doc files
# list text file.
function verify_extracted_files {
    local extracted_dir="${1}"
    local extracted_files="${base_dir}/extracted_files.txt"
    local doc_files="${2:-doc_files.txt}"

    echo "INFO: Verify that files extracted files are complete" 1>&2
    pushd "${extracted_dir}"
    find -L . -type f | sort | sed -s 's/^.//' > "${extracted_files}"
    popd
    diff -u "${extracted_files}" "${doc_files}"
}

# Creates a *.tar.xz archive of the given directory. The name of the archive
# file will be "<basename-of-archive-dir>.tar.xz".
function create_archive_of_dir {
    local extracted_dir="${1}"
    local target_archive

    target_archive="${2:-$(basename "${extracted_dir}").tar.xz}"
    echo "INFO: Creating archive of ${extracted_dir} in ${target_archive}" 1>&2
    pushd "${extracted_dir}"
    tar -cJf "${target_archive}" .
    popd
}

# Creates a detached GPG signature from the given "<file>" and stores it under
# "<file>.sig".
function sign_file {
    local file="${1}"
    local signature_file_out="${2:-${file}.sig}"

    echo "INFO: Signing file ${file} to ${signature_file_out}" 1>&2
    gpg --output "${signature_file_out}" --detach-sig "${file}"
}

function main {
    local rawhide_tag
    local nvr
    local arch=x86_64
    local base_dir="${PWD}/package-rhel-docs"
    local rhel_version="${1:-9}"
    local doc_files="${base_dir}/doc_files.txt"
    local doc_files_cpio="${base_dir}/doc_files_cpio.txt"
    local docs_archive

    check_tools

    rawhide_tag=$(get_rawhide_tag)
    nvr=$(get_nvr "${rawhide_tag}")

    docs_archive="${base_dir}/docs-${nvr}.tar.xz"

    mkdir -p "${base_dir}"

    echo "INFO: Architecture: ${arch}" 1>&2
    echo "INFO: Target RHEL version: ${rhel_version}" 1>&2

    download_rpms "${nvr}" "${arch}" "${base_dir}"
    download_rpms "${nvr}" "noarch" "${base_dir}"
    download_srpm "${nvr}" "${base_dir}"
    extract_srpm "${base_dir}/${nvr}.src.rpm" "${base_dir}/srpm"
    parse_spec_file_for_doc_files "${base_dir}/srpm/llvm.spec" "${rhel_version}" "${doc_files}"
    echo "INFO: Prepending files in list with . to match cpio operation: ${doc_files_cpio}" 1>&2
    sed -e 's/^/./' "${doc_files}" > "${doc_files_cpio}"
    for rpm in "${base_dir}"/*.rpm; do
        extract_files_from_rpm "${rpm}" "${base_dir}/install" "${doc_files_cpio}"
    done
    verify_extracted_files "${base_dir}/install" "${doc_files}"
    create_archive_of_dir "${base_dir}/install" "${docs_archive}"
    sign_file "${docs_archive}" "${docs_archive}.sig"
}

main
