import dataclasses
import json
import logging
import pathlib
import uuid
from typing import Any

import requests

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config
import snapshot_manager.util as util


def _make_contribution_url(copr_build_id: int, chroot: str) -> str:
    """Constructs a URL for a log detective contribution

    Args:
        copr_build_id (int): The build's ID on COPR
        chroot (str): The chroot for which the build was made
    Returns:
        str: The URL to submit a contribution to
    """
    # return f"http://localhost:5020/frontend/contribute/copr/{copr_build_id}/{chroot}"
    return f"https://logdetective.com/frontend/contribute/copr/{copr_build_id}/{chroot}"


def __make_contribution_post_data(
    username: str,
    fail_reason: str,
    how_to_fix: str,
    spec_file: pathlib.Path | None,
    log_file: pathlib.Path | None,
    snippet_texts: list[str],
    user_comments: list[str],
) -> dict[str, Any] | None:
    """This is a quick and dirty function to construct a contribution object to
    be submitted to log-detective as a review contribution.

    Args:
        username (str): Username under which to submit the review (e.g. "FAS:kkleine").
        fail_reason (str): Overall reason for why this build failed.
        how_to_fix (str): A description of means on how to fix the issue.
        spec_file (pathlib.Path | None): The spec file being used.
        log_file (pathlib.Path | None): The log file being used.
        snippet_texts (list[str]): A list of excerpts from the log file that are relevant for this error.
        user_comments (list[str]): A list of user comments that describe the snippets. Must be of same length as "snippet_texts".

    Raises:
        ValueError: In case snippet_texts and user_comments don't share the same length.

    Returns:
        dict[str, object] | None: A data object that can be submitted to log-detective using `requests.post(url, json=data)`
    """
    if log_file is None:
        logging.info("No log file was specified. Bailing.")
        return None

    logging.info("Reading log file: %s", log_file)
    log_file_content = log_file.read_text()

    spec_file_name = ""
    spec_file_content = ""
    if spec_file is not None:
        spec_file_name = spec_file.name
        spec_file_content = spec_file.read_text()

    data: dict[str, Any] = {
        "username": username,
        "fail_reason": fail_reason,
        "how_to_fix": how_to_fix,
        "spec_file": {
            "name": spec_file_name,
            "content": spec_file_content,
        },
        "logs": [
            {
                "name": "builder-live.log.gz",
                "content": log_file_content,
                "snippets": [],
            }
        ],
    }

    if len(snippet_texts) != len(user_comments):
        raise ValueError(
            "The number snippets and user comments must be identical! "
            "Current lengths: snippets={len(snippet_texts)}, user comments={len(user_comments)}"
        )
    for snippet_text, user_comment in zip(snippet_texts, user_comments):
        start_index = log_file_content.find(snippet_text)
        end_index = start_index + len(snippet_text)
        data["logs"][0]["snippets"].append(
            {
                "start_index": start_index,
                "end_index": end_index,
                "user_comment": user_comment,
                "text": snippet_text,
            }
        )
        logging.info("Snippet start/end index: %d/%d", start_index, end_index)

    return data


def _contrib_prefix() -> str:
    return "LOG_DETECTIVE_CONTRIBUTION_ID"


@dataclasses.dataclass(kw_only=True)
class Contribution:
    review_id: uuid.UUID | str
    chroot: str
    build_id: int

    @property
    def website_url(self) -> str:
        """Returns the URL to the log detective on which one can edit the contribution.

        Example:

        >>> contrib = Contribution(
        ...     review_id="b104bba7-2277-470f-a885-6218daa69572",
        ...     chroot="fedora-rawhide-x86_64",
        ...     build_id=1234)
        >>> contrib.website_url
        'https://log-detective.com/review/b104bba7-2277-470f-a885-6218daa69572'

        Example that uses the old timestamp a string for the review ID:

        >>> contrib = Contribution(
        ...     review_id="1748936595",
        ...     chroot="fedora-rawhide-x86_64",
        ...     build_id=1234)
        >>> contrib.website_url
        'https://log-detective.com/review/1748936595'
        """
        return f"https://log-detective.com/review/{self.review_id}"

    def to_html_comment(self) -> str:
        """Returns a HTML comment will all information about this log detective contribution.

        Embed this somewhere.

        Returns:
            str: A HTML comment.

        Example:

        >>> request = Contribution(review_id='1e2ff614-3bee-4519-b03e-ffd1bf2796a6', chroot='fedora-rawhide-x86_64', build_id=456)
        >>> request.to_html_comment()
        '<!--LOG_DETECTIVE_CONTRIBUTION_ID:1e2ff614-3bee-4519-b03e-ffd1bf2796a6/fedora-rawhide-x86_64/456-->\\n'
        """
        return f"<!--{_contrib_prefix()}:{self.review_id}/{self.chroot}/{self.build_id}-->\n"


def __submit_contribution(
    copr_build_id: int, chroot: str, contribution: dict[str, Any]
) -> Contribution:
    """Submits a contribution object to log detective and returns a proper `Contribution`
    object with a review ID this contribution.

    Args:
        copr_build_id (int): The build's ID on COPR
        chroot (str): The chroot that the build was done for
        contribution (Dict[str, Any]): The actual contribution object (see `make_contribution()`)

    Raises:
        HTTPError: if one occurred
        KeyError: if the review ID field wasn't found in the response from log-detective

    Returns:
        Contribution: A Contribution object with the review ID filled.
    """
    url = _make_contribution_url(copr_build_id=copr_build_id, chroot=chroot)
    logging.info("Submitting log detective contribution to %s", url)
    res = requests.post(url, json=contribution)
    res.raise_for_status()
    res_data = json.loads(res.content.decode("utf-8"))
    if res_data is not None:
        if "review_id" in res_data:
            contrib = Contribution(
                chroot=chroot,
                review_id=str(res_data["review_id"]),
                build_id=copr_build_id,
            )
            logging.info("Submitted to log detective: %s", contrib)
            return contrib
    raise KeyError(
        f"Failed to find 'review_id' field in log detective's response: {res.json()}"
    )


__how_to_fix_test_issue = """Here is list of some ways to fix an unexpected test result:

a) Find out the reason why the test fails and fix it. Should that not work, follow any of the following options.
b) If you've found out that your test is flaky, perhaps you can allow it to run more than once (see https://llvm.org/docs/CommandGuide/lit.html#cmdoption-lit-max-retries-per-test).
c) If you need to mark your test to expectedly fail, you can set the LIT_XFAIL environment variable (see https://llvm.org/docs/CommandGuide/lit.html#cmdoption-lit-xfail).
d) Should none of the above tips work, filter out the test by using the LIT_FILTER_OUT environment variable (see. https://llvm.org/docs/CommandGuide/lit.html#cmdoption-lit-filter-out).
"""


def upload(cfg: config.Config, state: build_status.BuildState) -> Contribution | None:
    """
    This will upload the build that is identified by the `state` object to log
    detective.

    The given `state` object should have called `state.augment_with_error()`
    before.

    Example:

    >>> cfg = config.Config(log_detective_username="FAS:kkleine")  # doctest: +SKIP
    >>> state = build_status.BuildState(  # doctest: +SKIP
    ...   package_name="llvm",
    ...   copr_ownername="@fedora-llvm-team",
    ...   copr_projectname="llvm-snapshots-big-merge-20250610",
    ...   chroot="fedora-41-x86_64",
    ...   build_id=9148650,
    ...   url_build_log='https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/llvm-snapshots-big-merge-20250610/fedora-41-x86_64/09148650-llvm/builder-live.log.gz',
    ...   copr_build_state=build_status.CoprBuildStatus.FAILED
    ...   )
    >>> state = state.augment_with_error()  # doctest: +SKIP
    >>> upload(cfg=cfg, state=state) # doctest: +SKIP
    """

    post_data = None
    spec_file = None

    # Expect a spec file to exist when a build log exists.
    if state._build_log_file is not None:
        spec_file_url = state.get_spec_file_url()
        logging.info("Getting spec file from: %s", spec_file_url)
        spec_file = util.read_url_response_into_file(spec_file_url)

    if state.err_cause == build_status.ErrorCause.ISSUE_TEST:
        if state._build_log_file is None:
            logging.info(
                "Build has no log file loaded (did you run augment_with_error() before?)"
            )
            return None

        logging.info("Build is a test issue and will be pre-annotated")

        # Test data is separated by binary zeros so we'll create a snippets
        # array from it.
        snippets_texts: list[str] = []
        user_comments: list[str] = []
        for failing_test in state._err_orig_ctx.split("\x00"):
            if not failing_test:
                continue
            test_name = "n/a"
            test_result = "n/a"
            lines = failing_test.splitlines()
            if len(lines) > 0:
                test_name = lines[0].replace("********************", "").strip()
                test_name = test_name.removeprefix("TEST '")
                idx = test_name.rfind("' ")
                test_result = test_name[(idx + 2) :]
                test_name = test_name[:idx]

            logging.info(f"Found test_name: {test_name} Result: {test_result}")

            snippets_texts.append(failing_test)
            user_comments.append(
                f'The test "{test_name}" ended with result: "{test_result}". This shows the output that was gathered for the test execution. It might contain insights into why the test "{test_name}" had an unexpected outcome.'
            )

        post_data = __make_contribution_post_data(
            username=cfg.log_detective_username,
            fail_reason="At least one test had an unexpected outcome.",
            how_to_fix=__how_to_fix_test_issue,
            spec_file=spec_file,
            log_file=state._build_log_file,
            snippet_texts=snippets_texts,
            user_comments=user_comments,
        )
    # TODO(kwk): Add more cases that we could annotate here.
    else:
        log_file = state._build_log_file
        if log_file is None:
            log_file = state._source_build_file
        post_data = __make_contribution_post_data(
            username=cfg.log_detective_username,
            fail_reason="error cause: " + str(state.err_cause),
            how_to_fix="",
            spec_file=spec_file,
            log_file=log_file,
            snippet_texts=[],
            user_comments=[],
        )

    if post_data is not None:
        logging.info("Uploading build to log-detective.")
        return __submit_contribution(
            chroot=state.chroot, copr_build_id=state.build_id, contribution=post_data
        )
    return None
