#!/bin/env python3

import argparse
import calendar
import os
import sys
import time
from datetime import datetime

from copr.v3 import Client, CoprNoResultException


def gather_build_stats(
    copr_ownername: str, copr_projectname: str, separator: str, show_header: bool
) -> None:
    """Prints stats for each build of the passed copr project

    Args:
        copr_ownername (str): The copr project's owner
        copr_projectname (str): The copr project's name
        separator (str): How to separate CSV data (e.g. by semicolon or comma)
        show_header (bool): Show a first line header
    """

    client = Client.create_from_config_file()
    current_GMT = time.gmtime()
    timestamp = calendar.timegm(current_GMT)

    if show_header:
        print(
            "date{sep}package{sep}chroot{sep}build_time{sep}state{sep}build_id{sep}timestamp".format(
                sep=separator
            )
        )

    try:
        monitor = client.monitor_proxy.monitor(
            ownername=copr_ownername, projectname=copr_projectname
        )
    except CoprNoResultException:
        pass
    else:
        for package in monitor.packages:
            for chroot_name in package["chroots"]:
                chroot = package["chroots"][chroot_name]
                build_id = chroot["build_id"]
                build = client.build_proxy.get(build_id)
                build_time = -1
                ended_on = build["ended_on"]
                started_on = build["started_on"]
                submitted_on = build["submitted_on"]
                yyyymmdd = datetime.utcfromtimestamp(submitted_on).strftime("%Y/%m/%d")
                if ended_on is not None and started_on is not None:
                    build_time = int(ended_on) - int(started_on)
                print(
                    "{yyyymmdd}{sep}{package}{sep}{chroot}{sep}{build_time}{sep}{state}{sep}{id}{sep}{timestamp}".format(
                        sep=separator,
                        yyyymmdd=yyyymmdd,
                        package=build["source_package"]["name"],
                        chroot=build["chroots"][0],
                        build_time=build_time,
                        state=build["state"],
                        id=build["id"],
                        timestamp=timestamp,
                    ),
                    flush=True,
                )


def main():
    defaut_yyyymmdd = datetime.today().strftime("%Y%m%d")
    default_copr_ownername = "@fedora-llvm-team"
    default_copr_projectname = f"llvm-snapshots-incubator-{defaut_yyyymmdd}"

    parser = argparse.ArgumentParser(
        description="Print stats for a snapshot run in CVS format for further consumption"
    )

    parser.add_argument(
        "--copr-ownername",
        dest="copr_ownername",
        type=str,
        default=default_copr_ownername,
        help=f"copr ownername to use (default: {default_copr_ownername})",
    )

    parser.add_argument(
        "--copr-projectname",
        dest="copr_projectname",
        type=str,
        default=default_copr_projectname,
        help="copr projectname to use (defaults to today's project, e.g.: {})".format(
            default_copr_projectname
        ),
    )

    parser.add_argument(
        "--separator",
        dest="separator",
        type=str,
        default=",",
        help="separator to delimit fields",
    )

    parser.add_argument(
        "--show-header",
        dest="show_header",
        action="store_true",
        help="The first row will be a header row",
    )

    args = parser.parse_args()
    gather_build_stats(
        copr_ownername=args.copr_ownername,
        copr_projectname=args.copr_projectname,
        separator=args.separator,
        show_header=args.show_header,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()


# To query the builds stats for the last 32 days in a minute in parallel, do this:
# rm -f build-stats.csv
# for i in {31..0}; do
#     #d=$(date --date "$i days ago" '+%Y%m%d');
#     d=$(date -v -d$i '+%Y%m%d');
#     ./get-build-stats.py --copr-projectname llvm-snapshots-incubator-$d | tee -a build-stats.csv &
# done;
# wait
