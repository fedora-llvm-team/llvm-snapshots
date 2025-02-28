"""
copr_util
"""

import functools
import logging
import os
import re

import copr.v3
import munch

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
        client (copr.v3.Client): A Copr client

    Returns:
        list[str]: All currently supported chroots on copr.
    """
    return client.mock_chroot_proxy.get_list().keys()


# pylint: disable=too-few-public-methods
class CoprClient:
    def __init__(
        self, config: config.Config = config.Config(), client: "CoprClient" = None
    ):
        """
        Keyword Arguments:
            client (Client): Copr client to use.
        """
        self.__client = None
        if client is not None:
            self.__client = client.__client

        self.config = config

    @property
    def copr(self) -> "copr.v3.Client":
        """
        Property for getting the copr client.
        Upon first call of this function, the client is instantiated.
        """
        if not self.__client:
            self.__client = make_client()
        return self.__client

    def project_exists(
        self,
        copr_ownername: str,
        copr_projectname: str,
    ) -> bool:
        """Returns True if the given copr project exists; otherwise False.

        Args:
            copr_ownername (str): Copr owner name
            copr_projectname (str): Copr project name

        Returns:
            bool: True if the project exists in copr; otherwise False.
        """
        try:
            self.copr.project_proxy.get(
                ownername=copr_ownername, projectname=copr_projectname
            )
        except copr.v3.CoprNoResultException:
            return False
        return True

    def get_active_builds(
        self,
        copr_ownername: str,
        copr_projectname: str,
        state_pattern: str | None = None,
    ) -> list[munch.Munch]:
        """Returns copr builds for the given owner/project where the state matches the given pattern.

        If no state pattern is provided, the `SnapshotManager.default_active_build_state_pattern` will be used.

        Args:
            copr_ownername (str): Copr ownername
            copr_projectname (str): Copr project name
            state_pattern (str|None, optional): Regular expression matching. Defaults to None.

        Returns:
            list[munch.Munch]: A list of filtered builds
        """
        if state_pattern is None:
            state_pattern = self.config.active_build_state_pattern
        builds = self.copr.build_proxy.get_list(
            ownername=copr_ownername, projectname=copr_projectname
        )

        return [
            build
            for build in builds
            if re.match(pattern=state_pattern, string=build.state)
        ]

    def get_active_copr_build_ids(
        self,
        copr_ownername: str,
        copr_projectname: str,
        state_pattern: str | None = None,
    ) -> list[int]:
        return [
            build.id
            for build in self.get_active_builds(
                copr_ownername=copr_ownername,
                copr_projectname=copr_projectname,
                state_pattern=state_pattern,
            )
        ]

    def get_copr_chroots(self, pattern: str | None = None) -> list[str]:
        """Return sorted list of chroots we care about

        If no pattern is supplied the config variable `chroot_pattern` will be used.

        Args:
            pattern (str|None, optional): Regular expression to filter chroot names by. Defaults to None.

        Returns:
            list[str]: List of filtered and sorted chroots
        """
        all_chroots = get_all_chroots(client=self.copr)

        if pattern is None:
            pattern = self.config.chroot_pattern

        return util.filter_chroots(chroots=all_chroots, pattern=pattern)

    def has_all_good_builds(
        self,
        copr_ownername: str,
        copr_projectname: str,
        required_packages: list[str],
        required_chroots: list[str],
        states: build_status.BuildStateList | None = None,
    ) -> bool:
        """Returns True if the given packages have been built in all chroots in the copr project; otherwise False is returned.

        Args:
            copr_ownername (str): Copr owner name
            copr_projectname (str): Copr project name
            required_packages (list[str]): List of required package names.
            required_chroots (list[str]): List of required chroot names.
            states (BuildStateList | None): List of states to use if already gathered before. If None, we will get the states for you.

        Returns:
            bool: True if the given copr project has successful/forked builds for all the required projects and chroots that we care about.

        Example: Check with a not existing copr project

        >>> CoprClient().has_all_good_builds(copr_ownername="non-existing-owner", copr_projectname="non-existing-project", required_packages=[], required_chroots=[])
        False
        """
        logging.info(
            f"Checking for all good builds in {copr_ownername}/{copr_projectname}..."
        )

        if not self.project_exists(
            copr_ownername=copr_ownername, copr_projectname=copr_projectname
        ):
            logging.warning(
                f"copr project {copr_ownername}/{copr_projectname} does not exist"
            )
            return False

        if states is None:
            states = self.get_build_states_from_copr_monitor(
                copr_ownername=copr_ownername, copr_projectname=copr_projectname
            )

        # Lists of (package,chroot) tuples
        expected: list[tuple[str, str]] = []
        actual_set: set[tuple[str, str]] = {
            (state.package_name, state.chroot) for state in states if state.success
        }

        for package in required_packages:
            for chroot in required_chroots:
                if self.is_package_supported_by_chroot(package, chroot):
                    expected.append((package, chroot))

        expected_set = set(expected)

        if not expected_set.issubset(actual_set):
            diff = expected_set.difference(actual_set)
            logging.error(
                f"These packages were not found or weren't successfull: {diff}"
            )
            return False
        return True

    @classmethod
    def is_package_supported_by_chroot(cls, package: str, chroot: str) -> bool:
        """Returns true if given package is supported by given chroot

        Args:
            package (str): A package name (e.g. "llvm", or "clang")
            chroot (str): A chroot name (e.g. "fedora-rawhide-x86_64")

        Returns:
            bool: True if package is supported by chroot; otherwise False
        """
        return True

    def get_build_states_from_copr_monitor(
        self,
        copr_ownername: str,
        copr_projectname: str,
    ) -> build_status.BuildStateList:
        states = build_status.BuildStateList()

        try:
            monitor = self.copr.monitor_proxy.monitor(
                ownername=copr_ownername,
                projectname=copr_projectname,
                additional_fields=["url_build_log", "url_build"],
            )
        except copr.v3.exceptions.CoprNoResultException:
            logging.info(
                f"Couldn't find copr project: {copr_ownername}/{copr_projectname}"
            )
            return states

        for package in monitor["packages"]:
            for chroot_name in package["chroots"]:
                chroot = package["chroots"][chroot_name]
                state = build_status.BuildState(
                    build_id=chroot["build_id"],
                    package_name=package["name"],
                    chroot=chroot_name,
                    url_build_log=chroot["url_build_log"],
                    copr_build_state=chroot["state"],
                    copr_ownername=copr_ownername,
                    copr_projectname=copr_projectname,
                )
                if "url_build" in chroot:
                    state.url_build = chroot["url_build"]

                states.append(state)
        return states
