"""
util
"""

import logging
import pathlib
import shlex
import subprocess
import os

import requests

import snapshot_manager.file_access as file_access
import snapshot_manager.build_status as build_status


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
    return _run_cmd(cmd)


def _run_cmd(cmd: str, timeout_secs: int = 5) -> tuple[int, str, str]:
    """Runs the given command and returns the output (stdout and stderr) if any.

    Args:
        cmd (str): Command to run, e.g. "ls -lha ."

    Returns:
        tuple[int, str, str]: The command exit code and it's stdout and sterr
    """

    proc = subprocess.run(shlex.split(cmd), timeout=timeout_secs, capture_output=True)
    logging.info(f"exit code: {proc.returncode} for cmd: {cmd}")

    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def read_url_response_into_file(url: str) -> pathlib.Path:
    """Fetch the given URL and store it in a temporary file whose name is returned.

    Args:
        url (str): URL to GET

    Returns:
        pathlib.Path: Path object of the temporary file to which the GET response was written to.
    """
    logging.debug(f"Getting URL {url}")
    response = requests.get(url)
    return file_access.write_to_temp_file(response.content)


def grep_url(url, **kw_args) -> tuple[int, str, str]:
    """GETs the given url and passes all other parameters on to grep_file

    See grep_file for knowing what arguments are accepted for kw_args.

    Args:
        url (_type_): URL to get

    Returns:
        tuple[int, str, str]: return code, stdout, stderr
    """
    file = read_url_response_into_file(url=url)
    res = grep_file(filepath=file, **kw_args)
    file.unlink(f"Removing temporary file: {file}")
    return res


def gunzip(f: tuple[str, pathlib.Path]) -> pathlib.Path:
    """Unzip log file on the fly if we need to"""
    if str(f).endswith(".gz"):
        unzipped_file = str(f).removesuffix(".gz")
        retcode, stdout, stderr = _run_cmd(cmd=f"gunzip -kf {f}")
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
