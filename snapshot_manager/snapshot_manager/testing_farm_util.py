"""
testing_farm_util
"""

import dataclasses
import datetime
import enum
import json
import logging
import os
import pathlib
import re
import string
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from typing import ClassVar

import github.Issue
import regex

import snapshot_manager.config as config
import snapshot_manager.util as util


@dataclasses.dataclass(kw_only=True, unsafe_hash=True)
class TestingFarmRequest:
    request_id: uuid.UUID
    """The request ID returned from a call to testing-farm request' """

    chroot: str
    """The chroot for which this testing-farm request was issues"""

    copr_build_ids: list[int]
    """The copr build IDs associated with the testing-farm request at the time
    the request was made."""

    # TODO(kwk): Don't compare these class variables.
    chroot_pattern: ClassVar[str] = r"[^-]+-[^-]+-[^-]+"
    uuid_pattern: ClassVar[str] = (
        r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
    )
    copr_build_ids_pattern: ClassVar[str] = r"(\d,)*\d"

    @property
    def are_build_ids_still_valid(self, copr_build_ids: list[int]) -> bool:
        """Returns True if the given copr builds are the same as the ones
        associated with this testing-farm request"""
        return set(self.copr_build_ids) == set(copr_build_ids)

    def to_html_comment(self) -> str:
        """Returns a HTML comment will all information about this testing-farm request.

        Embed this somewhere.

        Returns:
            str: A HTML comment.

        Example:

        >>> request = TestingFarmRequest(request_id='1e2ff614-3bee-4519-b03e-ffd1bf2796a6', chroot='fedora-rawhide-x86_64', copr_build_ids=[4,5,6])
        >>> request.to_html_comment()
        '<!--TESTING_FARM:fedora-rawhide-x86_64/1e2ff614-3bee-4519-b03e-ffd1bf2796a6/4,5,6-->\\n'
        """
        build_ids = ",".join([str(bid) for bid in self.copr_build_ids])
        return f"<!--TESTING_FARM:{self.chroot}/{self.request_id}/{build_ids}-->\n"

    def dict_to_html_comment(data: dict[str, "TestingFarmRequest"]) -> str:
        """Converts the data dictionary of chroot -> request object pairs to html comments.

        Example:

        >>> foo = TestingFarmRequest(chroot="fedora-rawhide-x86_64", request_id="5823b132-9651-43e4-b6b5-81794b9f4102", copr_build_ids=[1,2,3])
        >>> bar = TestingFarmRequest(chroot="fedora-40-s390x", request_id="23ec426f-eaa9-4cc3-a98d-bd7c0a5aeac9", copr_build_ids=[44,544,622])
        >>> TestingFarmRequest.dict_to_html_comment({"foo": foo, "bar": bar})
        '<!--TESTING_FARM:fedora-rawhide-x86_64/5823b132-9651-43e4-b6b5-81794b9f4102/1,2,3-->\\n<!--TESTING_FARM:fedora-40-s390x/23ec426f-eaa9-4cc3-a98d-bd7c0a5aeac9/44,544,622-->\\n'
        """

        return "".join([tfr.to_html_comment() for tfr in data.values()])

    @classmethod
    def parse(cls, string: str) -> dict[str, "TestingFarmRequest"]:
        """Extracts and sanitizes testing_farm requests from a text comment and returns a
        dictionary with chroots as keys and testing-farm request objects as values.

        If a chroot doesn't have the chroot format it won't be in the dictionary.
        If a request ID doesn't have the proper format, the chroot won't be added to the dictionary.
        If the comment body contains more than one entry for a the same chroot, the last one will be taken.

        Args:
            comment_body (str): Arbitrary text, e.g. a github comment body that contains invisible (HTML) comments.

        Returns:
            dict: A dictionary with chroots as keys and testing-farm request objects as values

        Example:

        >>> s='''
        ... Bla bla <!--TESTING_FARM:fedora-rawhide-x86_64/271a79e8-fc9a-4e1d-95fe-567cc9d62ad4/1,2,3--> bla bla
        ... Foo bar. <!--TESTING_FARM:fedora-39-x86_64/11111111-fc9a-4e1d-95fe-567cc9d62ad4/4--> fjjd
        ... Foo BAR. <!--TESTING_FARM:fedora-39-x86_64/22222222-fc9a-4e1d-95fe-567cc9d62ad4/5,6,7--> fafa
        ... Foo bAr. <!--TESTING_FARM:invalid-chroot/33333333-fc9a-4e1d-95fe-567cc9d62ad4/8,9,10--> fafa
        ... FOO bar. <!--TESTING_FARM: fedora-40-x86_64/; cat /tmp/secret/file/11--> fafa
        ... FOO bar. <!--TESTING_FARM: fedora-40-x86_64/33333333-fc9a-4e1d-95fe-567cc9d62ad4/12,13,14--> fafa
        ... This next request ID is missing build IDs. We allow it because there used to be comment IDs
        ... that didn't have these IDs.
        ... FOO bar. <!--TESTING_FARM: fedora-38-x86_64/44444444-fc9a-4e1d-95fe-567cc9d62ad4--> fafa
        ... '''
        >>> requests = TestingFarmRequest.parse(s)
        >>> keys = requests.keys()
        >>> keys
        dict_keys(['fedora-rawhide-x86_64', 'fedora-39-x86_64', 'fedora-40-x86_64', 'fedora-38-x86_64'])
        >>> requests['fedora-rawhide-x86_64']
        TestingFarmRequest(request_id=UUID('271a79e8-fc9a-4e1d-95fe-567cc9d62ad4'), chroot='fedora-rawhide-x86_64', copr_build_ids=[1, 2, 3])
        >>> requests['fedora-39-x86_64']
        TestingFarmRequest(request_id=UUID('22222222-fc9a-4e1d-95fe-567cc9d62ad4'), chroot='fedora-39-x86_64', copr_build_ids=[5, 6, 7])
        >>> requests['fedora-40-x86_64']
        TestingFarmRequest(request_id=UUID('33333333-fc9a-4e1d-95fe-567cc9d62ad4'), chroot='fedora-40-x86_64', copr_build_ids=[12, 13, 14])
        >>> requests['fedora-38-x86_64']
        TestingFarmRequest(request_id=UUID('44444444-fc9a-4e1d-95fe-567cc9d62ad4'), chroot='fedora-38-x86_64', copr_build_ids=[])
        """
        matches = re.findall(r"<!--TESTING_FARM:([^/]+)/([^/]+)(/([^/]+))?-->", string)
        if not matches:
            logging.info("No testing-farm requests found to recover.")
            return None

        res: dict[str, TestingFarmRequest] = {}
        for match in matches:
            try:
                chroot = util.expect_chroot(str(match[0]).strip())
                tfr = TestingFarmRequest(
                    chroot=chroot,
                    request_id=sanitize_request_id(str(match[1])),
                    copr_build_ids=[],
                )
                if match[3]:
                    tfr.copr_build_ids = [
                        int(item.strip()) for item in match[3].split(",")
                    ]
                res[chroot] = tfr
                logging.info(f"Added testing-farm request: {tfr}")
            except ValueError as e:
                logging.info(f"ignoring: {match} : {str(e)}")

        logging.info(f"Recovered testing-farm-requests: {res}")
        return res

    @classmethod
    def make(
        cls,
        config: config.Config,
        issue: github.Issue.Issue,
        chroot: str,
        copr_build_ids: list[int],
    ) -> "TestingFarmRequest":
        """Runs a "testing-farm request" command and returns a TestingFarmRequest object.

        The request is made without waiting for the result.
        It is the responsibility of the caller of this function to run "testing-farm watch --id <REQUEST_ID>",
        where "<REQUEST_ID>" is part of the result object of this function.

        Depending on the chroot, we'll automatically select the proper testing-farm ranch for you.
        For this to work you'll have to set the
        TESTING_FARM_API_TOKEN_PUBLIC_RANCH and
        TESTING_FARM_API_TOKEN_REDHAT_RANCH
        environment variables. We'll then use one of them to set the TESTING_FARM_API_TOKEN
        environment variable for the actual call to testing-farm.

        Args:
            chroot (str): The chroot that you want to run tests for.

        Raises:
            SystemError: When the testing-farm request failed

        Returns:
            TestingFarmRequest: testing-farm request object
        """
        logging.info(f"Kicking off new tests for chroot {chroot}.")

        ranch = cls.select_ranch(chroot)

        if not cls.is_chroot_supported(chroot=chroot, ranch=ranch):
            raise ValueError(
                f"Chroot {chroot} has an unsupported architecture on ranch {ranch}"
            )

        logging.info(f"Using testing-farm ranch: {ranch}")
        if ranch == "public":
            os.environ["TESTING_FARM_API_TOKEN"] = os.getenv(
                "TESTING_FARM_API_TOKEN_PUBLIC_RANCH", "MISSING_ENV"
            )
        if ranch == "redhat":
            os.environ["TESTING_FARM_API_TOKEN"] = os.getenv(
                "TESTING_FARM_API_TOKEN_REDHAT_RANCH", "MISSING_ENV"
            )
        cmd = f"""testing-farm \
            request \
            --compose {cls.get_compose(chroot=chroot)} \
            --git-url {config.test_repo_url} \
            --arch {util.chroot_arch(chroot)} \
            --plan /tests/snapshot-gating \
            --environment COPR_PROJECT={config.copr_projectname} \
            --context distro={util.chroot_os(chroot)} \
            --context arch={util.chroot_arch(chroot)} \
            --no-wait \
            --user-webpage={issue.html_url} \
            --user-webpage-name="GitHub Issue: {issue.title}" \
            --user-webpage-icon="https://github.com/fedora-llvm-team/llvm-snapshots/blob/main/media/github-mark.png?raw=true" \
            --context snapshot={config.yyyymmdd}"""
        exit_code, stdout, stderr = util.run_cmd(cmd, timeout_secs=None)
        if exit_code == 0:
            return TestingFarmRequest(
                request_id=cls.parse_output_for_request_id(stdout),
                copr_build_ids=copr_build_ids,
                chroot=chroot,
            )
        raise SystemError(
            f"failed to run 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
        )

    def watch(self) -> tuple["TestingFarmWatchResult", str]:
        request_id = sanitize_request_id(request_id=self.request_id)
        cmd = f"testing-farm watch --no-wait --id {self.request_id}"
        # We ignore the exit code because in case of a test error, 1 is the exit code
        _, stdout, stderr = util.run_cmd(cmd=cmd)
        watch_result, artifacts_url = TestingFarmWatchResult.from_output(stdout)
        if watch_result is None:
            raise SystemError(
                f"failed to watch 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
            )
        return (watch_result, artifacts_url)

    @classmethod
    def select_ranch(cls, chroot: str) -> str:
        """Depending on the chroot, we decide if we build in the public or redhat testing ranch

        Args:
            chroot (str): chroot to use for determination of ranch

        Returns:
            str: "public", "private" or None

        Examples:

        >>> TestingFarmRequest.select_ranch("fedora-rawhide-x86_64")
        'public'

        >>> TestingFarmRequest.select_ranch("fedora-40-aarch64")
        'public'

        >>> TestingFarmRequest.select_ranch("rhel-9-x86_64")
        'redhat'

        >>> TestingFarmRequest.select_ranch("fedora-rawhide-s390x")
        'redhat'

        >>> TestingFarmRequest.select_ranch("fedora-rawhide-ppc64le")
        'redhat'

        >>> TestingFarmRequest.select_ranch("fedora-rawhide-i386")
        'redhat'
        """
        util.expect_chroot(chroot)
        ranch = None
        if re.search(r"(x86_64|aarch64)$", chroot):
            ranch = "public"
        if re.search(r"(^rhel|(ppc64le|s390x|i386)$)", chroot):
            ranch = "redhat"
        return ranch

    @classmethod
    def is_chroot_supported(cls, chroot: str, ranch: str | None = None) -> bool:
        if ranch is None:
            ranch = cls.select_ranch(chroot=chroot)
        return cls.is_arch_supported(arch=util.chroot_arch(chroot), ranch=ranch)

    @classmethod
    def parse_output_for_request_id(cls, string: str) -> uuid.UUID:
        """Takes in the stdout from a "testing-farm request" command and returns
        the request ID to be used for watching the request.

        Args:
            string (str): A "testing-farm request" output.

        Raises:
            ValueError: If string is not a "testing-farm request" output with the
            proper line in it, an exception is raised

        Example:

        >>> s='''8J+TpiByZXBvc2l0b3J5IGh0dHBzOi8vZ2l0aHViLmNvbS9mZWRvcmEtbGx2bS10ZWFtL2xsdm0t
        ... c25hcHNob3RzIHJlZiBtYWluIHRlc3QtdHlwZSBmbWYK8J+SuyBGZWRvcmEtMzkgb24geDg2XzY0
        ... IArwn5SOIGFwaSBodHRwczovL2FwaS5kZXYudGVzdGluZy1mYXJtLmlvL3YwLjEvcmVxdWVzdHMv
        ... MjcxYTc5ZTgtZmM5YS00ZTFkLTk1ZmUtNTY3Y2M5ZDYyYWQ0CvCfkbYgcmVxdWVzdCBpcyB3YWl0
        ... aW5nIHRvIGJlIHF1ZXVlZAo='''
        >>> import base64
        >>> s = base64.b64decode(s).decode()
        >>> TestingFarmRequest.parse_output_for_request_id(s)
        UUID('271a79e8-fc9a-4e1d-95fe-567cc9d62ad4')
        """
        string = clean_testing_farm_output(string)
        match = regex.search(pattern=r"api https:.*/requests/\K.*", string=string)
        if not match:
            raise ValueError(
                f"string doesn't look not a 'testing-farm request' output: {string}"
            )
        return uuid.UUID(match[0])

    @classmethod
    def is_arch_supported(cls, arch: str, ranch: str) -> bool:
        """Returns True if the architecture is supported by testing-farm.

        See https://docs.testing-farm.io/Testing%20Farm/0.1/test-environment.html#_supported_architectures

        Args:
            arch (str): Architecture string (e.g. "x86_64")
            ranch (str): "public" or "redhat"

        Raises:
            ValueError: if the ranch is not "public" or "redhat"

        Returns:
            bool: if the architecture is supported on the given ranch

        Examples:

        >>> TestingFarmRequest.is_arch_supported("i386", "public")
        False

        >>> TestingFarmRequest.is_arch_supported("i386", "redhat")
        False

        >>> TestingFarmRequest.is_arch_supported("x86_64", "public")
        True
        """
        if arch == "i386":
            return False
        if ranch == "public":
            if not arch in ("x86_64", "aarch64"):
                return False
        elif ranch == "redhat":
            if not arch in ("x86_64", "aarch64", "ppc64le", "s390x"):
                return False
        else:
            raise ValueError(f"unknown ranch: {ranch}")
        return True

    @classmethod
    def get_compose(cls, chroot: str) -> str:
        """
        Returns the testing farm compose for the given chroot

        For the redhat ranch see this list: https://api.testing-farm.io/v0.1/composes/redhat
        For the public ranch see this list: https://api.testing-farm.io/v0.1/composes/public

        Examples:

        >>> TestingFarmRequest.get_compose("fedora-rawhide-x86_64")
        'Fedora-Rawhide'
        >>> TestingFarmRequest.get_compose("fedora-39-x86_64")
        'Fedora-39'
        >>> TestingFarmRequest.get_compose("rhel-9-aarch")
        'RHEL-9-Nightly'
        """
        util.expect_chroot(chroot)

        if util.chroot_name(chroot) == "rhel":
            return f"RHEL-{util.chroot_version(chroot)}-Nightly"

        if util.chroot_version(chroot) == "rawhide":
            return "Fedora-Rawhide"
        return util.chroot_os(chroot).capitalize()

    def fetch_failed_test_cases(
        self, artifacts_url_origin: str
    ) -> list["FailedTestCase"]:
        request_file = self.get_request_file()
        xunit_file = self.get_xunit_file(request_file=request_file)
        # The xunit file is None, if it is only available internally.
        if xunit_file is None:
            return []
        return self.get_failed_test_cases_from_xunit_file(
            xunit_file=xunit_file, artifacts_url_origin=artifacts_url_origin
        )

    def get_request_file(self) -> pathlib.Path:
        result_url = f"https://api.testing-farm.io/v0.1/requests/{self.request_id}"
        logging.info(
            f"Fetching request file for request ID {self.request_id} from URL: {result_url}"
        )
        return util.read_url_response_into_file(result_url)

    def get_xunit_file(self, request_file: pathlib.Path) -> pathlib.Path | None:
        result_json = json.loads(request_file.read_text())
        if "result" not in result_json:
            raise KeyError("failed to find 'result' key in JSON result response")
        if "xunit_url" not in result_json["result"]:
            raise KeyError("failed to find 'xunit_url' key in result dict response")
        xunit_url = result_json["result"]["xunit_url"]

        # Get xunit file to log all testcases that have errors
        if self.url_inside_redhat(xunit_url):
            logging.info(
                f"Not getting xunit file from testing-farm results inside redhat: {xunit_url}"
            )
            return None

        logging.info(
            f"Fetching xunit URL for request ID {self.request_id} from URL: {xunit_url}"
        )
        return util.read_url_response_into_file(xunit_url)

    def get_failed_test_cases_from_xunit_file(
        self, xunit_file: pathlib.Path, artifacts_url_origin: str
    ) -> list["FailedTestCase"]:
        res: list["FailedTestCase"] = []

        tree = ET.parse(xunit_file)
        root = tree.getroot()
        # see https://docs.python.org/3/library/xml.etree.elementtree.html#example
        failed_testcases = root.findall('./testsuite/testcase[@result="failed"]')

        for failed_testcase in failed_testcases:
            distro = failed_testcase.find(
                './properties/property[@name="baseosci.distro"]'
            ).get("value")
            arch = failed_testcase.find(
                './properties/property[@name="baseosci.arch"]'
            ).get("value")
            log_output_url = failed_testcase.find(
                './logs/log[@name="testout.log"]'
            ).get("href")

            log_file = util.read_url_response_into_file(log_output_url)
            tc = FailedTestCase(
                test_name=failed_testcase.get("name"),
                log_output_url=log_output_url,
                log_output=log_file.read_text(),
                request_id=self.request_id,
                chroot=f"{distro.lower()}-{arch}",
                artifacts_url=artifacts_url_origin,
            )
            res.append(tc)
        return res

    @classmethod
    def url_inside_redhat(cls, url: str) -> bool:
        """Returns True if the url is only accessible from within the Red Hat VPN.

        Examples:

        >>> TestingFarmRequest.url_inside_redhat("https://artifacts.dev.testing-farm.io/ebadbef5-aca9-455f-b458-c245f928ca7d")
        False

        >>> TestingFarmRequest.url_inside_redhat("http://artifacts.osci.redhat.com/testing-farm/8cd428b8-4ea7-43f4-b405-bda8dc93839f/results.xml")
        True
        """
        return urllib.parse.urlparse(url).hostname == "artifacts.osci.redhat.com"


@enum.unique
class TestingFarmWatchResult(enum.StrEnum):
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
    def all_watch_results(cls) -> list["TestingFarmWatchResult"]:
        return [s for s in TestingFarmWatchResult]

    @property
    def is_complete(self) -> bool:
        """Returns True if the watch result indicates that the testing-farm
        request has been completed.

        Examples:

        >>> TestingFarmWatchResult("tests failed").is_complete
        True

        >>> TestingFarmWatchResult("request is queued").is_complete
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

        >>> TestingFarmWatchResult("tests failed").is_complete
        True

        >>> TestingFarmWatchResult("request is queued").is_complete
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
        """_summary_

        Args:
            string (str): _description_

        Returns:
            bool: _description_

        Examples:

        >>> TestingFarmWatchResult.is_watch_result('foo')
        False

        >>> TestingFarmWatchResult.is_watch_result('tests failed')
        True
        """
        return string in cls.all_watch_results()

    @classmethod
    def from_output(cls, string: str) -> tuple["TestingFarmWatchResult", str]:
        """Inspects the output of a testing-farm watch call and returns a tuple of result and artifacts url (if any).

        Args:
            string (str): The output of a testing-farm watch call.

        Returns:
            tuple[str, TestingFarmWatchResult]: _description_

        Examples:
        >>> s='''8J+UjiBhcGkgaHR0cHM6Ly9hcGkuZGV2LnRlc3RpbmctZmFybS5pby92MC4xL3JlcXVlc3RzLzI3
        ... MWE3OWU4LWZjOWEtNGUxZC05NWZlLTU2N2NjOWQ2MmFkNArwn5qiIGFydGlmYWN0cyBodHRwOi8v
        ... YXJ0aWZhY3RzLm9zY2kucmVkaGF0LmNvbS90ZXN0aW5nLWZhcm0vMjcxYTc5ZTgtZmM5YS00ZTFk
        ... LTk1ZmUtNTY3Y2M5ZDYyYWQ0CuKdjCB0ZXN0cyBlcnJvcgpOb25lCg=='''
        >>> import base64
        >>> s = base64.b64decode(s).decode()
        >>> TestingFarmWatchResult.from_output(s)
        (<TestingFarmWatchResult.TESTS_ERROR: 'tests error'>, 'http://artifacts.osci.redhat.com/testing-farm/271a79e8-fc9a-4e1d-95fe-567cc9d62ad4')
        >>> s='''8J+UjiBhcGkgaHR0cHM6Ly9hcGkuZGV2LnRlc3RpbmctZmFybS5pby92MC4xL3JlcXVlc3RzLzcy
        ... ZWZiYWZjLTdkYjktNGUwNS04NTZjLTg3MzExNGE5MjQzNQrwn5ObIHBpcGVsaW5lIGVycm9yCkd1
        ... ZXN0IGNvdWxkbid0IGJlIHByb3Zpc2lvbmVkOiBBcnRlbWlzIHJlc291cmNlIGVuZGVkIGluICdl
        ... cnJvcicgc3RhdGUKCg=='''
        >>> s = base64.b64decode(s).decode()
        >>> TestingFarmWatchResult.from_output(s)
        (<TestingFarmWatchResult.PIPELINE_ERROR: 'pipeline error'>, None)
        """
        string = clean_testing_farm_output(string)
        for watch_result in TestingFarmWatchResult.all_watch_results():
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


def render_html(
    request: TestingFarmRequest,
    watch_result: TestingFarmWatchResult,
    artifacts_url: str | None,
) -> str:
    title = f"{watch_result.to_icon()} {watch_result}"
    if artifacts_url is None:
        return title
    vpn = ""
    if TestingFarmRequest.select_ranch(request.chroot) == "redhat":
        vpn = " :lock: "
    return f'<a href="{artifacts_url}">{title}{vpn}</a>'


def sanitize_request_id(request_id: str | uuid.UUID) -> uuid.UUID:
    """Sanitizes a testing-farm request ID by ensuring that it is a UUID.

    Args:
        request_id (str | uuid.UUID): A testing-farm request ID

    Raises:
        ValueError: if the given string is not in the right format

    Returns:
        uuid.UUID: the uuid object that matched the pattern

    Examples:

    >>> sanitize_request_id(request_id="271a79e8-fc9a-4e1d-95fe-567cc9d62ad4")
    UUID('271a79e8-fc9a-4e1d-95fe-567cc9d62ad4')

    >>> import uuid
    >>> sanitize_request_id(uuid.UUID('271a79e8-fc9a-4e1d-95fe-567cc9d62ad5'))
    UUID('271a79e8-fc9a-4e1d-95fe-567cc9d62ad5')

    >>> sanitize_request_id(request_id="; cat /etc/passwd")
    Traceback (most recent call last):
     ...
    ValueError: string is not a valid testing-farm request ID: badly formed hexadecimal UUID string
    """
    if isinstance(request_id, uuid.UUID):
        return request_id
    res: uuid.UUID = None
    try:
        res = uuid.UUID(request_id)
    except Exception as e:
        raise ValueError(f"string is not a valid testing-farm request ID: {e}")
    return res


def clean_testing_farm_output(mystring: str) -> str:
    """Returns a string with only printable characters.

    Args:
        mystring (str): The output of a testing-farm CLI command

    Returns:
        str: The same as the input but without anything that's not printable.
    """
    return "".join(filter(lambda x: x in string.printable, mystring))


@dataclasses.dataclass(kw_only=True, unsafe_hash=True, frozen=True)
class FailedTestCase:
    """The FailedTestCase class represents a test from the testing-farm artifacts page"""

    test_name: str
    request_id: str
    chroot: str
    log_output_url: str
    log_output: str = None
    artifacts_url: str

    @classmethod
    def shorten_test_output(cls, log_output: str) -> str:
        """Remove cmake configure and build output"""
        log_output = re.sub(
            r"-- .*", "[... CMAKE CONFIGURE LOG SHORTENED ...]", log_output, 1
        )
        log_output = re.sub(r"-- .*\n", "", log_output)
        log_output = re.sub(
            r"\[\d+/\d+\] .*", "[... CMAKE BUILD LOG SHORTENED ...]", log_output, 1
        )
        log_output = re.sub(r"\[\d+/\d+\] .*\n", "", log_output)
        return log_output

    def render_as_markdown(self) -> str:
        return f"""
<details>
<summary>
<code>{self.test_name}</code> on <code>{self.chroot}</code> (see <a href="{self.artifacts_url}">testing-farm artifacts</a>)
</summary>

```
{self.shorten_test_output(self.log_output)}
```

</details>
"""

    @classmethod
    def render_list_as_markdown(cls, test_cases: list["FailedTestCase"]) -> str:
        if len(test_cases) == 0:
            return ""

        return f"""
{results_html_comment()}

<h1><img src="https://github.com/fedora-llvm-team/llvm-snapshots/blob/main/media/tft-logo.png?raw=true" width="42" /> Testing-farm results are in!</h1>

<p><b>Last updated: {datetime.datetime.now().isoformat()}</b></p>

Some (if not all) results from testing-farm are in. This comment will be updated over time and is detached from the main issue comment because we want to preserve the logs entirely and not shorten them.

> [!NOTE]
> Please be aware that the testing-farm artifact links a valid for no longer than 90 days. That is why we persists the log outputs here.

> [!WARNING]
> This list is not extensive if tests have been run in the Red Hat internal testing-farm ranch and failed. For those, take a look in the "chroot" column of the build matrix above and look for failed tests that show a :lock: symbol.

<h2>Failed testing-farm test cases</h2>

{"".join([ test_case.render_as_markdown() for test_case in test_cases ])}
"""


def results_html_comment() -> str:
    """Returns an HTML comment that must be present in a GitHub comment to be
    considered for storing the testing-farm results."""
    return "<!--TESTING_FARM_RESULTS-->"
