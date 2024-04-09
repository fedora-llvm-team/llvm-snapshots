""" Tests for build_status """

import tests.base_test as base_test

import snapshot_manager.testing_farm_util as tf


class TestTestingFarmUtil(base_test.TestBase):
    def test_fetch_failed_test_cases_from_file(self):
        request_id = "1f25b0df-71f1-4a13-a4b8-c066f6f5f116"
        chroot = "fedora-39-x86_64"
        req = tf.TestingFarmRequest(
            request_id=request_id,
            chroot=chroot,
            copr_build_ids=[11, 22, 33],
        )
        actual = req.get_failed_test_cases_from_xunit_file(
            xunit_file=self.abspath(f"testing-farm-logs/results_{request_id}.xml"),
            artifacts_url_origin="https://example.com",
        )

        expected = [
            tf.FailedTestCase(
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


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.testing_farm_util

    tests.addTests(doctest.DocTestSuite(snapshot_manager.testing_farm_util))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
