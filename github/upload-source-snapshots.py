#!/bin/env python3

from github import Github, UnknownObjectException
import argparse
import datetime
import os
from glob import glob


def main(args) -> None:
    g = Github(login_or_token=args.token)
    repo = g.get_repo(args.project)

    yyyymmdd = args.yyyymmdd
    release_name = args.release_name
    tag_name = release_name
    print("uploading assets for yyyymmdd='{}'".format(yyyymmdd))
    try:
        release = repo.get_release(release_name)
    except UnknownObjectException as ex:
        print("release '{}' not found but creating it now".format(release_name))
        release = repo.create_git_release(
            prerelease=True,
            name=release_name,
            draft=False,
            tag=tag_name,
            message="daily updated source-snapshots",
        )
    else:
        dir = os.getenv(key="GITHUB_WORKSPACE", default=".")
        print("looking for source snapshots in directory: {}".format(dir))
        glob_patterns = [
            "*-{}.src.tar.xz",
            "llvm-release-{}.txt",
            "llvm-rc-{}.txt",
            "llvm-git-revision-{}.txt",
        ]
        for pattern in glob_patterns:
            for name in glob(pattern.format(yyyymmdd)):
                path = os.path.join(dir, name)
                print("uploading path: {}".format(path))
                release.upload_asset(path=path)


if __name__ == "__main__":
    yyyymmdd = datetime.date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(
        description="Uploads the source snapshots as assets"
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
        default="kwk/llvm-daily-fedora-rpms",
        help="github project to use (default: kwk/llvm-daily-fedora-rpms)",
    )
    parser.add_argument(
        "--release-name",
        dest="release_name",
        type=str,
        default="source-snapshot",
        help="name of the release to store the source snapshots (source-snapshot)",
    )
    parser.add_argument(
        "--yyyymmdd",
        dest="yyyymmdd",
        type=str,
        default=yyyymmdd,
        help="year month day combination to filter upload files by (default for today: {})".format(
            yyyymmdd
        ),
    )

    main(parser.parse_args())
