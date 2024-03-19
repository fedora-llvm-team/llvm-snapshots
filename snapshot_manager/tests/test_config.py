""" Tests for config """

import datetime

import tests.test_base as test_base
import snapshot_manager.config as config


class TestConfig(test_base.TestBase):
    def test_yyyymmdd(self):
        self.assertEqual(
            "20240227",
            config.Config(
                datetime=datetime.datetime(year=2024, month=2, day=27)
            ).yyyymmdd,
        )


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.config

    tests.addTests(doctest.DocTestSuite(snapshot_manager.config))
    return tests


if __name__ == "__main__":
    test_base.run_tests()
