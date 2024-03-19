""" Tests for build_status """

import snapshot_manager.build_status as build_status
import tests.test_base as test_base


class TestError(test_base.TestBase):
    def test_render_as_markdown(self):
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
<code>foo</code> on <code>fedora-40-x86_64</code> (see <a href="https://example.com/url_build_log">build log</a>)
</summary>
This is the context for the error
</details>
"""
        self.assertEqual(expected, state.render_as_markdown())


class TestErrorList(test_base.TestBase):
    def test_sort(self):
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

    def test_render_as_markdown(self):
        """Test that a list of errors is rendered properly to HTML"""
        # fmt: off
        kwargs = {"copr_ownername": "foo", "copr_projectname": "bar"}
        e1 = build_status.BuildState(url_build_log="http://e1", err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-a", **kwargs)
        e2 = build_status.BuildState(url_build_log="http://e2", err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-b", **kwargs)
        e3 = build_status.BuildState(url_build_log="http://e3", err_cause=build_status.ErrorCause.ISSUE_NETWORK, chroot="chroot-a", package_name="package-c", **kwargs)
        e4 = build_status.BuildState(url_build_log="http://e4", err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-a", **kwargs)
        e5 = build_status.BuildState(url_build_log="http://e5", err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-b", **kwargs)
        e6 = build_status.BuildState(url_build_log="http://e6", err_cause=build_status.ErrorCause.ISSUE_TEST, chroot="chroot-c", package_name="package-c", **kwargs)
        # fmt: on
        unsorted: build_status.BuildStateList = [e3, e6, e1, e5, e4, e2]

        # Uncomment if you want to see the whole diff if something below is wrong.
        # self.maxDiff = None

        actual = build_status.render_as_markdown(unsorted)

        expected = """

<details open><summary><h2>network_issue</h2></summary>

<ol><li>
<details>
<summary>
<code>package-a</code> on <code>chroot-a</code> (see <a href="http://e1">build log</a>)
</summary>

</details>
</li><li>
<details>
<summary>
<code>package-b</code> on <code>chroot-a</code> (see <a href="http://e2">build log</a>)
</summary>

</details>
</li><li>
<details>
<summary>
<code>package-c</code> on <code>chroot-a</code> (see <a href="http://e3">build log</a>)
</summary>

</details>
</li></ol></details>

<details open><summary><h2>test</h2></summary>

<ol><li>
<details>
<summary>
<code>package-a</code> on <code>chroot-c</code> (see <a href="http://e4">build log</a>)
</summary>

</details>
</li><li>
<details>
<summary>
<code>package-b</code> on <code>chroot-c</code> (see <a href="http://e5">build log</a>)
</summary>

</details>
</li><li>
<details>
<summary>
<code>package-c</code> on <code>chroot-c</code> (see <a href="http://e6">build log</a>)
</summary>

</details>
</li></ol></details>"""
        self.assertEqual(expected, actual)


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.build_status

    tests.addTests(doctest.DocTestSuite(snapshot_manager.build_status))
    return tests


if __name__ == "__main__":
    test_base.run_tests()
