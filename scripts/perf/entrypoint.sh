#!/usr/bin/bash

set -x
set -e

. /root/lib.sh

build_test_suite pgo llvm-snapshots-pgo-$YYYYMMDD
build_test_suite snapshot llvm-snapshots-big-merge-$YYYYMMDD
build_test_suite system

compare_compile_time pgo snapshot show_csv_header
compare_compile_time pgo system
compare_compile_time snapshot system

function generate_markdown_report() {
    # calculate min/max for y-axis in diagram with some padding
    a=$(get_geomean_difference $RESULT_DIR/pgo_vs_snapshot.compile_time.txt)
    b=$(get_geomean_difference $RESULT_DIR/pgo_vs_system.compile_time.txt)
    c=$(get_geomean_difference $RESULT_DIR/snapshot_vs_system.compile_time.txt)
    pad=5
    min=$(python3 -c "print(min($a,$b,$c)-$pad)")
    max=$(python3 -c "print(max($a,$b,$c)+$pad)")

    redhat_release=$(cat /etc/redhat-release)
    arch=$(uname -m)

    echo '<!--BEGIN REPORT-->' > $RESULT_DIR/report.md
    cat <<EOF >> $RESULT_DIR/report.md
\`\`\`mermaid
xychart-beta horizontal
    title "Compile time performance (${YYYYMMDD}, ${arch}, ${redhat_release})"
    x-axis ["PGO vs. snapshot", "PGO vs. system", "snapshot vs. system"]
    y-axis "Geomean performance (in %)" ${min} --> ${max}
    bar [${a}, ${b}, ${c}]
    line [${a}, ${b}, ${c}]
\`\`\`

<details>
<summary>Compile time results for ${YYYYMMDD}</summary>

<h2>PGO vs. snapshot</h2>

\`\`\`
$(cat $RESULT_DIR/pgo_vs_snapshot.compile_time.txt)
\`\`\`

<h2>PGO vs. system</h2>

\`\`\`
$(cat $RESULT_DIR/pgo_vs_system.compile_time.txt)
\`\`\`

<h2>snapshot vs. system</h2>

\`\`\`
$(cat $RESULT_DIR/snapshot_vs_system.compile_time.txt)
\`\`\`
</details>
EOF
    echo '<!--END REPORT-->' >> $RESULT_DIR/report.md
}

generate_markdown_report
