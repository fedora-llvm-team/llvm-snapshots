"""
isort:skip_file
"""

import datetime
import unittest
import difflib
import filecmp
from unittest import mock

import pytest
import pathlib
import tests.base_test as base_test

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config


class TestSnapshotManager(base_test.TestBase):
    def test_check_todays_builds(self) -> None:
        # cfg = self.config
        # cfg.copr_ownername = "@fedora-llvm-team"
        # cfg.copr_project_tpl = "llvm-snapshots-incubator-20240405"
        # cfg.datetime = datetime.date(year=2024, month=4, day=5)
        # cfg.strategy = "standalone"
        # cfg.maintainer_handle = "kwk"
        # cfg.creator_handle = "kwk"
        # cfg.github_repo = "fedora-llvm-team/llvm-snapshots-test"
        # mgr = snapshot_manager.SnapshotManager(config=cfg)
        # mgr.check_todays_builds()
        pass


@pytest.fixture  # type: ignore[untyped-decorator]
def config_fxt_a() -> config.Config:
    """Returns a configuration object for strategy A that has an overlap of chroots with the one returned by config_fxt_b."""
    return config.Config(
        datetime=datetime.datetime(year=2025, month=4, day=2),
        build_strategy="strategy A",
        copr_project_tpl="foo/strategy-A-YYYYMMDD",
        chroots=["fedora-rawhide-x86_64", "rhel-9-ppc64le", "fedora-42-aarch64"],
        maintainer_handle="maintainerA",
    )


@pytest.fixture  # type: ignore[untyped-decorator]
def config_fxt_b() -> config.Config:
    """Returns a configuration object for strategy A that has an overlap of chroots with the one returned by config_fxt_a."""
    return config.Config(
        datetime=datetime.datetime(year=2025, month=4, day=2),
        build_strategy="strategy B",
        copr_project_tpl="foo/strategy-B-YYYYMMDD",
        chroots=[
            "rhel-9-x86_64",
            "fedora-rawhide-x86_64",
            "fedora-42-aarch64",
            "rhel-9-ppc64le",
        ],
        maintainer_handle="maintainerB",
    )


def get_build_states(
    cfg: config.Config, copr_build_state: build_status.CoprBuildStatus
) -> build_status.BuildStateList:
    return [
        build_status.BuildState(
            chroot=chroot,
            copr_ownername=cfg.copr_ownername,
            copr_projectname=cfg.copr_projectname,
            copr_build_state=copr_build_state,
        )
        for chroot in cfg.chroots
    ]


def assert_files_match(actual: pathlib.Path, expected: pathlib.Path) -> None:
    """Fails the current test with a unified diff if both files differ."""
    if not filecmp.cmp(actual, expected):
        diff = difflib.unified_diff(
            a=actual.read_text().splitlines(),
            b=expected.read_text().splitlines(),
            fromfile=str(actual),
            tofile=str(expected),
        )
        pytest.fail(f"Files don't match: \n{'\n'.join(list(diff))}")


def log_contains(log_mock: mock.Mock, needle: str) -> bool:
    for call in log_mock.call_args_list:
        if str(call).find(needle) != -1:
            return True
    return False


def load_tests(
    loader: unittest.TestLoader, standard_tests: unittest.TestSuite, pattern: str
) -> unittest.TestSuite:
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.snapshot_manager

    standard_tests.addTests(doctest.DocTestSuite(snapshot_manager.snapshot_manager))
    return standard_tests


if __name__ == "__main__":
    base_test.run_tests()
