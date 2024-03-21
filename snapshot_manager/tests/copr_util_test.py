""" Tests for copr_client """

import uuid

import tests.base_test as base_test
import snapshot_manager.copr_util as copr_util
import snapshot_manager.config as config


class TestCopr(base_test.TestBase):
    def test_project_exists(self):
        """Test if copr project exists."""
        self.assertTrue(
            copr_util.CoprClient().project_exists(
                copr_ownername="@fedora-llvm-team", copr_projectname="llvm-snapshots"
            )
        )

        rand = str(uuid.uuid4())
        self.assertFalse(
            copr_util.CoprClient().project_exists(
                copr_ownername=rand, copr_projectname=rand
            )
        )

    def test_copr_chroots(self):
        """Ensure all chroots match the default chroot pattern."""
        chroots = copr_util.CoprClient().get_copr_chroots()
        for chroot in chroots:
            self.assertRegex(chroot, config.Config().chroot_pattern)

    def test_is_package_supported_by_chroot(self):
        """Test if package is supported by chroot"""
        self.assertTrue(
            copr_util.CoprClient.is_package_supported_by_chroot(
                package="lld", chroot="fedora-rawhide-x86_64"
            )
        )
        self.assertTrue(
            copr_util.CoprClient.is_package_supported_by_chroot(
                package="llvm", chroot="fedora-rawhide-x86_64"
            )
        )
        self.assertFalse(
            copr_util.CoprClient.is_package_supported_by_chroot(
                package="lld", chroot="fedora-rawhide-s390x"
            )
        )


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.copr_util

    tests.addTests(doctest.DocTestSuite(snapshot_manager.copr_util))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
