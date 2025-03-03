""" Tests for copr_client """

import os
import uuid
from unittest import mock

import munch
import pytest
import tests.base_test as base_test

import snapshot_manager.copr_util as copr_util
from snapshot_manager.build_status import BuildState


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


@pytest.mark.parametrize(
    "owner, project, expected",
    [
        ("@fedora-llvm-team", "llvm-snapshots", True),
        (str(uuid.uuid4()), str(uuid.uuid4()), False),
    ],
)
def test_project_exists(owner: str, project: str, expected: bool):
    """Test if copr project exists."""
    client = copr_util.make_client()
    actual = copr_util.project_exists(
        client=client, ownername=owner, projectname=project
    )
    assert actual == expected


@mock.patch("copr.v3.Client")
def test_get_all_builds(client_mock: mock.Mock):
    copr_util.get_all_builds(client=client_mock, ownername="foo", projectname="bar")
    client_mock.build_proxy.get_list.assert_called_once_with(
        ownername="foo", projectname="bar"
    )


@mock.patch("copr.v3.Client")
def test_get_all_build_states(client_mock: mock.Mock):
    # given
    ownername = "@fedora-llvm-team"
    projectname = "llvm-snapshots-big-merge-20250217"
    chroot1 = {
        "build_id": 8662297,
        "state": "succeeded",
        "url_build_log": "https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/llvm-snapshots-big-merge-20250217/rhel-9-x86_64/08662297-llvm/builder-live.log.gz",
    }
    chroot2 = {
        "build_id": 8662296,
        "state": "running",
        "url_build_log": "https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/llvm-snapshots-big-merge-20250217/rhel-9-s390x/08662296-llvm/builder-live.log",
        "url_build": "https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-big-merge-20250217/build/8662296/",
    }
    client_mock.monitor_proxy.monitor.return_value = munch.munchify(
        {
            "output": "ok",
            "message": "Project monitor request successful",
            "packages": [
                {
                    "name": "llvm",
                    "chroots": {
                        "rhel-9-x86_64": chroot1,
                        "rhel-9-s390x": chroot2,
                    },
                }
            ],
        }
    )
    # when
    actual = copr_util.get_all_build_states(
        client=client_mock, ownername=ownername, projectname=projectname
    )
    # then
    client_mock.monitor_proxy.monitor.assert_called_once_with(
        ownername=ownername,
        projectname=projectname,
        additional_fields=["url_build_log", "url_build"],
    )
    expected = [
        BuildState(
            err_cause=None,
            package_name="llvm",
            chroot="rhel-9-x86_64",
            url_build_log=chroot1["url_build_log"],
            url_build="",
            build_id=chroot1["build_id"],
            copr_build_state=chroot1["state"],
            err_ctx="",
            copr_ownername=ownername,
            copr_projectname=projectname,
        ),
        BuildState(
            err_cause=None,
            package_name="llvm",
            chroot="rhel-9-s390x",
            url_build_log=chroot2["url_build_log"],
            url_build=chroot2["url_build"],
            build_id=chroot2["build_id"],
            copr_build_state=chroot2["state"],
            err_ctx="",
            copr_ownername=ownername,
            copr_projectname=projectname,
        ),
    ]

    assert actual == expected


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
