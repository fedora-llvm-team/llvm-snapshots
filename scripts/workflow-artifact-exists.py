#!/bin/env python3

import argparse
import re
import sys
from datetime import date
from pprint import pprint

from github import Github


def workflow_artifact_exists(
    token: str,
    project: str,
    artifact_name: str,
    workflow_name: str,
    run_date: str = None,
) -> bool:
    """Checks if the given workflow artifact exists

    Args:
        token (str): The GitHub token to use
        project (str): The GitHub project to query
        artifact_name (str): The artifact to look for
        workflow_name (str): The workflow name to look for
        run_date (str, optional): Date when the workflow run happened. Defaults to None.

    Returns:
        bool: Whether the artifact exists or not.
    """
    extra_args = {}
    if run_date is not None:
        extra_args["created"] = str(run_date)

    g = Github(login_or_token=token)
    repo = g.get_repo(project)

    for wf in repo.get_workflows():
        print(f"Workflow: {wf.name}", file=sys.stderr)
        if wf.name != workflow_name:
            continue
        print(
            "  Found matching workflow. Now listing runs and their artifacts.",
            file=sys.stderr,
        )
        for run in wf.get_runs(exclude_pull_requests=True, **extra_args):
            print(f"  Run started at: {run.run_started_at}", file=sys.stderr)
            for artifact in run.get_artifacts():
                print(f"    Artifact: {artifact.name}", file=sys.stderr)
                if artifact_name == artifact.name:
                    print(f"    Found a match", file=sys.stderr)
                    return True

    print(f"Found no match", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Find the latest commit that passed tests"
    )
    parser.add_argument(
        "--token",
        dest="token",
        type=str,
        default="YOUR-TOKEN-HERE",
        help="Your GitHub token",
    )
    parser.add_argument(
        "--project",
        dest="project",
        type=str,
        default="fedora-llvm-team/llvm-snapshots",
        help="The GitHub project to use (default: fedora-llvm-team/llvm-snapshots)",
    )
    parser.add_argument(
        "--workflow-name",
        dest="workflow_name",
        type=str,
        default="",
        help="The GitHub workflow name to look for (e.g. Test Tool Management)",
    )
    parser.add_argument(
        "--artifact-name",
        dest="artifact_name",
        type=str,
        default="",
        help="The artifact name to look for (e.g. tmt-test-results-big-merge-20240206-fedora-rawhide)",
    )
    parser.add_argument(
        "--run-date",
        dest="run_date",
        type=str,
        default=None,
        help=f"Date when the workflow run happened. (e.g. 2024-01-29)",
    )

    args = parser.parse_args()

    if not workflow_artifact_exists(
        token=args.token,
        project=args.project,
        run_date=args.run_date,
        artifact_name=args.artifact_name,
        workflow_name=args.workflow_name,
    ):
        sys.exit(-1)


if __name__ == "__main__":
    main()
