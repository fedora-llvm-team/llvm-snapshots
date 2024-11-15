import argparse
import datetime
import json
import re
from typing import Set

import copr.v3
import dnf
import hawkey


def filter_llvm_pkgs(pkgs: set[str]) -> set[str]:
    llvm_pkgs = [
        "llvm",
        "clang",
        "llvm-bolt",
        "libomp",
        "compiler-rt",
        "lld",
        "lldb",
        "polly",
        "libcxx",
        "libclc",
        "flang",
        "mlir",
    ]
    filtered = set()
    for p in pkgs:
        exclude = False
        for l in llvm_pkgs:
            if re.match(l + "[0-9]*$", p):
                exclude = True
                break
        if not exclude:
            filtered.add(p)
    return filtered


"""
This returns a list of packages we don't want to test.
"""


def get_exclusions() -> set[str]:
    return set()


def get_pkgs(exclusions: set[str]) -> set[set]:
    base = dnf.Base()
    conf = base.conf
    for c in "AppStream", "BaseOS", "CRB", "Extras":
        base.repos.add_new_repo(
            f"{c}-source",
            conf,
            baseurl=[
                f"https://odcs.fedoraproject.org/composes/production/latest-Fedora-ELN/compose/{c}/source/tree/"
            ],
        )
    repos = base.repos.get_matching("*")
    repos.disable()
    repos = base.repos.get_matching("*-source*")
    repos.enable()

    base.fill_sack()
    q = base.sack.query(flags=hawkey.IGNORE_MODULAR_EXCLUDES)
    q = q.available()
    q = q.filter(requires=["clang", "gcc", "gcc-c++"])
    pkgs = {[p.name for p in list(q)]}
    return filter_llvm_pkgs(pkgs) - exclusions


def get_monthly_rebuild_packages(
    project_owner: str, project_name: str, copr_client: copr.v3.Client, pkgs: set[str]
) -> set[str]:
    for p in copr_client.package_proxy.get_list(
        project_owner,
        project_name,
        with_latest_succeeded_build=True,
        with_latest_build=True,
    ):
        latest_succeeded = p["builds"]["latest_succeeded"]
        latest = p["builds"]["latest"]
        if p["name"] not in pkgs:
            continue
        if not latest_succeeded:
            pkgs.discard(p["name"])
            continue
        if latest["id"] != latest_succeeded["id"]:
            pkgs.discard(p["name"])
    return pkgs


def get_monthly_rebuild_regressions(
    project_owner: str,
    project_name: str,
    copr_client: copr.v3.Client,
    start_time: datetime.datetime,
) -> set[str]:
    pkgs = []
    for p in copr_client.package_proxy.get_list(
        project_owner,
        project_name,
        with_latest_succeeded_build=True,
        with_latest_build=True,
    ):
        latest_succeeded = p["builds"]["latest_succeeded"]
        latest = p["builds"]["latest"]

        # Don't report regressions if there are still builds in progress
        if latest["state"] not in [
            "succeeded",
            "forked",
            "skipped",
            "failed",
            "canceled",
        ]:
            return []

        if not latest_succeeded:
            continue
        if latest["id"] == latest_succeeded["id"]:
            continue
        # latest is a bit a successful build, but this doesn't mean it failed.
        # It could be in progress.
        if latest["state"] != "failed":
            continue
        if int(latest["submitted_on"]) < start_time.timestamp():
            continue
        latest["name"] = p["name"]
        pkgs.append(
            {
                "name": p["name"],
                "url": f"https://copr.fedorainfracloud.org/coprs/{project_owner}/{project_name}/build/{latest['id']}/",
            }
        )
    return pkgs


def start_rebuild(
    project_owner: str,
    project_name: str,
    copr_client: copr.v3.Client,
    pkgs: set[str],
    snapshot_project_name: str,
):

    # Update the rebuild project to use the latest snapshot
    copr_client.project_proxy.edit(
        project_owner,
        project_name,
        additional_repos=[
            "copr://tstellar/fedora-clang-default-cc",
            f"copr://@fedora-llvm-team/{snapshot_project_name}",
        ],
    )

    buildopts = {
        "background": True,
    }
    print("Rebuilding", len(pkgs), "packages")
    for p in pkgs:
        print("Rebuild", p)
        copr_client.build_proxy.create_from_distgit(
            project_owner, project_name, p, "f41", buildopts=buildopts
        )
        return


def select_snapshot_project(
    copr_client: copr.v3.Client, target_chroots: list[str]
) -> str:
    project_owner = "@fedora-llvm-team"
    for i in range(14):
        chroots = set()
        day = datetime.date.today() - datetime.timedelta(days=i)
        project_name = day.strftime("llvm-snapshots-big-merge-%Y%m%d")
        print("Trying:", project_name)
        try:
            p = copr_client.project_proxy.get(project_owner, project_name)
            if not p:
                continue
            pkgs = copr_client.build_proxy.get_list(
                project_owner, project_name, "llvm", status="succeeded"
            )
            for pkg in pkgs:
                chroots.update(pkg["chroots"])

            print(project_name, chroots)
            if all(t in chroots for t in target_chroots):
                print("PASS", project_name)
                return project_name
        except:
            continue
    print("FAIL")
    return None


def create_new_project(
    project_owner: str,
    project_name: str,
    copr_client: copr.v3.Client,
    target_chroots: list[str],
):
    copr_client.project_proxy.add(project_owner, project_name, chroots=target_chroots)
    for c in target_chroots:
        copr_client.project_chroot_proxy.edit(
            project_owner,
            project_name,
            c,
            additional_packages=["fedora-clang-default-cc"],
            with_opts=["toolchain_clang", "clang_lto"],
        )


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=str, choices=["rebuild", "get-regressions"])
    parser.add_argument(
        "--start-date", type=str, help="Any ISO date format is accepted"
    )

    args = parser.parse_args()
    copr_client = copr.v3.Client.create_from_config_file()

    os_name = "fedora-41"
    clang_version = "20"
    target_arches = ["aarch64", "ppc64le", "s390x", "x86_64"]
    target_chroots = [f"{os_name}-{a}" for a in target_arches]
    project_owner = "@fedora-llvm-team"
    project_name = f"{os_name}-clang-{clang_version}"

    if args.command == "rebuild":
        exclusions = get_exclusions()
        pkgs = get_pkgs(exclusions)
        try:
            copr_client.project_proxy.get(project_owner, project_name)
            pkgs = get_monthly_rebuild_packages(
                project_owner, project_name, copr_client, pkgs
            )
        except:
            create_new_project(project_owner, project_name, copr_client, target_chroots)
        snapshot_project = select_snapshot_project(copr_client, target_chroots)
        start_rebuild(project_owner, project_name, copr_client, pkgs, snapshot_project)
    elif args.command == "get-regressions":
        start_time = datetime.datetime.fromisoformat(args.start_date)
        pkg_failures = get_monthly_rebuild_regressions(
            project_owner, project_name, copr_client, start_time
        )
        print(json.dumps(pkg_failures))


if __name__ == "__main__":
    main()
