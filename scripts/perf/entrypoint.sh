#!/usr/bin/bash

set -x
set -e

. /root/lib.sh

build_test_suite pgo llvm-snapshots-pgo-$YYYYMMDD
build_test_suite big-merge llvm-snapshots-big-merge-$YYYYMMDD
build_test_suite system

compare_compile_time pgo big-merge show_csv_header
compare_compile_time pgo system
compare_compile_time big-merge system

echo "Check $RESULT_DIR/results.csv"

# Enter interactive shell for you to explore
bash
