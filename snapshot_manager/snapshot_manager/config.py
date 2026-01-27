"""
config
"""

import dataclasses
import datetime


@dataclasses.dataclass(kw_only=True)
class Config:
    chroot_pattern: str = r"^(fedora-(rawhide|[0-9]+)|rhel-[8,9]-)"
    """Regular expression to select chroots from all chroots currently supported on Copr."""

    chroots: list[str] = dataclasses.field(default_factory=list)
    """A list of chroot names. To be filled automatically for you from the chroot_pattern. See util.augment_config_with_chroots()"""

    additional_copr_buildtime_repos: list[str] = dataclasses.field(
        default_factory=lambda: []
    )
    """Additional repositories that shall be passed to 'copr create' as '--repo' arguments in order to be available during build time"""

    datetime: "datetime.datetime" = datetime.datetime.now()
    """Datetime of today"""

    build_strategy: str = "big-merge"
    """The build strategy to use a by default."""

    performance_comparison_label: str = "performance-comparison"
    """Label used to identify performance comparison issue"""

    github_repo: str = "fedora-llvm-team/llvm-snapshots-test"
    """Default github repo to use for creating issues"""

    package_clone_url: str = "https://src.fedoraproject.org/rpms/llvm.git"
    """The package to clone from when creating RPMs"""

    package_clone_ref: str = "rawhide"
    """The git clone ref to use for creating the RPMs"""

    github_token_env: str = "GITHUB_TOKEN"
    """Default name of the environment variable which holds the github token"""

    update_marker: str = "<!--UPDATES_FOLLOW_HERE-->"
    """Prints the marker after a broken snapshot issue comment body when the updates shall follow."""

    maintainer_handle: str = "kwk"
    """The GitHub maintainer handle without the @ sign"""

    creator_handle: str = "github-actions[bot]"
    """The Github user that is expected to have created the daily issue (TODO(kwk): Improve documentation)"""

    copr_target_project: str = "@fedora-llvm-team/llvm-snapshots"
    """The Copr project that the daily snapshot will be converted to if all goes well"""

    copr_ownername: str = "@fedora-llvm-team"
    """The Copr owner name of the project to work with"""

    copr_project_tpl: str = "llvm-snapshots-incubator-YYYYMMDD"
    """The Copr project name template of the project to work with. YYYYMMDD will be replace with the correct date"""

    forked_repo: bool = True
    """Indicates if project copr_project_tpl should be forked into copr_target_project. Otherwise, copr_project_tlp is treated as target repository"""

    copr_monitor_tpl: str = (
        "https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-incubator-YYYYMMDD/monitor/"
    )
    """URL to the Copr monitor page. We'll use this in the issue comment's body, not for querying Copr."""

    test_repo_url: str = "https://github.com/fedora-llvm-team/llvm-snapshots"
    """TBD"""

    retest_team_slug: str = "llvm-toolset-engineers"
    """The team that commenters must be in in order to run /retest comments."""

    label_prefix_in_testing: str = "in_testing/"
    label_prefix_tested_on: str = "tests_succeeded_on/"
    label_prefix_tests_failed_on: str = "tests_failed_on/"

    label_prefix_llvm_release: str = "release/"

    log_detective_username: str = "FAS:kkleine"

    copr_project_description_file: str = "project-description.md"
    """ Path to the file that holds a description for the project's page on Copr """

    copr_project_instructions_file: str = "project-instructions.md"
    """ Path to the file that holds a installation instructions for the project's page on Copr """

    spec_file: str = "my-package.spec"
    """ Name of the spec file to be build on Copr """

    copr_package_name: str = "my-package"
    """ Name of the main package to build on Copr """

    run_check_snapshots_workflow: bool = False
    """ Turn this on if you want to run the 'check-snapshots.yml' workflow in github for this configuration """

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

    def to_github_dict(self) -> dict[str, object]:
        """Returns a subset of config entries to be used in a github workflow matrix.

        The keys in this dict are accessed from github workflow files using the "matrix." object.
        For example the maintainer handle will be accessed as `${{ matrix.maintainer_handle }}`.

        Examples:

        >>> import pprint
        >>> pprint.pprint(Config(build_strategy="mybuildstrategy",
        ...   copr_target_project="@mycoprgroup/mycoprproject",
        ...   package_clone_url="https://src.fedoraproject.org/rpms/mypackage.git",
        ...   package_clone_ref="mainbranch",
        ...   maintainer_handle="fakeperson",
        ...   copr_project_tpl="SomeProjectTemplate-YYYYMMDD",
        ...   copr_project_description_file="description.md",
        ...   copr_project_instructions_file="instructions.md",
        ...   copr_monitor_tpl="https://copr.fedorainfracloud.org/coprs/g/mycoprgroup/SomeProjectTemplate-YYYYMMDD/monitor/",
        ...   chroot_pattern="^(fedora-(rawhide|[0-9]+)|rhel-[8,9]-)",
        ...   chroots=["fedora-rawhide-x86_64", "rhel-9-ppc64le"],
        ...   additional_copr_buildtime_repos=["copr://@fedora-llvm-team/llvm-test-suite", "https://example.com"],
        ...   spec_file="mypackage.spec",
        ...   copr_package_name="my-package",
        ...   run_check_snapshots_workflow=True,
        ... ).to_github_dict())
        {'additional_copr_buildtime_repos': 'copr://@fedora-llvm-team/llvm-test-suite '
                                            'https://example.com',
         'chroot_pattern': '^(fedora-(rawhide|[0-9]+)|rhel-[8,9]-)',
         'chroots': 'fedora-rawhide-x86_64 rhel-9-ppc64le',
         'clone_ref': 'mainbranch',
         'clone_url': 'https://src.fedoraproject.org/rpms/mypackage.git',
         'copr_monitor_tpl': 'https://copr.fedorainfracloud.org/coprs/g/mycoprgroup/SomeProjectTemplate-YYYYMMDD/monitor/',
         'copr_ownername': '@fedora-llvm-team',
         'copr_package_name': 'my-package',
         'copr_project_description_file': 'description.md',
         'copr_project_instructions_file': 'instructions.md',
         'copr_project_tpl': 'SomeProjectTemplate-YYYYMMDD',
         'copr_target_project': '@mycoprgroup/mycoprproject',
         'forked_repo': True,
         'maintainer_handle': 'fakeperson',
         'name': 'mybuildstrategy',
         'run_check_snapshots_workflow': True,
         'spec_file': 'mypackage.spec'}
        """
        return {
            "name": self.build_strategy,
            "copr_target_project": self.copr_target_project,
            "clone_url": self.package_clone_url,
            "clone_ref": self.package_clone_ref,
            "maintainer_handle": self.maintainer_handle,
            "copr_ownername": self.copr_ownername,
            "copr_package_name": self.copr_package_name,
            "copr_project_tpl": self.copr_project_tpl,
            "copr_monitor_tpl": self.copr_monitor_tpl,
            "chroot_pattern": self.chroot_pattern,
            "chroots": " ".join(self.chroots),
            "copr_project_description_file": self.copr_project_description_file,
            "copr_project_instructions_file": self.copr_project_instructions_file,
            "additional_copr_buildtime_repos": " ".join(
                self.additional_copr_buildtime_repos
            ),
            "run_check_snapshots_workflow": self.run_check_snapshots_workflow,
            "spec_file": self.spec_file,
            "forked_repo": self.forked_repo,
        }


def build_config_map() -> dict[str, Config]:
    """Builds a dictionary for each supported build strategy with the name of the build strategy as key.

    Returns:
        dict: The config map with build strategies as keys and config objects as values.
    """
    configs = [
        Config(
            build_strategy="big-merge",
            spec_file="llvm.spec",
            copr_package_name="llvm",
            copr_target_project="@fedora-llvm-team/llvm-snapshots",
            package_clone_url="https://src.fedoraproject.org/rpms/llvm.git",
            package_clone_ref="rawhide",
            maintainer_handle="tbaederr",
            copr_project_tpl="llvm-snapshots-big-merge-YYYYMMDD",
            forked_repo=True,
            copr_monitor_tpl="https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-big-merge-YYYYMMDD/monitor/",
            chroot_pattern="^(fedora-(rawhide|[0-9]+)|centos-stream-[10,9]|rhel-8)",
            copr_project_description_file="llvm-project-description.md",
            copr_project_instructions_file="llvm-project-instructions.md",
            additional_copr_buildtime_repos=[
                "copr://@fedora-llvm-team/llvm-test-suite/",
                "copr://@fedora-llvm-team/python-nanobind/",
            ],
            run_check_snapshots_workflow=True,
        ),
        Config(
            build_strategy="llvm-test-suite",
            spec_file="llvm-test-suite.spec",
            copr_package_name="llvm-test-suite",
            copr_target_project="@fedora-llvm-team/llvm-test-suite",
            package_clone_url="https://src.fedoraproject.org/rpms/llvm-test-suite.git",
            package_clone_ref="rawhide",
            maintainer_handle="kkleine",
            copr_project_tpl="llvm-test-suite",
            forked_repo=False,
            copr_monitor_tpl="https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-test-suite/monitor/",
            chroot_pattern="^(fedora-(rawhide|[0-9]+)|centos-stream-[10,9]|rhel-8)",
            copr_project_description_file="llvm-test-suite-project-description.md",
            copr_project_instructions_file="llvm-test-suite-project-instructions.md",
            run_check_snapshots_workflow=False,
        ),
    ]

    return {config.build_strategy: config for config in configs}
