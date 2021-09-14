#!/bin/bash -xe
# Set the date --yyyymmdd to an output like the one from $(date +%Y%m%d).

curl --compressed -s -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/kwk/llvm-daily-fedora-rpms/main/build.sh?$(uuidgen) | bash -s -- \
    --verbose \
    --reset-project \
    --generate-spec-file \
    --build-in-one-dir /workdir/buildroot \
    --project {} \
    --yyyymmdd "{}"