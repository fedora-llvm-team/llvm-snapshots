#!/bin/bash

set -ex

pkg_or_buildid=$1

srpm_name=$(find . -iname *.src.rpm)
if echo $pkg_or_buildid | grep '[0-9]\+'; then 
  buildid=pkg_or_buildid
  pkg=$(curl -X 'GET' "https://copr.fedorainfracloud.org/api_3/build/$buildid" -H 'accept: application/json' | jq -r .source_package.name)
else
  buildid=$(curl -X 'GET' \
  "https://copr.fedorainfracloud.org/api_3/package/?ownername=%40fedora-llvm-team&projectname=fedora-41-clang-20&packagename=$pkg_or_buildid&with_latest_build=true&with_latest_succeeded_build=false" \
  -H 'accept: application/json' | jq .builds.latest.id )
  pkg=$pkg_or_buildid
fi
srpm_url=$(curl -X 'GET' "https://copr.fedorainfracloud.org/api_3/build/$buildid" -H 'accept: application/json' | jq -r .source_package.url)
curl -O -L $srpm_url
srpm_name=$(basename $srpm_url)

dnf builddep -y $srpm_name

good_commit=llvmorg-20-init
bad_commit=origin/main

git bisect start
git bisect good $good_commit
git bisect bad $bad_commit

cmake -G Ninja -B build -S llvm -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_PROJECTS=clang -DLLVM_TARGETS_TO_BUILD=Native -DLLVM_BINUTILS_INCDIR=/usr/include/ -DCMAKE_COMPILER_LAUNCHER=ccache

git bisect run ./git-bisect-script.sh $srpm_name

