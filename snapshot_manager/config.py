#!/bin/env python3

import json
import sys

from snapshot_manager.copr_util import get_all_chroots, make_client
from snapshot_manager.util import filter_chroots, sanitize_chroots


def get_github_matrix(
    strategy: str, lookback_days: list[int], all_chroots: list[str]
) -> dict:
    """Returns a dictionary that can be serialized to JSON to be used in as a github workflow matrix.

    See https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow.

    Args:
        strategy (str): Which strategy to output for (big-merge, pgo, "" are supported)
        lookback_days (list[int]): Integer array for how many days to look back (0 means just today)
        all_chroots (list[str]): A list of all possible chroots currently supported on Copr

    Returns:
        dict: A github workflow matrix dictionary
    """
    res = {
        "names": [],
        "includes": [],
        "today_minus_n_days": lookback_days,
    }

    if strategy in ("", "big-merge", "all"):
        res["names"].append("big-merge")
        res["includes"].append(
            {
                "name": "big-merge",
                "copr_target_project": "@fedora-llvm-team/llvm-snapshots",
                "clone_url": "https://src.fedoraproject.org/rpms/llvm.git",
                "clone_ref": "rawhide",
                "maintainer_handle": "tuliom",
                "copr_ownername": "@fedora-llvm-team",
                "copr_project_tpl": "llvm-snapshots-big-merge-YYYYMMDD",
                "copr_monitor_tpl": "https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-big-merge-YYYYMMDD/monitor/",
                "chroot_pattern": "^(fedora-(rawhide|[0-9]+)|rhel-[8,9]-)",
                "chroots": [],
            }
        )

    if strategy in ("", "pgo", "all"):
        res["names"].append("pgo")
        res["includes"].append(
            {
                "name": "pgo",
                "copr_target_project": "@fedora-llvm-team/llvm-snapshots-pgo",
                "extra_script_file": "scripts/functions-pgo.sh",
                "clone_url": "https://src.fedoraproject.org/forks/kkleine/rpms/llvm.git",
                "clone_ref": "pgo",
                "maintainer_handle": "kwk",
                "copr_ownername": "@fedora-llvm-team",
                "copr_project_tpl": "llvm-snapshots-pgo-YYYYMMDD",
                "copr_monitor_tpl": "https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-pgo-YYYYMMDD/monitor/",
                "chroot_pattern": "^(fedora-41)",
                "chroots": [],
            }
        )

    # Take chroot_pattern for each strategy and translate it into a list of
    # "sanitized" chroots. "Santized" in this case means that we'll strip out
    # any fedora s390x chroots that are not "rawhide" or the highest numbered
    # release in the filtered list.
    for include in res["includes"]:
        chroots = filter_chroots(chroots=all_chroots, pattern=include["chroot_pattern"])
        include["chroots"] = sanitize_chroots(chroots=chroots)

    return res


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Print stats for a snapshot run in CVS format for further consumption"
    )

    parser.add_argument(
        "--strategy",
        dest="strategy",
        type=str,
        default="",
        help=f"Strategy to use (not specifying a strategy will include all of them)",
    )

    parser.add_argument(
        "--lookback",
        metavar="DAY",
        type=int,
        nargs="+",
        dest="lookback_days",
        default=0,
        help="Integers for how many days to look back (0 means just today)",
    )

    args = parser.parse_args()

    copr_client = make_client()
    all_chroots = get_all_chroots(client=copr_client)

    matrix = get_github_matrix(
        all_chroots=all_chroots,
        strategy=args.strategy,
        lookback_days=args.lookback_days,
    )
    print(json.dumps(matrix))

    sys.exit(0)


if __name__ == "__main__":
    main()
