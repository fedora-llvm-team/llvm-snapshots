#!/usr/bin/bash

set -x
set -e

function configure_build_run {
    # Configure the test suite
    cmake \
        -DCMAKE_GENERATOR=Ninja \
        -DCMAKE_C_COMPILER=/usr/bin/clang \
        -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
        -DTEST_SUITE_BENCHMARKING_ONLY=ON \
        -DTEST_SUITE_COLLECT_STATS=ON \
        -DTEST_SUITE_USE_PERF=OFF \
        -DTEST_SUITE_SUBDIRS=CTMark \
        -DTEST_SUITE_RUN_BENCHMARKS=OFF \
        -C~/test-suite/cmake/caches/O3.cmake \
        ~/test-suite

    # Build the test-suite
    ninja -j1

    # Run the tests with lit:
    lit -v -o results.json . || true
}

# Query version information for given day
yyyymmdd=20240911
git_rev=$(curl -sL https://github.com/fedora-llvm-team/llvm-snapshots/releases/download/snapshot-version-sync/llvm-git-revision-${yyyymmdd}.txt)
git_rev_short="${git_rev:0:14}"
llvm_release=$(curl -sL https://github.com/fedora-llvm-team/llvm-snapshots/releases/download/snapshot-version-sync/llvm-release-${yyyymmdd}.txt)
rpm_suffix="${llvm_release}~pre${yyyymmdd}.g${git_rev_short}"

echo "git_rev=$git_rev"
echo "git_rev_short=$git_rev_short"
echo "llvm_release=$llvm_release"
echo "rpm_suffix=$rpm_suffix"

######################################################################################
# PGO
######################################################################################

# Install and enable the repository that provides the PGO LLVM Toolchain
# See https://llvm.org/docs/HowToBuildWithPGO.html#building-clang-with-pgo
dnf copr enable -y @fedora-llvm-team/llvm-snapshots-pgo-${yyyymmdd}
repo_file=$(dnf repoinfo --json *llvm-snapshots-pgo* | jq -r ".[0].repo_file_path")
distname=$(rpm --eval "%{?fedora:fedora}%{?rhel:rhel}") envsubst '$distname' < $repo_file > /tmp/new_repo_file
cat /tmp/new_repo_file > $repo_file
dnf -y install \
    clang-${rpm_suffix} \
    clang-${rpm_suffix} \
    clang-libs-${rpm_suffix} \
    clang-resource-filesystem-${rpm_suffix} \
    llvm-${rpm_suffix} \
    llvm-libs-${rpm_suffix}

mkdir -pv ~/pgo
cd ~/pgo

configure_build_run

# Remove packages from that PGO repo and the repo itself
repo_pkgs_installed=$(dnf repoquery --installed --queryformat ' %{name} %{from_repo} ' | grep -Po "[^ ]+ [^ ]+llvm-snapshots-pgo" | awk '{print $1}')
dnf -y remove $repo_pkgs_installed;
dnf copr disable -y @fedora-llvm-team/llvm-snapshots-pgo-${yyyymmdd}

######################################################################################
# big-merge
######################################################################################

# Install and enable the repository that provides the big-merge LLVM Toolchain
dnf copr enable -y @fedora-llvm-team/llvm-snapshots-big-merge-${yyyymmdd}
repo_file=$(dnf repoinfo --json *llvm-snapshots-big-merge* | jq -r ".[0].repo_file_path")
distname=$(rpm --eval "%{?fedora:fedora}%{?rhel:rhel}") envsubst '$distname' < $repo_file > /tmp/new_repo_file
cat /tmp/new_repo_file > $repo_file
dnf -y install \
    clang-${rpm_suffix} \
    clang-${rpm_suffix} \
    clang-libs-${rpm_suffix} \
    clang-resource-filesystem-${rpm_suffix} \
    llvm-${rpm_suffix} \
    llvm-libs-${rpm_suffix}

mkdir -pv ~/big-merge
cd ~/big-merge

configure_build_run
# Remove packages from that big-merge repo and the repo itself
repo_pkgs_installed=$(dnf repoquery --installed --queryformat ' %{name} %{from_repo} ' | grep -Po "[^ ]+ [^ ]+llvm-snapshots-big-merge" | awk '{print $1}')
dnf -y remove $repo_pkgs_installed;
dnf copr disable -y @fedora-llvm-team/llvm-snapshots-big-merge-${yyyymmdd}

######################################################################################
# system llvm
######################################################################################

# Build with regular clang
dnf install -y clang clang-libs clang-resource-filesystem llvm llvm-libs
mkdir -pv ~/system
cd ~/system

configure_build_run

system_llvm_release=$(clang --version | grep -Po '[0-9]+\.[0-9]+\.[0-9]' | head -n1)

/root/test-suite/utils/compare.py \
    --metric compile_time \
    --lhs-name ${system_llvm_release} \
    --rhs-name pgo-${yyyymmdd} \
    ~/system/results.json vs ~/pgo/results.json > ~/results-system-vs-pgo.txt || true

/root/test-suite/utils/compare.py \
    --metric compile_time \
    --lhs-name ${system_llvm_release} \
    --rhs-name big-merge-${yyyymmdd} \
    ~/system/results.json vs ~/big-merge/results.json > ~/results-system-vs-big-merge.txt || true

/root/test-suite/utils/compare.py \
    --metric compile_time \
    --lhs-name big-merge \
    --rhs-name pgo-${yyyymmdd} \
    ~/big-merge/results.json vs ~/pgo/results.json > ~/results-big-merge-vs-pgo.txt || true

bash
