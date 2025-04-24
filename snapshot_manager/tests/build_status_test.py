"""Tests for build_status"""

import tests.base_test as base_test

import snapshot_manager.build_status as build_status
import snapshot_manager.util as util
from snapshot_manager.build_status import ErrorCause


class TestErrorCauseAndBuildStatus(base_test.TestBase):
    def test_get_cause_from_build_log(self) -> None:
        """Get cause from build log"""

        causes = [e.value for e in ErrorCause]

        # TODO(kwk): Find good example log files for these three error causes
        # (existing ones have timed out and were already deleted)
        causes.remove(ErrorCause.ISSUE_NETWORK)
        causes.remove(ErrorCause.ISSUE_SRPM_BUILD)
        causes.remove(ErrorCause.ISSUE_UNKNOWN)

        for expectedCause in causes:
            with self.subTest(expectedCause=expectedCause):
                actualCause, actualCtx = build_status.get_cause_from_build_log(
                    build_log_file=self.abspath(
                        f"test_logs/cause_{expectedCause}.log.gz"
                    ),
                    write_golden_file=False,  # TODO(kwk): Turn this on when the format has changed.
                )
                self.assertEqual(expectedCause, actualCause)

                # Read in expected cause
                expectedCtxFile = util.golden_file_path(
                    basename=f"cause_{str(expectedCause)}"
                )

                self.assertEqual(actualCtx, expectedCtxFile.read_text())

    def test_markdown_build_matrix(self) -> None:
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
|fedora-rawhide-x86_64|[{build_status.CoprBuildStatus.IMPORTING.to_icon()}](https://copr.fedorainfracloud.org/coprs/build/22) | [{build_status.CoprBuildStatus.FAILED.to_icon()}](https://copr.fedorainfracloud.org/coprs/build/44)|
|fedora-40-ppc64le|[{build_status.CoprBuildStatus.SUCCEEDED.to_icon()}](https://copr.fedorainfracloud.org/coprs/build/33) | :grey_question:|
<details><summary>Build status legend</summary><ul><li>:o: : canceled</li><li>:x: : failed</li><li>:ballot_box_with_check: : forked</li><li>:inbox_tray: : importing</li><li>:soon: : pending</li><li>:running: : running</li><li>:no_entry_sign: : skipped</li><li>:star: : starting</li><li>:white_check_mark: : succeeded</li><li>:hourglass: : waiting</li><li>:grey_question: : unknown</li><li>:warning: : pipeline error (only relevant to testing-farm)</li></ul></details>
</details>"""
        self.assertEqual(expected_result, matrix)

    def test_render_as_markdown(self) -> None:
        """Test HTML string representation of a BuildState"""
        state = build_status.BuildState(
            err_cause=build_status.ErrorCause.ISSUE_NETWORK,
            package_name="foo",
            chroot="fedora-40-x86_64",
            url_build_log="https://example.com/url_build_log",
            url_build="https://example.com/url_build",
            build_id=1234,
            err_ctx="This is the context for the error",
            copr_ownername="foo",
            copr_projectname="bar",
        )

        expected = """
<details>
<summary>
<code>foo</code> on <code>fedora-40-x86_64</code> (see <a href="https://example.com/url_build_log">build log</a>, <a href="https://logdetective.com/contribute/copr/00001234/fedora-40-x86_64">Teach AI</a>, <a href="https://log-detective.com/explain?url=https%3A//example.com/url_build_log">Ask AI</a>)
</summary>
This is the context for the error
</details>
"""
        self.assertEqual(expected, state.render_as_markdown())


class TestErrorList(base_test.TestBase):
    def test_sort(self) -> None:
        """Test sorting of errors in an array works as expected"""
        # fmt: off
        e1 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-a")
        e2 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-b", package_name="package-a")
        e3 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-b")
        e4 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-b", package_name="package-b")
        e5 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-c")
        e6 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-b", package_name="package-c")
        e7 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-a")
        e8 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-b")
        e9 = build_status.BuildState(err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-c")
        # fmt: on

        # Sorted by cause, package name, chroot (see BuildState order of dataclass fields)
        sorted = [e1, e2, e3, e4, e5, e6, e7, e8, e9]
        resorted = [e3, e9, e1, e8, e6, e7, e5, e4, e2]
        resorted.sort()

        self.assertEqual(sorted, resorted)

    def test_render_as_markdown(self) -> None:
        """Test that a list of errors is rendered properly to HTML"""
        # fmt: off
        e1 = build_status.BuildState(build_id=111, url_build_log="http://e1", err_ctx="e1", err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-a", copr_ownername="foo", copr_projectname="bar")
        e2 = build_status.BuildState(build_id=222, url_build_log="http://e2", err_ctx="e2", err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-b", copr_ownername="foo", copr_projectname="bar")
        e3 = build_status.BuildState(build_id=333, url_build_log="http://e3", err_ctx="e3", err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-c", copr_ownername="foo", copr_projectname="bar")
        e4 = build_status.BuildState(build_id=444, url_build_log="http://e4", err_ctx="e4", err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-a", copr_ownername="foo", copr_projectname="bar")
        e5 = build_status.BuildState(build_id=555, url_build_log="http://e5", err_ctx="e5", err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-b", copr_ownername="foo", copr_projectname="bar")
        e6 = build_status.BuildState(build_id=666, url_build_log="http://e6", err_ctx="e6", err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-c", copr_ownername="foo", copr_projectname="bar")
        # fmt: on
        unsorted: build_status.BuildStateList = [e3, e6, e1, e5, e4, e2]

        # Uncomment if you want to see the whole diff if something below is wrong.
        # self.maxDiff = None

        actual = build_status.render_as_markdown(unsorted)

        expected = """<ul><li><b>network_issue</b><ol><li>
<details>
<summary>
<code>package-a</code> on <code>chroot-a</code> (see <a href="http://e1">build log</a>, <a href="https://logdetective.com/contribute/copr/00000111/chroot-a">Teach AI</a>, <a href="https://log-detective.com/explain?url=http%3A//e1">Ask AI</a>)
</summary>
e1
</details>
</li><li>
<details>
<summary>
<code>package-b</code> on <code>chroot-a</code> (see <a href="http://e2">build log</a>, <a href="https://logdetective.com/contribute/copr/00000222/chroot-a">Teach AI</a>, <a href="https://log-detective.com/explain?url=http%3A//e2">Ask AI</a>)
</summary>
e2
</details>
</li><li>
<details>
<summary>
<code>package-c</code> on <code>chroot-a</code> (see <a href="http://e3">build log</a>, <a href="https://logdetective.com/contribute/copr/00000333/chroot-a">Teach AI</a>, <a href="https://log-detective.com/explain?url=http%3A//e3">Ask AI</a>)
</summary>
e3
</details>
</li></ol></li><li><b>test</b><ol><li>
<details>
<summary>
<code>package-a</code> on <code>chroot-c</code> (see <a href="http://e4">build log</a>, <a href="https://logdetective.com/contribute/copr/00000444/chroot-c">Teach AI</a>, <a href="https://log-detective.com/explain?url=http%3A//e4">Ask AI</a>)
</summary>
e4
</details>
</li><li>
<details>
<summary>
<code>package-b</code> on <code>chroot-c</code> (see <a href="http://e5">build log</a>, <a href="https://logdetective.com/contribute/copr/00000555/chroot-c">Teach AI</a>, <a href="https://log-detective.com/explain?url=http%3A//e5">Ask AI</a>)
</summary>
e5
</details>
</li><li>
<details>
<summary>
<code>package-c</code> on <code>chroot-c</code> (see <a href="http://e6">build log</a>, <a href="https://logdetective.com/contribute/copr/00000666/chroot-c">Teach AI</a>, <a href="https://log-detective.com/explain?url=http%3A//e6">Ask AI</a>)
</summary>
e6
</details>
</li></ol></li></ul>"""
        self.assertEqual(expected, actual)


def load_tests(loader, tests, ignore):  # type: ignore[no-untyped-def]
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.build_status

    tests.addTests(doctest.DocTestSuite(snapshot_manager.build_status))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
