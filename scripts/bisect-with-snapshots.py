import argparse
import re
import subprocess
import tempfile
from typing import Self

import copr.v3
import dnf
import dnf.cli
import git


class CoprProject:
    UNTESTED = 0
    GOOD = 1
    BAD = 2

    def __init__(self, name: str):
        self.name = name
        self.index = -1
        self._status = CoprProject.UNTESTED

    def __lt__(self, other: Self) -> bool:
        return self.name < other.name

    @property
    def commit(self) -> str:
        return self._commit

    @commit.setter
    def commit(self, commit: str) -> None:
        self._commit = commit

    @property
    def status(self) -> int:
        return self._status

    @status.setter
    def status(self, status: int) -> None:
        self._status = status


def get_snapshot_projects(chroot: str | None = None) -> list[CoprProject]:
    copr_client = copr.v3.Client.create_from_config_file()
    projects = []
    for p in copr_client.project_proxy.get_list(ownername="@fedora-llvm-team"):
        if not re.match(r"llvm-snapshots-big-merge-[0-9]+", p.name):
            continue
        if chroot and chroot not in list(p.chroot_repos.keys()):
            continue
        projects.append(CoprProject(p.name))
    projects.sort()
    for idx, p in enumerate(projects):
        p.index = idx
    return projects


def get_clang_commit_for_snapshot_project(project_name: str, chroot: str) -> str:
    copr_client = copr.v3.Client.create_from_config_file()

    builds = copr_client.build_proxy.get_list(
        "@fedora-llvm-team", project_name, packagename="llvm", status="succeeded"
    )
    regex = re.compile("llvm-[0-9.]+~pre[0-9]+.g([0-9a-f]+)")
    for b in builds:
        if chroot in b["chroots"]:
            print(b)
            m = regex.search(b["source_package"]["url"])
            if m:
                return m.group(1)
    raise Exception(f"Could not find commit for {project_name}, {chroot}")


def test_with_copr_builds(copr_project: str, test_command: str) -> bool:
    rpms = {"llvm", "clang"}

    print(f"Testing {copr_project}\n")
    copr_fullname = f"@fedora-llvm-team/{copr_project}"
    # Remove existing versions of clang and llvm
    with dnf.Base() as base:
        base.read_all_repos()
        base.fill_sack()
        for r in rpms:
            try:
                base.remove(r)
            except dnf.exceptions.PackagesNotInstalledError:
                pass
        base.resolve(allow_erasing=True)
        base.do_transaction()

    # Enable the copr repo that we want to test.
    # FIXME: There is probably some way to do this via the python API, but I
    # can't figure it out.
    subprocess.run(["dnf", "copr", "enable", "-y", copr_fullname])
    # Install clang and llvm builds to test
    with dnf.Base() as base:
        base.read_all_repos()
        base.fill_sack()
        for r in rpms:
            base.install(r)
        base.resolve(allow_erasing=True)
        base.download_packages(base.transaction.install_set)
        base.do_transaction()

    # Disable project so future installs don't use it.
    # FIXME: There is probably some way to do this via the python API, but I
    # can't figure it out.
    subprocess.run(["dnf", "copr", "disable", "-y", copr_fullname])

    print(test_command)
    p = subprocess.run(test_command.split())
    success = True if p.returncode == 0 else False
    print("{} project".format("Good" if success else "Bad"))
    return success


def git_bisect(
    repo: git.Repo,
    good_commit: str,
    bad_commit: str,
    configure_command: str,
    build_command: str,
    test_command: str,
) -> bool:
    print(f"Running git bisect with {good_commit} and {bad_commit}")
    print(configure_command)
    print(build_command)
    print(test_command)

    # Configure llvm
    subprocess.run(configure_command.split(), cwd=repo.working_tree_dir)

    # Use subprocess.run here instead of builtin commands so we can stream output.
    subprocess.run(
        ["git", "-C", repo.working_tree_dir, "bisect", "start", bad_commit, good_commit]
    )
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as bisect_script:
        cmd = f"""
            set -x
            pwd
            if ! {build_command}; then
              exit 125
            fi
            {test_command}
        """
        print(cmd)
        bisect_script.write(cmd)
        # Use the cwd argument instead of passing -C to git, so that the bisect script is
        # run in the llvm-project directory.
        subprocess.run(
            ["git", "bisect", "run", "/usr/bin/bash", bisect_script.name],
            cwd=repo.working_tree_dir,
            shell=True,
        )
    print(repo.git.bisect("log"))
    return True


def main() -> bool:

    parser = argparse.ArgumentParser()
    parser.add_argument("--good-commit")
    parser.add_argument("--bad-commit")
    parser.add_argument("--llvm-project-dir")
    parser.add_argument(
        "--configure-command",
        default="cmake -S llvm -G Ninja -B build -DCMAKE_BUILD_TYPE=Release -DLLVM_TARGETS_TO_BUILD=Native -DLLVM_ENABLE_PROJECTS=clang -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_C_COMPILER_LAUNCHER=ccache",
    )
    parser.add_argument(
        "--build-command",
        default="ninja -C build install-clang install-clang-resource-headers install-LLVMgold install-llvm-ar install-llvm-ranlib",
    )
    parser.add_argument("--test-command")
    parser.add_argument("--srpm")
    parser.add_argument("--chroot")
    args = parser.parse_args()

    repo = git.Repo(args.llvm_project_dir)

    chroot = args.chroot
    projects = get_snapshot_projects()
    good_project = None
    bad_project = None

    # Find for the oldest COPR project that is newer than the good commit.
    for p in projects:
        try:
            p.commit = get_clang_commit_for_snapshot_project(p.name, chroot)
            repo.git.merge_base("--is-ancestor", args.good_commit, p.commit)
        except Exception:
            continue
        print(p.commit, p.name, p.index, "/", len(projects))

        if not test_with_copr_builds(p.name, args.test_command):
            # The oldest commit was a 'bad' commit so we can use that as our
            # 'bad' commit for bisecting.
            return git_bisect(
                repo,
                args.good_commit,
                p.commit,
                args.configure_command,
                args.build_command,
                args.test_command,
            )
        good_project = p
        break

    # Find the newest COPR project that is older than the bad commit.
    for p in reversed(projects):
        try:
            p.commit = get_clang_commit_for_snapshot_project(p.name, chroot)
            repo.git.merge_base("--is-ancestor", p.commit, args.bad_commit)
        except Exception:
            continue
        print(p.commit, p.name, p.index, "/", len(projects))

        # We found a project, so test it.
        if test_with_copr_builds(p.name, args.test_command):
            # The newest commit was a 'good' commit, so we can use that as our
            # good commit for testing.
            return git_bisect(
                repo,
                p.commit,
                args.bad_commit,
                args.configure_command,
                args.build_command,
                args.test_command,
            )
        bad_project = p
        break

    # Bisect using copr builds
    if good_project and bad_project:
        while good_project.index + 1 < bad_project.index:
            test_project = projects[(good_project.index + bad_project.index) // 2]
            print(f"Testing: {test_project.name} - {test_project.commit}")
            if test_with_copr_builds(test_project.name, args.test_command):
                print("Good")
                good_project = test_project
            else:
                print("Bad")
                bad_project = test_project
    if good_project:
        args.good_commit = good_project.commit
    if bad_project:
        args.bad_commit = bad_project.commit

    # Bisect the rest of the way using git.
    return git_bisect(
        repo,
        args.good_commit,
        args.bad_commit,
        args.configure_command,
        args.build_command,
        args.test_command,
    )


if __name__ == "__main__":
    main()
