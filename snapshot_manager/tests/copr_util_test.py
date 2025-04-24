"""Tests for copr_client"""

import os
import uuid
from typing import Any
from unittest import mock

import munch
import pytest
import tests.base_test as base_test

import snapshot_manager.copr_util as copr_util
from snapshot_manager.build_status import BuildState, CoprBuildStatus


@mock.patch("copr.v3.Client")
def test_make_client__from_env(client_mock: mock.Mock) -> None:
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
def test_make_client__from_file(client_mock: mock.Mock) -> None:
    # Missing a few parameters, so defaulting back to creation from file
    myconfig = {"COPR_URL": "myurl"}
    with mock.patch.dict(os.environ, values=myconfig, clear=True):
        copr_util.make_client()
    client_mock.create_from_config_file.assert_called_once()


@mock.patch("copr.v3.Client")
def test_get_all_chroots(client_mock: mock.Mock) -> None:
    # When calling the function under test multiple times,
    # ensure the internal get_list function is only called
    # once. This is because the result it has to be cached.
    # by functools.cache.
    copr_util.get_all_chroots(client=client_mock)
    copr_util.get_all_chroots(client=client_mock)
    copr_util.get_all_chroots(client=client_mock)
    client_mock.mock_chroot_proxy.get_list.assert_called_once()


@mock.patch("copr.v3.Client")
def test_get_all_builds(client_mock: mock.Mock) -> None:
    copr_util.get_all_builds(client=client_mock, ownername="foo", projectname="bar")
    client_mock.build_proxy.get_list.assert_called_once_with(
        ownername="foo", projectname="bar"
    )


@mock.patch("copr.v3.helpers.wait")
@mock.patch("snapshot_manager.copr_util.get_all_builds")
@mock.patch("copr.v3.Client")
def test_delete_project(
    client_mock: mock.Mock, get_all_builds_mock: mock.Mock, wait_mock: mock.Mock
) -> None:
    # Prepare a set of builds, some "active" and some not.
    build1 = munch.Munch(id=1, build_id=1, state=CoprBuildStatus.RUNNING)
    build2 = munch.Munch(id=2, build_id=2, state=CoprBuildStatus.FAILED)
    build3 = munch.Munch(id=3, build_id=3, state=CoprBuildStatus.PENDING)
    get_all_builds_mock.return_value = [build1, build2, build3]

    # The actual test call
    copr_util.delete_project(client=client_mock, ownername="foo", projectname="bar")

    # Assert that the active builds have been called
    get_all_builds_mock.assert_called_once_with(
        client=client_mock, ownername="foo", projectname="bar"
    )

    # Assert that build1 and build3 have been cancelled but not build2
    assert client_mock.build_proxy.cancel.call_count == 2
    cancel_call_list = client_mock.build_proxy.cancel.call_args_list
    cancelled_build_ids = [call.kwargs["build_id"] for call in cancel_call_list]
    assert build1["build_id"] in cancelled_build_ids
    assert build2["build_id"] not in cancelled_build_ids
    assert build3["build_id"] in cancelled_build_ids

    # Assert that we waited on build1 and build3 but not on build2
    waited_on_builds = wait_mock.call_args.kwargs["waitable"]
    assert build1 in waited_on_builds
    assert build2 not in waited_on_builds
    assert build3 in waited_on_builds

    # Assert that we finally deleted the project
    client_mock.project_proxy.delete.assert_called_once_with(
        ownername="foo", projectname="bar"
    )


@mock.patch("copr.v3.Client")
def test_get_all_build_states(client_mock: mock.Mock) -> None:
    # given
    ownername = "@fedora-llvm-team"
    projectname = "llvm-snapshots-big-merge-20250217"
    chroot1: dict[str, Any] = {
        "build_id": int(8662297),
        "state": "succeeded",
        "url_build_log": "https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/llvm-snapshots-big-merge-20250217/rhel-9-x86_64/08662297-llvm/builder-live.log.gz",
    }
    chroot2: dict[str, Any] = {
        "build_id": int(8662296),
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
            url_build_log=str(chroot1["url_build_log"]),
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


def load_tests(loader, tests, ignore):  # type: ignore[no-untyped-def]
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
