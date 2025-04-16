import enum
import re

import testing_farm.tfutil as tfutil


@enum.unique
class WatchResult(enum.StrEnum):
    """An enum to represent states from a testing-farm watch call

    See https://gitlab.com/testing-farm/cli/-/blob/main/src/tft/cli/commands.py?ref_type=heads#L248-272
    """

    REQUEST_WAITING_TO_BE_QUEUED = "request is waiting to be queued"  #  Package sources are being imported into Copr DistGit.
    REQUEST_QUEUED = (
        "request is queued"  # Build is waiting in queue for a backend worker.
    )
    REQUEST_RUNNING = (
        "request is running"  # Backend worker is trying to acquire a builder machine.
    )
    TESTS_PASSED = "tests passed"  # Build in progress.
    TESTS_FAILED = "tests failed"  # Successfully built.
    TESTS_ERROR = "tests error"  # Build has been forked from another build.
    TESTS_UNKNOWN = "tests unknown"  # This package was skipped, see the reason for each chroot separately.
    PIPELINE_ERROR = "pipeline error"

    def to_icon(self) -> str:
        """Get a github markdown icon for the given testing-farm watch result.

        See https://gist.github.com/rxaviers/7360908 for a list of possible icons."""
        if self == self.REQUEST_WAITING_TO_BE_QUEUED:
            return ":hourglass:"
        if self == self.REQUEST_QUEUED:
            return ":inbox_tray:"
        if self == self.REQUEST_RUNNING:
            return ":running:"
        if self == self.TESTS_PASSED:
            return ":white_check_mark:"
        if self == self.TESTS_FAILED:
            return ":x:"
        if self == self.TESTS_ERROR:
            return ":x:"
        if self == self.TESTS_UNKNOWN:
            return ":grey_question:"
        if self == self.PIPELINE_ERROR:
            return ":warning:"

    @classmethod
    def all_watch_results(cls) -> list["WatchResult"]:
        return [s for s in WatchResult]

    @property
    def is_complete(self) -> bool:
        """Returns True if the watch result indicates that the testing-farm
        request has been completed.

        Examples:

        >>> WatchResult("tests failed").is_complete
        True

        >>> WatchResult("request is queued").is_complete
        False
        """
        return self.value in [
            self.TESTS_PASSED,
            self.TESTS_FAILED,
            self.TESTS_ERROR,
        ]

    @property
    def is_error(self) -> bool:
        """Returns True if the watch result indicates that the testing-farm
        request has an error.

        Examples:

        >>> WatchResult("tests failed").is_complete
        True

        >>> WatchResult("request is queued").is_complete
        False
        """
        return self.value in [
            self.TESTS_FAILED,
            self.TESTS_ERROR,
        ]

    @property
    def expect_artifacts_url(self) -> bool:
        """Returns True if for the watch result we can expect and artifacts URL in the watch output."""
        if self.value in [
            self.REQUEST_WAITING_TO_BE_QUEUED,
            self.REQUEST_QUEUED,
            self.PIPELINE_ERROR,
        ]:
            return False
        return True

    @classmethod
    def is_watch_result(cls, string: str) -> bool:
        """Returns True if the given string is a valid what result.

        Args:
            string (str): The string to be tested

        Returns:
            bool: True if the string is a watch result.

        Examples:

        >>> WatchResult.is_watch_result('foo')
        False

        >>> WatchResult.is_watch_result('tests failed')
        True
        """
        return string in cls.all_watch_results()

    @classmethod
    def from_output(cls, string: str) -> tuple["WatchResult", str]:
        """Inspects the output of a testing-farm watch call and returns a tuple of result and artifacts url (if any).

        Args:
            string (str): The output of a testing-farm watch call.

        Returns:
            tuple[str, WatchResult]: _description_

        Examples:
        >>> s='''8J+UjiBhcGkgaHR0cHM6Ly9hcGkuZGV2LnRlc3RpbmctZmFybS5pby92MC4xL3JlcXVlc3RzLzI3
        ... MWE3OWU4LWZjOWEtNGUxZC05NWZlLTU2N2NjOWQ2MmFkNArwn5qiIGFydGlmYWN0cyBodHRwOi8v
        ... YXJ0aWZhY3RzLm9zY2kucmVkaGF0LmNvbS90ZXN0aW5nLWZhcm0vMjcxYTc5ZTgtZmM5YS00ZTFk
        ... LTk1ZmUtNTY3Y2M5ZDYyYWQ0CuKdjCB0ZXN0cyBlcnJvcgpOb25lCg=='''
        >>> import base64
        >>> s = base64.b64decode(s).decode()
        >>> WatchResult.from_output(s)
        (<WatchResult.TESTS_ERROR: 'tests error'>, 'http://artifacts.osci.redhat.com/testing-farm/271a79e8-fc9a-4e1d-95fe-567cc9d62ad4')
        >>> s='''8J+UjiBhcGkgaHR0cHM6Ly9hcGkuZGV2LnRlc3RpbmctZmFybS5pby92MC4xL3JlcXVlc3RzLzcy
        ... ZWZiYWZjLTdkYjktNGUwNS04NTZjLTg3MzExNGE5MjQzNQrwn5ObIHBpcGVsaW5lIGVycm9yCkd1
        ... ZXN0IGNvdWxkbid0IGJlIHByb3Zpc2lvbmVkOiBBcnRlbWlzIHJlc291cmNlIGVuZGVkIGluICdl
        ... cnJvcicgc3RhdGUKCg=='''
        >>> s = base64.b64decode(s).decode()
        >>> WatchResult.from_output(s)
        (<WatchResult.PIPELINE_ERROR: 'pipeline error'>, None)
        >>> s='''8J+UjiBhcGkgaHR0cHM6Ly9hcGkuZGV2LnRlc3RpbmctZmFybS5pby92MC4xL3JlcXVlc3RzLzk3
        ... YTdjYzI0LTY5MjYtNDA1OS04NGFjLWQwMDc4Mjk3YzMxOQrwn5qAIHJlcXVlc3QgaXMgcnVubmlu
        ... Zwrwn5qiIGFydGlmYWN0cyBodHRwczovL2FydGlmYWN0cy5kZXYudGVzdGluZy1mYXJtLmlvLzk3
        ... YTdjYzI0LTY5MjYtNDA1OS04NGFjLWQwMDc4Mjk3YzMxOQo='''
        >>> s = base64.b64decode(s).decode()
        >>> WatchResult.from_output(s)
        (<WatchResult.REQUEST_RUNNING: 'request is running'>, 'https://artifacts.dev.testing-farm.io/97a7cc24-6926-4059-84ac-d0078297c319')
        >>> s='''8J+UjiBhcGkgaHR0cHM6Ly9hcGkuZGV2LnRlc3RpbmctZmFybS5pby92MC4xL3JlcXVlc3RzLzg2
        ... MGExZjdlLTA2NmMtNGU0Mi1iYWRkLThlNmRjYTkwYzE0Ygrwn5qiIGFydGlmYWN0cyBodHRwczov
        ... L2FydGlmYWN0cy5vc2NpLnJlZGhhdC5jb20vdGVzdGluZy1mYXJtLzg2MGExZjdlLTA2NmMtNGU0
        ... Mi1iYWRkLThlNmRjYTkwYzE0YgrinIUgdGVzdHMgcGFzc2VkCg=='''
        >>> s = base64.b64decode(s).decode()
        >>> WatchResult.from_output(s)
        (<WatchResult.TESTS_PASSED: 'tests passed'>, 'https://artifacts.osci.redhat.com/testing-farm/860a1f7e-066c-4e42-badd-8e6dca90c14b')
        """
        string = tfutil.clean_testing_farm_output(string)
        for watch_result in WatchResult.all_watch_results():
            if not re.search(pattern=str(watch_result), string=string):
                continue
            if not watch_result.expect_artifacts_url:
                return (watch_result, None)
            url_match = re.search(pattern=r"artifacts http[s]?://.*", string=string)
            if not url_match:
                raise ValueError(f"expected an artifacts URL but couldn't find one")
            artifacts_url = str(
                re.search(pattern=r"http[s]?://.*", string=url_match[0])[0]
            ).strip()
            return (watch_result, artifacts_url)

        return (None, None)
