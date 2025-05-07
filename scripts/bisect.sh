#!/bin/bash

set -ex

function get_clang_commit {
  buildid=$1
  pkg=$2

  curl "https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/clang-monthly-fedora-rebuild/fedora-rawhide-x86_64/0$buildid-$pkg/root.log.gz" | gunzip |  grep -o 'clang[[:space:]]\+x86_64[[:space:]]\+[0-9a-g~pre.]\+' | cut -d 'g' -f 3
}

function get_clang_copr_project {
  buildid=$1
  pkg=$2
  arch=$(rpm --eval %{_arch})

  date=$(curl "https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/clang-monthly-fedora-rebuild/fedora-rawhide-$arch/0$buildid-$pkg/root.log.gz" | gunzip |  grep -o "clang[[:space:]]\+$arch[[:space:]]\+[0-9.]\+~pre[0-9]\+" | cut -d '~' -f 2 | sed 's/pre//g')
  echo "@fedora-llvm-team/llvm-snapshots-big-merge-$date"
}

function configure_llvm {

  if [ -n "$LLVM_SYSROOT" ] && [ -e "$LLVM_SYSROOT/bin/clang" ]; then
    cc=$LLVM_SYSROOT/bin/clang
    cxx=$LLVM_SYSROOT/bin/clang++
  else
    cc=clang
    cxx=clang++
  fi

  cmake -G Ninja -B build -S llvm -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_PROJECTS=clang -DLLVM_TARGETS_TO_BUILD=Native -DLLVM_BINUTILS_INCDIR=/usr/include/ -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER=$cxx -DCMAKE_C_COMPILER=$cc

}

function copr_project_exists {
  project=$1
  owner=$(echo $project | cut -d '/' -f 1)
  name=$(echo $project | cut -d '/' -f 2)

  curl -f -X 'GET' "https://copr.fedorainfracloud.org/api_3/project/?ownername=$owner&projectname=$name"   -H 'accept: application/json'
}

function test_with_copr_builds {
  copr_project=$1
  srpm_name=$2

  dnf remove -y clang llvm
  dnf copr enable -y $copr_project
  dnf install --best -y clang llvm
  dnf builddep -y $srpm_name
  # Disable project so future installs don't use it.
  dnf copr disable $copr_project
  if ! rpmbuild -D '%toolchain clang' -rb $srpm_name; then
    return 1
  fi
}

function test_copr_or_commit {
  copr_project=$1
  commit=$2
  srpm_name=$3

  if copr_project_exists $copr_project; then
    if ! test_with_copr_builds $copr_project $srpm_name; then
      return 1
    fi
  else
    git checkout $commit
    configure_llvm
    if ! ./git-bisect-script.sh $srpm_name; then
      return 1
    fi
  fi
}


pkg_or_buildid=$1

if echo $pkg_or_buildid | grep '^[0-9]\+'; then
  buildid=$pkg_or_buildid
  read -r pkg last_success_id <<<$(curl -X 'GET' "https://copr.fedorainfracloud.org/api_3/build/$buildid" -H 'accept: application/json' | jq -r '[.builds.latest.source_package.name,.builds.latest_succeeded.id] |  join(" ")')
else
  pkg=$pkg_or_buildid
fi

read -r buildid last_success_id <<<$(curl -X 'GET' \
  "https://copr.fedorainfracloud.org/api_3/package/?ownername=%40fedora-llvm-team&projectname=clang-monthly-fedora-rebuild&packagename=$pkg&with_latest_build=true&with_latest_succeeded_build=true" \
  -H 'accept: application/json' | jq -r '[.builds.latest.id,.builds.latest_succeeded.id] | join(" ")' )


good_commit=llvmorg-20-init
bad_commit=origin/main

good_commit=$(get_clang_commit $last_success_id $pkg)
bad_commit=$(get_clang_commit $buildid $pkg)

srpm_url=$(curl -X 'GET' "https://copr.fedorainfracloud.org/api_3/build/$buildid" -H 'accept: application/json' | jq -r .source_package.url)
curl -O -L $srpm_url
srpm_name=$(basename $srpm_url)

# We are downloading an SRPM prepared for x86, so we need to rebuild it on the
# host arch in case there are arch specific depedencies.
#
# HACK: There seems to be a bug in `rpmbuild -rs` where it won't create all the
# necessary  rpmbuild directories, so we need to run some other command first to
# make sure the directories are created.  `rpmbuild -rp` does the least
# of all the commands which is why we are using it to 'create' the directories.
rpmbuild --nodeps -rp $srpm_name &>/dev/null || true
rpmbuild -rs $srpm_name
srpm_name=$(find $(rpm --eval %{_srcrpmdir}) -iname '*.src.rpm')

# Enable the compat libraries so we can install a clang snapshot.
# We need to do this because the runtime repo dependencies from
# the snapshot copr projects is not resolved when using dnf5 see:
# https://github.com/fedora-copr/copr/issues/3387
dnf copr enable -y @fedora-llvm-team/llvm-compat-packages

# Test if the good commit still succeeds. A failure may indicate an
# intermittent failure or an issue that is unrelated to LLVM. In either case,
# this is not a "good commit".
good_copr_project=$(get_clang_copr_project $last_success_id $pkg)

if ! test_copr_or_commit $good_copr_project $good_commit $srpm_name; then
  echo "False Positive."
  exit 1
fi

# Test the bad commit to see if this a false positive.
bad_copr_project=$(get_clang_copr_project $buildid $pkg)
if test_copr_or_commit $bad_copr_project $bad_commit $srpm_name; then
  echo "False Positive."
  exit 1
fi

# First attempt to bisect using prebuilt binaries.
chroot="fedora-$(rpm --eval %{fedora})-$(rpm --eval %{_arch})"
good=$good_copr_project
bad=$bad_copr_project

while [ True ]; do
  test_project=$(python3 rebuilder.py bisect --chroot $chroot --good $good --bad $bad)
  echo "Trying $test_project"

  if [ "$test_project" = "$good_copr_project" ] || [ "$test_project" = "$bad_copr_project" ]; then
    break
  fi

  if test_with_copr_builds $test_project $srpm_name; then
    good=$test_project
    good_commit=$(dnf info --installed clang | grep '^Version' | cut -d 'g' -f 2)
    echo "GOOD"
  else
    bad=$test_project
    bad_commit=$(dnf info --installed clang | grep '^Version' | cut -d 'g' -f 2)
    echo "BAD"
  fi
done

dnf builddep -y $srpm_name
git bisect start
git bisect good $good_commit
git bisect bad $bad_commit
configure_llvm
git bisect run ./git-bisect-script.sh $srpm_name
