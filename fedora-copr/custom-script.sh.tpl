#!/bin/bash -xe

# This script will be used in copr packages as the custom build script.
# We're downloading the script in order to  downloads the latest version of the build script and executes it

# Set the date --yyyymmdd to an output like the one from $(date +%Y%m%d).

curl \
    --compressed \
    -s \
    -H 'Cache-Control: no-cache' \
    https://raw.githubusercontent.com/kwk/llvm-daily-fedora-rpms/main/fedora-copr/create-spec-file.sh?$(uuidgen) \
    | bash -s -- \
        --project {} \
        --yyyymmdd "{}"