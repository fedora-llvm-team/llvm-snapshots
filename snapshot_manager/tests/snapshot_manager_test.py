""" Tests for snapshot_manager """

import datetime

import tests.base_test as base_test
import snapshot_manager.snapshot_manager as snapshot_manager
import snapshot_manager.build_status as build_status


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
