"""
config
"""

import datetime
import dataclasses


@dataclasses.dataclass(kw_only=True)
class Config:
    chroot_pattern: str = r"^fedora-(rawhide|[0-9]+)"
    """Regular expression to select chroots from all chroots currently supported on Copr."""

    packages: list[str] = dataclasses.field(
        default_factory=lambda: [
            "python-lit",
            "llvm",
            "clang",
            "lld",
            "compiler-rt",
            "libomp",
        ]
    )
    """List of packages that are relevant to you."""

    active_build_state_pattern: str = r"(running|waiting|pending|importing|starting)"
    """Regular expression to select what states of a copr build are considered active."""

    datetime: "datetime.datetime" = datetime.datetime.now()
    """Datetime of today"""

    build_strategy: str = "big-merge"
    """The build strategy to use a by default."""

    github_repo: str = "fedora-llvm-team/llvm-snapshots-test"
    """Default github repo to use"""

    github_token_env: str = "GH_TEST_TOKEN"
    """Default name of the environment variable which holds the github token"""

    update_marker: str = "<!--UPDATES_FOLLOW_HERE-->"
    """Prints the marker after a broken snapshot issue comment body when the updates shall follow."""

    maintainer_handle: str = "kwk"
    """The GitHub maintainer handle without the @ sign"""

    creator_handle: str = "github-actions[bot]"
    """The Github user that is expected to have created the daily issue (TODO(kwk): Improve documentation)"""

    copr_ownername: str = "@fedora-llvm-team"
    """The Copr owner name of the project to work with"""

    copr_project_tpl: str = "llvm-snapshots-incubator-YYYYMMDD"
    """The Copr project name template of the project to work with. YYYYMMDD will be replace with the correct date"""

    copr_monitor_tpl: str = (
        "https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-incubator-YYYYMMDD/monitor/"
    )
    """URL to the Copr monitor page. We'll use this in the issue comment's body, not for querying Copr."""

    test_repo_url: str = "https://github.com/fedora-llvm-team/llvm-snapshots"
    """TBD"""

    retest_team_slug: str = "llvm-toolset-engineers"
    """The team that commenters must be in in order to run /retest comments."""

    label_prefix_in_testing: str = "in_testing/"
    label_prefix_tested_on: str = "tested_on/"
    label_prefix_failed_on: str = "failed_on/"

    label_prefix_llvm_release: str = "release/"

    @property
    def copr_projectname(self) -> str:
        """Takes the copr_project_tpl and replaces the YYYYMMDD placeholder (if any) with a date.

        Example:

        >>> dt = datetime.date(year=2024, month=2, day=29)
        >>> Config(datetime=dt, copr_project_tpl="begin-YYYYMMDD-end").copr_projectname
        'begin-20240229-end'

        >>> Config(copr_project_tpl="begin-NODATE-end").copr_projectname
        'begin-NODATE-end'
        """
        return self.copr_project_tpl.replace("YYYYMMDD", self.yyyymmdd)

    @property
    def copr_project(self) -> str:
        """Returns the owner/project string for the current date."""
        return f"{self.config.copr_ownername}/{self.config.copr_projectname}"

    @property
    def copr_monitor_url(self) -> str:
        """Takes the copr_monitor_tpl and replaces the YYYYMMDD placeholder (if any) with a date.

        Example:

        >>> dt = datetime.date(year=2024, month=2, day=29)
        >>> Config(datetime=dt, copr_monitor_tpl="begin-YYYYMMDD-end").copr_monitor_url
        'begin-20240229-end'

        >>> Config(copr_monitor_tpl="begin-NODATE-end").copr_monitor_url
        'begin-NODATE-end'
        """
        return self.copr_monitor_tpl.replace("YYYYMMDD", self.yyyymmdd)

    @property
    def yyyymmdd(self) -> str:
        """Returns the default datetime formatted as a YYYYMMDD string

        Returns:
            str: default datetime in YYYYMMDD form

        Example: Adjust the default time and print this yyyymmdd property

        >>> Config(datetime = datetime.date(year=2024, month=2, day=29)).yyyymmdd
        '20240229'
        """
        return self.datetime.strftime("%Y%m%d")
