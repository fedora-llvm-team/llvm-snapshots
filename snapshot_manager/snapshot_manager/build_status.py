"""
BuildStatus
"""

import dataclasses
import enum
import logging
import pathlib
import re

import regex

import snapshot_manager.build_status as build_status
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
        return [s for s in CoprBuildStatus]

    @property
    def success(self) -> bool:
        return self.value in {self.SUCCEEDED, self.FORKED}

    def toIcon(self) -> str:
        """Get a github markdown icon for the given build status

        See https://gist.github.com/rxaviers/7360908 for a list of possible icons."""
        match self:
            case self.IMPORTING:
                return ":inbox_tray:"
            case self.PENDING:
                return ":soon:"  # Alternatives: :snail:
            case self.STARTING:
                return ":star:"
            case self.RUNNING:  # Alternatives: :hammer:
                return ":running:"
            case self.SUCCEEDED:
                return ":white_check_mark:"  # Alternatives: :tada:
            case self.FORKED:
                return ":ballot_box_with_check:"
            case self.SKIPPED:
                return ":no_entry_sign:"
            case self.FAILED:
                return ":x:"
            case self.CANCELED:
                return ":o:"
            case self.WAITING:
                return ":hourglass:"
            case _:
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
    ISSUE_UNKNOWN = "unknown"

    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))


@dataclasses.dataclass(kw_only=True, order=True)
class BuildState:
    """An error describes what and why some package failed to build in a particular chroot."""

    err_cause: ErrorCause = None
    package_name: str = ""
    chroot: str = ""
    url_build_log: str = ""
    url_build: str = ""
    build_id: int = -1
    copr_build_state: CoprBuildStatus = None
    err_ctx: str = ""
    copr_ownername: str = ""
    copr_projectname: str = ""

    def render_as_markdown(self) -> str:
        """Return an HTML string representation of this Build State to be used in a github issue"""
        link = f'<a href="{self.build_log_url}">build log</a>'
        if self.url_build_log is None:
            link = f'<a href="{self.build_page_url}">build page</a>'
        return f"""
<details>
<summary>
<code>{self.package_name}</code> on <code>{self.chroot}</code> (see {link})
</summary>
{self.err_ctx}
</details>
"""

    @property
    def success(self) -> bool:
        return self.copr_build_state.success

    @property
    def os(self):
        """Get the os part of a chroot string

        Args:
            chroot (str): A string like "fedora-rawhide-x86_64

        Returns:
            str: The OS part of the chroot string.

        Examples:

        >>> BuildState(chroot="fedora-rawhide-x86_64").os
        'fedora-rawhide'

        >>> BuildState(chroot="fedora-40-ppc64le").os
        'fedora-40'

        >>> BuildState(chroot="fedora-rawhide-NEWARCH").os
        'fedora-rawhide'
        """
        match = re.search(pattern=r"[^-]+-[0-9,rawhide]+", string=self.chroot)
        if match:
            return str(match[0])
        return ""

    @property
    def arch(self):
        """Get architecture part of a chroot string

        Args:
            chroot (str): A string like "fedora-rawhide-x86_64

        Returns:
            str: The architecture part of the chroot string.

        Example:

        >>> BuildState(chroot="fedora-rawhide-x86_64").arch
        'x86_64'

        >>> BuildState(chroot="fedora-40-ppc64le").arch
        'ppc64le'

        >>> BuildState(chroot="fedora-rawhide-NEWARCH").arch
        'NEWARCH'
        """
        match = regex.search(pattern=r"[^-]+-[^-]+-\K[^\s]+", string=self.chroot)
        if match:
            return str(match[0])
        return ""

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

    @property
    def build_log_url(self) -> str:
        """Returns the URL to to the build log page for this build state"""
        return self.url_build_log

    def augment_with_error(self) -> "BuildState":
        """Inspects the build status and if it is an error it will get and scan the logs"""
        if self.copr_build_state != CoprBuildStatus.FAILED:
            logging.info(
                f"package {self.chroot}/{self.package_name} didn't fail no need to look for errors"
            )
            return self

        # Treat errors with no build logs as unknown and tell user to visit the
        # build URL manually.
        if not self.url_build_log:
            logging.warning(
                f"No build log found for package {self.chroot}/{self.package_name}. Falling back to scanning the SRPM build log: {self.source_build_url}"
            )
            _, match, _ = util.grep_url(
                url=self.source_build_url,
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
        logging.info(f"Reading build log: {self.url_build_log}")
        build_log_file = util.read_url_response_into_file(url=self.url_build_log)

        self.err_cause, self.err_ctx = get_cause_from_build_log(
            build_log_file=build_log_file
        )

        logging.info(f"Remove temporary log file: {build_log_file}")
        build_log_file.unlink()

        return self


def get_cause_from_build_log(
    srpm_build_file=str | pathlib.Path,
    build_log_file: str | pathlib.Path = None,
) -> tuple[ErrorCause, str]:
    cause = ErrorCause.ISSUE_UNKNOWN
    ctx = ""

    logging.info(f"Determine error cause for: {build_log_file}")

    # Unzip log file on the fly if we need to
    build_log_file = util.gunzip(build_log_file)

    logging.info(" Checking for copr timeout...")
    ret, ctx, err = util.grep_file(pattern=r"!! Copr timeout", filepath=build_log_file)
    if ret == 0:
        return (
            ErrorCause.ISSUE_COPR_TIMEOUT,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for network issue...")
    ret, ctx, _ = util.grep_file(
        pattern=r"Errors during downloading metadata for repository",
        filepath=build_log_file,
    )
    if ret == 0:
        return (
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
        return (
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
        return (
            ErrorCause.ISSUE_DEPENDENCY,
            util.fenced_code_block(ctx),
        )

    logging.info(" Checking for test issues...")
    ret, ctx, _ = util.grep_file(
        pattern="(Failed Tests|Unexpectedly Passed Tests).*(\n|.)*Total Discovered Tests:",
        extra_args="-M -n",
        grep_bin="pcre2grep",
        lines_after=10,
        filepath=build_log_file,
    )
    if ret == 0:
        cause = ErrorCause.ISSUE_TEST
        _, stdout, _ = util._run_cmd(
            cmd=rf"sed '/\(\*\)\{{20\}} TEST [^\*]* FAILED \*\{{20\}}/,/\*\{{20\}}/ p' {build_log_file}"
        )
        ctx = f"""
### Failing tests

```
{ctx}
```

### Test output

```
{util.shorten_text(stdout)}
```
"""
        return (cause, ctx)

    # TODO: Feel free to add your check here...

    logging.info(" Default to unknown cause...")
    _, tail, _ = util._run_cmd(cmd=f"tail {build_log_file}")
    _, rpm_build_errors, _ = util._run_cmd(
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
    return (cause, ctx)


BuildStateList = list[BuildState]


def lookup_state(states: BuildStateList, package: str, chroot: str) -> BuildState:
    for state in states:
        if state.package_name == package and state.chroot == chroot:
            return state
    return None


def list_only_errors(states: BuildStateList) -> BuildStateList:
    return [
        state for state in states if state.copr_build_state == CoprBuildStatus.FAILED
    ]


def render_as_markdown(states: BuildStateList) -> str:
    """Sorts the build state list and renders it as HTML

    Args:
        errors (ErrorList): A list of errors

    Returns:
        str: The HTML output as a string
    """
    states.sort()
    last_cause = None
    html = ""
    for state in states:
        if state.err_cause != last_cause:
            if last_cause is not None:
                html += "</ol></details>"
            html += f"\n\n<details open><summary><h2>{state.err_cause}</h2></summary>\n\n<ol>"
        html += f"<li>{state.render_as_markdown()}</li>"
        last_cause = state.err_cause
    if html != "":
        html += "</ol></details>"
    return html


def markdown_build_status_matrix(
    chroots: list[str],
    packages: list[str],
    build_states: BuildStateList,
    init_state: str = ":grey_question:",
    add_legend: bool = True,
) -> str:
    """Creates a build matrix table in markdown

    Returns:
        str: Markdown table string
    """

    table = "<details open><summary>Build Matrix</summary>\n"
    package_header = "|".join(packages)
    table += f"\n| |{package_header}|\n"
    table_header_border = "|".join([":---:" for package in packages])
    table += f"|:---|{table_header_border}|\n"

    for c in chroots:
        cols = []
        for p in packages:
            state = lookup_state(states=build_states, package=p, chroot=c)
            if state is not None:
                cols.append(
                    f"[{CoprBuildStatus(state.copr_build_state).toIcon()}]({state.build_page_url})"
                )
            else:
                cols.append(init_state)
        table += f"|{c}|{" | ".join(cols)}|\n"

    if add_legend:
        table += "<details><summary>Build status legend</summary><ul>"
        states = [state for state in CoprBuildStatus]
        states.sort()
        for state in states:
            table += f"<li>{CoprBuildStatus(state).toIcon()} : {state}</li>"
        table += f"<li>:grey_question: : unknown</li>"
        table += "</ul></details>\n"

    table += "</details>"

    return table
