#!/bin/env python3

import argparse
import datetime
import sys

from github import Github, UnknownObjectException


def delete_assets(
    token: str, project: str, release_name: str, delete_older: int, delete_today: bool
) -> bool:
    """
    Deletes release assets of a github project that are older than a given
    number of days. Optionally assets from today are also deleted.

    :param str token: to be used for github token authentication
    :param str project: the github project to work with
    :param str release_name: the github release within the project to operate on
    :param int delete_older: delete assets that are older than this amount of days
    :param bool delete_today: if True, deletes assets from today
    """
    g = Github(login_or_token=token)
    repo = g.get_repo(project)

    print(
        "deleting assets older than a week and from today in release '{}'".format(
            release_name
        )
    )
    try:
        release = repo.get_release(release_name)
    except UnknownObjectException:
        print(
            "release '{}' not found and so there's nothing to delete".format(
                release_name
            )
        )
    else:
        for asset in release.get_assets():
            now = datetime.datetime.now(asset.created_at.tzinfo)
            if asset.created_at < (now - datetime.timedelta(days=delete_older)):
                print(
                    "deleting asset '{}' created at {}".format(
                        asset.name, asset.created_at
                    )
                )
                if not asset.delete_asset():
                    return False
            if delete_today and asset.created_at.strftime("%Y%m%d") == now.strftime(
                "%Y%m%d"
            ):
                print(
                    "deleting asset '{}' created at {}".format(
                        asset.name, asset.created_at
                    )
                )
                if not asset.delete_asset():
                    return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete assets from today and older than a week (by default)."
    )
    parser.add_argument(
        "--token",
        dest="token",
        type=str,
        default="YOUR-TOKEN-HERE",
        help="your github token",
    )
    parser.add_argument(
        "--project",
        dest="project",
        type=str,
        default="fedora-llvm-team/llvm-snapshots",
        help="github project to use (default: fedora-llvm-team/llvm-snapshots)",
    )
    parser.add_argument(
        "--release-name",
        dest="release_name",
        type=str,
        default="source-snapshot",
        help="name of the release to store the source snapshots (default: source-snapshot)",
    )
    parser.add_argument(
        "--delete-older",
        dest="delete_older",
        type=int,
        default="7",
        help="assets older than the given amount of days will be deleted (default: 7)",
    )
    parser.add_argument(
        "--delete-today",
        dest="delete_today",
        action="store_true",
        help="delete assets of today before recreating them (default: no)",
    )
    args = parser.parse_args()
    if not delete_assets(
        token=args.token,
        project=args.project,
        release_name=args.release_name,
        delete_older=args.delete_older,
        delete_today=args.delete_today,
    ):
        sys.exit(-1)
    sys.exit(0)


if __name__ == "__main__":
    main()
