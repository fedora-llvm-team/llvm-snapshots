#!/bin/env python3

import argparse
import logging
import sys

from github import Github


def get_good_commit(
    token: str,
    project: str,
    start_ref: str,
    max_tries: int,
    required_checks: list[str],
) -> str:
    """
    Takes a github project and walks up the chain of commits beginning with
    `start_ref`. All the checks in `required_checks` must have run for the commit to
    be considered the best of the `max_tries` commits.

    :param str token: to be used for github token authentication
    :param str project: the github project to work with
    :param str start_ref: the git ref to check first (can be a SHA, a branch name, or a tag name)
    :param int max_tries: the number of parents that the algorithm tries before giving up and returning an empty string
    :param list[str] required_checks: the list of checks that must exist for a commit to be classified as "good"
    """
    g = Github(login_or_token=token)
    repo = g.get_repo(project)
    next_sha = start_ref
    logging.basicConfig(level=logging.INFO)
    logging.info(
        f"""
Scanning for best of commit
Project:         {project}
Start ref:       {start_ref}
Max tries:       {max_tries}
Required checks: {required_checks}
"""
    )

    required_checks = {(check, "success") for check in required_checks}
    for i in range(0, max_tries):
        commit = repo.get_commit(sha=next_sha)
        commit_url = f"https://github.com/{project}/commit/{commit.sha}"
        next_sha = commit.parents[0].sha

        logging.info(
            f"{i}. Checking commit {commit_url} (Date: {commit.commit.committer.date}, Combined status: {commit.get_combined_status().state})"
        )
        # Makes sure the required checks are among the ones that have been run
        # on the commit.
        actual_checks = {
            (status.context, status.state) for status in commit.get_statuses()
        }
        if not required_checks.issubset(actual_checks):
            logging.warning(
                f"- Ignoring commit because of missing or failed check(s): {required_checks - actual_checks}"
            )
            continue

        logging.info(f"Found good commit: {commit_url}")
        return commit.sha

    sha = repo.get_commit(sha=start_ref).sha
    logging.info(f"No good commit found, using the initial one: {start_ref}, aka {sha}")
    return sha


def main():
    parser = argparse.ArgumentParser(
        description="Find the latest commit that passed tests or return the start-ref commit sha"
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
        "--required-checks",
        dest="required_checks",
        metavar="CHECK",
        nargs="+",
        default=["clang-x86_64-debian-fast"],
        type=str,
        help="list check names that must have run (default: clang-x86_64-debian-fast)",
    )
    args = parser.parse_args()

    sha = get_good_commit(
        token=args.token,
        project=args.project,
        start_ref=args.start_ref,
        required_checks=args.required_checks,
        max_tries=args.max_tries,
    )

    print(sha)


if __name__ == "__main__":
    main()
