""" Tests for copr_client """

import os
import uuid
from unittest import mock

import tests.base_test as base_test

import snapshot_manager.config as config
import snapshot_manager.copr_util as copr_util


@mock.patch("copr.v3.Client")
def test_make_client__from_env(client_mock: mock.Mock):
    myconfig = {
        "COPR_URL": "myurl",
        "COPR_LOGIN": "mylogin",
        "COPR_TOKEN": "mytoken",
        "COPR_USERNAME": "myusername",
    }
    with mock.patch.dict(os.environ, values=myconfig, clear=True):
        copr_util.make_client()

    config = {
        "copr_url": myconfig["COPR_URL"],
        "login": myconfig["COPR_LOGIN"],
        "token": myconfig["COPR_TOKEN"],
        "username": myconfig["COPR_USERNAME"],
    }
    client_mock.assert_called_once_with(config)


@mock.patch("copr.v3.Client")
def test_make_client__from_file(client_mock: mock.Mock):
    # Missing a few parameters, so defaulting back to creation from file
    myconfig = {"COPR_URL": "myurl"}
    with mock.patch.dict(os.environ, values=myconfig, clear=True):
        copr_util.make_client()
    client_mock.create_from_config_file.assert_called_once()


@mock.patch("copr.v3.Client")
def test_get_all_chroots(client_mock: mock.Mock):
    # When calling the function under test multiple times,
    # ensure the internal get_list function is only called
    # once. This is because the result it has to be cached.
    # by functools.cache.
    copr_util.get_all_chroots(client=client_mock)
    copr_util.get_all_chroots(client=client_mock)
    copr_util.get_all_chroots(client=client_mock)
    client_mock.mock_chroot_proxy.get_list.assert_called_once()


class TestCopr(base_test.TestBase):
    def test_project_exists(self):
        """Test if copr project exists."""
        self.assertTrue(
            copr_util.CoprClient().project_exists(
                copr_ownername="@fedora-llvm-team", copr_projectname="llvm-snapshots"
            )
        )

        rand = str(uuid.uuid4())
        self.assertFalse(
            copr_util.CoprClient().project_exists(
                copr_ownername=rand, copr_projectname=rand
            )
        )

    def test_copr_chroots(self):
        """Ensure all chroots match the default chroot pattern."""
        chroots = copr_util.CoprClient().get_copr_chroots()
        for chroot in chroots:
            self.assertRegex(chroot, config.Config().chroot_pattern)

    def test_is_package_supported_by_chroot(self):
        """Test if package is supported by chroot"""
        self.assertTrue(
            copr_util.CoprClient.is_package_supported_by_chroot(
                package="lld", chroot="fedora-rawhide-x86_64"
            )
        )
        self.assertTrue(
            copr_util.CoprClient.is_package_supported_by_chroot(
                package="llvm", chroot="fedora-rawhide-x86_64"
            )
        )


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.copr_util

    tests.addTests(doctest.DocTestSuite(snapshot_manager.copr_util))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
