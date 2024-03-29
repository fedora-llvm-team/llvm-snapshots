"""
testing_farm_util
"""

import enum
import logging
import re
import string
import uuid
import os
import json
import re

import regex

import snapshot_manager.util as util
import snapshot_manager.config as config


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

    @classmethod
    def all_watch_results(cls) -> list["TestingFarmWatchResult"]:
        return [s for s in TestingFarmWatchResult]

    @property
    def is_complete(self) -> bool:
        """Returns True if the watch result indicates that the testing-farm
        request has been completed. The outcome doesn't matter.
        """
        if self.value in [
            self.REQUEST_WAITING_TO_BE_QUEUED,
            self.REQUEST_QUEUED,
            self.REQUEST_RUNNING,
        ]:
            return False
        return True

    @property
    def expect_artifacts_url(self) -> bool:
        """Returns True if for the watch result we can expect and artifacts URL in the watch output."""
        if self.value in [self.REQUEST_WAITING_TO_BE_QUEUED, self.REQUEST_QUEUED]:
            return False
        return True

    def is_watch_result(self, string: str) -> bool:
        return string in self.all_watch_results()


def select_ranch(chroot: str) -> str:
    """Depending on the chroot, we decide if we build in the public or redhat testing ranch

    Args:
        chroot (str): chroot to use for determination of ranch

    Returns:
        str: "public", "private" or None

    Examples:

    >>> select_ranch("fedora-rawhide-x86_64")
    'public'

    >>> select_ranch("fedora-40-aarch64")
    'public'

    >>> select_ranch("rhel-9-x86_64")
    'redhat'

    >>> select_ranch("fedora-rawhide-s390x")
    'redhat'

    >>> select_ranch("fedora-rawhide-ppc64le")
    'redhat'

    >>> select_ranch("fedora-rawhide-i386")
    'redhat'
    """
    util.expect_chroot(chroot)
    ranch = None
    if re.search(r"(x86_64|aarch64)$", chroot):
        ranch = "public"
    if re.search(r"(^rhel|(ppc64le|s390x|i386)$)", chroot):
        ranch = "redhat"
    return ranch


def parse_comment_for_request_ids(comment_body: str) -> dict:
    """Extracts and sanitizes testing_farm requests from a github comment and returns a
    dictionary with chroots as keys and testing-farm request IDs as values.

    If a chroot doesn't have the chroot format it won't be in the dictionary.
    If a request ID doesn't have the proper format, the chroot won't be added to the dictionary.
    If the comment body contains more than one entry for a the same chroot, the last one will be taken.

    Args:
        comment_body (str): A github comment body that contains invisible (HTML) comments.

    Returns:
        dict: A dictionary with chroots as keys and testing-farm request IDs as values

    Example:

    >>> comment_body='''
    ... Bla bla <!--TESTING_FARM:fedora-rawhide-x86_64/271a79e8-fc9a-4e1d-95fe-567cc9d62ad4--> bla bla
    ... Foo bar. <!--TESTING_FARM:fedora-39-x86_64/11111111-fc9a-4e1d-95fe-567cc9d62ad4--> fjjd
    ... Foo BAR. <!--TESTING_FARM:fedora-39-x86_64/22222222-fc9a-4e1d-95fe-567cc9d62ad4--> fafa
    ... Foo bAr. <!--TESTING_FARM:invalid-chroot/33333333-fc9a-4e1d-95fe-567cc9d62ad4--> fafa
    ... FOO bar. <!--TESTING_FARM: fedora-40-x86_64/; cat /tmp/secret/file--> fafa
    ... FOO bar. <!--TESTING_FARM: fedora-40-x86_64/33333333-fc9a-4e1d-95fe-567cc9d62ad4--> fafa
    ... '''
    >>> parse_comment_for_request_ids(comment_body=comment_body)
    {'fedora-rawhide-x86_64': '271a79e8-fc9a-4e1d-95fe-567cc9d62ad4', 'fedora-39-x86_64': '22222222-fc9a-4e1d-95fe-567cc9d62ad4', 'fedora-40-x86_64': '33333333-fc9a-4e1d-95fe-567cc9d62ad4'}
    """
    testing_farm_requests = dict()
    for ci in [
        comb.split("/")
        for comb in re.findall(r"<!--TESTING_FARM:(.*?)-->", comment_body)
    ]:
        try:
            chroot = util.expect_chroot(ci[0]).strip()
            request_id = sanitize_request_id(ci[1]).strip()
            testing_farm_requests[chroot] = request_id
        except ValueError as e:
            logging.info(f"ignoring: {ci[0]} and {ci[1]} {str(e)}")
    return testing_farm_requests


def sanitize_request_id(request_id: str) -> str:
    """Sanitizes a testing-farm request ID by ensuring that it matches a pattern.

    Args:
        request_id (str): A testing-farm request ID

    Raises:
        ValueError: if the given string is not in the right format

    Returns:
        str: the string that matched the pattern

    Examples:

    >>> sanitize_request_id(request_id="271a79e8-fc9a-4e1d-95fe-567cc9d62ad4")
    '271a79e8-fc9a-4e1d-95fe-567cc9d62ad4'

    >>> sanitize_request_id(request_id="; cat /etc/passwd")
    Traceback (most recent call last):
     ...
    ValueError: string is not a valid testing-farm request ID: badly formed hexadecimal UUID string
    """
    try:
        res = uuid.UUID(request_id)
    except Exception as e:
        raise ValueError(f"string is not a valid testing-farm request ID: {e}")
    return request_id


def clean_testing_farm_output(mystring: str) -> str:
    """Returns a string with only printable characters.

    Args:
        mystring (str): The output of a testing-farm CLI command

    Returns:
        str: The same as the input but without anything that's not printable.
    """
    return "".join(filter(lambda x: x in string.printable, mystring))


def parse_output_for_request_id(string: str) -> str:
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
    >>> parse_output_for_request_id(s)
    '271a79e8-fc9a-4e1d-95fe-567cc9d62ad4'
    """
    string = clean_testing_farm_output(string)
    match = regex.search(pattern=r"api https:.*/requests/\K.*", string=string)
    if not match:
        raise ValueError(
            f"string doesn't look not a 'testing-farm request' output: {string}"
        )
    return str(match[0])


def parse_for_watch_result(string: str) -> tuple[TestingFarmWatchResult, str]:
    """Inspects the output of a testing-farm watch call and returns a tuple of result and artifacts url (if any).

    Args:
        string (str): The output of a testing-farm watch call.

    Returns:
        tuple[str, TestingFarmWatchResult]: _description_

    Example:
    >>> s='''8J+UjiBhcGkgaHR0cHM6Ly9hcGkuZGV2LnRlc3RpbmctZmFybS5pby92MC4xL3JlcXVlc3RzLzI3
    ... MWE3OWU4LWZjOWEtNGUxZC05NWZlLTU2N2NjOWQ2MmFkNArwn5qiIGFydGlmYWN0cyBodHRwOi8v
    ... YXJ0aWZhY3RzLm9zY2kucmVkaGF0LmNvbS90ZXN0aW5nLWZhcm0vMjcxYTc5ZTgtZmM5YS00ZTFk
    ... LTk1ZmUtNTY3Y2M5ZDYyYWQ0CuKdjCB0ZXN0cyBlcnJvcgpOb25lCg=='''
    >>> import base64
    >>> s = base64.b64decode(s).decode()
    >>> parse_for_watch_result(s)
    (<TestingFarmWatchResult.TESTS_ERROR: 'tests error'>, 'http://artifacts.osci.redhat.com/testing-farm/271a79e8-fc9a-4e1d-95fe-567cc9d62ad4')
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


def chroot_request_ids_to_html_comment(data: dict) -> str:
    """Converts the data dictionary of chroot -> request ID pairs to html comments.

    Example:

    >>> chroot_request_ids_to_html_comment({"foo": "bar", "hello": "world", "abra": "kadabra"})
    '<!--TESTING_FARM:foo/bar--><!--TESTING_FARM:hello/world--><!--TESTING_FARM:abra/kadabra-->'
    """
    res: list[str] = []
    for key in data.keys():
        res.append(f"<!--TESTING_FARM:{key}/{data[key]}-->")
    return "".join(res)


def watch_testing_farm_request(request_id: str) -> tuple[TestingFarmWatchResult, str]:
    request_id = sanitize_request_id(request_id=request_id)
    cmd = f"testing-farm watch --no-wait --id {request_id}"
    # We ignore the exit code because in case of a test error, 1 is the exit code
    _, stdout, stderr = util.run_cmd(cmd=cmd)
    watch_result, artifacts_url = parse_for_watch_result(stdout)
    if watch_result is None:
        raise SystemError(
            f"failed to watch 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
        )
    return (watch_result, artifacts_url)


def is_arch_supported(arch: str, ranch: str) -> bool:
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

    >>> is_arch_supported("i386", "public")
    False

    >>> is_arch_supported("i386", "redhat")
    False

    >>> is_arch_supported("x86_64", "public")
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


def is_chroot_supported(chroot: str, ranch: str | None = None) -> bool:
    if ranch is None:
        ranch = select_ranch(chroot=chroot)
    return is_arch_supported(arch=util.chroot_arch(chroot), ranch=ranch)


def make_testing_farm_request(config: config.Config, chroot: str) -> str:
    """Runs a "testing-farm request" command and returns the request ID.

    The request is made without waiting for the result.
    It is the responsibility of the caller of this function to run "testing-farm watch --id <REQUEST_ID>",
    where "<REQUEST_ID>" is the result of this function.

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
        str: Request ID
    """
    logging.info(f"Kicking off new tests for chroot {chroot}.")

    ranch = select_ranch(chroot)

    if not is_chroot_supported(chroot=chroot, ranch=ranch):
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
        --compose {get_compose(ranch)} \
        --git-url {config.test_repo_url} \
        --arch {util.chroot_arch(chroot)} \
        --plan /tests/snapshot-gating \
        --environment COPR_PROJECT={config.copr_projectname} \
        --context distro={util.chroot_os(chroot)} \
        --context arch={util.chroot_arch(chroot)} \
        --no-wait \
        --context snapshot={config.yyyymmdd}"""
    exit_code, stdout, stderr = util.run_cmd(cmd, timeout_secs=None)
    if exit_code == 0:
        return parse_output_for_request_id(stdout)
    raise SystemError(
        f"failed to run 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
    )


def get_compose(ranch: str) -> str:
    """Returns the N-1 Fedora version supported on the given ranch.

    When N is the latest Fedora version, we use the N-1 version to be safe.
    If there's no N-1, we return the latest Fedora version N.

    Args:
        ranch (str): "public" or "redhat"

    Raises:
        ValueError: if the ranch isn't "public" or "redhat"

    Returns:
        str: The preferred compose for the given ranch

    Examples:

    >>> get_compose("public")
    'Fedora-39'
    >>> get_compose("public")
    'Fedora-39'

    >>> get_compose("redhat")
    'Fedora-39'
    """

    def get_composes(url: str) -> list[str]:
        logging.info(f"Parsing URL for composes: {url}")
        file = util.read_url_response_into_file(url)
        res = json.loads(file.read_text())
        composes = [
            compose["name"]
            for compose in res["composes"]
            if re.match(pattern="^Fedora-[0-9]+$", string=compose["name"])
        ]
        composes.sort(reverse=True)
        return composes

    composes = []
    if ranch == "redhat":
        if not hasattr(get_compose, "composes_cache_redhat"):
            get_compose.composes_cache_redhat = get_composes(
                url="https://api.testing-farm.io/v0.1/composes/redhat"
            )
        composes = get_compose.composes_cache_redhat
    elif ranch == "public":
        if not hasattr(get_compose, "composes_cache_public"):
            get_compose.composes_cache_public = get_composes(
                url="https://api.testing-farm.io/v0.1/composes/public"
            )
        composes = get_compose.composes_cache_public
    else:
        raise ValueError(f"unknown ranch: {ranch}")

    if len(composes) >= 2:
        return composes[1]
    return composes[0]
