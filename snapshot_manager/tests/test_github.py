""" Tests for github """

import datetime

import tests.test_base as test_base
import snapshot_manager.github_util as github_util


class TestGithub(test_base.TestBase):
    def test_create_or_get_todays_github_issue(self):
        """Creates or gets today's github issue"""
        gh = github_util.GithubClient(config=self.config)
        issue, _ = gh.create_or_get_todays_github_issue(
            maintainer_handle="kwk", creator="kwk"
        )
        self.assertIsNotNone(issue)

    def test_get_todays_issue(self):
        """Get today's github issue"""
        # Example: Get issue for day in the past
        cfg = self.config
        cfg.datetime = datetime.datetime(year=2024, month=2, day=27)
        self.assertEqual("20240227", cfg.yyyymmdd)
        gh = github_util.GithubClient(config=cfg)

        issue = gh.get_todays_github_issue(
            strategy="big-merge", github_repo="fedora-llvm-team/llvm-snapshots"
        )
        self.assertIsNotNone(issue)
        self.assertEqual(287, issue.number)

        # Example: Get issue when in fact, no issue was created (should be always True for the day after tomorrow)
        cfg.datetime = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=2)
        issue = gh.get_todays_github_issue(
            strategy="big-merge", github_repo="fedora-llvm-team/llvm-snapshots"
        )
        self.assertIsNone(issue)


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.github_util

    tests.addTests(doctest.DocTestSuite(snapshot_manager.github_util))
    return tests


if __name__ == "__main__":
    test_base.run_tests()
