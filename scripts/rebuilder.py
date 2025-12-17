import argparse
import datetime
import json
import logging
import re
import sys
import unittest
import urllib.request
from typing import Any

import copr.v3
import dnf
import hawkey
import koji
from munch import Munch


def get_rawhide_tag() -> str:
    """ Returns the current tag for rawhide, i.e. "f44". """
    koji_session = koji.ClientSession("https://koji.fedoraproject.org/kojihub")
    target = koji_session.getBuildTarget("rawhide")
    return target["build_tag_name"].split("-")[0]


def is_tier0_package(pkg: str) -> bool:
    return pkg in [
        "dotnet6.0",
        "dotnet7.0",
        "dotnet8.0",
        "dotnet9.0",
        "qemu-kvm",  # RHEL name
        "qemu",  # Fedora name
        "golang",
        "wasi-lbc",
    ]


def filter_unsupported_pkgs(pkgs: set[str]|list[str]) -> set[str]:
    """Filters out unsupported packages and returns the rest.

    Args:
        pkgs (set[str]|list[str]): List of package names

    Returns:
        set[str]: Set of package names without unsupported packages

    Example:

    >>> pkgs={"foo", "dotnet6.0", "bar"}
    >>> filtered=list(filter_unsupported_pkgs(pkgs))
    >>> filtered.sort()
    >>> print(filtered)
    ['bar', 'foo']
    """
    return set(pkgs) - {"dotnet6.0", "dotnet7.0"}


# Packages in CentOS Stream that are built by clang
def get_tier1_pkgs(version: int) -> set[str]:
    base = dnf.Base()
    conf = base.conf
    for c in "AppStream", "BaseOS", "CRB":
        base.repos.add_new_repo(
            f"{c}-{version}-source",
            conf,
            baseurl=[
                f"https://mirror.stream.centos.org/{version}-stream/{c}/source/tree/"
            ],
        )
    repos = base.repos.get_matching("*")
    repos.disable()
    repos = base.repos.get_matching("*-source*")
    repos.enable()

    base.fill_sack()
    q = base.sack.query(flags=hawkey.IGNORE_MODULAR_EXCLUDES)
    q = q.available()
    q = q.filter(requires=["clang"])
    pkgs = [p.name for p in list(q)]
    return filter_unsupported_pkgs(filter_llvm_pkgs(set(pkgs)))


def get_tier2_pkgs(version: str = "rawhide") -> set[str]:
    base = dnf.Base()
    conf = base.conf

    if version == "rawhide":
        base.repos.add_new_repo(
            f"{version}-source",
            conf,
            baseurl=[
                f"https://download-ib01.fedoraproject.org/pub/fedora/linux/development/{version}/Everything/source/tree/"
            ],
        )
    else:
        base.repos.add_new_repo(
            f"{version}-source",
            conf,
            baseurl=[
                f"https://download-ib01.fedoraproject.org/pub/fedora/linux/releases/{version}/Everything/source/tree/"
            ],
        )
        base.repos.add_new_repo(
            f"{version}-updates-source",
            conf,
            baseurl=[
                f"https://download-ib01.fedoraproject.org/pub/fedora/linux/updates/{version}/Everything/source/tree/"
            ],
        )

    repos = base.repos.get_matching("*")
    repos.disable()
    repos = base.repos.get_matching("*-source*")
    repos.enable()

    base.fill_sack()
    q = base.sack.query(flags=hawkey.IGNORE_MODULAR_EXCLUDES)
    q = q.available()
    q = q.filter(requires=["clang"])
    pkgs = [p.name for p in list(q)]
    return filter_llvm_pkgs(set(pkgs))


# In order to remove the type: ignore[misc] check for this ticket: see https://github.com/Infinidat/munch/issues/84
class CoprBuild(Munch):  # type: ignore[misc]
    pass

    def is_in_progress(self) -> bool:
        return self.state not in [
            "succeeded",
            "forked",
            "skipped",
            "failed",
            "canceled",
        ]


# In order to remove the type: ignore[misc] check for this ticket: see https://github.com/Infinidat/munch/issues/84
class CoprPkg(Munch):  # type: ignore[misc]
    @classmethod
    def get_packages_from_copr(
        cls, project_owner: str, project_name: str, copr_client: copr.v3.Client
    ) -> list["CoprPkg"]:
        return [
            CoprPkg(p)
            for p in copr_client.package_proxy.get_list(
                project_owner,
                project_name,
                with_latest_succeeded_build=True,
                with_latest_build=True,
            )
        ]

    def get_build(self, name: str) -> CoprBuild | None:
        if "builds" not in self:
            return None
        if name not in self.builds:
            return None
        build = self.builds[name]
        if not build:
            return None
        return CoprBuild(build)

    def get_regression_info(
        self, project_owner: str, project_name: str
    ) -> dict[str, Any] | None:
        owner_url = project_owner
        if owner_url[0] == "@":
            owner_url = f"g/{owner_url[1:]}"
        latest = self.latest
        if latest is not None:
            return {
                "name": self.name,
                "fail_id": latest.id,
                "url": f"https://copr.fedorainfracloud.org/coprs/{owner_url}/{project_name}/build/{latest.id}/",
                "chroots": latest.chroots,
            }
        return None

    @property
    def latest(self) -> CoprBuild | None:
        return self.get_build("latest")

    @property
    def latest_succeeded(self) -> CoprBuild | None:
        return self.get_build("latest_succeeded")


def load_tests(
    loader: unittest.TestLoader, standard_tests: unittest.TestSuite, pattern: str
) -> unittest.TestSuite:
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    standard_tests.addTests(doctest.DocTestSuite())
    return standard_tests


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


def get_pkgs(exclusions: set[str]) -> set[str]:
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


def get_monthly_rebuild_packages(pkgs: set[str], copr_pkgs: list[CoprPkg]) -> set[str]:
    """Returns the list of packages that should be built in the next rebuild.
        It will select all the packages that built successfully during the last
        rebuild.

    Args:
        pkgs (set[str]): A list of every package that should be considered for
                        the rebuild.
        copr_pkgs (list[dist]): A list containing the latest build results from
                                the COPR project.

    Returns:
        set[str]: List of packages that should be rebuilt.

    Example:

    >>> a = {"name" : "a", "builds" : { "latest" : { "id" : 1 } , "latest_succeeded" : { "id" : 1 } } }
    >>> b = {"name" : "b", "builds" : { "latest" : { "id" : 1 } , "latest_succeeded" : None } }
    >>> c = {"name" : "c", "builds" : { "latest" : { "id" : 2 } , "latest_succeeded" : { "id" : 1 } } }
    >>> d = {"name" : "d", "builds" : { "latest" : { "id" : 2 } , "latest_succeeded" : { "id" : 2 } } }
    >>> pkgs = { "b", "c", "d"}
    >>> copr_pkgs = [CoprPkg(p) for p in [a, b, c, d]]
    >>> rebuild_pkgs = get_monthly_rebuild_packages(pkgs, copr_pkgs)
    >>> print(rebuild_pkgs)
    {'d'}
    """

    for p in copr_pkgs:
        if p.name not in pkgs:
            continue
        # Always build tier0 packges.
        if is_tier0_package(p.name):
            continue
        if not p.latest_succeeded:
            pkgs.discard(p.name)
            continue
        if p.latest is not None and p.latest.id != p.latest_succeeded.id:
            pkgs.discard(p.name)
    return pkgs


def get_monthly_rebuild_regressions(
    project_owner: str,
    project_name: str,
    start_time: datetime.datetime,
    copr_pkgs: list[CoprPkg],
) -> list[dict[str, Any] | None]:
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

    >>> a = {"name" : "a", "builds" : { "latest" : { "id" : 1, "state" : "running", "submitted_on" : 1731457321, "chroots" : [] } , "latest_succeeded" : None } }
    >>> b = {"name" : "b", "builds" : { "latest" : { "id" : 1, "state" : "succeeded", "submitted_on" : 1731457321, "chroots" : [] } , "latest_succeeded" : None } }
    >>> c = {"name" : "c", "builds" : { "latest" : { "id" : 1, "state" : "succeeded", "submitted_on" : 1731457321, "chroots" : [] } , "latest_succeeded" : { "id" : 1 } } }
    >>> d = {"name" : "d", "builds" : { "latest" : { "id" : 2, "state" : "canceled", "submitted_on" : 1731457321, "chroots" : [] } , "latest_succeeded" : { "id" : 1 } } }
    >>> e = {"name" : "e", "builds" : { "latest" : { "id" : 2, "state" : "failed", "submitted_on" : 1, "chroots" : [] } , "latest_succeeded" : { "id" : 1 } } }
    >>> f = {"name" : "f", "builds" : { "latest" : { "id" : 2, "state" : "failed", "submitted_on" : 1731457321, "chroots" : ["x86_64", "ppc64le", "s390x", "aarch64"] } , "latest_succeeded" : { "id" : 1 } } }
    >>> copr_pkgs= [CoprPkg(p) for p in [ a, b, c, d, e, f ]]
    >>> project_owner = "@fedora-llvm-team"
    >>> project_name = "fedora41-clang-20"
    >>> regressions = get_monthly_rebuild_regressions(project_owner, project_name, datetime.datetime.fromisoformat("2024-11-11"), copr_pkgs)
    >>> print(regressions)
    [{'name': 'f', 'fail_id': 2, 'url': 'https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/fedora41-clang-20/build/2/', 'chroots': ['x86_64', 'ppc64le', 's390x', 'aarch64']}]

    """
    pkgs = []
    for p in copr_pkgs:
        if not p.latest:
            continue

        # Don't report regressions if there are still builds in progress
        if p.latest.is_in_progress():
            continue

        if not p.latest_succeeded:
            if is_tier0_package(p.name):
                pkgs.append(p.get_regression_info(project_owner, project_name))
            continue
        if p.latest.id == p.latest_succeeded.id:
            continue
        # latest is a successful build, but this doesn't mean it failed.
        # It could be in progress.
        if p.latest.state != "failed":
            continue
        if int(p.latest.submitted_on) < start_time.timestamp():
            continue
        pkgs.append(p.get_regression_info(project_owner, project_name))
    return pkgs


def get_chroot_results(
    pkgs: list[dict[str, Any] | None], copr_client: copr.v3.Client
) -> None:
    for p in pkgs:
        if p is None:
            continue
        p["failed_chroots"] = []
        for c in p["chroots"]:
            result = copr_client.build_chroot_proxy.get(p["fail_id"], c)
            if result["state"] == "failed":
                p["failed_chroots"].append(c)


def build_pkg(
    project_owner: str,
    project_name: str,
    copr_client: copr.v3.Client,
    pkg: str,
    default_commitish: str,
    build_tag: str,
    koji_server: str = "https://koji.fedoraproject.org/kojihub",
    distgit: str = "fedora",
    chroots: list[str] | None = None,
) -> None:

    buildopts = {
        "background": True,
        "chroots": chroots,
        # Increase default timeout because some packages take longer than 5
        # hours.  This is easier to do globally tahn to maintain a list of
        # long building packages and I don't think there is any downside to
        # having a longer default timeout.
        "timeout": 90000,
    }
    koji_session = koji.ClientSession(koji_server)
    try:
        build = koji_session.getLatestBuilds(tag=build_tag, package=pkg)[0]
        build_info = koji_session.getBuild(build["build_id"])
        commitish = build_info["source"].split("#")[1]
    except:  # noqa: E722
        logging.warn(
            "Could not determine git commit for latest build of {p}.  Defaulting to {default_commitish}."
        )
        commitish = default_commitish

    copr_client.build_proxy.create_from_distgit(
        project_owner,
        project_name,
        pkg,
        commitish,
        buildopts=buildopts,
        distgit=distgit,
    )


def start_rebuild(
    project_owner: str,
    project_name: str,
    copr_client: copr.v3.Client,
    pkgs: set[str],
    snapshot_project_name: str,
    chroots: list[str],
) -> None:
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

    logging.info("Rebuilding", len(pkgs), "packages")
    rawhide_tag = get_rawhide_tag()
    for p in pkgs:
        build_pkg(
            project_owner,
            project_name,
            copr_client,
            p,
            default_commitish="rawhide",
            build_tag=rawhide_tag,
            chroots=chroots,
        )


def select_snapshot_project(
    copr_client: copr.v3.Client, target_chroots: list[str], max_lookback_days: int = 14
) -> str | None:
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
        except:  # noqa: E722
            continue
    logging.warning("FAIL")
    return None


def create_new_project(
    project_owner: str,
    project_name: str,
    copr_client: copr.v3.Client,
    target_chroots: list[str],
    additional_packages: list[str] | None = ["fedora-clang-default-cc"],
    with_opts: list[str] | None = ["toolchain_clang", "clang_lto"],
) -> None:
    copr_client.project_proxy.add(project_owner, project_name, chroots=target_chroots)
    for c in target_chroots:
        if c.startswith("centos-stream"):
            centos_version = c.split("-")[2]
            arch = c.split("-")[3]
            # Add centos stream buildroot, because not all packages in the
            # buildroot are shipped in the CRB.
            additional_repos = [
                f"https://kojihub.stream.centos.org/kojifiles/repos/c{centos_version}s-build/latest/{arch}/"
            ]
        copr_client.project_chroot_proxy.edit(
            project_owner,
            project_name,
            c,
            additional_packages=additional_packages,
            with_opts=with_opts,
            additional_repos=additional_repos,
        )


def extract_date_from_project(project_name: str) -> datetime.date:
    m = re.search("[0-9]+$", project_name)
    if not m:
        raise Exception(f"Invalid project name: {project_name}")
    return datetime.datetime.fromisoformat(m.group(0)).date()


def find_midpoint_project(
    copr_client: copr.v3.Client, good: str, bad: str, chroot: str
) -> str:
    good_date = extract_date_from_project(good)
    bad_date = extract_date_from_project(bad)
    days = (bad_date - good_date).days
    mid_date = good_date + datetime.timedelta(days=days / 2)
    increment = 0
    while mid_date != good_date and mid_date != bad_date:
        mid_project = re.sub("[0-9]+$", mid_date.strftime("%Y%m%d"), good)
        owner = mid_project.split("/")[0]
        project = mid_project.split("/")[1]
        try:
            for builds in copr_client.build_proxy.get_list(
                owner, project, "llvm", "succeeded"
            ):
                if chroot in builds["chroots"]:
                    return mid_project
        except:  # noqa: E722
            pass

        increment = increment * -1
        if increment < 0:
            increment -= 1
        else:
            increment += 1
        mid_date += datetime.timedelta(days=increment)

    return good


def pkg_is_ftbfs(ftbfs_data: list[dict[str, str]], pkg: str, tag: str) -> bool:

    for ftbfs_pkg in ftbfs_data:
        if ftbfs_pkg["name"] != pkg:
            continue
        if ftbfs_pkg["collection"] != tag:
            continue
        return ftbfs_pkg["state"] == "failing"
    return False


def main() -> None:
    logging.basicConfig(filename="rebuilder.log", level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        type=str,
        choices=[
            "rebuild",
            "get-regressions",
            "get-snapshot-date",
            "rebuild-in-progress",
            "bisect",
            "test",
        ],
    )
    parser.add_argument(
        "--start-date", type=str, help="Any ISO date format is accepted"
    )
    parser.add_argument("--chroot", type=str)
    parser.add_argument("--good", type=str)
    parser.add_argument("--bad", type=str)
    parser.add_argument("--llvm-major", type=int)
    parser.add_argument("--skip-same-version", action="store_true")

    args = parser.parse_args()
    copr_client = copr.v3.Client.create_from_config_file()

    os_name = "fedora-rawhide"
    target_arches = ["aarch64", "ppc64le", "s390x", "x86_64"]
    target_chroots = [f"{os_name}-{a}" for a in target_arches]
    project_owner = "@fedora-llvm-team"
    project_name = "clang-monthly-fedora-rebuild"

    if args.command == "rebuild":
        exclusions = get_exclusions()
        pkgs = get_pkgs(exclusions)
        print(pkgs)
        try:
            copr_client.project_proxy.get(project_owner, project_name)
            copr_pkgs = CoprPkg.get_packages_from_copr(
                project_owner, project_name, copr_client
            )
            pkgs = get_monthly_rebuild_packages(pkgs, copr_pkgs)
        except:  # noqa: E722
            create_new_project(project_owner, project_name, copr_client, target_chroots)
        snapshot_project = select_snapshot_project(copr_client, target_chroots)
        if snapshot_project is not None:
            start_rebuild(
                project_owner,
                project_name,
                copr_client,
                pkgs,
                snapshot_project,
                target_chroots,
            )
    elif args.command == "get-regressions":
        start_time = datetime.datetime.fromisoformat(args.start_date)
        copr_pkgs = CoprPkg.get_packages_from_copr(
            project_owner, project_name, copr_client
        )
        pkg_failures = get_monthly_rebuild_regressions(
            project_owner, project_name, start_time, copr_pkgs
        )
        get_chroot_results(list(pkg_failures), copr_client)
        # Delete attributes we don't need to print
        for p in pkg_failures:
            if p is None:
                continue
            for k in ["fail_id", "chroots"]:
                del p[k]

        print(json.dumps(pkg_failures))
    elif args.command == "get-snapshot-date":
        project = copr_client.project_proxy.get(project_owner, project_name)
        for repo in project["additional_repos"]:
            match = re.match(
                r"copr://@fedora-llvm-team/llvm-snapshots-big-merge-([0-9]+)$", repo
            )
            if match:
                print(datetime.datetime.fromisoformat(match.group(1)).isoformat())
                return
    elif args.command == "rebuild-in-progress":
        for pkg in copr_client.monitor_proxy.monitor(project_owner, project_name)[
            "packages"
        ]:
            for c in pkg["chroots"]:
                build = CoprBuild(pkg["chroots"][c])
                if build.is_in_progress():
                    sys.exit(0)
        sys.exit(1)
    elif args.command == "bisect":
        print(find_midpoint_project(copr_client, args.good, args.bad, args.chroot))
    elif args.command == "test":
        project_owner = "@fedora-llvm-team"
        project_name = "clang-fedora-centos-testing"
        centos_stream9_chroots = [f"centos-stream-9-{arch}" for arch in target_arches]
        centos_stream10_chroots = [f"centos-stream-10-{arch}" for arch in target_arches]
        fedora_chroots = [f"fedora-rawhide-{a}" for a in target_arches]
        target_chroots = (
            centos_stream10_chroots + centos_stream9_chroots + fedora_chroots
        )
        try:
            copr_client.project_proxy.get(project_owner, project_name)
        except Exception:
            create_new_project(
                project_owner,
                project_name,
                copr_client,
                target_chroots,
                additional_packages=None,
                with_opts=None,
            )
            # Set repo priority so that built packages that depend on a specific
            # LLVM snapshot version do not get installed.
            copr_client.project_proxy.edit(
                project_owner, project_name, repo_priority=1000
            )
        centos9_pkgs = get_tier1_pkgs(9)
        centos10_pkgs = get_tier1_pkgs(10)
        fedora_pkgs = get_tier2_pkgs()

        copr_client.project_proxy.edit(
            project_owner,
            project_name,
            additional_repos=[
                "copr://@fedora-llvm-team/llvm-compat-packages",
            ],
        )

        # Iterate over a copy of a list so we can remove items:
        for chroot in list(target_chroots):
            snapshot_project_name = select_snapshot_project(copr_client, [chroot])
            if not snapshot_project_name:
                print(f"Could not find snapshot for {chroot}")
                target_chroots.remove(chroot)
                continue
            else:
                print(f"Using {snapshot_project_name} for {chroot}")
            snapshot_url = f"copr://@fedora-llvm-team/{snapshot_project_name}"
            repos = []
            for r in copr_client.project_chroot_proxy.get(
                project_owner, project_name, chroot
            )["additional_repos"]:
                if args.skip_same_version and r == snapshot_url:
                    print(
                        f"Not building for {chroot} since snapshot version is the same as the last build"
                    )
                    target_chroots.remove(chroot)
                if not r.startswith(
                    "copr://@fedora-llvm-team/llvm-snapshots-big-merge"
                ):
                    repos.append(r)
            if chroot not in target_chroots:
                continue

            copr_client.project_chroot_proxy.edit(
                project_owner,
                project_name,
                chroot,
                additional_repos=repos + [snapshot_url],
            )

        centos_stream9_chroots = [
            c for c in centos_stream9_chroots if c in target_chroots
        ]
        for pkg in centos9_pkgs:
            build_pkg(
                project_owner=project_owner,
                project_name=project_name,
                copr_client=copr_client,
                pkg=pkg,
                koji_server="https://kojihub.stream.centos.org/kojihub",
                default_commitish="c9s",
                build_tag="c9s-candidate",
                distgit="centos-stream",
                chroots=centos_stream9_chroots,
            )

        centos_stream10_chroots = [
            c for c in centos_stream10_chroots if c in target_chroots
        ]
        for pkg in centos10_pkgs:
            build_pkg(
                project_owner=project_owner,
                project_name=project_name,
                copr_client=copr_client,
                pkg=pkg,
                koji_server="https://kojihub.stream.centos.org/kojihub",
                default_commitish="c10s",
                build_tag="c10s-candidate",
                distgit="centos-stream",
                chroots=centos_stream10_chroots,
            )

        fedora_chroots = [c for c in fedora_chroots if c in target_chroots]

        # Load FTBFS data so we can skip building packages that currently don't build.
        request = urllib.request.Request(
            "https://koschei.fedoraproject.org/api/v1/packages"
        )
        # We need to set these headers due to new anti-spam measures in Fedora infrastructure.
        request.add_header("Accept", "text/plain")
        request.add_header("User-Agent", "fedora-llvm-team/1.0")
        with urllib.request.urlopen(request) as url:
            ftbfs_data = json.loads(url.read().decode())

        rawhide_tag = get_rawhide_tag()
        for pkg in fedora_pkgs:
            if pkg_is_ftbfs(ftbfs_data, pkg, tag=rawhide_tag):
                print(f"Skip building {pkg} on rawhide, because it is FTBFS")
                continue
            print(f"Building {pkg}")
            build_pkg(
                project_owner=project_owner,
                project_name=project_name,
                copr_client=copr_client,
                pkg=pkg,
                default_commitish="rawhide",
                build_tag=rawhide_tag,
                chroots=fedora_chroots,
            )


if __name__ == "__main__":
    main()
