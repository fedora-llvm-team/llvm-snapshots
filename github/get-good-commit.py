#!/bin/env python3

import argparse
import sys
from github import Github


def get_good_commit(
    token: str, project: str, start_ref: str, max_tries: int, ensure_checks: list[str]
) -> str:
    """
    Takes a github project and walks up the list of first parents beginning at
    `start_ref` until a "good" git commit is found. For a git commit to be good,
    the combined status of the git commit must be "success" and all the checks
    in `ensure_checks` must have run for the commit.

    See also: https://docs.github.com/en/rest/reference/repos#get-the-combined-status-for-a-specific-reference

    :param str token: to be used for github token authentication
    :param str project: the github project to work with
    :param str start_ref: the git ref to check first (can be a SHA, a branch name, or a tag name)
    :param int max_tries: the number of parents that the algorithm tries before giving up and returning an empty string
    :param list[str] ensure_checks: the list of checks that must exist for a commit to be classified as "good"
    """
    g = Github(login_or_token=token)
    repo = g.get_repo(project)
    sha = start_ref

    print("Scanning for good commit", file=sys.stderr)
    print("Project:   {}".format(project), file=sys.stderr)
    print("Start Ref: {}".format(start_ref), file=sys.stderr)
    print("Max Tries: {}".format(max_tries), file=sys.stderr)
    print("Checks:    {}".format(ensure_checks), file=sys.stderr)
    for i in range(0, max_tries):
        commit = repo.get_commit(sha=sha)
        combined_status = commit.get_combined_status().state
        print(
            "{}. Combined Status for {} = {}".format(i, commit, combined_status),
            file=sys.stderr,
        )
        if combined_status != "success":
            # move on with first parent if combined status is not successful
            sha = commit.parents[0].sha
            continue

        statuses = commit.get_statuses()
        checks = ensure_checks.copy()
        for status in statuses:
            if status.context in checks:
                print(
                    "  * Status: {} - {}".format(status.context, status.description),
                    file=sys.stderr,
                )
                checks.remove(status.context)
        if len(checks) != 0:
            sha = commit.parents[0].sha
            print(
                "  Not all checks found. Continue with parent commit: {}".format(sha),
                file=sys.stderr,
            )
            continue

        print("SUCCESS: First stable commit: {}".format(sha), file=sys.stderr)
        return sha
    print(
        "ERROR: No good commit found after {} tries".format(max_tries), file=sys.stderr
    )
    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Find the latest commit that passed tests"
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
        default="llvm/llvm-project",
        help="github project to use (default: llvm/llvm-project)",
    )
    parser.add_argument(
        "--start-ref",
        dest="start_ref",
        type=str,
        default="main",
        help="git reference (e.g. branch name or sha1) to check first (default: main)",
    )
    parser.add_argument(
        "--max-tries",
        dest="max_tries",
        type=int,
        default="20",
        help="how many commit to try before giving up (default: 20)",
    )
    parser.add_argument(
        "--ensure-checks",
        dest="ensure_checks",
        metavar="CHECK",
        nargs="+",
        default=[
            "clang-x86_64-debian-fast",
            "llvm-clang-x86_64-expensive-checks-debian",
        ],
        type=str,
        help="list check names that must have run (default: clang-x86_64-debian-fast, llvm-clang-x86_64-expensive-checks-debian)",
    )
    args = parser.parse_args()

    sha = get_good_commit(
        token=args.token,
        project=args.project,
        start_ref=args.start_ref,
        ensure_checks=args.ensure_checks,
        max_tries=args.max_tries,
    )
    if sha == "":
        sys.exit(-1)
    print(sha)


if __name__ == "__main__":
    main()
