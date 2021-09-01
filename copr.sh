#!/bin/bash

set -x
set -eu

# Ensure Bash pipelines (e.g. cmd | othercmd) return a non-zero status if any of
# the commands fail, rather than returning the exit status of the last command
# in the pipeline.
set -o pipefail

project=$1
yyyymmdd=$(date +%Y%m%d)

rm -rfv /workdir/*
git clone https://github.com/kwk/llvm-daily-fedora-rpms.git /workdir/llvm-daily-fedora-rpms
cd /workdir/llvm-daily-fedora-rpms

# mkdir -pv /workdir/rpmbuild
HOME=/workdir DEBUG=1 rpmdev-setuptree

make VERBOSE=1 clean

HOME=/workdir /workdir/llvm-daily-fedora-rpms/home/johndoe/bin/build.sh \
    --verbose \
    --reset-project \
    --generate-spec-file \
    --build-srpm \
    --yyyymmdd ${yyyymmdd} \
    --project ${project}