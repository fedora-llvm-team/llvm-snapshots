#!/bin/env python3

import argparse
import sys
from github import Github


def get_good_commit(
    token: str,
    project: str,
    start_ref: str,
    max_tries: int,
    ensure_checks: list[str],
    extend: int = 1,
) -> str:
    """
    Takes a github project and walks up the chain of commits beginning with
    `start_ref`. From there it checks the combined status of `max_tries` parent
    commits. All the checks in `ensure_checks` must have run for the commit to
    be considered the best of the `max_tries` commits. If among the `max_tries`
    commits there are multiples commits that have a successful combined status,
    the one is picked that passes all tests from `ensure_checks` and has the
    most overall checks run.

    See also: https://docs.github.com/en/rest/reference/repos#get-the-combined-status-for-a-specific-reference

    :param str token: to be used for github token authentication
    :param str project: the github project to work with
    :param str start_ref: the git ref to check first (can be a SHA, a branch name, or a tag name)
    :param int max_tries: the number of parents that the algorithm tries before giving up and returning an empty string
    :param list[str] ensure_checks: the list of checks that must exist for a commit to be classified as "good"
    :param int extend: how many times we extend the max_tries (if we don't have a good commit yet) before we give up
    """
    g = Github(login_or_token=token)
    repo = g.get_repo(project)
    next_sha = start_ref

    print("Scanning for best of commit", file=sys.stderr)
    print("Project:   {}".format(project), file=sys.stderr)
    print("Start ref: {}".format(start_ref), file=sys.stderr)
    print("Max tries: {}".format(max_tries), file=sys.stderr)
    print("Checks:    {}".format(ensure_checks), file=sys.stderr)
    print("Extend:    {}".format(extend), file=sys.stderr)

    max_check_runs = 0
    best_commit = ""

    for j in range(0, extend):
        if best_commit != "":
            break
        if j > 0:
            print(
                "Extending search radius because we haven't found a good commit yet: {}/{}".format(
                    j + 1, extend
                ),
                file=sys.stderr,
            )
        for i in range(0, max_tries):
            commit = repo.get_commit(sha=next_sha)
            next_sha = commit.parents[0].sha
            combined_status = commit.get_combined_status().state
            print(
                f"{i}. Combined status for {commit.sha} = {combined_status} (author.date={commit.commit.author.date}, commiter.date={commit.commit.comitter.date})",
                file=sys.stderr,
            )

            # move on with first parent if combined status is not successful
            if combined_status != "success":
                continue

            statuses = commit.get_statuses()
            num_check_runs = len(list(statuses))

            # Commit is only worth considering if it has more check runs than the
            # best commit so far.
            if num_check_runs <= max_check_runs:
                print(
                    "    Ignoring commit because number of check runs ({}) is below or equal current best ({})".format(
                        num_check_runs, max_check_runs
                    ),
                    file=sys.stderr,
                )
                continue

            # Makes sure the required check is among the ones that have been run on
            # the commit.
            checks = ensure_checks.copy()
            for status in statuses:
                if status.context in checks:
                    print(
                        "    * Status: {} - {}".format(
                            status.context, status.description
                        ),
                        file=sys.stderr,
                    )
                    checks.remove(status.context)
                # Ignore other checks that ran if all of the required ones have been found
                if len(checks) == 0:
                    break

            if len(checks) != 0:
                print("    Not all required checks have been run.", file=sys.stderr)
                continue

            best_commit = commit.sha
            max_check_runs = num_check_runs
            print(
                "    New best commit: sha {} (#check runs={})".format(
                    commit.sha, max_check_runs
                ),
                file=sys.stderr,
            )

    return best_commit


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
        "--extend",
        dest="extend",
        type=int,
        default="1",
        help="how many times we extend the max-tries (default: 1)",
    )
    parser.add_argument(
        "--ensure-checks",
        dest="ensure_checks",
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
        ensure_checks=args.ensure_checks,
        max_tries=args.max_tries,
        extend=args.extend,
    )
    if sha == "":
        sys.exit(-1)
    print(sha)


if __name__ == "__main__":
    main()
