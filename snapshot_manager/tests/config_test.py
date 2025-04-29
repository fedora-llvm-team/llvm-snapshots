"""Tests for config"""

import datetime
import unittest

import tests.base_test as base_test

import snapshot_manager.config as config


class TestConfig(base_test.TestBase):
    def test_yyyymmdd(self) -> None:
        self.assertEqual(
            "20240227",
            config.Config(
                datetime=datetime.datetime(year=2024, month=2, day=27)
            ).yyyymmdd,
        )


def load_tests(
    loader: unittest.TestLoader, standard_tests: unittest.TestSuite, pattern: str
) -> unittest.TestSuite:
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.config

    standard_tests.addTests(doctest.DocTestSuite(snapshot_manager.config))
    return standard_tests


if __name__ == "__main__":
    base_test.run_tests()
