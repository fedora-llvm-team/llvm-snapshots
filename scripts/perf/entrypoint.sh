#!/usr/bin/bash

set -x
set -e

function configure_build_run {
    # See also https://llvm.org/docs/TestSuiteGuide.html#common-configuration-options
    cmake_args=""

    # Recommended setting for compile-time benchmarks
    cmake_args="$cmake_args -DTEST_SUITE_SUBDIRS=CTMark"

    # For PGO performance comparison we expect differences in the range of 10%
    # and more. Therefore we don't need perf.
    cmake_args="$cmake_args -DTEST_SUITE_USE_PERF=OFF"

    # We want to measure the run-time of the compiler and therefore don't have
    # to "run" the benchmarks. We just need to compile them.
    cmake_args="$cmake_args -DTEST_SUITE_RUN_BENCHMARKS=OFF"

    # Collect internal LLVM statistics. Appends -save-stats=obj when invoking
    # the compiler and makes the lit runner collect and merge the statistic
    # files.
    cmake_args="$cmake_args -DTEST_SUITE_COLLECT_STATS=ON"

    # Some programs are unsuitable for performance measurements. Setting the
    # TEST_SUITE_BENCHMARKING_ONLY CMake option to ON will disable them.
    cmake_args="$cmake_args -DTEST_SUITE_BENCHMARKING_ONLY=ON"

    # Configure the test suite
    cmake \
        -GNinja \
        -DCMAKE_C_COMPILER=/usr/bin/clang \
        -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
        $cmake_args \
        -C/usr/share/llvm-test-suite/cmake/caches/O3.cmake \
        /usr/share/llvm-test-suite

    # Build the test-suite with one job at a time for a fair comparison.
    ninja -j1

    # Run the tests with lit:
    lit -v -o results.json . || true
}

function get_llvm_version() {
    clang --version | grep -Po '[0-9]+\.[0-9]+\.[0-9](pre[0-9]{8}.g[0-9a-f]{14})?' | head -n1
}

# Query version information for given day
yyyymmdd=$(date +%Y%m%d)
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
    llvm-libs-${rpm_suffix} \
    llvm-test-suite

pgo_version=$(get_llvm_version)

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
    llvm-libs-${rpm_suffix} \
    llvm-test-suite

big_merge_version=$(get_llvm_version)

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
dnf install -y clang clang-libs clang-resource-filesystem llvm llvm-libs llvm-test-suite
system_version=$(get_llvm_version)
mkdir -pv ~/system
cd ~/system

configure_build_run

/usr/share/llvm-test-suite/utils/compare.py \
    --metric compile_time \
    --lhs-name ${system_version} \
    --rhs-name pgo-${yyyymmdd} \
    ~/system/results.json vs ~/pgo/results.json > ~/results-system-vs-pgo.txt || true

/usr/share/llvm-test-suite/utils/compare.py \
    --metric compile_time \
    --lhs-name ${system_version} \
    --rhs-name big-merge-${yyyymmdd} \
    ~/system/results.json vs ~/big-merge/results.json > ~/results-system-vs-big-merge.txt || true

/usr/share/llvm-test-suite/utils/compare.py \
    --metric compile_time \
    --lhs-name big-merge \
    --rhs-name pgo-${yyyymmdd} \
    ~/big-merge/results.json vs ~/pgo/results.json > ~/results-big-merge-vs-pgo.txt || true


set +x

function print_report() {
    # calculate min/max for y-axis in diagram with some padding
    a=$(grep -ioP "Geomean difference\s+\K(-)?[0-9]+\.[0-9]+" ~/results-big-merge-vs-pgo.txt)
    b=$(grep -ioP "Geomean difference\s+\K(-)?[0-9]+\.[0-9]+" ~/results-system-vs-big-merge.txt)
    c=$(grep -ioP "Geomean difference\s+\K(-)?[0-9]+\.[0-9]+" ~/results-system-vs-pgo.txt)
    a=$(python3 -c "print(-1*$a)")
    b=$(python3 -c "print(-1*$b)")
    c=$(python3 -c "print(-1*$c)")
    pad=5
    min=$(python3 -c "print(min($a,$b,$c)-$pad)")
    max=$(python3 -c "print(max($a,$b,$c)+$pad)")

    redhat_release=$(cat /etc/redhat-release)
    arch=$(uname -m)

    echo '<!--BEGIN REPORT-->'
    cat <<EOF
\`\`\`mermaid
xychart-beta horizontal
    title "Compile time performance (${yyyymmdd}, ${arch}, ${redhat_release})"
    x-axis ["PGO vs. big-merge", "PGO vs. system", "big-merge vs. system"]
    y-axis "Geomean performance (in %)" ${min} --> ${max}
    bar [${a}, ${c}, ${b}]
    line [${a}, ${c}, ${b}]
\`\`\`

<details>
<summary>Compile time results for ${yyyymmdd}</summary>

<h2>big-merge (${big_merge_version}) vs. PGO (${pgo_version})</h2>

\`\`\`
$(cat ~/results-big-merge-vs-pgo.txt)
\`\`\`

<h2>System (${system_version}) vs. big-merge (${big_merge_version})</h2>

\`\`\`
$(cat ~/results-system-vs-big-merge.txt)
\`\`\`

<h2>System (${system_version}) vs. PGO (${pgo_version})</h2>

\`\`\`
$(cat ~/results-system-vs-pgo.txt)
\`\`\`
</details>
EOF
    echo '<!--END REPORT-->'
}

print_report
