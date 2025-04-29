"""Tests for file_access"""

import unittest

import tests.base_test as base_test


class TestFileAccess(base_test.TestBase):
    pass


def load_tests(
    loader: unittest.TestLoader, standard_tests: unittest.TestSuite, pattern: str
) -> unittest.TestSuite:
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.file_access

    standard_tests.addTests(doctest.DocTestSuite(snapshot_manager.file_access))
    return standard_tests


if __name__ == "__main__":
    base_test.run_tests()
