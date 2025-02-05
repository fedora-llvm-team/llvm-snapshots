#!/bin/bash

set -ex

function get_clang_commit {
  buildid=$1
  pkg=$2

  curl "https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/fedora-41-clang-20/fedora-41-x86_64/0$buildid-$pkg/root.log.gz" | gunzip |  grep -o 'clang[[:space:]]\+x86_64[[:space:]]\+[0-9a-g~pre.]\+' | cut -d 'g' -f 3
}


pkg_or_buildid=$1

if echo $pkg_or_buildid | grep '^[0-9]\+'; then
  buildid=$pkg_or_buildid
  read -r pkg last_success_id <<<$(curl -X 'GET' "https://copr.fedorainfracloud.org/api_3/build/$buildid" -H 'accept: application/json' | jq -r '[.builds.latest.source_package.name,.builds.latest_succeeded.id] |  join(" ")')
else
  pkg=$pkg_or_buildid
fi

read -r buildid last_success_id <<<$(curl -X 'GET' \
  "https://copr.fedorainfracloud.org/api_3/package/?ownername=%40fedora-llvm-team&projectname=fedora-41-clang-20&packagename=$pkg&with_latest_build=true&with_latest_succeeded_build=true" \
  -H 'accept: application/json' | jq -r '[.builds.latest.id,.builds.latest_succeeded.id] | join(" ")' )


good_commit=llvmorg-20-init
bad_commit=origin/main

good_commit=$(get_clang_commit $last_success_id $pkg)
bad_commit=$(get_clang_commit $buildid $pkg)

srpm_url=$(curl -X 'GET' "https://copr.fedorainfracloud.org/api_3/build/$buildid" -H 'accept: application/json' | jq -r .source_package.url)
curl -O -L $srpm_url
srpm_name=$(basename $srpm_url)

dnf builddep -y $srpm_name

# Test the good commit to see if this a false positive
git checkout $good_commit

cmake -G Ninja -B build -S llvm -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_PROJECTS=clang -DLLVM_TARGETS_TO_BUILD=Native -DLLVM_BINUTILS_INCDIR=/usr/include/ -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER=/opt/llvm/bin/clang++ -DCMAKE_C_COMPILER=/opt/llvm/bin/clang

if ! ./git-bisect-script.sh $srpm_name; then
  echo "False Positive."
  exit 1
fi

git checkout $bad_commit
# Test the bad commit to see if this a false positive
if ./git-bisect-script.sh $srpm_name; then
  echo "False Positive."
  exit 1
fi

git bisect start
git bisect good $good_commit
git bisect bad $bad_commit

cmake -G Ninja -B build -S llvm -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_PROJECTS=clang -DLLVM_TARGETS_TO_BUILD=Native -DLLVM_BINUTILS_INCDIR=/usr/include/ -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER=/opt/llvm/bin/clang++ -DCMAKE_C_COMPILER=/opt/llvm/bin/clang

git bisect run ./git-bisect-script.sh $srpm_name
