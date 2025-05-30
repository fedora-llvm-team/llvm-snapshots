"""
BuildStatus
"""

import dataclasses
import enum
import logging
import pathlib
import urllib

import snapshot_manager.util as util


@enum.unique
class CoprBuildStatus(enum.StrEnum):
    """An enum for Copr build states"""

    IMPORTING = "importing"  #  Package sources are being imported into Copr DistGit.
    PENDING = "pending"  # Build is waiting in queue for a backend worker.
    STARTING = "starting"  # Backend worker is trying to acquire a builder machine.
    RUNNING = "running"  # Build in progress.
    SUCCEEDED = "succeeded"  # Successfully built.
    FORKED = "forked"  # Build has been forked from another build.
    SKIPPED = "skipped"  # This package was skipped, see the reason for each chroot separately.
    FAILED = "failed"  # Build failed. See logs for more details.
    CANCELED = "canceled"  # The build has been cancelled manually.
    WAITING = "waiting"  # Task is waiting for something else to finish.

    @classmethod
    def all_states(cls) -> list["CoprBuildStatus"]:
        """
        >>> all_states = CoprBuildStatus.all_states()
        >>> all_states.sort()
        >>> all_states # doctest: +NORMALIZE_WHITESPACE
        [<CoprBuildStatus.CANCELED: 'canceled'>, <CoprBuildStatus.FAILED: 'failed'>,
        <CoprBuildStatus.FORKED: 'forked'>, <CoprBuildStatus.IMPORTING: 'importing'>,
        <CoprBuildStatus.PENDING: 'pending'>, <CoprBuildStatus.RUNNING: 'running'>,
        <CoprBuildStatus.SKIPPED: 'skipped'>, <CoprBuildStatus.STARTING: 'starting'>,
        <CoprBuildStatus.SUCCEEDED: 'succeeded'>, <CoprBuildStatus.WAITING: 'waiting'>]
        """
        return [s for s in CoprBuildStatus]

    @property
    def success(self) -> bool:
        return self.value in {self.SUCCEEDED, self.FORKED}

    def to_icon(self) -> str:
        """Get a github markdown icon for the given build status

        See https://gist.github.com/rxaviers/7360908 for a list of possible icons."""
        if self == self.IMPORTING:
            return ":inbox_tray:"
        elif self == self.PENDING:
            return ":soon:"  # Alternatives: :snail:
        elif self == self.STARTING:
            return ":star:"
        elif self == self.RUNNING:  # Alternatives: :hammer:
            return ":running:"
        elif self == self.SUCCEEDED:
            return ":white_check_mark:"  # Alternatives: :tada:
        elif self == self.FORKED:
            return ":ballot_box_with_check:"
        elif self == self.SKIPPED:
            return ":no_entry_sign:"
        elif self == self.FAILED:
            return ":x:"
        elif self == self.CANCELED:
            return ":o:"
        elif self == self.WAITING:
            return ":hourglass:"
        else:
            return ":grey_question:"


@enum.unique
class ErrorCause(enum.StrEnum):
    """A list of issue types that we can detect"""

    ISSUE_SRPM_BUILD = "srpm_build_issue"
    ISSUE_COPR_TIMEOUT = "copr_timeout"
    ISSUE_NETWORK = "network_issue"
    ISSUE_DEPENDENCY = "dependency_issue"
    ISSUE_TEST = "test"
    ISSUE_DOWNSTREAM_PATCH_APPLICATION = "downstream_patch_application"
    ISSUE_RPM__INSTALLED_BUT_UNPACKAGED_FILES_FOUND = (
        "rpm__installed_but_unpackaged_files_found"
    )
    ISSUE_RPM__DIRECTORY_NOT_FOUND = "rpm__directory_not_found"
    ISSUE_RPM__FILE_NOT_FOUND = "rpm__file_not_found"
    ISSUE_CMAKE_ERROR = "cmake_error"
    ISSUE_UNKNOWN = "unknown"

    @classmethod
    def list(cls) -> list[str]:
        """
        Returns a list of strings with all possible error causes.

        >>> causes = ErrorCause.list()
        >>> causes.sort()
        >>> causes # doctest: +NORMALIZE_WHITESPACE
        ['cmake_error', 'copr_timeout', 'dependency_issue', 'downstream_patch_application',
        'network_issue', 'rpm__directory_not_found', 'rpm__file_not_found',
        'rpm__installed_but_unpackaged_files_found', 'srpm_build_issue', 'test', 'unknown']
        """
        return list(map(lambda c: str(c), cls))


@dataclasses.dataclass(kw_only=True, order=True)
class BuildState:
    """A BuildState holds information about a package build on Copr in a particular chroot."""

    err_cause: ErrorCause | None = None
    package_name: str = ""
    chroot: str = ""
    url_build_log: str = ""
    url_build: str = ""
    build_id: int = -1
    copr_build_state: CoprBuildStatus | None = None
    err_ctx: str = ""
    copr_ownername: str = ""
    copr_projectname: str = ""

    def render_as_markdown(self, shortened: bool = False) -> str:
        """Return an HTML string representation of this Build State to be used in a github issue"""
        if self.url_build_log is None or self.url_build_log.strip() == "":
            link = f'<a href="{self.build_page_url}">build page</a>'
        else:
            quoted_build_log_link = urllib.parse.quote(self.url_build_log)
            link = f'<a href="{self.url_build_log}">build log</a>, <a href="https://logdetective.com/contribute/copr/{self.build_id:08}/{self.chroot}">Teach AI</a>, <a href="https://log-detective.com/explain?url={quoted_build_log_link}">Ask AI</a>'

        if shortened:
            details = "The log of errors is too long for Github. See the details in the build log."
        else:
            details = self.err_ctx
        return f"""
<details>
<summary>
<code>{self.package_name}</code> on <code>{self.chroot}</code> (see {link})
</summary>
{details}
</details>
"""

    @property
    def success(self) -> bool:
        """Returns True if the underlying copr build state is "succeeded" or "forked".

        Examples:

        >>> BuildState(copr_build_state="succeeded").success
        True

        >>> BuildState(copr_build_state="forked").success
        True

        >>> BuildState(copr_build_state=CoprBuildStatus.SUCCEEDED).success
        True

        >>> BuildState(copr_build_state=CoprBuildStatus.FORKED).success
        True

        >>> BuildState(copr_build_state="waiting").success
        False

        >>> BuildState(copr_build_state=CoprBuildStatus.IMPORTING).success
        False
        """
        return CoprBuildStatus(str(self.copr_build_state)).success

    @property
    def os(self) -> str:
        return util.chroot_os(self.chroot)

    @property
    def arch(self) -> str:
        return util.chroot_arch(self.chroot)

    @property
    def source_build_url(self) -> str:
        """Returns the URL to to the SRPM build page for this build state

        Example:

        >>> BuildState(build_id=123, copr_projectname="foo", copr_ownername="bar").source_build_url
        'https://download.copr.fedorainfracloud.org/results/bar/foo/srpm-builds/00000123/builder-live.log.gz'
        """
        # See https://github.com/fedora-copr/log-detective-website/issues/73#issuecomment-1889042206
        return f"https://download.copr.fedorainfracloud.org/results/{self.copr_ownername}/{self.copr_projectname}/srpm-builds/{self.build_id:08}/builder-live.log.gz"

    @property
    def build_page_url(self) -> str:
        """Returns the URL to to the build page for this build state

        Example:

        >>> BuildState(build_id=123).build_page_url
        'https://copr.fedorainfracloud.org/coprs/build/123'
        """
        return f"https://copr.fedorainfracloud.org/coprs/build/{self.build_id}"

    def augment_with_error(self) -> "BuildState":
        """Inspects the build status and if it is an error it will get and scan the logs"""
        if self.copr_build_state != CoprBuildStatus.FAILED:
            logging.debug(
                f"package {self.chroot}/{self.package_name} didn't fail no need to look for errors"
            )
            return self

        # Treat errors with no build logs as unknown and tell user to visit the
        # build URL manually.
        if not self.url_build_log:
            logging.debug(
                f"No build log found for package {self.chroot}/{self.package_name}. Falling back to scanning the SRPM build log: {self.source_build_url}"
            )
            file = util.read_url_response_into_file(
                url=self.source_build_url,
                prefix=f"{self.package_name}-{self.chroot}-source-build-log",
            )
            _, match, _ = util.grep_file(
                filepath=file,
                pattern=r"error:",
                lines_after=3,
                lines_before=3,
            )
            self.err_ctx = f"""
<h4>No build log available</h4>
Sorry, but this build contains no build log file, please consult the
<a href="{self.build_page_url}">build page</a> to find out more.

<h4>Errors in SRPM build log</h4>
We've scanned the <a href="{self.source_build_url}">SRPM build log</a>
for <code>error:</code> (case insesitive) and here's what we've found:

```
{util.shorten_text(match)}
```
"""

            self.err_cause = ErrorCause.ISSUE_SRPM_BUILD
            return self

        # Now analyze the build log but store it in a file first
        logging.debug(f"Reading build log: {self.url_build_log}")
        build_log_file = util.read_url_response_into_file(
            url=self.url_build_log,
            prefix=f"{self.package_name}-{self.chroot}-source-log",
        )

        self.err_cause, self.err_ctx = get_cause_from_build_log(
            build_log_file=build_log_file
        )

        return self


def get_cause_from_build_log(
    build_log_file: str | pathlib.Path,
    write_golden_file: bool = False,
) -> tuple[ErrorCause, str]:
    """Analyzes the given build log for recognizable error patterns and categorized the overall error.

    The function returns a tuple of the error pattern and the error context.
    An error context is a string that has some markup to be rendered inside a github issue.

    If write_to_golden_file is True, the error context is written to a golden file.
    This allows us to create large test result files upon a change to the analysis.

    Args:
        build_log_file (str | pathlib.Path): The build log file to analyze
        write_golden_file (bool, optional): If True, error context is written to a golden file. Defaults to False.

    Returns:
        tuple[ErrorCause, str]: The tuple of identied error pattern and the error context.
    """
    cause = ErrorCause.ISSUE_UNKNOWN
    ctx = ""

    def handle_golden_file(cause: ErrorCause, ctx: str) -> tuple[ErrorCause, str]:
        if write_golden_file:
            util.golden_file_path(basename=f"cause_{str(cause)}").write_text(ctx)
        return (cause, ctx)

    logging.info(f"Determine error cause for: {build_log_file}")

    # Unzip log file on the fly if we need to
    build_log_file = util.gunzip(build_log_file)

    logging.info(" Checking for copr timeout...")
    ret, ctx, err = util.grep_file(pattern=r"!! Copr timeout", filepath=build_log_file)
    if ret == 0:
        return handle_golden_file(
            ErrorCause.ISSUE_COPR_TIMEOUT,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for network issue...")
    ret, ctx, _ = util.grep_file(
        pattern=r"Errors during downloading metadata for repository",
        filepath=build_log_file,
    )
    if ret == 0:
        return handle_golden_file(
            ErrorCause.ISSUE_NETWORK,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for downstream patch application issue...")
    ret, ctx, _ = util.grep_file(
        pattern=r"\d+ out of \d+ hunk[s]? FAILED -- saving rejects to file",
        lines_before=3,
        lines_after=4,
        filepath=build_log_file,
        extra_args="-P",
    )
    if ret == 0:
        return handle_golden_file(
            ErrorCause.ISSUE_DOWNSTREAM_PATCH_APPLICATION,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for dependency issues...")
    ret, ctx, _ = util.grep_file(
        pattern=r"(No matching package to install:|Not all dependencies satisfied|No match for argument:)",
        extra_args="-P",
        filepath=build_log_file,
    )
    if ret == 0:
        return handle_golden_file(
            ErrorCause.ISSUE_DEPENDENCY,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for test issues...")
    ret, ctx, _ = util.grep_file(
        pattern=r"(?s)\*{20} TEST .*?\n--\n.*?\n--\n",
        filepath=build_log_file,
        extra_args="-Pzo",
        case_insensitive=False,
    )
    if ret == 0:
        new_ctx = ""
        for failing_test in ctx.split("\x00"):
            if not failing_test:
                continue
            test_name = "n/a"
            lines = failing_test.splitlines()
            if len(lines) > 0:
                test_name = lines[0].replace("********************", "").strip()
            new_ctx += f"""
<details><summary>{test_name}</summary>

``````
{util.shorten_text(failing_test)}
``````

</details>
"""
        return handle_golden_file(ErrorCause.ISSUE_TEST, new_ctx)

    logging.info(" Checking for installed but unackaged files...")
    ret, ctx, _ = util.grep_file(
        pattern=r"(?s)Installed \(but unpackaged\) file\(s\) found:.*Finish",
        extra_args="-Pzo",
        filepath=build_log_file,
    )
    if ret == 0:
        # Remove trailing binary zero
        ctx = ctx.rstrip("\x00")
        return handle_golden_file(
            ErrorCause.ISSUE_RPM__INSTALLED_BUT_UNPACKAGED_FILES_FOUND,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for alternative installed but unackaged files...")
    ret, ctx, _ = util.grep_file(
        pattern=r"(?s)Checking for unpackaged file(s):.*Installed (but unpackaged) file(s) found:.*\n\n",
        extra_args="-Pzo",
        filepath=build_log_file,
    )
    if ret == 0:
        # Remove trailing binary zero
        ctx = ctx.rstrip("\x00")
        return handle_golden_file(
            ErrorCause.ISSUE_RPM__INSTALLED_BUT_UNPACKAGED_FILES_FOUND,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for directory not found...")
    ret, ctx, _ = util.grep_file(
        pattern=r"(?s)RPM build errors:\n.*    Directory not found: /builddir/.*Finish",
        extra_args="-Pzo",
        filepath=build_log_file,
    )
    if ret == 0:
        # Remove trailing binary zero
        ctx = ctx.rstrip("\x00")
        return handle_golden_file(
            ErrorCause.ISSUE_RPM__DIRECTORY_NOT_FOUND,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for file not found...")
    ret, ctx, _ = util.grep_file(
        pattern=r"(?s)RPM build errors:\n.*    File not found: /builddir/.*Finish",
        extra_args="-Pzo",
        filepath=build_log_file,
    )
    if ret == 0:
        # Remove trailing binary zero
        ctx = ctx.rstrip("\x00")
        return handle_golden_file(
            ErrorCause.ISSUE_RPM__FILE_NOT_FOUND,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for CMake error...")
    ret, ctx, _ = util.grep_file(
        pattern=r"(?s)CMake Error at.*Configuring incomplete, errors occurred!",
        extra_args="-Pzo",
        filepath=build_log_file,
    )
    if ret == 0:
        # Remove trailing binary zero
        ctx = ctx.rstrip("\x00")
        return handle_golden_file(
            ErrorCause.ISSUE_CMAKE_ERROR,
            util.fenced_code_block(ctx),
        )

    # TODO: Feel free to add your check here...

    logging.info(" Default to unknown cause...")
    _, tail, _ = util.run_cmd(cmd=f"tail {build_log_file}")
    _, rpm_build_errors, _ = util.run_cmd(
        cmd=rf"sed -n -e '/RPM build errors/,/Finish:/' p {build_log_file}"
    )
    _, errors_to_look_into, _ = util.grep_file(
        pattern=r"error:",
        filepath=build_log_file,
        lines_before=1,
        case_insensitive=True,
    )

    cause = ErrorCause.ISSUE_UNKNOWN
    ctx = f"""
### Build log tail

Sometimes the end of the build log contains useful information.

```
{util.shorten_text(tail)}
```

### RPM build errors

If we have found <code>RPM build errors</code> in the log file, you'll find them here.

```
{util.shorten_text(rpm_build_errors)}
```

### Errors to look into

If we have found the term <code>error:</code> (case insentitive) in the build log,
you'll find all occurrences here together with the preceding lines.

```
{util.shorten_text(errors_to_look_into)}
```
"""
    return handle_golden_file(cause, ctx)


BuildStateList = list[BuildState]


def lookup_state(
    states: BuildStateList, package: str, chroot: str
) -> BuildState | None:
    for state in states:
        if state.package_name == package and state.chroot == chroot:
            return state
    return None


def list_only_errors(states: BuildStateList) -> BuildStateList:
    return [
        state for state in states if state.copr_build_state == CoprBuildStatus.FAILED
    ]


def render_as_markdown(states: BuildStateList, shortened: bool = False) -> str:
    """Sorts the build state list and renders it as HTML

    Args:
        errors (ErrorList): A list of errors

    Returns:
        str: The HTML output as a string
    """
    states.sort()
    last_cause = None
    html = "<ul>"
    for state in states:
        if state.err_cause != last_cause:
            if last_cause is not None:
                html += "</ol></li>"
            html += f"<li><b>{state.err_cause}</b><ol>"
        html += f"<li>{state.render_as_markdown(shortened=shortened)}</li>"
        last_cause = state.err_cause
    if html != "":
        html += "</ol></li></ul>"
    return html


def markdown_build_status_matrix(
    chroots: list[str],
    build_states: BuildStateList,
    init_state: str = ":grey_question:",
    add_legend: bool = True,
) -> str:
    """Creates a build matrix table in markdown

    Returns:
        str: Markdown table string
    """

    table = "<details open><summary>Build Matrix</summary>\n"
    table += "\n|chroot|llvm|\n"
    table += "|:---|:---:|\n"

    for c in chroots:
        cols = []
        state = lookup_state(states=build_states, package="llvm", chroot=c)
        if state is not None:
            if state.copr_build_state is not None:
                cols.append(
                    f"[{CoprBuildStatus(state.copr_build_state).to_icon()}]({state.build_page_url})"
                )
        else:
            cols.append(init_state)
        # fmt: off
        table += f"|{c}|{" | ".join(cols)}|\n"
        # fmt: on

    if add_legend:
        table += "<details><summary>Build status legend</summary><ul>"
        copr_build_states = [state for state in CoprBuildStatus.all_states()]
        copr_build_states.sort()
        for copr_build_state in copr_build_states:
            table += f"<li>{copr_build_state.to_icon()} : {copr_build_state}</li>"
        table += "<li>:grey_question: : unknown</li>"
        table += "<li>:warning: : pipeline error (only relevant to testing-farm)</li>"
        table += "</ul></details>\n"

    table += "</details>"

    return table
