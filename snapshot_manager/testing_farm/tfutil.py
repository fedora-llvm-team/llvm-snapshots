"""TBD"""

import functools
import json
import logging
import os
import pathlib
import re
import string
import urllib.parse
import uuid
import xml.etree.ElementTree as ET

import regex
import requests

import snapshot_manager.util as util

# Set _IN_TEST_MODE to True in for functions that deal with URLs to be able to
# workaround this restriction in unit-tests.
_IN_TEST_MODE = False

# Use this for constructing paths when _IN_TEST_MODE is on
_DIRNAME: str = pathlib.Path(os.path.dirname(__file__))


def _test_path(path: pathlib.Path | str) -> pathlib.Path:
    """Returns the full path to testing farm resource files for tests

    Args:
        path (pathlib.Path | str): path to add to join with prefix

    Returns:
        pathlib.Path: Full path to the given path including the prefix
    """
    if isinstance(path, str):
        path = pathlib.Path(path)

    return _DIRNAME.joinpath(pathlib.Path("../tests/testing-farm-logs/").joinpath(path))


def results_html_comment() -> str:
    """Returns an HTML comment that must be present in a GitHub comment to be
    considered for storing the testing-farm results."""
    return "<!--TESTING_FARM_RESULTS-->"


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


def adjust_token_env(chroot: str) -> None:
    """Adjusts the TESTING_FARM_API_TOKEN env var based on the chroot.
    The next testing-farm command is then set up to work with the correct
    ranch.

    Raises:
        ValueError: if the chroot is not supported by the ranch

    Example:
    """
    ranch = select_ranch(chroot)

    if not is_chroot_supported_by_ranch(chroot=chroot, ranch=ranch):
        raise ValueError(
            f"Chroot {chroot} has an unsupported architecture on ranch {ranch}"
        )

    logging.info(f"Adjusting TESTING_FARM_API_TOKEN for ranch: {ranch}")
    if ranch == "public":
        os.environ["TESTING_FARM_API_TOKEN"] = os.getenv(
            "TESTING_FARM_API_TOKEN_PUBLIC_RANCH", "MISSING_ENV_FOR_PUBLIC_RANCH"
        )
    if ranch == "redhat":
        os.environ["TESTING_FARM_API_TOKEN"] = os.getenv(
            "TESTING_FARM_API_TOKEN_REDHAT_RANCH", "MISSING_ENV_FOR_REDHAT_RANCH"
        )


def parse_output_for_request_id(string: str) -> uuid.UUID:
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
    UUID('271a79e8-fc9a-4e1d-95fe-567cc9d62ad4')
    """
    string = clean_testing_farm_output(string)
    match = regex.search(pattern=r"api https:.*/requests/\K.*", string=string)
    if not match:
        raise ValueError(
            f"string doesn't look not a 'testing-farm request' output: {string}"
        )
    return uuid.UUID(match[0])


def is_chroot_supported_by_ranch(chroot: str, ranch: str | None = None) -> bool:
    if ranch is None:
        ranch = select_ranch(chroot=chroot)
    return is_arch_supported_by_ranch(arch=util.chroot_arch(chroot), ranch=ranch)


def is_arch_supported_by_ranch(arch: str, ranch: str) -> bool:
    """Returns True if the architecture is supported by a testing-farm ranch.

    See https://docs.testing-farm.io/Testing%20Farm/0.1/test-environment.html#_supported_architectures

    Args:
        arch (str): Architecture string (e.g. "x86_64")
        ranch (str): "public" or "redhat"

    Raises:
        ValueError: if the ranch is not "public" or "redhat"

    Returns:
        bool: if the architecture is supported on the given ranch

    Examples:

    >>> is_arch_supported_by_ranch("i386", "public")
    False

    >>> is_arch_supported_by_ranch("i386", "redhat")
    False

    >>> is_arch_supported_by_ranch("x86_64", "public")
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


def get_compose_from_chroot(chroot: str) -> str:
    """
    Returns the testing farm compose for the given chroot

    For the redhat ranch see this list: https://api.testing-farm.io/v0.1/composes/redhat
    For the public ranch see this list: https://api.testing-farm.io/v0.1/composes/public

    Examples:

    >>> get_compose_from_chroot("fedora-rawhide-x86_64")
    'Fedora-Rawhide'
    >>> get_compose_from_chroot("fedora-39-x86_64")
    'Fedora-39'
    >>> get_compose_from_chroot("rhel-9-aarch64")
    'RHEL-9-Nightly'
    >>> get_compose_from_chroot("rhel-8-x86_64")
    'RHEL-8-Nightly'
    >>> get_compose_from_chroot("centos-stream-10-s390x")
    'CentOS-Stream-10'
    """
    util.expect_chroot(chroot)

    if util.chroot_name(chroot) == "rhel":
        return f"RHEL-{util.chroot_version(chroot)}-Nightly"

    if util.chroot_name(chroot) == "centos-stream":
        return f"CentOS-Stream-{util.chroot_version(chroot)}"

    if util.chroot_version(chroot) == "rawhide":
        return "Fedora-Rawhide"
    return util.chroot_os(chroot).capitalize()


def get_request_file(request_id: str) -> pathlib.Path:
    """Downloads the JSON request for a given request ID and returns the path to the downloaded location.

    Args:
        request_id (str): The testing farm request ID

    Returns:
        pathlib.Path: The path to which the JSON request was downloaded.
    """
    result_url = f"https://api.testing-farm.io/v0.1/requests/{request_id}"
    logging.info(
        f"Reading request file for request ID {request_id} from URL: {result_url}"
    )

    if not _IN_TEST_MODE:
        request_file = util.read_url_response_into_file(result_url)
    else:
        request_file = _test_path(f"{request_id}/request.json")
        logging.info(f"Using request file from file: {request_file}")

    return request_file


def get_xunit_file_from_request_file(
    request_file: pathlib.Path, request_id: str
) -> pathlib.Path | None:
    result_json = json.loads(request_file.read_text())
    if "result" not in result_json:
        raise KeyError("failed to find 'result' key in JSON result response")
    if "xunit_url" not in result_json["result"]:
        raise KeyError("failed to find 'xunit_url' key in result dict response")
    xunit_url = result_json["result"]["xunit_url"]

    # Get xunit file to log all testcases that have errors
    if not is_url_expectably_reachable(xunit_url):
        logging.info(
            f"Not getting expectably unreachable xunit file from testing-farm: {xunit_url}"
        )
        return None

    logging.info(f"Fetching xunit URL from URL: {xunit_url}")

    if not _IN_TEST_MODE:
        xuint_file = util.read_url_response_into_file(xunit_url)
    else:
        xuint_file = _test_path(f"{request_id}/xunit.xml")
        logging.info(f"Using xunit URL from file: {xuint_file}")
    return xuint_file


def get_testsuite_data_url_from_xunit_file(xunit_file: pathlib.Path) -> str:
    """
    Returns the data URL for the whole test suite (not just for a single test case).

    >>> get_testsuite_data_url_from_xunit_file(xunit_file=_DIRNAME.joinpath("../tests/testing-farm-logs/e388863b-e123-44fd-b832-ef26486344fd/xunit.xml"))
    'https://artifacts.dev.testing-farm.io/e388863b-e123-44fd-b832-ef26486344fd/work-compare-compile-timewt7dlmkf/tests/compare-compile-time/data'
    """
    tree = ET.parse(xunit_file)
    root = tree.getroot()
    # see https://docs.python.org/3/library/xml.etree.elementtree.html#example
    log_ele = root.find('./testsuite/logs/log[@name="data"]')
    if log_ele is not None:
        return log_ele.get(key="href", default="")
    return ""


def is_url_expectably_reachable(url: str) -> bool:
    """Returns True if the url is expected to be reachable. For internal Red Hat
    URLs we check if Red Hat resources are reachable and adjust the
    expectation accordingly.
    """
    if urllib.parse.urlparse(url).hostname == "artifacts.osci.redhat.com":
        if not is_redhat_reachable():
            return False
    return True


@functools.cache
def is_redhat_reachable() -> bool:
    """Returns True if the Red Hat network is reachable."""
    reachable = False
    try:
        reachable = requests.options("https://artifacts.osci.redhat.com").ok
    except:
        pass
    return reachable


def clean_testing_farm_output(mystring: str) -> str:
    """Returns a string with only printable characters.

    Args:
        mystring (str): The output of a testing-farm CLI command

    Returns:
        str: The same as the input but without anything that's not printable.
    """
    return "".join(filter(lambda x: x in string.printable, mystring))


def select_ranch(chroot: str) -> str:
    """Depending on the chroot, we decide if we build in the public or redhat testing ranch

    Args:
        chroot (str): chroot to use for determination of ranch

    Returns:
        str: "public", "redhat" or None

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

    >>> select_ranch("centos-stream-10-x86_64")
    'public'

    >>> select_ranch("centos-stream-10-ppc64le")
    'redhat'
    """
    util.expect_chroot(chroot)
    ranch = None
    arch = util.chroot_arch(chroot)
    if arch in ["x86_64", "aarch64"]:
        ranch = "public"
    if util.chroot_name(chroot) == "rhel":
        ranch = "redhat"
    if arch in ["ppc64le", "s390x", "i386"]:
        ranch = "redhat"
    return ranch


def remove_chroot_html_comment(comment_body: str, chroot: str):
    """
    Removes any testing-farm HTML comment from an input string that are meant for the given chroot.

    >>> chroot="fedora-40-aarch64"
    >>> req1 = f'<!--TESTING_FARM:{chroot}/68b70645-221d-4391-a918-06db7f414a48/7320315,7320317,7320318,7320316,7320314,7320231,7320313-->'
    >>> req2 = '<!--TESTING_FARM:fedora-40-ppc64le/eee0e5d5-2d7a-4cbd-9b7d-7d60a10c40fe/7320327,7320329,7320330,7320328,7320326,7320231,7320325-->'
    >>> input = f'''foo
    ... {req1}
    ... {req2}
    ... bar'''
    >>> expected = f'''foo
    ...
    ... {req2}
    ... bar'''
    >>> actual = remove_chroot_html_comment(comment_body=input, chroot=chroot)
    >>> actual == expected
    True
    >>> actual = remove_chroot_html_comment(comment_body=input, chroot="rhel-9-x86_64")
    >>> actual == input
    True
    """
    util.expect_chroot(chroot)
    pattern = re.compile(rf"<!--TESTING_FARM:\s*{chroot}/.*?-->")
    return re.sub(pattern=pattern, repl="", string=comment_body)


def get_artifacts_url(chroot: str, request_id: str) -> str:
    """Returns an URL to the artifacts of the testing-farm request ID with the testing-farm ranch determined by the chroot.

    Args:
        chroot (str): The chroot on which the performance test was run
        request_id (str): The request ID used when making the testing-farm request

    Returns:
        str: The URL to the testing-farm artifacts for the given request ID
    """
    ranch = select_ranch(chroot)
    if ranch == "public":
        return f"https://artifacts.dev.testing-farm.io/{request_id}"
    elif ranch == "redhat":
        return f"https://artifacts.osci.redhat.com/testing-farm/{request_id}"
    return ""
