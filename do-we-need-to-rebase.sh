#!/bin/bash

# This script checks if my forks of the LLVM subproject RPM repos need to be
# updated against their upstream counter part.

set -eu
set -o pipefail

projects="llvm clang lld compiler-rt libomp mlir python-lit"
temp_dir=$(mktemp -d -t LLVM-PROJECTS.XXX)
trap 'rm -rf -- "$temp_dir"' EXIT

# this exit code is used for non-error exit codes
exit_code=0

for project in $projects; do
    # Create temporary directory for the LLVM subproject
    project_dir="$temp_dir/$project"

    git clone --quiet --origin upstream https://src.fedoraproject.org/rpms/$project $project_dir > /dev/null 2>&1
    if [ $? -ne 0 ] ; then
        echo "failed to clone git repo into $project_dir"
        exit 1
    fi
    if ! git -C $project_dir remote add -f fork https://src.fedoraproject.org/forks/kkleine/rpms/$project.git > /dev/null 2>&1; then
        echo "failed to add git remote"
        exit 1
    fi
    if ! git -C $project_dir fetch --multiple upstream fork --quiet > /dev/null 2>&1; then
        echo "failed to fetch git remotes"
        exit 1
    fi

    branches="snapshot-build"
    if [[ $project =~ llvm|clang ]]; then
        # only for the compat builds we need the f34 and f35 branches
        branches="$branches f34 f35"
    fi

    for branch in $branches; do
        # translate fork branch to upstream branch
        upstream_branch=$branch
        if [[ $branch == "snapshot-build" ]]; then
            upstream_branch="rawhide"
        fi

        upstream_commit=$(git -C $project_dir rev-parse --verify upstream/$upstream_branch^{commit})

        # check if the upstream commit is already in the respective fork's branch
        if ! git -C $project_dir branch --contains $upstream_commit --no-color --all | grep -E "(^|\s)remotes/fork/$branch$" > /dev/null 2>&1; then
            echo "$project's fork/$branch branch needs rebasing onto upstream/$upstream_branch"
            exit_code=-1
        fi
    done
done

exit $exit_code