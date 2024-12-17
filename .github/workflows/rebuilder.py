import argparse
import datetime
import json
import logging
import re
from typing import Set

import copr.v3
import dnf
import hawkey


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    tests.addTests(doctest.DocTestSuite())
    return tests


def filter_llvm_pkgs(pkgs: set[str]) -> set[str]:
    """Filters out LLVM packages and returns the rest.

    Args:
        pkgs (set[str]): List of package names

    Returns:
        set[str]: List of package names without LLVM packages

    Example:

    >>> pkgs={'firefox', 'llvm99', 'libreoffice', 'clang18', 'compiler-rt'}
    >>> filtered=list(filter_llvm_pkgs(pkgs))
    >>> filtered.sort()
    >>> print(filtered)
    ['firefox', 'libreoffice']

    """
    llvm_pkgs = {
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
    }
    llvm_pkg_pattern = rf"({'|'.join(llvm_pkgs)})[0-9]*$"
    return {pkg for pkg in pkgs if not re.match(llvm_pkg_pattern, pkg)}


def get_exclusions() -> set[str]:
    """
    This returns a list of packages we don't want to test.
    """
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
    pkgs = [p.name for p in list(q)]
    return filter_llvm_pkgs(set(pkgs)) - exclusions


def get_builds_from_copr(
    project_owner: str, project_name: str, copr_client: copr.v3.Client
) -> list[dict]:
    return copr_client.package_proxy.get_list(
        project_owner,
        project_name,
        with_latest_succeeded_build=True,
        with_latest_build=True,
    )


def get_monthly_rebuild_packages(pkgs: set[str], copr_pkgs: list[dict]) -> set[str]:
    for p in copr_pkgs:
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
    start_time: datetime.datetime,
    copr_pkgs: list[dict],
) -> set[str]:
    """Returns the list of packages that failed to build in the most recent
       rebuild, but built successfully in the previous rebuild.

    Args:
        start_time (datetime.datetime): The start time of the most recent mass
                                        rebuild.  This needs to be a time
                                        before the most recent mass rebuild
                                        and after the previous one.
        copr_pkgs (list[dict]): List of built packages for the COPR project.

    Returns:
        set[str]: List of packages that regressed in the most recent rebuilt.

    Example:

    >>> a = {"name" : "a", "builds" : { "latest" : { "id" : 1, "state" : "running", "submitted_on" : 1731457321 } , "latest_succeeded" : None } }
    >>> b = {"name" : "b", "builds" : { "latest" : { "id" : 1, "state" : "succeeded", "submitted_on" : 1731457321 } , "latest_succeeded" : None } }
    >>> c = {"name" : "c", "builds" : { "latest" : { "id" : 1, "state" : "succeeded", "submitted_on" : 1731457321 } , "latest_succeeded" : { "id" : 1 } } }
    >>> d = {"name" : "d", "builds" : { "latest" : { "id" : 2, "state" : "canceled", "submitted_on" : 1731457321 } , "latest_succeeded" : { "id" : 1 } } }
    >>> e = {"name" : "e", "builds" : { "latest" : { "id" : 2, "state" : "failed", "submitted_on" : 1 } , "latest_succeeded" : { "id" : 1 } } }
    >>> f = {"name" : "f", "builds" : { "latest" : { "id" : 2, "state" : "failed", "submitted_on" : 1731457321 } , "latest_succeeded" : { "id" : 1 } } }
    >>> copr_pkgs=[ a, b, c, d, e, f ]
    >>> project_owner = "@fedora-llvm-team"
    >>> project_name = "fedora41-clang-20"
    >>> regressions = get_monthly_rebuild_regressions(project_owner, project_name, datetime.datetime.fromisoformat("2024-11-11"), copr_pkgs)
    >>> print(regressions)
    [{'name' : 'f', 'url' : 'https://copr.fedorainfracloud.org/coprs/@fedora-llvm-team/fedora-41-clang-20/build/2/'}]

    """
    pkgs = []
    for p in copr_pkgs:
        latest_succeeded = p["builds"]["latest_succeeded"]
        latest = p["builds"]["latest"]

        if not latest:
            continue

        # Don't report regressions if there are still builds in progress
        if latest["state"] not in [
            "succeeded",
            "forked",
            "skipped",
            "failed",
            "canceled",
        ]:
            continue

        if not latest_succeeded:
            continue
        if latest["id"] == latest_succeeded["id"]:
            continue
        # latest is a successful build, but this doesn't mean it failed.
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

    print("START", pkgs, "END")
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
    logging.info("Rebuilding", len(pkgs), "packages")
    for p in pkgs:
        logging.info("Rebuild", p)
        copr_client.build_proxy.create_from_distgit(
            project_owner, project_name, p, "f41", buildopts=buildopts
        )


def select_snapshot_project(
    copr_client: copr.v3.Client, target_chroots: list[str], max_lookback_days: int = 14
) -> str:
    project_owner = "@fedora-llvm-team"
    for i in range(max_lookback_days):
        chroots = set()
        day = datetime.date.today() - datetime.timedelta(days=i)
        project_name = day.strftime("llvm-snapshots-big-merge-%Y%m%d")
        logging.info("Trying:", project_name)
        try:
            p = copr_client.project_proxy.get(project_owner, project_name)
            if not p:
                continue
            pkgs = copr_client.build_proxy.get_list(
                project_owner, project_name, "llvm", status="succeeded"
            )
            for pkg in pkgs:
                chroots.update(pkg["chroots"])

            logging.info(project_name, chroots)
            if all(t in chroots for t in target_chroots):
                logging.info("PASS", project_name)
                return project_name
        except:
            continue
    logging.warn("FAIL")
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

    logging.basicConfig(filename='rebuilder.log', level=logging.INFO)
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
        print(pkgs)
        try:
            copr_client.project_proxy.get(project_owner, project_name)
            copr_pkgs = get_builds_from_copr(project_owner, project_name, copr_client)
            print(copr_pkgs)
            pkgs = get_monthly_rebuild_packages(pkgs, copr_pkgs)
            print(pkgs)
        except:
            create_new_project(project_owner, project_name, copr_client, target_chroots)
        snapshot_project = select_snapshot_project(copr_client, target_chroots)
        start_rebuild(project_owner, project_name, copr_client, pkgs, snapshot_project)
    elif args.command == "get-regressions":
        start_time = datetime.datetime.fromisoformat(args.start_date)
        copr_pkgs = get_builds_from_copr(project_owner, project_name, copr_client)
        pkg_failures = get_monthly_rebuild_regressions(
            project_owner, project_name, start_time, copr_pkgs
        )
        print(json.dumps(pkg_failures))


if __name__ == "__main__":
    main()
