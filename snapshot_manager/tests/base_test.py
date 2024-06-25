"""
TestBase
"""

import contextlib
import logging
import os
import pathlib
import sys
import typing
import unittest

import snapshot_manager.config as config


def run_tests():
    """Call this from wherever you want to run the tests"""
    unittest.main(failfast=True, durations=0, verbosity=5, tb_locals=True)


class TestBase(unittest.TestCase):
    dirname = pathlib.Path(os.path.dirname(__file__))

    @property
    def config(self) -> config.Config:
        """Creates a new config with helpful defaults."""
        return config.Config(github_repo="fedora-llvm-team/llvm-snapshots-test")

    def setUp(self) -> None:
        # This will print all diffs for an assertEqual for example, no matter
        # how many character the diff has.
        self.maxDiff = None

        # logger = logging.getLogger()
        # logger.setLevel(logging.INFO)
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(levelname)s [%(pathname)s:%(lineno)d %(funcName)s] %(message)s",
            datefmt="%d/%b/%Y %H:%M:%S",
            stream=sys.stderr,
        )

    @classmethod
    def abspath(cls, p: tuple[str, pathlib.Path]) -> pathlib.Path:
        return cls.dirname.joinpath(p)

    @contextlib.contextmanager
    def get_text_file(self, text: str) -> typing.Generator[pathlib.Path, None, None]:
        """
        Returns a temporary filename with the given text written to it.
        Use this as a context manager:

            with self.get_text_file(text="foo") as filename:
        """
        import tempfile

        file_handle = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8")
        file_handle.writelines(text)
        file_handle.flush()
        try:
            yield pathlib.Path(file_handle.name)
        finally:
            file_handle.close()


if __name__ == "__main__":
    run_tests()
