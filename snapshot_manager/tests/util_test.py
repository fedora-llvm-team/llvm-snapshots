"""Tests for util"""

import tests.base_test as base_test

import snapshot_manager.util as util


class TestUtil(base_test.TestBase):
    def test_grep_file(self):
        """Grep file"""
        with self.get_text_file("foo") as log_file:
            with self.assertRaises(ValueError) as ex:
                util.grep_file(pattern="", filepath=log_file.resolve())
            self.assertEqual("pattern is invalid:", str(ex.exception))

            with self.assertRaises(ValueError) as ex:
                util.grep_file(
                    pattern="foo",
                    lines_before=-1,
                    filepath=log_file.resolve(),
                )
            self.assertEqual(
                "lines_before must be zero or a positive integer",
                str(ex.exception),
            )

            with self.assertRaises(ValueError) as ex:
                util.grep_file(
                    pattern="foo",
                    lines_after=-1,
                    filepath=log_file.resolve(),
                )
            self.assertEqual(
                "lines_after must be zero or a positive integer",
                str(ex.exception),
            )


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.util

    tests.addTests(doctest.DocTestSuite(snapshot_manager.util))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
