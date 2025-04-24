import datetime
import os
import uuid
from unittest import mock

import pytest
import testing_farm as tf
import testing_farm.tfutil as tfutil
import tests.base_test as base_test
from testing_farm.failed_test_case import FailedTestCase
from testing_farm.request import Request
from testing_farm.tfutil import adjust_token_env

import snapshot_manager.github_util as github_util


@mock.patch.dict(
    os.environ,
    {
        "TESTING_FARM_API_TOKEN_PUBLIC_RANCH": "public",
        "TESTING_FARM_API_TOKEN_REDHAT_RANCH": "redhat",
    },
    clear=True,
)
def test_adjust_token_env() -> None:
    os.getenv("TESTING_FARM_API_TOKEN") is None

    adjust_token_env("fedora-rawhide-x86_64")
    assert os.environ["TESTING_FARM_API_TOKEN"] == "public"

    adjust_token_env("rhel-9-x86_64")
    assert os.environ["TESTING_FARM_API_TOKEN"] == "redhat"


class TestTestingFarmUtil(base_test.TestBase):
    def test_make_with_missing_compose(self) -> None:
        cfg = self.config
        cfg.datetime = datetime.datetime(year=2024, month=2, day=27)
        self.assertEqual("20240227", cfg.yyyymmdd)

        try:
            gh = github_util.GithubClient(config=cfg)
        except github_util.MissingToken:
            pytest.skip(
                "Skip test because this execution doesn't have access to a Github token"
            )

        issue = gh.get_todays_github_issue(
            strategy="big-merge", github_repo="fedora-llvm-team/llvm-snapshots"
        )
        assert issue is not None

        with self.assertRaises(SystemError):
            tf.make_snapshot_gating_request(
                chroot="fedora-900-x86_64",
                config=self.config,
                issue=issue,
                copr_build_ids=[1, 2, 3],
            )

    def test_fetch_failed_test_cases_from_file(self) -> None:
        tfutil._IN_TEST_MODE = True

        request_id = uuid.UUID("1f25b0df-71f1-4a13-a4b8-c066f6f5f116")
        chroot = "fedora-39-x86_64"
        req = Request(
            request_id=tfutil.sanitize_request_id(request_id),
            chroot=chroot,
            copr_build_ids=[11, 22, 33],
        )
        actual = req.get_failed_test_cases_from_xunit_file(
            xunit_file=self.abspath(f"testing-farm-logs/{request_id}/xunit.xml"),
            artifacts_url_origin="https://example.com",
        )

        expected = [
            FailedTestCase(
                test_name="/compiler-rt-tests/cross-compile-i686",
                request_id=request_id,
                chroot=chroot,
                log_output_url=f"https://artifacts.dev.testing-farm.io/{request_id}/work-snapshot-gatingk5n38qtr/tests/snapshot-gating/execute/data/guest/default-0/compiler-rt-tests/cross-compile-i686-18/output.txt",
                log_output="+ clang -m32 -fsanitize=address test.c\n"
                "/usr/bin/ld: cannot find -lgcc_s: No such file or "
                "directory\n"
                "clang: error: linker command failed with exit code "
                "1 (use -v to see invocation)\n"
                "Shared connection to 3.12.104.11 closed.\n",
                artifacts_url="https://example.com",
            )
        ]
        self.assertEqual(actual, expected)


def load_tests(loader, tests, ignore):  # type: ignore[no-untyped-def]
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import testing_farm

    tests.addTests(doctest.DocTestSuite(testing_farm))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
