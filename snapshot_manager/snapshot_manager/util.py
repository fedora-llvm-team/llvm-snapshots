"""
util
"""

import datetime
import functools
import logging
import os
import pathlib
import re
import shlex
import subprocess

import regex
import requests

import snapshot_manager.file_access as file_access


def fenced_code_block(
    text: str, prefix: str = "\n```\n", suffix: str = "\n```\n"
) -> str:
    """Returns the text wrapped in a code fence.

    See https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-and-highlighting-code-blocks#fenced-code-blocks

    Args:
        text (str): The text to wrap in a code fence
        prefix (str, optional): Start of the code block. Defaults to "\n```\n".
        suffix (str, optional): End of the code block. Defaults to "\n```\n".

    Returns:
        str: The text to be wrapped in a fenced code block
    """
    return f"{prefix}{text}{suffix}"


def grep_file(
    pattern: str,
    filepath: str | pathlib.Path,
    lines_before: int = 0,
    lines_after: int = 0,
    case_insensitive: bool = True,
    extra_args: str | None = None,
    grep_bin: str = "grep",
) -> tuple[int, str, str]:
    """Runs the grep binary on the filepath and includes lines before and after repsectively.

    Args:
        pattern (str): The pattern to find
        filepath (str | pathlib.Path): The file to search for the pattern
        lines_before (int, optional): Includes N-lines before a given match.. Defaults to 0.
        lines_after (int, optional): Includes N-lines after a given match. Defaults to 0.
        case_insensitive (bool, optional): Ignores cases. Defaults to True.
        extra_args (str | None, optional): A string of grep extra arguments (e.g. "-P"). Defaults to None.
        grep_bin (str, optional): Path to the grep binary. Defaults to "grep".

    Raises:
        ValueError: If the pattern is empty
        ValueError: If the lines_before is negative
        ValueError: If the lines_after is negative

    Returns:
        tuple[int, str, str]: return code, stdout, stderr
    """
    if pattern is None or pattern == "":
        raise ValueError(f"pattern is invalid:{pattern}")

    if lines_before is None or lines_before < 0:
        raise ValueError(f"lines_before must be zero or a positive integer")

    if lines_after is None or lines_after < 0:
        raise ValueError(f"lines_after must be zero or a positive integer")

    opts = []
    if case_insensitive:
        opts.append("-i")
    if lines_before > 0:
        opts.append(f"--before-context={lines_before}")

    if lines_after > 0:
        opts.append(f"--after-context={lines_after}")

    if isinstance(filepath, pathlib.Path):
        filepath = filepath.resolve()

    if extra_args is None:
        extra_args = ""

    cmd = f"{grep_bin} {" ".join(opts)} {extra_args} '{pattern}' {filepath}"
    return run_cmd(cmd)


def run_cmd(cmd: str, timeout_secs: int = 5) -> tuple[int, str, str]:
    """Runs the given command and returns the output (stdout and stderr) if any.

    Args:
        cmd (str): Command to run, e.g. "ls -lha ."

    Returns:
        tuple[int, str, str]: The command exit code and it's stdout and sterr

    Example:

    >>> exit_code, stdout, _ = run_cmd(cmd="echo 'hello'")
    >>> exit_code
    0
    >>> stdout
    'hello\\n'
    """

    proc = subprocess.run(shlex.split(cmd), timeout=timeout_secs, capture_output=True)
    stdout = proc.stdout.decode()
    stderr = proc.stderr.decode()
    exit_code = proc.returncode
    if exit_code != 0:
        logging.debug(
            f"exit code: {proc.returncode} for cmd: {cmd}\n\nstdout={stdout}\n\nstderr={stderr}"
        )

    return exit_code, stdout, stderr


def read_url_response_into_file(url: str, **kw_args) -> pathlib.Path:
    """Fetch the given URL and store it in a temporary file whose name is returned.

    Args:
        url (str): URL to GET

    Returns:
        pathlib.Path: Path object of the temporary file to which the GET response was written to.
    """
    logging.info(f"Getting URL {url}")
    response = requests.get(url)
    return file_access.write_to_temp_file(response.content, **kw_args)


def gunzip(f: tuple[str, pathlib.Path]) -> pathlib.Path:
    """Unzip log file on the fly if we need to"""
    if str(f).endswith(".gz"):
        unzipped_file = str(f).removesuffix(".gz")
        retcode, stdout, stderr = run_cmd(cmd=f"gunzip -kf {f}")
        if retcode != 0:
            raise Exception(f"Failed to gunzip build log '{f}': {stderr}")
        f = unzipped_file
    return pathlib.Path(str(f))


def shorten_text(text: str, max_length: int = 3000) -> str:
    """Truncates the given text to at most max_length.

    If we don't shorten log snippets, the github comment body will
    be too long for a github comment.

    Args:
        text (str): Text to shorten
        max_length (int, optional): Max. number of bytes to shorten to. Defaults to 3000.
    """
    return text[:max_length]


def golden_file_path(basename: str, extension: str = ".golden.txt") -> pathlib.Path:
    path = os.path.join(
        pathlib.Path(__file__).parent.parent.absolute(),
        "tests",
        "test_logs",
        f"{basename}{extension}",
    )
    return pathlib.Path(path)


def get_yyyymmdd_from_string(string: str) -> str:
    """Returns the year-month-day combination in YYYYMMDD form from
    `string` or raises an error.

    Args:
        string (str): e.g. the title of a github issue

    Raises:
        ValueError: If `string` doesn't contain proper YYYYMMDD string
        ValueError: If the date in the title is invalid

    Returns:
        str: The year-month-day extracted from `string`

    Examples:

    >>> get_yyyymmdd_from_string("Foo 20240124 Bar")
    '20240124'

    >>> get_yyyymmdd_from_string("Foo 20240132 Bar")
    Traceback (most recent call last):
      ...
    ValueError: invalid date found in issue title: Foo 20240132 Bar

    >>> get_yyyymmdd_from_string("Foo")
    Traceback (most recent call last):
      ...
    ValueError: title doesn't appear to reference a snapshot issue: Foo
    """
    issue_datetime: datetime = None
    year_month_day = re.search("([0-9]{4})([0-9]{2})([0-9]{2})", string)
    if year_month_day is None:
        raise ValueError(
            f"title doesn't appear to reference a snapshot issue: {string}"
        )

    y = int(year_month_day.group(1))
    m = int(year_month_day.group(2))
    d = int(year_month_day.group(3))
    try:
        issue_datetime = datetime.date(year=y, month=m, day=d)
    except ValueError as ex:
        raise ValueError(f"invalid date found in issue title: {string}") from ex
    return issue_datetime.strftime("%Y%m%d")


def allowed_os_names() -> list[str]:
    """Returns a list of allowed OS names.

    Example:

    >>> sorted(allowed_os_names())
    ['centos-stream', 'fedora', 'rhel']
    """
    return ["centos-stream", "fedora", "rhel"]


def allowed_os_names_as_regex_str() -> str:
    """Returns a list of allowed OS names as a regex

    Example:

    >>> allowed_os_names_as_regex_str()
    '(centos-stream|fedora|rhel)'
    """
    return "(" + "|".join(allowed_os_names()) + ")"


def allowed_archs() -> list[str]:
    """Returns a list of allowed architectures.

    Example:

    >>> sorted(allowed_archs())
    ['aarch64', 'i386', 'ppc64le', 's390x', 'x86_64']
    """
    return ["aarch64", "i386", "ppc64le", "s390x", "x86_64"]


def allowed_archs_as_regex_str() -> str:
    """Returns a list of allowed architectures as a regex

    Example:

    >>> allowed_archs_as_regex_str()
    '(aarch64|i386|ppc64le|s390x|x86_64)'
    """
    return "(" + "|".join(allowed_archs()) + ")"


def allowed_os_versions_as_regex_str() -> str:
    """Returns a list of allowed version

    Example:

    >>> allowed_os_versions_as_regex_str()
    '([0-9]+|rawhide)'
    """
    return "([0-9]+|rawhide)"


def expect_chroot(chroot: str) -> str:
    """Raises an exception if given string is not a chroot

    Args:
        chroot (str): Any chroot string

    Raises:
        ValueError: if chroot argument is not a chroot string

    Examples:

    >>> expect_chroot("fedora-rawhide-x86_64")
    'fedora-rawhide-x86_64'

    >>> expect_chroot("centos-stream-10-x86_64")
    'centos-stream-10-x86_64'

    >>> expect_chroot("fedora-rawhide-")
    Traceback (most recent call last):
      ...
    ValueError: invalid chroot fedora-rawhide-
    """
    if not re.search(
        pattern=rf"^{allowed_os_names_as_regex_str()}-{allowed_os_versions_as_regex_str()}-{allowed_archs_as_regex_str()}$",
        string=chroot,
    ):
        raise ValueError(f"invalid chroot {chroot}")
    return chroot


def is_chroot(chroot: str) -> bool:
    """Returns True if the string in `chroot` is really a chroot.

    Args:
        chroot (str): Any chroot string

    Examples:

    >>> is_chroot("fedora-rawhide-x86_64")
    True

    >>> is_chroot("fedora-rawhide-")
    False
    """
    try:
        expect_chroot(chroot=chroot)
    except:
        return False
    return True


def chroot_name(chroot: str) -> str:
    """Get the name part of a chroot string

    Args:
        chroot (str): A string like "fedora-rawhide-x86_64

    Returns:
        str: The Name part of the chroot string.

    Examples:

    >>> chroot_name(chroot="fedora-rawhide-x86_64")
    'fedora'

    >>> chroot_name(chroot="fedora-40-ppc64le")
    'fedora'

    >>> chroot_name(chroot="fedora-rawhide-NEWARCH")
    Traceback (most recent call last):
      ...
    ValueError: invalid chroot fedora-rawhide-NEWARCH

    >>> chroot_name(chroot="rhel-9-x86_64")
    'rhel'

    >>> chroot_name("centos-stream-10-s390x")
    'centos-stream'
    """
    expect_chroot(chroot)
    match = re.search(pattern=rf"^{allowed_os_names_as_regex_str()}", string=chroot)
    return str(match[0])


def chroot_version(chroot: str) -> str:
    """Get the version part of a chroot string

    Args:
        chroot (str): A string like "fedora-rawhide-x86_64

    Returns:
        str: The Name part of the chroot string.

    Examples:

    >>> chroot_version(chroot="fedora-rawhide-x86_64")
    'rawhide'

    >>> chroot_version(chroot="fedora-40-ppc64le")
    '40'

    >>> chroot_version(chroot="fedora-rawhide-NEWARCH")
    Traceback (most recent call last):
      ...
    ValueError: invalid chroot fedora-rawhide-NEWARCH

    >>> chroot_version(chroot="rhel-9-x86_64")
    '9'
    """
    expect_chroot(chroot)
    match = re.search(
        pattern=rf"(-){allowed_os_versions_as_regex_str()}(-)", string=chroot
    )
    return str(match.groups()[1])


def chroot_os(chroot: str) -> str:
    """Get the os part of a chroot string

    Args:
        chroot (str): A string like "fedora-rawhide-x86_64

    Raises:
        ValueError: if chroot argument is not a chroot string

    Returns:
        str: The OS part of the chroot string.

    Examples:

    >>> chroot_os(chroot="fedora-rawhide-x86_64")
    'fedora-rawhide'

    >>> chroot_os(chroot="fedora-40-ppc64le")
    'fedora-40'

    >>> chroot_os(chroot="fedora-rawhide-NEWARCH")
    Traceback (most recent call last):
      ...
    ValueError: invalid chroot fedora-rawhide-NEWARCH

    >>> chroot_os(chroot="centos-stream-10-x86_64")
    'centos-stream-10'
    """
    expect_chroot(chroot)
    match = re.search(
        pattern=rf"{allowed_os_names_as_regex_str()}-{allowed_os_versions_as_regex_str()}",
        string=chroot,
    )

    return str(match[0])


def chroot_arch(chroot: str) -> str:
    """Get architecture part of a chroot string

    Args:
        chroot (str): A string like "fedora-rawhide-x86_64

    Raises:
        ValueError: if chroot argument is not a chroot string

    Returns:
        str: The architecture part of the chroot string.

    Example:

    >>> chroot_arch(chroot="fedora-rawhide-x86_64")
    'x86_64'

    >>> chroot_arch(chroot="fedora-40-ppc64le")
    'ppc64le'

    >>> chroot_arch(chroot="fedora-rawhide-NEWARCH")
    Traceback (most recent call last):
      ...
    ValueError: invalid chroot fedora-rawhide-NEWARCH

    >>> chroot_arch(chroot="centos-stream-10-ppc64le")
    'ppc64le'
    """
    expect_chroot(chroot)
    match = regex.search(pattern=rf"-\K{allowed_archs_as_regex_str()}", string=chroot)
    return str(match[0])


@functools.cache
def get_git_revision_for_yyyymmdd(yyyymmdd: str) -> str:
    """Get LLVM commit hash for the given date"""
    yyyymmdd = get_yyyymmdd_from_string(yyyymmdd)
    url = f"https://github.com/fedora-llvm-team/llvm-snapshots/releases/download/snapshot-version-sync/llvm-git-revision-{yyyymmdd}.txt"
    logging.info(f"Getting URL {url}")
    response = requests.get(url)
    return response.text.strip()


@functools.cache
def get_release_for_yyyymmdd(yyyymmdd: str) -> str:
    """Get LLVM release (e.g. 19.0.0) for the given date"""
    yyyymmdd = get_yyyymmdd_from_string(yyyymmdd)
    url = f"https://github.com/fedora-llvm-team/llvm-snapshots/releases/download/snapshot-version-sync/llvm-release-{yyyymmdd}.txt"
    logging.info(f"Getting URL {url}")
    response = requests.get(url)
    return response.text.strip()
