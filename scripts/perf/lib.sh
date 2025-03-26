#!/usr/bin/bash

# This file houses functions to help with comparison of different LLVM build
# strategies.

set -e
set -x

# When run in testing-farm we'll use the TMT_PLAN_DATA to store all artifacts
# from the functions below.
# (For TMT_PLAN_DATA see https://tmt.readthedocs.io/en/stable/overview.html#step-variables)
RESULT_DIR=${TMT_PLAN_DATA:-/tmp}
YYYYMMDD=${YYYYMMDD:-$(date +%Y%m%d)}

# Construct chroot if needed
CHROOT=${COPR_CHROOT:-}
if [[ -z "$CHROOT" ]]; then
    os=$(cat /etc/os-release | grep -oP '^ID=["]?\K[^"]+')
    product_version=$(cat /etc/os-release | grep -oP "REDHAT_BUGZILLA_PRODUCT_VERSION=\K.*")
    arch=$(uname -m)
    CHROOT=${os}-${product_version}-${arch}
fi

# Helper function to configure, build and test the llvm-test-suite in a
# directory with the given `NAME` and dump the test results in a file called
# `<RESULT_DIR>/<NAME>.json` for later comparison.
function _configure_build_test {
    local NAME=$1
    local N_BUILD_JOBS=$2

    local BUILD_DIR=builds/$NAME

    mkdir -pv $BUILD_DIR
    pushd $BUILD_DIR

    # See also https://llvm.org/docs/TestSuiteGuide.html#common-configuration-options
    local cmake_args=""

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
    ninja -j$N_BUILD_JOBS

    # Run the tests with lit:
    lit -v -o ${RESULT_DIR}/${NAME}.json . || true

    popd

    # We delete the build directory in order to not artificially decrease the
    # performance of upcoming builds due to "file system pressure".
    rm -rf ${BUILD_DIR}
}

# This function builds the llvm-test-suite in the directory for the given
# `NAME`. It will use the optional `COPR_PROJECT` as a source for installing
# clang. When no `COPR_PROJECT` is given, we will install clang from the system
# without any copr repo. After the job is done the copr repo and all packages
# from it will be uninstalled.
function build_test_suite() {
    local NAME=$1
    local COPR_PROJECT=${2:-}
    local N_BUILD_JOBS=${N_BUILD_JOBS:-$(nproc)}

    # The Copr owner/project to enable for installing clang
    local COPR_OWNER=${COPR_OWNER:-@fedora-llvm-team}

    # Install and enable the repository that provides the LLVM Toolchain
    if [[ -n "${COPR_PROJECT}" ]]; then
        dnf copr enable -y ${COPR_OWNER}/${COPR_PROJECT}
        local repo_file=$(dnf repoinfo --json *${COPR_PROJECT}* | jq -r ".[0].repo_file_path")
        distname=$(rpm --eval "%{?fedora:fedora}%{?rhel:rhel}")
        sed -i "s/\$distname/$distname/g" $repo_file

        # Query version information for given day
        local git_rev=$(curl -sL https://github.com/fedora-llvm-team/llvm-snapshots/releases/download/snapshot-version-sync/llvm-git-revision-${YYYYMMDD}.txt)
        local git_rev_short="${git_rev:0:14}"
        local llvm_release=$(curl -sL https://github.com/fedora-llvm-team/llvm-snapshots/releases/download/snapshot-version-sync/llvm-release-${YYYYMMDD}.txt)
        local rpm_suffix="-${llvm_release}~pre${YYYYMMDD}.g${git_rev_short}"
    else
        local rpm_suffix=""
    fi

    dnf -y install \
        clang${rpm_suffix} \
        clang-libs${rpm_suffix} \
        clang-resource-filesystem${rpm_suffix} \
        llvm${rpm_suffix} \
        llvm-libs${rpm_suffix} \
        llvm-test-suite

    _configure_build_test $NAME $N_BUILD_JOBS

    if [[ -n "${COPR_PROJECT}" ]]; then
        # Remove packages from that repo and the repo itself
        local repo_pkgs_installed=$(dnf repoquery --installed --queryformat ' %{name} %{from_repo} ' | grep -Po "[^ ]+ [^ ]+${COPR_PROJECT}" | awk '{print $1}')
        dnf -y remove $repo_pkgs_installed;
        dnf copr disable -y ${COPR_OWNER}/${COPR_PROJECT}
    fi
}

# This function compares two JSON files produced by `_configure_build_test()`.
# This function accepts a name for the left and right hand side of the
# comparison. The input data for each side is deduced from the name and the
# result of the comparison is stored in a file named
# `<RESULT>/<LHS>_vs_<RHS>.<KIND>.txt`. Additionally this function will produce
# a CSV file entry in <RESULT_DIR>/results.csv for further processing (e.g.
# plotting).
function compare_compile_time() {
    local LHS_NAME=$1
    local RHS_NAME=$2
    local OUTPUT_CSV_HEADER=${3:-}
    local LHS_DATA=$RESULT_DIR/$LHS_NAME.json
    local RHS_DATA=$RESULT_DIR/$RHS_NAME.json

    rpm -q llvm-test-suite || dnf install -y llvm-test-suite

    if [[ ! -d .venv ]]; then
        python3 -m venv .venv
    fi
    source ./.venv/bin/activate
    pip install "pandas>=2.2.3"

    /usr/share/llvm-test-suite/utils/compare.py \
        --metric compile_time \
        --lhs-name $LHS_NAME \
        --rhs-name $RHS_NAME \
        $LHS_DATA vs $RHS_DATA | tee ${RESULT_DIR}/${LHS_NAME}_vs_${RHS_NAME}.compile_time.txt

    deactivate

    _csv compile_time $LHS_NAME $RHS_NAME $OUTPUT_CSV_HEADER
}

function get_geomean_difference() {
    local FILE=$1
    grep -ioP "Geomean difference\s+\K(-)?[0-9]+\.[0-9]+" $FILE
}

# This function looks up the <RESULT_DIR>/<LHS>_vs_<RHS>.<KIND>.txt comparison
# result file (see `compare_compile_time()`) and looks for the geomean
# difference in it. It then appends a line in CSV format to
# <RESULT_DIR>/results.csv which can be processed later (e.g. for plotting). The
# result.csv file will have this format:
#
#    date,package,chroot,name,kind,geomean_diff,timestamp
#    2025/03/17,llvm,fedora-rawhide-x86_64,pgo_vs_snapshot,compile_time,40.5,1742508016
#    2025/03/17,llvm,fedora-rawhide-x86_64,pgo_vs_system,compile_time,40.7,1742508017
#    2025/03/17,llvm,fedora-rawhide-x86_64,snapshot_vs_system,compile_time,0.1,1742508018
#
# NOTE: Currently the only <KIND> supported is `compile_time`
function _csv() {
    local KIND=$1
    local LHS_NAME=$2
    local RHS_NAME=$3
    local OUTPUT_CSV_HEADER=${4:-}

    # Name used in the CSV entry to say what was compared
    local NAME=${LHS_NAME}_vs_${RHS_NAME}

    # Output of comparison script
    local INPUT_PATH=$RESULT_DIR/$NAME.${KIND}.txt

    # Grep the geomean difference line from the "compare.py" output above
    local geomean_diff=$(get_geomean_difference ${INPUT_PATH})
    #local geomean_diff=$(python3 -c "print(-1*${geomean_diff})")

    # Not to mix with YYYYMMDD!
    local current_timestamp=$(date +%s)

    # Correctly formatted date string for easy consumption with plotly
    local date_string=$(python3 -c "import datetime; print(datetime.datetime.strptime('${YYYYMMDD}', '%Y%m%d').strftime('%Y/%m/%d'))")

    if [[ -n "${OUTPUT_CSV_HEADER}" ]]; then
        echo "date,package,chroot,name,kind,geomean_diff,timestamp" | tee -a $RESULT_DIR/results.csv
    fi
    echo "${date_string},llvm,${CHROOT},${NAME},${KIND},${geomean_diff},${current_timestamp}" | tee -a $RESULT_DIR/results.csv
}
