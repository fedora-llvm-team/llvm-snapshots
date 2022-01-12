#!/bin/bash -xe

# This script will be used in copr packages as the custom build script.

# Set the date --yyyymmdd to an output like the one from $(date +%Y%m%d).

URL=https://raw.githubusercontent.com/kwk/llvm-daily-fedora-rpms/{commitish}/fedora-copr/create-spec-file.sh

curl -L -s $URL bash -s -- --project {project} --yyyymmdd "{yyyymmdd}"