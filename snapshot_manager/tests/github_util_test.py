""" Tests for github """

import datetime
import logging
import uuid

import tests.base_test as base_test

import snapshot_manager.github_util as github_util


class TestGithub(base_test.TestBase):
    def test_create_or_get_todays_github_issue(self):
        """Creates or gets today's github issue"""
        gh = github_util.GithubClient(config=self.config)
        issue, _ = gh.create_or_get_todays_github_issue(
            maintainer_handle="kwk", creator="kwk"
        )
        self.assertIsNotNone(issue)

        marker = "<!--HIDE_COMMMENT-->"
        comment = gh.create_or_update_comment(
            issue=issue, comment_body=f"{marker} Comment to be hidden", marker=marker
        )
        self.assertTrue(gh.minimize_comment_as_outdated(comment))

        marker = "<!--HIDE_AND_UNHIDE_COMMMENT-->"
        comment = gh.create_or_update_comment(
            issue=issue,
            comment_body=f"{marker} Comment to be hidden and unhidden",
            marker=marker,
        )
        self.assertTrue(gh.minimize_comment_as_outdated(comment))
        self.assertTrue(gh.unminimize_comment(comment))

        marker = "<!--REACT_TO_COMMMENT-->"
        comment = gh.create_or_update_comment(
            issue=issue, comment_body=f"{marker} Comment to react to", marker=marker
        )
        self.assertTrue(gh.add_comment_reaction(comment, github_util.Reaction.HEART))
        self.assertTrue(
            gh.add_comment_reaction(comment, github_util.Reaction.THUMBS_UP)
        )

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

    def test_flip_test_label(self):
        gh = github_util.GithubClient(config=self.config)
        issue = gh.gh_repo.create_issue(
            title=f"TestGithub.test_flip_test_label {uuid.uuid4()}",
            body="This comment is for testing TestGithub.test_flip_test_label",
        )
        self.assertIsNotNone(issue)

        # Remove all labels
        logging.info(f"Removing all labels from issue: {issue.html_url}")
        for label in issue.get_labels():
            issue.remove_from_labels(label)
        self.assertEqual(issue.get_labels().totalCount, 0)

        # Ensure those labels that we need for our test exist
        chroot = "fedora-rawhide-x86_64"
        all_chroots = [chroot]
        logging.info("Creating test labels")
        gh.create_labels_for_in_testing(all_chroots)
        gh.create_labels_for_failed_on(all_chroots)
        gh.create_labels_for_tested_on(all_chroots)

        in_testing = gh.label_in_testing(chroot=chroot)
        failed_on = gh.label_failed_on(chroot=chroot)
        tested_on = gh.label_tested_on(chroot=chroot)

        all_test_states = [in_testing, failed_on, tested_on]
        for test_state in all_test_states:
            logging.info(f"Flipping test label for chroot {chroot} to: {test_state}")
            gh.flip_test_label(issue, chroot, test_state)
            labels = issue.get_labels()
            self.assertIsNotNone(labels)
            self.assertEqual(labels.totalCount, 1)
            page = labels.get_page(0)
            self.assertIsNotNone(page)
            self.assertEqual(page[0].name, test_state)
        pass

    def test_get_workflow(self):
        gh = github_util.GithubClient(config=self.config)
        repo = gh.github.get_repo("fedora-llvm-team/llvm-snapshots")
        workflow = repo.get_workflow("check-snapshots.yml")
        self.assertIsNotNone(workflow)


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
    base_test.run_tests()
