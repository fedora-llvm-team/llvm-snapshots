"""
isort:skip_file
"""

import datetime
import uuid
import difflib
import filecmp
import sys
from unittest import mock

import pytest
import pathlib
import testing_farm as tf
import tests.base_test as base_test
import testing_farm.tfutil as tfutil

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config
import snapshot_manager.github_util as github_util
import snapshot_manager.snapshot_manager as snapshot_manager
from snapshot_manager.snapshot_manager import (
    collect_performance_comparison_results,
    run_performance_comparison,
)


class TestSnapshotManager(base_test.TestBase):
    def test_check_todays_builds(self):
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


@pytest.fixture
def config_fxt_a() -> config.Config:
    """Returns a configuration object for strategy A that has an overlap of chroots with the one returned by config_fxt_b."""
    return config.Config(
        datetime=datetime.datetime(year=2025, month=4, day=2),
        build_strategy="strategy A",
        copr_project_tpl="foo/strategy-A-YYYYMMDD",
        chroots=["fedora-rawhide-x86_64", "rhel-9-ppc64le", "fedora-42-aarch64"],
        maintainer_handle="maintainerA",
    )


@pytest.fixture
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


@mock.patch("snapshot_manager.snapshot_manager.get_performance_github_issue")
@mock.patch("github.Github")
@mock.patch("copr.v3.Client")
def test_run_performance_comparison__no_chroot_overlap_in_strategies(
    copr_client_mock: mock.Mock,
    github_client_mock: mock.Mock,
    get_performance_github_issue_mock: mock.Mock,
    config_fxt_a,
    config_fxt_b,
):
    get_performance_github_issue_mock.return_value = None

    config_fxt_a.chroots = ["fedora-rawhide-x86_64"]
    config_fxt_b.chroots = ["rhel-9-x86_64"]

    assert not run_performance_comparison(
        conf_a=config_fxt_a,
        conf_b=config_fxt_b,
        github_repo="foo/bar",
        copr_client=copr_client_mock,
        github_client=github_client_mock,
    )


def get_build_states(
    cfg: config.Config, copr_build_state: build_status.CoprBuildStatus
) -> list[build_status.BuildStateList]:
    return [
        build_status.BuildState(
            chroot=chroot,
            copr_ownername=cfg.copr_ownername,
            copr_projectname=cfg.copr_projectname,
            copr_build_state=copr_build_state,
        )
        for chroot in cfg.chroots
    ]


@mock.patch("logging.Logger.info")
@mock.patch("snapshot_manager.snapshot_manager.get_performance_github_issue")
@mock.patch("testing_farm.make_compare_compile_time_request")
@mock.patch("github.Github")
@mock.patch("copr.v3.Client")
@mock.patch("snapshot_manager.snapshot_manager.copr_util")
def test_run_performance_comparison__overlap_but_no_successful_match(
    copr_util_mock: mock.Mock,
    copr_client_mock: mock.Mock,
    github_client_mock: mock.Mock,
    make_compare_compile_time_request_mock: mock.Mock,
    get_performance_github_issue_mock: mock.Mock,
    info_log_mock: mock.Mock,
    config_fxt_a,
    config_fxt_b,
):
    states_a = get_build_states(config_fxt_a, build_status.CoprBuildStatus.FAILED)
    states_b = get_build_states(config_fxt_b, build_status.CoprBuildStatus.SUCCEEDED)
    copr_util_mock.get_all_build_states.side_effect = [states_a, states_b]

    # Pretend there's no performance issue yet
    get_performance_github_issue_mock.return_value = None

    github_repo_name = "foo/bar"
    assert not run_performance_comparison(
        conf_a=config_fxt_a,
        conf_b=config_fxt_b,
        github_repo=github_repo_name,
        copr_client=copr_client_mock,
        github_client=github_client_mock,
    )

    assert log_contains(info_log_mock, "No performance requests were made")

    make_compare_compile_time_request_mock.assert_not_called()


@mock.patch("testing_farm.make_compare_compile_time_request")
@mock.patch("github.Github")
@mock.patch("copr.v3.Client")
@mock.patch("snapshot_manager.snapshot_manager.copr_util")
def test_run_performance_comparison__full(
    copr_util_mock: mock.Mock,
    copr_client_mock: mock.Mock,
    github_client_mock: mock.Mock,
    make_compare_compile_time_request_mock: mock.Mock,
    config_fxt_a,
    config_fxt_b,
):
    # Simulate successful COPR builds
    states_a = get_build_states(config_fxt_a, build_status.CoprBuildStatus.SUCCEEDED)
    states_b = get_build_states(config_fxt_b, build_status.CoprBuildStatus.SUCCEEDED)
    copr_util_mock.get_all_build_states.side_effect = [states_a, states_b]

    # Prepare return values of the make_compare_compile_time_request() calls.
    req1 = tf.Request(
        request_id=uuid.uuid4(),
        chroot=config_fxt_a.chroots[0],
        copr_build_ids=[1, 2, 3],
        test_plan_name="mytestplan",
    )
    req2 = tf.Request(
        request_id=uuid.uuid4(),
        chroot=config_fxt_a.chroots[1],
        copr_build_ids=[4, 5, 6],
        test_plan_name="mytestplan",
    )
    req3 = tf.Request(
        request_id=uuid.uuid4(),
        chroot=config_fxt_a.chroots[2],
        copr_build_ids=[7, 8, 9],
        test_plan_name="mytestplan",
    )
    make_compare_compile_time_request_mock.side_effect = [
        req1,
        req2,
        req3,
    ]

    # Pretend there's no performance issue yet
    github_client_mock.search_issues.return_value = None

    github_repo_name = "foo/bar"
    assert run_performance_comparison(
        conf_a=config_fxt_a,
        conf_b=config_fxt_b,
        github_repo=github_repo_name,
        copr_client=copr_client_mock,
        github_client=github_client_mock,
    )

    # Check that three performance requests were made
    make_compare_compile_time_request_mock.call_count == 3

    # Check that we search for a github issue
    github_client_mock.search_issues.assert_called_once_with(
        "is:issue repo:foo/bar author:github-actions[bot] label:strategy/strategy A label:strategy/strategy B label:performance-comparison 20250402 in:title"
    )

    # Check that issue was created with proper values
    get_repo: mock.Mock = github_client_mock.get_repo
    assert get_repo.call_count == 2
    assert get_repo.call_args_list[0] == mock.call(github_repo_name)
    assert get_repo.call_args_list[1] == mock.call(github_repo_name)

    create_issue: mock.Mock = get_repo.return_value.create_issue
    create_issue.assert_called_once()
    _, kwargs = create_issue.call_args
    assert (
        kwargs["title"]
        == "Performance comparison: strategy A vs. strategy B - 20250402"
    )
    assert kwargs["assignees"] == ["maintainerA", "maintainerB"]
    assert kwargs["labels"] == [
        "strategy/strategy A",
        "strategy/strategy B",
        "performance-comparison",
    ]
    assert tf.requests_to_html_list([req1, req2, req3]) in str(kwargs["body"])
    assert tf.requests_to_html_comment([req1, req2, req3]) in str(kwargs["body"])


@mock.patch("logging.Logger.info")
@mock.patch(
    "snapshot_manager.snapshot_manager.get_performance_github_issue", return_value=None
)
@mock.patch("testing_farm.make_compare_compile_time_request")
@mock.patch("github.Github")
@mock.patch("copr.v3.Client")
@mock.patch("snapshot_manager.snapshot_manager.copr_util")
def test_run_performance_comparison__already_got_an_issue(
    copr_util_mock: mock.Mock,
    copr_client_mock: mock.Mock,
    github_client_mock: mock.Mock,
    make_compare_compile_time_request_mock: mock.Mock,
    get_performance_github_issue_mock: mock.Mock,
    info_log_mock: mock.Mock,
    config_fxt_a,
    config_fxt_b,
):
    # Pretend there's already a performance issue
    get_performance_github_issue_mock.return_value = mock.Mock()

    github_repo_name = "foo/bar"
    assert not run_performance_comparison(
        conf_a=config_fxt_a,
        conf_b=config_fxt_b,
        github_repo=github_repo_name,
        copr_client=copr_client_mock,
        github_client=github_client_mock,
    )

    get_performance_github_issue_mock.assert_called_once()

    # Ensure we "aborted" with an appropriate error message and not because of some other reason
    assert log_contains(info_log_mock, "Not starting new performance tests")


@mock.patch("logging.Logger.info")
@mock.patch("snapshot_manager.snapshot_manager.get_performance_github_issue")
@mock.patch("testing_farm.make_compare_compile_time_request")
@mock.patch("github.Github")
@mock.patch("copr.v3.Client")
@mock.patch("snapshot_manager.snapshot_manager.copr_util")
def test_collect_performance_comparison_results__no_issue_found(
    copr_util_mock: mock.Mock,
    copr_client_mock: mock.Mock,
    github_client_mock: mock.Mock,
    make_compare_compile_time_request_mock: mock.Mock,
    get_performance_github_issue_mock: mock.Mock,
    info_log_mock: mock.Mock,
    config_fxt_a,
    config_fxt_b,
):
    # Pretend there's no performance issue yet
    get_performance_github_issue_mock.return_value = None

    github_repo_name = "foo/bar"
    collect_performance_comparison_results(
        conf_a=config_fxt_a,
        conf_b=config_fxt_b,
        github_repo=github_repo_name,
        github_client=github_client_mock,
        csv_file_in="results-in.csv",
        csv_file_out="results-out.csv",
    )

    get_performance_github_issue_mock.assert_called_once()

    # Ensure we "aborted" with an appropriate error message and not because of some other reason
    assert log_contains(info_log_mock, "Performance issue not found for")


@mock.patch("logging.Logger.info")
@mock.patch("snapshot_manager.snapshot_manager.get_performance_github_issue")
@mock.patch("testing_farm.make_compare_compile_time_request")
@mock.patch("github.Github")
@mock.patch("copr.v3.Client")
@mock.patch("snapshot_manager.snapshot_manager.copr_util")
def test_collect_performance_comparison_results__end_to_end(
    copr_util_mock: mock.Mock,
    copr_client_mock: mock.Mock,
    github_client_mock: mock.Mock,
    make_compare_compile_time_request_mock: mock.Mock,
    get_performance_github_issue_mock: mock.Mock,
    info_log_mock: mock.Mock,
    config_fxt_a,
    config_fxt_b,
):
    # Allow gathering of performance results from cached responses
    tfutil._IN_TEST_MODE = True

    # We know the cached testing-farm request ID upfront
    request_id = "e388863b-e123-44fd-b832-ef26486344fd"
    # Pretend there's no performance issue yet.
    # This is the issue body we will use for recreating the requests.
    get_performance_github_issue_mock.return_value = type(
        "object",
        (object,),
        {
            "body": f"""
    Some text before <!--TESTING_FARM:fedora-rawhide-aarch64/{request_id}/1,2,3--> Some text after
    """
        },
    )

    github_repo_name = "foo/bar"
    csv_filepath_old = tfutil._test_path(f"{request_id}/results-old.csv")
    csv_filepath_out = tfutil._test_path(f"{request_id}/results-out.csv")
    collect_performance_comparison_results(
        conf_a=config_fxt_a,
        conf_b=config_fxt_b,
        github_repo=github_repo_name,
        github_client=github_client_mock,
        csv_file_in=csv_filepath_old,
        csv_file_out=csv_filepath_out,
    )

    csv_filepath_expected_merge = tfutil._test_path(
        f"{request_id}/results-expected-merge.csv"
    )

    assert_files_match(csv_filepath_out, csv_filepath_expected_merge)

    get_performance_github_issue_mock.assert_called_once()

    assert log_contains(
        info_log_mock, f"Reading request file for request ID {request_id}"
    )
    assert log_contains(info_log_mock, f"Fetching xunit URL from URL")
    assert log_contains(info_log_mock, f"Downloading CSV file from")
    assert log_contains(info_log_mock, f"Writing merged CSV file to")


def assert_files_match(actual: pathlib.Path, expected: pathlib.Path):
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


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.snapshot_manager

    tests.addTests(doctest.DocTestSuite(snapshot_manager.snapshot_manager))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
