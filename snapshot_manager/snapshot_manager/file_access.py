"""
file_access
"""

import logging
import pathlib
import tempfile
import typing


@typing.overload
def write_to_temp_file(content: bytes) -> pathlib.Path: ...


@typing.overload
def write_to_temp_file(text: str) -> pathlib.Path: ...


def write_to_temp_file(content: str | bytes) -> pathlib.Path:
    """Creates a named temporary file that isn't deleted and writes content to it.

    Args:
        content (str|bytes): String or bytes be written to the file

    Raises:
        ValueError: If the content has an unsupported type

    Returns:
        pathlib.Path: Path object of the temporary file created

    Example: Write a string to a temporary file

    >>> p = write_to_temp_file("foo")
    >>> data = p.read_text()
    >>> print(data)
    foo

    Example: Write unsupported content to temp file

    >>> p = write_to_temp_file(123)
    Traceback (most recent call last):
    ValueError: unsupported content type to write to temporary file
    """
    with tempfile.NamedTemporaryFile(delete_on_close=False, delete=False) as f:
        logging.debug(f"Created temporary file: {f.name}")
        p = pathlib.Path(f.name)
        if isinstance(content, str):
            p.write_text(content)
        elif isinstance(content, bytes):
            p.write_bytes(content)
        else:
            raise ValueError("unsupported content type to write to temporary file")
        return p
