"""
copr_util
"""

import functools
import logging
import os
import re

import copr.v3
import munch
from copr.v3.helpers import wait

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config
import snapshot_manager.util as util


def make_client() -> "copr.v3.Client":
    """
    Instatiates a copr client.

    If the environment contains COPR_URL, COPR_LOGIN, COPR_TOKEN, and
    COPR_USERNAME, we'll try to create a Copr client from those environment
    variables; otherwise, A Copr API client is created from the config file
    in ~/.config/copr. See https://copr.fedorainfracloud.org/api/ for how to
    create such a file.
    """
    client = None
    if {"COPR_URL", "COPR_LOGIN", "COPR_TOKEN", "COPR_USERNAME"} <= set(os.environ):
        logging.debug("create copr client config from environment variables")
        config = {
            "copr_url": os.environ["COPR_URL"],
            "login": os.environ["COPR_LOGIN"],
            "token": os.environ["COPR_TOKEN"],
            "username": os.environ["COPR_USERNAME"],
        }
        client = copr.v3.Client(config)
    else:
        logging.debug("create copr client config from file")
        client = copr.v3.Client.create_from_config_file()
    return client


@functools.cache
def get_all_chroots(client: copr.v3.Client) -> list[str]:
    """Asks Copr to list all currently supported chroots. The response Copr will
    give varies over time whenever a new Fedora or RHEL version for example
    is released. But for our purposes, we let the function cache the results.

    Args:
        client (copr.v3.Client): Copr client to use

    Returns:
        list[str]: All currently supported chroots on copr.
    """
    return client.mock_chroot_proxy.get_list().keys()


def project_exists(
    client: copr.v3.Client,
    ownername: str,
    projectname: str,
) -> bool:
    """Returns True if the given copr project exists; otherwise False.

    Args:
        client (copr.v3.Client): Copr client to use
        ownername (str): Copr owner name
        projectname (str): Copr project name

    Returns:
        bool: True if the project exists in copr; otherwise False.
    """
    try:
        client.project_proxy.get(ownername=ownername, projectname=projectname)
    except copr.v3.CoprNoResultException:
        return False
    return True


def get_all_builds(
    client: copr.v3.Client,
    ownername: str,
    projectname: str,
) -> list[munch.Munch]:
    return client.build_proxy.get_list(ownername=ownername, projectname=projectname)


def filter_builds_by_state(
    builds: list[munch.Munch],
    state_pattern: str,
) -> list[munch.Munch]:
    """Returns copr builds for the given owner/project where the state matches the given pattern.

    Args:
        builds (list[munch.Munch]): A list of builds. See `get_all_builds` to get all builds for a given owner/project
        state_pattern (str): Regular expression to select what states of a copr build are considered active. (e.g. `r"(running|waiting|pending|importing|starting)"`)

    Returns:
        list[munch.Munch]: A list of filtered builds

    >>> from snapshot_manager.build_status import CoprBuildStatus
    >>> b1 = munch.Munch(package_name="llvm", chroot = "rhel-9-ppc64le", state = CoprBuildStatus.RUNNING)
    >>> b2 = munch.Munch(package_name="llvm", chroot = "centos-stream-10-ppc64le", state = CoprBuildStatus.STARTING)
    >>> b3 = munch.Munch(package_name="llvm", chroot = "fedora-rawhide-x86_64", state = CoprBuildStatus.FAILED)
    >>> res = filter_builds_by_state(builds=[b1,b2,b3], state_pattern=r"(running|waiting|pending|importing|starting)")
    >>> res == [b1,b2]
    True
    """
    return [
        build for build in builds if re.match(pattern=state_pattern, string=build.state)
    ]


def delete_project(client: copr.v3.Client, ownername: str, projectname: str):
    """Cancels all active builds in the given project, waits for them to truely finish and then deletes the project.

    Args:
        client (copr.v3.Client): The copr client to use
        ownername (str): The copr ownername or groupname
        projectname (str): The copr project name
    """
    all_builds = get_all_builds(
        client=client, ownername=ownername, projectname=projectname
    )
    active_builds = filter_builds_by_state(
        builds=all_builds, state_pattern=r"(running|waiting|pending|importing|starting)"
    )

    for build in active_builds:
        logging.info(f"Cancelling build with ID {build['build_id']}")
        client.build_proxy.cancel(build_id=build["build_id"])

    logging.info(f"Waiting for cancelled builds to finish")
    wait(waitable=active_builds, timeout=0)

    logging.info(f"Deleting project {ownername}/{projectname}")
    client.project_proxy.delete(ownername=ownername, projectname=projectname)


def get_all_build_states(
    client: copr.v3.Client,
    ownername: str,
    projectname: str,
) -> build_status.BuildStateList:
    """Queries all builds for the given project/owner and returns them as build statuses in a list.

    Args:
        client (copr.v3.Client): Copr client to use
        ownername (str): Copr projectname
        projectname (str): Copr ownername

    Returns:
        build_status.BuildStateList: The list of all build states for the given owner/project in copr.
    """
    states = build_status.BuildStateList()

    monitor = client.monitor_proxy.monitor(
        ownername=ownername,
        projectname=projectname,
        additional_fields=["url_build_log", "url_build"],
    )

    for package in monitor["packages"]:
        for chroot_name in package["chroots"]:
            chroot = package["chroots"][chroot_name]
            state = build_status.BuildState(
                build_id=chroot["build_id"],
                package_name=package["name"],
                chroot=chroot_name,
                url_build_log=chroot["url_build_log"],
                copr_build_state=chroot["state"],
                copr_ownername=ownername,
                copr_projectname=projectname,
            )
            if "url_build" in chroot:
                state.url_build = chroot["url_build"]

            states.append(state)
    return states


def has_all_good_builds(
    required_packages: list[str],
    required_chroots: list[str],
    states: build_status.BuildStateList,
) -> bool:
    """Check for all required combinations of successful package+chroot build states.

    Args:
        required_packages (list[str]): List of required package names.
        required_chroots (list[str]): List of required chroot names.
        states (BuildStateList): List of states to use.

    Returns:
        bool: True if all required combinations of package+chroot are in a successful state in the given `states` list.

    Example: Check with a not existing copr project

    >>> from snapshot_manager.build_status import BuildState, CoprBuildStatus
    >>> required_packages=["llvm"]
    >>> required_chroots=["fedora-rawhide-x86_64", "rhel-9-ppc64le"]
    >>> s1 = BuildState(package_name="llvm", chroot="rhel-9-ppc64le", copr_build_state=CoprBuildStatus.FORKED)
    >>> s2 = BuildState(package_name="llvm", chroot="fedora-rawhide-x86_64", copr_build_state=CoprBuildStatus.FAILED)
    >>> s3 = BuildState(package_name="llvm", chroot="fedora-rawhide-x86_64", copr_build_state=CoprBuildStatus.SUCCEEDED)
    >>> has_all_good_builds(required_packages=required_packages, required_chroots=required_chroots, states=[s1])
    False
    >>> has_all_good_builds(required_packages=required_packages, required_chroots=required_chroots, states=[s1,s2])
    False
    >>> has_all_good_builds(required_packages=required_packages, required_chroots=required_chroots, states=[s1,s2,s3])
    True
    """
    # Lists of (package,chroot) tuples
    expected: list[tuple[str, str]] = []
    actual_set: set[tuple[str, str]] = {
        (state.package_name, state.chroot) for state in states if state.success
    }

    for package in required_packages:
        for chroot in required_chroots:
            expected.append((package, chroot))

    expected_set = set(expected)

    if not expected_set.issubset(actual_set):
        diff = expected_set.difference(actual_set)
        logging.error(f"These packages were not found or weren't successfull: {diff}")
        return False
    return True
