""" Tests for file_access """

import tests.test_base as test_base

import snapshot_manager.file_access as file_access
import snapshot_manager.build_status as build_status


class TestFileAccess(test_base.TestBase):
    pass


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest
    import snapshot_manager.file_access

    tests.addTests(doctest.DocTestSuite(snapshot_manager.file_access))
    return tests


if __name__ == "__main__":
    test_base.run_tests()
