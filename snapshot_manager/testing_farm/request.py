import dataclasses
import logging
import pathlib
import re
import uuid
import xml.etree.ElementTree as ET

import github.Issue
import testing_farm.tfutil as tfutil
from testing_farm.failed_test_case import FailedTestCase
from testing_farm.watch_result import WatchResult

import snapshot_manager.config as config
import snapshot_manager.util as util


@dataclasses.dataclass(kw_only=True, unsafe_hash=True)
class Request:
    request_id: uuid.UUID | None = None
    """The request ID returned from a call to testing-farm request' """

    chroot: str
    """The chroot for which this testing-farm request was issues"""

    copr_build_ids: list[int] = dataclasses.field(default_factory=list)
    """The copr build IDs associated with the testing-farm request at the time
    the request was made."""

    _in_test_mode: bool = False
    """When this mode is on, we can workaround certain restrictions for fetching
    outdated URLs for example."""

    test_plan_name: str = "snapshot-gating"
    """The plan name. Old test plans default to 'snapshot-gating' because there
    we didn't differentiate between different test plans."""

    def are_build_ids_still_valid(self, copr_build_ids: list[int]) -> bool:
        """Returns True if the given copr builds are the same as the ones
        associated with this testing-farm request"""
        return set(self.copr_build_ids) == set(copr_build_ids)

    def to_html_comment(self) -> str:
        """Returns a HTML comment will all information about this testing-farm request.

        Embed this somewhere.

        Returns:
            str: A HTML comment.

        Example:

        >>> request = Request(request_id='1e2ff614-3bee-4519-b03e-ffd1bf2796a6', chroot='fedora-rawhide-x86_64', copr_build_ids=[4,5,6])
        >>> request.to_html_comment()
        '<!--TESTING_FARM:fedora-rawhide-x86_64/1e2ff614-3bee-4519-b03e-ffd1bf2796a6/4,5,6-->\\n'
        """
        build_ids = ",".join([str(bid) for bid in self.copr_build_ids])
        return f"<!--TESTING_FARM:{self.chroot}/{self.request_id}/{build_ids}-->\n"

    def to_html_link(self) -> str:
        """Returns an HTML link to the artifacts page for this request

        Returns:
            str: A HTML link.

        Example:

        >>> request = Request(request_id='1e2ff614-3bee-4519-b03e-ffd1bf2796a6', chroot='fedora-rawhide-x86_64', copr_build_ids=[4,5,6])
        >>> request.to_html_link()
        '<a href="https://artifacts.dev.testing-farm.io/1e2ff614-3bee-4519-b03e-ffd1bf2796a6/">fedora-rawhide-x86_64</a>'

        >>> request = Request(request_id='15dc4ed3-2653-4a5e-ae03-6b3a038b7222', chroot='rhel-9-x86_64', copr_build_ids=[7,8,9])
        >>> request.to_html_link()
        '<a href="http://artifacts.osci.redhat.com/testing-farm/15dc4ed3-2653-4a5e-ae03-6b3a038b7222/">rhel-9-x86_64</a>'
        """
        if tfutil.select_ranch(self.chroot) == "public":
            return f'<a href="https://artifacts.dev.testing-farm.io/{self.request_id}/">{self.chroot}</a>'
        elif tfutil.select_ranch(self.chroot) == "redhat":
            return f'<a href="http://artifacts.osci.redhat.com/testing-farm/{self.request_id}/">{self.chroot}</a>'
        return ""

    @classmethod
    def parse(cls, string: str) -> list["Request"]:
        """Extracts and sanitizes testing_farm requests from a text comment and returns an array
        with farm request objects.

        If a chroot doesn't have the chroot format it won't be in the resultset.
        If a request ID doesn't have the proper format, the chroot won't be added to the resultset.
        If the comment body contains more than one entry for a the same chroot, the last one will be added to the resulset.

        Args:
            comment_body (str): Arbitrary text, e.g. a github comment body that contains invisible (HTML) comments.

        Returns:
            list["Request"]: list of testing-farm request objects

        Example:

        >>> s='''
        ... Bla bla <!--TESTING_FARM:fedora-rawhide-x86_64/271a79e8-fc9a-4e1d-95fe-567cc9d62ad4/1,2,3--> bla bla
        ... Foo bar. <!--TESTING_FARM:fedora-39-x86_64/11111111-fc9a-4e1d-95fe-567cc9d62ad4/4--> fjjd
        ... Foo BAR. <!--TESTING_FARM:fedora-39-x86_64/22222222-fc9a-4e1d-95fe-567cc9d62ad4/5,6,7--> fafa
        ... Foo bAr. <!--TESTING_FARM:invalid-chroot/33333333-fc9a-4e1d-95fe-567cc9d62ad4/8,9,10--> fafa
        ... FOO bar. <!--TESTING_FARM: fedora-40-x86_64/; cat /tmp/secret/file/11--> fafa
        ... FOO bar. <!--TESTING_FARM: fedora-40-x86_64/33333333-fc9a-4e1d-95fe-567cc9d62ad4/12,13,14--> fafa
        ... This next request ID is missing build IDs. We allow it because there used to be comment IDs
        ... that didn't have these IDs.
        ... FOO bar. <!--TESTING_FARM: fedora-38-x86_64/44444444-fc9a-4e1d-95fe-567cc9d62ad4--> fafa
        ... '''
        >>> reqs = Request.parse(s)
        >>> [req.chroot for req in reqs]
        ['fedora-38-x86_64', 'fedora-39-x86_64', 'fedora-40-x86_64', 'fedora-rawhide-x86_64']
        >>> [req.request_id for req in reqs]
        [UUID('44444444-fc9a-4e1d-95fe-567cc9d62ad4'), UUID('22222222-fc9a-4e1d-95fe-567cc9d62ad4'), UUID('33333333-fc9a-4e1d-95fe-567cc9d62ad4'), UUID('271a79e8-fc9a-4e1d-95fe-567cc9d62ad4')]
        >>> [req.copr_build_ids for req in reqs]
        [[], [5, 6, 7], [12, 13, 14], [1, 2, 3]]
        """
        matches = re.findall(r"<!--TESTING_FARM:([^/]+)/([^/]+)(/([^/]+))?-->", string)
        if not matches:
            logging.debug("No testing-farm requests found to recover.")
            return []

        request_map: dict[str, Request] = {}
        for match in matches:
            try:
                chroot = util.expect_chroot(str(match[0]).strip())
                req = Request(
                    chroot=chroot,
                    request_id=tfutil.sanitize_request_id(str(match[1])),
                    copr_build_ids=[],
                )
                if match[3]:
                    req.copr_build_ids = [
                        int(item.strip()) for item in match[3].split(",")
                    ]
                request_map[chroot] = req
                logging.debug(f"Added testing-farm request: {req}")
            except ValueError as e:
                logging.debug(f"ignoring: {match} : {str(e)}")

        reqs = sorted(request_map.values(), key=lambda req: req.chroot)
        # logging.info(f"Recovered testing-farm-requests: {requests}")
        return reqs

    def watch(self) -> tuple["WatchResult", str] | tuple[None, str]:
        tfutil.adjust_token_env(self.chroot)

        request_id = tfutil.sanitize_request_id(request_id=self.request_id)
        cmd = f"testing-farm watch --no-wait --id {self.request_id}"
        # We ignore the exit code because in case of a test error, 1 is the exit code
        try:
            logging.info(f"Watching for testing-farm request: {cmd}")
            _, stdout, stderr = util.run_cmd(cmd=cmd, timeout_secs=40)
            watch_result, artifacts_url = WatchResult.from_output(stdout)
            if watch_result is None:
                raise SystemError(
                    f"failed to watch 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
                )
        except Exception as ex:
            logging.warning(f"failed to watch for testing-farm result {ex}")
            return (None, "")
        return (watch_result, artifacts_url)

    def fetch_failed_test_cases(
        self, artifacts_url_origin: str
    ) -> list["FailedTestCase"]:
        request_file = tfutil.get_request_file(
            request_id=tfutil.sanitize_request_id(self.request_id)
        )
        xunit_file = tfutil.get_xunit_file_from_request_file(
            request_file=request_file,
            request_id=tfutil.sanitize_request_id(self.request_id),
        )
        # The xunit file is None, if it is only available internally.
        if xunit_file is None:
            return []
        return self.get_failed_test_cases_from_xunit_file(
            xunit_file=xunit_file, artifacts_url_origin=artifacts_url_origin
        )

    def get_failed_test_cases_from_xunit_file(
        self, xunit_file: pathlib.Path, artifacts_url_origin: str
    ) -> list["FailedTestCase"]:
        res: list["FailedTestCase"] = []

        tree = ET.parse(xunit_file)
        root = tree.getroot()
        # see https://docs.python.org/3/library/xml.etree.elementtree.html#example
        failed_testcases = root.findall('./testsuite/testcase[@result="failed"]')

        for failed_testcase in failed_testcases:
            distro_ele = failed_testcase.find(
                './properties/property[@name="baseosci.distro"]'
            )
            if distro_ele is not None:
                distro_attr = distro_ele.get("value")
                if distro_attr is not None:
                    distro = distro_attr

            arch_ele = failed_testcase.find(
                './properties/property[@name="baseosci.arch"]'
            )
            if arch_ele is not None:
                arch_attr = arch_ele.get("value")
                if arch_attr is not None:
                    arch = arch_attr

            log_output_url_ele = failed_testcase.find('./logs/log[@name="testout.log"]')
            if log_output_url_ele is not None:
                log_output_url_attr = log_output_url_ele.get("href")
                if log_output_url_attr is not None:
                    log_output_url = log_output_url_attr

            log_file: pathlib.Path
            if not tfutil._IN_TEST_MODE:
                log_file = util.read_url_response_into_file(log_output_url)
            else:
                p = tfutil._test_path(f"{self.request_id}/failed_test_cases.txt")
                log_file = pathlib.Path(p)
            tc = FailedTestCase(
                test_name=str(failed_testcase.get("name")),
                log_output_url=log_output_url,
                log_output=log_file.read_text(),
                request_id=tfutil.sanitize_request_id(self.request_id),
                chroot=f"{distro.lower()}-{arch}",
                artifacts_url=artifacts_url_origin,
            )
            res.append(tc)
        return res


def make_snapshot_gating_request(
    config: config.Config,
    issue: github.Issue.Issue,
    chroot: str,
    copr_build_ids: list[int],
) -> Request:
    """Runs a "testing-farm request" command and returns a Request object.

    The request is made without waiting for the result.
    It is the responsibility of the caller of this function to run "testing-farm watch --id <REQUEST_ID>",
    where "<REQUEST_ID>" is part of the result object of this function.

    Depending on the chroot, we'll automatically select the proper testing-farm ranch for you.
    For this to work you'll have to set the
    TESTING_FARM_API_TOKEN_PUBLIC_RANCH and
    TESTING_FARM_API_TOKEN_REDHAT_RANCH
    environment variables. We'll then use one of them to set the TESTING_FARM_API_TOKEN
    environment variable for the actual call to testing-farm.

    Args:
        chroot (str): The chroot that you want to run tests for.

    Raises:
        SystemError: When the testing-farm request failed

    Returns:
        Request: testing-farm request object
    """
    test_plan_name = "snapshot-gating"

    logging.info(f"Kicking off new {test_plan_name} test for chroot {chroot}.")

    tfutil.adjust_token_env(chroot)

    cmd = f"""testing-farm \
        request \
        --compose {tfutil.get_compose_from_chroot(chroot=chroot)} \
        --git-url {config.test_repo_url} \
        --arch {util.chroot_arch(chroot)} \
        --plan /tests/{test_plan_name} \
        --environment COPR_PROJECT={config.copr_projectname} \
        --environment COPR_CHROOT={chroot} \
        --context distro={util.chroot_os(chroot)} \
        --context arch={util.chroot_arch(chroot)} \
        --no-wait \
        --user-webpage={issue.html_url} \
        --user-webpage-name="GitHub Issue: {issue.title}" \
        --user-webpage-icon="https://github.com/fedora-llvm-team/llvm-snapshots/blob/main/media/github-mark.png?raw=true" \
        --context snapshot={config.yyyymmdd}"""
    exit_code, stdout, stderr = util.run_cmd(cmd, timeout_secs=None)
    if exit_code == 0:
        return Request(
            test_plan_name=test_plan_name,
            request_id=tfutil.parse_output_for_request_id(stdout),
            copr_build_ids=copr_build_ids,
            chroot=chroot,
        )
    raise SystemError(
        f"failed to run 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
    )


def make_compare_compile_time_request(
    config_a: config.Config,
    config_b: config.Config,
    chroot: str,
) -> Request:
    """Runs a "testing-farm request" command and returns a Request object.

    The request is made without waiting for the result.
    It is the responsibility of the caller of this function to run "testing-farm watch --id <REQUEST_ID>",
    where "<REQUEST_ID>" is part of the result object of this function.

    Depending on the chroot, we'll automatically select the proper testing-farm ranch for you.
    For this to work you'll have to set the
    TESTING_FARM_API_TOKEN_PUBLIC_RANCH and
    TESTING_FARM_API_TOKEN_REDHAT_RANCH
    environment variables. We'll then use one of them to set the TESTING_FARM_API_TOKEN
    environment variable for the actual call to testing-farm.

    Args:
        chroot (str): The chroot that you want to run tests for.

    Raises:
        SystemError: When the testing-farm request failed

    Returns:
        Request: testing-farm request object
    """
    test_plan_name = "compare-comile-time"

    logging.info(f"Kicking off new {test_plan_name} test for chroot {chroot}.")

    tfutil.adjust_token_env(chroot)

    cmd = f"""testing-farm \
        request \
        --compose {tfutil.get_compose_from_chroot(chroot=chroot)} \
        --git-url {config_a.package_clone_url} \
        --arch {util.chroot_arch(chroot)} \
        --plan /tests/{test_plan_name} \
        --context distro={util.chroot_os(chroot)} \
        --context arch={util.chroot_arch(chroot)} \
        --context snapshot={config_a.yyyymmdd} \
        --environment YYYYMMDD={config_a.yyyymmdd} \
        --environment CONFIG_A={config_a.build_strategy} \
        --environment CONFIG_B={config_b.build_strategy} \
        --environment CONFIG_A_COPR_PROJECT={config_a.copr_projectname} \
        --environment CONFIG_B_COPR_PROJECT={config_b.copr_projectname} \
        --environment COPR_CHROOT={chroot}
        --no-wait
        """

    exit_code, stdout, stderr = util.run_cmd(cmd, timeout_secs=None)
    if exit_code == 0:
        return Request(
            test_plan_name=test_plan_name,
            chroot=chroot,
        )
    raise SystemError(
        f"failed to run 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
    )


def render_html(
    request: Request,
    watch_result: WatchResult,
    artifacts_url: str | None,
) -> str:
    title = f"{watch_result.to_icon()} {watch_result}"
    if artifacts_url is None:
        return title
    vpn = ""
    if tfutil.select_ranch(request.chroot) == "redhat":
        vpn = " :lock: "
    return f'<a href="{artifacts_url}">{title}{vpn}</a>'


def requests_to_html_comment(requests: list[Request]) -> str:
    """Converts the data dictionary of chroot -> request object pairs to html comments.

    Example:

    >>> foo = Request(chroot="fedora-rawhide-x86_64", request_id="5823b132-9651-43e4-b6b5-81794b9f4102", copr_build_ids=[1,2,3])
    >>> bar = Request(chroot="fedora-40-s390x", request_id="23ec426f-eaa9-4cc3-a98d-bd7c0a5aeac9", copr_build_ids=[44,544,622])
    >>> requests_to_html_comment(requests=[foo, bar])
    '<!--TESTING_FARM:fedora-rawhide-x86_64/5823b132-9651-43e4-b6b5-81794b9f4102/1,2,3-->\\n<!--TESTING_FARM:fedora-40-s390x/23ec426f-eaa9-4cc3-a98d-bd7c0a5aeac9/44,544,622-->\\n'
    """

    return "".join([req.to_html_comment() for req in requests])


def requests_to_html_list(requests: list[Request], list_type: str = "ul") -> str:
    res = f"<{list_type}>"
    for req in requests:
        res += f"<li>{req.to_html_link()}</li>"
    res += f"</{list_type}>"
    return res
