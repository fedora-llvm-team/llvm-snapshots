#!/bin/env python3

import sys
from github import Github
import argparse

def main(args) -> None:
    g = Github(login_or_token=args.token)
    repo = g.get_repo(args.project)
    sha=args.start_ref

    for i in range(0, args.max_tries):
        commit = repo.get_commit(sha=sha)
        combined_status = commit.get_combined_status().state
        if combined_status != "success":
            # move on with parent if combined status is not successful
            sha=commit.parents[0].sha
            continue
        
        ok = False
        statuses = commit.get_statuses()
        checks = args.ensure_checks
        for status in statuses:
            if status.context in checks:
                checks.remove(status.context)
        if len(checks) != 0:
            # not all checks were found, continue with parent commit
            sha=commit.parents[0].sha
            continue
        
        print(commit.sha)
        sys.exit(0)
    sys.exit(-1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Find the latest commit that passed tests')
    parser.add_argument('--token',
                        dest='token',
                        type=str,
                        default="YOUR-TOKEN-HERE",
                        help="your github token")
    parser.add_argument('--project',
                        dest='project',
                        type=str,
                        default="llvm/llvm-project",
                        help="github project to use (default: llvm/llvm-project)")
    parser.add_argument('--start-ref',
                        dest='start_ref',
                        type=str,
                        default="main",
                        help="git reference (e.g. branch name or sha1) to check first (default: main)")
    parser.add_argument('--max-tries',
                        dest='max_tries',
                        type=int,
                        default="20",
                        help="how many commit to try before giving up (default: 10)")
    parser.add_argument('--ensure-checks',
                        dest='ensure_checks',
                        metavar='CHECK',
                        nargs='+',
                        default=["clang-x86_64-debian-fast", "llvm-clang-x86_64-expensive-checks-debian"],
                        type=str,
                        help="list check names that must have run (default: clang-x86_64-debian-fast, llvm-clang-x86_64-expensive-checks-debian)")
    main(parser.parse_args())