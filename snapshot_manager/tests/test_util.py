""" Tests for util """

import tests.test_base as test_base

import snapshot_manager.file_access as file_access
import snapshot_manager.build_status as build_status
import snapshot_manager.util as util


class TestUtil(test_base.TestBase):
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

    def test_get_cause_from_build_log(self):
        """Get cause from build log"""
        causes = [e.value for e in build_status.ErrorCause]

        # TODO(kwk): Find good example log files for these two error causes
        # (existing ones have timed out and were already deleted)
        causes.remove(build_status.ErrorCause.ISSUE_NETWORK)
        causes.remove(build_status.ErrorCause.ISSUE_SRPM_BUILD)

        for expectedCause in causes:
            with self.subTest(expectedCause=expectedCause):
                actualCause, ctx = build_status.get_cause_from_build_log(
                    build_log_file=self.abspath(
                        f"test_logs/cause_{expectedCause}.log.gz"
                    )
                )
                self.assertEqual(expectedCause, actualCause)

    def test_markdown_build_matrix(self):
        """Creates and then updates a build matrix"""
        all_copr_states = build_status.CoprBuildStatus.all_states()
        packages = ["stupefy", "alohomora"]
        chroots = ["fedora-rawhide-x86_64", "fedora-40-ppc64le"]

        self.maxDiff = None

        # Let's say these are the actual builds currently in the copr project.
        # Only three should show up in the matrix.
        s1 = build_status.BuildState(
            package_name="not-in-list", chroot=chroots[0], build_id=11
        )
        s2 = build_status.BuildState(
            package_name="stupefy",
            chroot="fedora-rawhide-x86_64",
            copr_build_state=build_status.CoprBuildStatus.IMPORTING,
            build_id=22,
        )
        s3 = build_status.BuildState(
            package_name="stupefy",
            chroot="fedora-40-ppc64le",
            copr_build_state=build_status.CoprBuildStatus.SUCCEEDED,
            build_id=33,
        )
        s4 = build_status.BuildState(
            package_name="alohomora",
            chroot="fedora-rawhide-x86_64",
            copr_build_state=build_status.CoprBuildStatus.FAILED,
            build_id=44,
        )

        build_states = [s1, s2, s3, s4]

        matrix = build_status.markdown_build_status_matrix(
            chroots=chroots,
            packages=packages,
            add_legend=True,
            build_states=build_states,
        )
        expected_result = f"""<details open><summary>Build Matrix</summary>

| |stupefy|alohomora|
|:---|:---:|:---:|
|fedora-rawhide-x86_64|[{build_status.CoprBuildStatus.IMPORTING.toIcon()}](https://copr.fedorainfracloud.org/coprs/build/22) | [{build_status.CoprBuildStatus.FAILED.toIcon()}](https://copr.fedorainfracloud.org/coprs/build/44)|
|fedora-40-ppc64le|[{build_status.CoprBuildStatus.SUCCEEDED.toIcon()}](https://copr.fedorainfracloud.org/coprs/build/33) | :grey_question:|
<details><summary>Build status legend</summary><ul><li>:o: : canceled</li><li>:x: : failed</li><li>:ballot_box_with_check: : forked</li><li>:inbox_tray: : importing</li><li>:soon: : pending</li><li>:running: : running</li><li>:no_entry_sign: : skipped</li><li>:star: : starting</li><li>:white_check_mark: : succeeded</li><li>:hourglass: : waiting</li><li>:grey_question: : unknown</li></ul></details>
</details>"""
        self.assertEqual(expected_result, matrix)


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
    test_base.run_tests()
