"""
SnapshotManager
"""

import logging
import pathlib

import copr.v3
import github
import github.Issue
import pandas as pd
import testing_farm as tf
import testing_farm.tfutil as tfutil

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config
import snapshot_manager.copr_util as copr_util
import snapshot_manager.github_util as github_util
import snapshot_manager.util as util


class SnapshotManager:
    def __init__(self, config: config.Config):
        self.config = config
        self.copr = copr_util.make_client()
        # In case this wasn't done before, augment the config with a list of
        # chroots of interest.
        if len(self.config.chroots) == 0:
            all_chroots = copr_util.get_all_chroots(client=self.copr)
            util.augment_config_with_chroots(config=config, all_chroots=all_chroots)
        self.github = github_util.GithubClient(config=config)

    def retest(
        self, issue_number: int, trigger_comment_id: int, chroots: list[str]
    ) -> None:
        """Causes testing-farm tests to (re-)run for a day.

        There are a number of preconditions what qualifies an issue to be valid here.
        The author of the trigger comment also needs to be in a special team.
        The list of chroots is validated as well.

        Whenever something doesn't work we bail and leave a message in the logs.

        If everything is validated and the workflow is kicked off, we add the thumbs
        up reaction to the trigger comment to signal the user that we've processed his
        retest request. NOTE: This doesn't mean that the actual retest is done, yet!

        Args:
            issue_number (int): The issue for the day a retest is requested
            trigger_comment_id (int): The ID of the comment in which the user requested a retest
            chroots (list[str]): The list of chroots for which to run retests.
        """
        # Get repo
        repo = self.github.github.get_repo(self.config.github_repo)

        # Get issue
        logging.info(
            f"Getting issue with number {issue_number} from repo {self.config.github_repo}"
        )
        issue = repo.get_issue(number=issue_number)
        if issue is None:
            return
        logging.info(f"Got issue: {issue.html_url}")

        # Get YYYYMMDD from issue.title
        try:
            yyyymmdd = util.get_yyyymmdd_from_string(issue.title)
        except ValueError as ex:
            logging.info(
                f"issue title doesn't appear to look like a snapshot issue: {issue.title}: {ex}"
            )
            return

        # Get strategy from issue
        strategy: str | None = None
        labels = issue.get_labels()
        for label in labels:
            if label.name.startswith("strategy/"):
                strategy = label.name.removeprefix("strategy/")
                break
        if strategy is None:
            logging.info(
                f"No strategy label found in labels: {[label.name for label in labels]}"
            )
            return

        # Get trigger comment
        trigger_comment = issue.get_comment(id=trigger_comment_id)
        if trigger_comment is None:
            logging.info(f"Trigger comment with ID {trigger_comment_id} not found")
            return

        # Check chroots
        if chroots is None or len(chroots) == 0:
            logging.info("No chroots found")
            return

        logging.info(
            "Checking if all given chroots are really relevant for us or even chroots"
        )
        for chroot in chroots:
            logging.info(f"Checking chroot: {chroot}")
            if not util.is_chroot(chroot):
                logging.info(f"Chroot {chroot} is not a valid chroot.")
                return
            if chroot not in self.config.chroots:
                logging.info(
                    f"Chroot {chroot} is not in the list of chroots that we consider: {self.config.chroots}"
                )
                return

        # Now everything is validated!

        # Remove chroot HTML comments from issue body comment. The next time
        # around, a check-snapshots workflow runs, it will notice the absence of
        # a testing-farm request ID for a package with all Copr builds
        # successful.
        new_comment_body = issue.body
        for chroot in chroots:
            new_comment_body = tf.remove_chroot_html_comment(
                comment_body=new_comment_body, chroot=chroot
            )
        issue.edit(
            body=new_comment_body,
            title=self.github.issue_title(strategy=strategy, yyyymmdd=yyyymmdd),
        )

        # Kick off a new workflow run and pass the exact date in YYYYMMDD
        # form because we don't know if the issue was for today
        # or some other day.
        workflow = repo.get_workflow("check-snapshots.yml")
        inputs = {"strategy": strategy, "yyyymmdd": yyyymmdd}
        if not workflow.create_dispatch(ref="main", inputs=inputs):
            logging.info(
                f"Failed to create workflow dispatch event with inputs: {inputs}"
            )
            return

        # # Signal to the user that we've processed his retest request
        # # NOTE: This doesn't use the correct github PAT.
        # self.github.add_comment_reaction(
        #     trigger_comment, github_util.Reaction.THUMBS_UP
        # )
        logging.info(f"All done! Workflow dispatch event created with inputs: {inputs}")

    def check_todays_builds(self) -> None:
        """This method is driven from the config settings"""
        issue, issue_is_newly_created = self.github.create_or_get_todays_github_issue(
            creator=self.config.creator_handle,
        )

        if issue_is_newly_created:
            # The issue was newly created so we'll create comments for each
            # chroot that we care about and hide them for now. Then humanly
            # created output will always come at the end.
            for chroot in self.config.chroots:
                comment = issue.create_comment(
                    f"<!--ERRORS_FOR_CHROOT/{chroot}--> This is a placeholder for any errors that might happen for the <code>{chroot}</code> chroot."
                )
                self.github.minimize_comment_as_outdated(comment)

        else:
            # Only assign the issue now so that there are no notifications for
            # all the error comments we've just created.
            issue.add_to_assignees(self.config.maintainer_handle)

        logging.info("Get build states from copr")
        states = copr_util.get_all_build_states(
            client=self.copr,
            ownername=self.config.copr_ownername,
            projectname=self.config.copr_projectname,
        )

        logging.info("Filter states by chroot of interest")
        states = [state for state in states if state.chroot in self.config.chroots]

        logging.info("Augment the states with information from the build logs")
        states = [state.augment_with_error() for state in states]

        comment_body = issue.body

        logging.info("Add a build matrix")
        build_status_matrix = build_status.markdown_build_status_matrix(
            chroots=self.config.chroots,
            build_states=states,
        )

        logging.info("Get ordered list of errors to the issue's body comment")
        errors = build_status.list_only_errors(states=states)

        logging.info("Recover testing-farm requests")
        requests = tf.Request.parse(comment_body)

        # Migrate recovered requests without build IDs.
        # Just assign the build IDs of the current chroot respectively.
        for req in requests:
            if req.copr_build_ids == []:
                logging.info(
                    f"Migrating request ID {req.request_id} to get copr build IDs"
                )
                req.copr_build_ids = [
                    state.build_id for state in states if state.chroot == chroot
                ]

        # Immediately update issue comment and maybe later we update it again:
        logging.info("Update issue comment body")
        comment_body = f"""
{self.github.initial_comment}
{build_status_matrix}
{tf.requests_to_html_comment(requests)}
"""
        issue.edit(body=comment_body, title=self.github.issue_title())

        logging.info("Filter testing-farm requests by chroots of interest")
        requests = [req for req in requests if req.chroot in self.config.chroots]

        # logging.info(f"Update the issue comment body")
        # # See https://github.com/fedora-llvm-team/llvm-snapshots/issues/205#issuecomment-1902057639
        # max_length = 65536
        # logging.info(f"Checking for maximum length of comment body: {max_length}")
        # if len(comment_body) >= max_length:
        #     logging.info(
        #         f"Github only allows {max_length} characters on a comment body and we have reached {len(comment_body)} characters."
        #     )

        self.handle_labels(issue=issue, errors=errors)

        failed_test_cases: list[tf.FailedTestCase] = []

        for chroot in self.config.chroots:
            # Create or update a comment for each chroot that has errors and render
            errors_for_this_chroot = [
                error for error in errors if error.chroot == chroot
            ]
            marker = f"<!--ERRORS_FOR_CHROOT/{chroot}-->"
            if errors_for_this_chroot is not None and len(errors_for_this_chroot) > 0:
                comment = self.github.create_or_update_comment(
                    issue=issue,
                    marker=marker,
                    comment_body=f"""{marker}
<h3>Errors found in Copr builds on <code>{chroot}</code></h3>
{build_status.render_as_markdown(errors_for_this_chroot)}
""",
                )
                self.github.unminimize_comment(comment)
                build_status_matrix = build_status_matrix.replace(
                    chroot,
                    f'{chroot}<br /> :x: <a href="{comment.html_url}">Copr build(s) failed</a>',
                )
            else:
                # Hide any outdated comments
                comment = self.github.get_comment(issue=issue, marker=marker)
                if comment is not None:
                    self.github.minimize_comment_as_outdated(comment)

        for chroot in self.config.chroots:
            # Check if we can ignore the chroot because it is not supported by testing-farm
            if not tf.is_chroot_supported_by_ranch(chroot):
                # see https://docs.testing-farm.io/Testing%20Farm/0.1/test-environment.html#_supported_architectures
                logging.debug(
                    f"Ignoring chroot {chroot} because testing-farm doesn't support it."
                )
                continue

            in_testing = f"{self.config.label_prefix_in_testing}{chroot}"
            tested_on = f"{self.config.label_prefix_tested_on}{chroot}"
            failed_on = f"{self.config.label_prefix_tests_failed_on}{chroot}"

            # Gather build IDs associated with this chroot.
            # We'll attach them a new testing-farm request, and for a recovered
            # request we'll check if they still match the current ones.
            current_copr_build_ids = [
                state.build_id for state in states if state.chroot == chroot
            ]

            # Check if we need to invalidate a recovered testing-farm requests.
            # Background: It can be that we have old testing-farm request IDs in the issue comment.
            # But if a package was re-build and failed, the old request ID for that chroot is invalid.
            # To compensate for this scenario that we saw on April 1st 2024 btw., we're gonna
            # delete any request that has a different set of Copr build IDs associated with it.
            request = get_req_for_chroot(requests=requests, chroot=chroot)
            if request is not None:
                if set(request.copr_build_ids) != set(current_copr_build_ids):
                    logging.info(
                        f"Recovered request ({request.request_id}) invalid (build IDs changed):\\nRecovered: {request.copr_build_ids}\\nCurrent: {current_copr_build_ids}"
                    )
                    self.github.flip_test_label(
                        issue=issue, chroot=chroot, new_label=None
                    )
                    requests.remove(request)

            logging.info(f"Check if all builds in chroot {chroot} have succeeded")
            builds_succeeded = copr_util.has_all_good_builds(
                required_chroots=[chroot],
                states=states,
            )

            if not builds_succeeded:
                continue

            logging.info(f"All builds in chroot {chroot} have succeeded!")

            # Check for current status of testing-farm request
            request = get_req_for_chroot(requests=requests, chroot=chroot)
            if request is not None:
                watch_result, artifacts_url = request.watch()
                if watch_result is None and artifacts_url is None:
                    continue

                html = ""
                if watch_result is not None:
                    html = tf.render_html(request, watch_result, artifacts_url)
                build_status_matrix = build_status_matrix.replace(
                    chroot,
                    f"{chroot}<br />{html}",
                )

                logging.info(
                    f"Chroot {chroot} testing-farm watch result: {watch_result} (URL: {artifacts_url})"
                )

                if watch_result is not None and watch_result.is_error:
                    # Fetch all failed test cases for this request
                    failed_test_cases.extend(
                        request.fetch_failed_test_cases(
                            artifacts_url_origin=artifacts_url
                        )
                    )
                    self.github.flip_test_label(issue, chroot, failed_on)
                elif watch_result == tf.WatchResult.TESTS_PASSED:
                    self.github.flip_test_label(issue, chroot, tested_on)
                else:
                    self.github.flip_test_label(issue, chroot, in_testing)
            else:
                logging.info(f"Starting tests for chroot {chroot}")
                try:
                    request = tf.make_snapshot_gating_request(
                        chroot=chroot,
                        config=self.config,
                        issue=issue,
                        copr_build_ids=current_copr_build_ids,
                    )
                except SystemError as ex:
                    logging.warning(
                        f"testing-farm request for {chroot} failed with: {ex}"
                    )
                else:
                    logging.info(
                        f"testing-farm request ID for {chroot}: {request.request_id}"
                    )
                    requests.append(request)
                    self.github.flip_test_label(issue, chroot, in_testing)

            # Create or update a comment for testing-farm results display
            if len(failed_test_cases) > 0:
                self.github.create_or_update_comment(
                    issue=issue,
                    marker=tf.results_html_comment(),
                    comment_body=tf.FailedTestCase.render_list_as_markdown(
                        failed_test_cases
                    ),
                )

        logging.info("Constructing issue comment body")
        comment_body = f"""
{self.github.initial_comment}
{build_status_matrix}
{tf.requests_to_html_comment(requests)}
"""
        issue.edit(body=comment_body, title=self.github.issue_title())

        logging.info("Checking if issue can be closed")
        # issue.update()
        tested_chroot_labels = [
            label.name
            for label in issue.labels
            if label.name.startswith("{self.config.label_prefix_tested_on}")
        ]
        required_chroot_abels = [
            "{self.config.label_prefix_tested_on}{chroot}"
            for chroot in self.config.chroots
            if tfutil.is_chroot_supported_by_ranch(chroot=chroot)
        ]
        if set(tested_chroot_labels) == set(required_chroot_abels):
            msg = f"@{self.config.maintainer_handle}, all required packages have been successfully built and tested on all required chroots. We'll close this issue for you now as completed. Congratulations!"
            logging.info(msg)
            issue.create_comment(body=msg)
            issue.edit(
                state="closed",
                state_reason="completed",
                title=self.github.issue_title(),
            )
            # TODO(kwk): Promotion of issue goes here.
        else:
            logging.info("Cannot close issue yet.")

        logging.info(f"Updated today's issue: {issue.html_url}")

    def handle_labels(
        self,
        issue: github.Issue.Issue,
        errors: build_status.BuildStateList,
    ) -> None:
        logging.info("Gather labels based on the errors we've found")
        error_labels = list({f"error/{err.err_cause}" for err in errors})
        build_failed_on_labels = list(
            {f"build_failed_on/{err.chroot}" for err in errors}
        )
        strategy_labels = [f"strategy/{self.config.build_strategy}"]
        llvm_release = util.get_release_for_yyyymmdd(self.config.yyyymmdd)
        other_labels: list[str] = [
            f"{self.config.label_prefix_llvm_release}{llvm_release}"
        ]
        if errors is None and len(errors) > 0:
            other_labels.append("broken_snapshot_detected")

        logging.info("Create labels")
        self.github.create_labels(
            labels=["broken_snapshot_detected"], color="F46696", prefix=""
        )
        self.github.create_labels_for_error_causes(error_labels)
        self.github.create_labels_for_build_failed_on(build_failed_on_labels)
        self.github.create_labels_for_strategies(strategy_labels)
        self.github.create_labels_for_in_testing(self.config.chroots)
        self.github.create_labels_for_tested_on(self.config.chroots)
        self.github.create_labels_for_tests_failed_on(self.config.chroots)
        self.github.create_labels_for_llvm_releases([llvm_release])

        # Remove old labels from issue if they no longer apply. This is great
        # for restarted builds for example to make all builds green and be able
        # to promote this snapshot.

        labels_to_be_removed: list[str] = []
        old_error_labels = self.github.get_error_label_names_on_issue(issue=issue)
        old_build_failed_labels = self.github.get_build_failed_on_names_on_issue(
            issue=issue
        )

        labels_to_be_removed.extend(set(old_error_labels) - set(error_labels))
        labels_to_be_removed.extend(
            set(old_build_failed_labels) - set(build_failed_on_labels)
        )

        for label in labels_to_be_removed:
            logging.info(f"Removing label that no longer applies: {label}")
            issue.remove_from_labels(label=label)

        # Labels must be added or removed manually in order to not remove manually added labels :/
        labels_to_add = (
            error_labels + build_failed_on_labels + strategy_labels + other_labels
        )
        logging.info(f"Adding label: {labels_to_add}")
        issue.add_to_labels(*labels_to_add)


def run_performance_comparison(
    conf_a: config.Config,
    conf_b: config.Config,
    github_repo: str,
    copr_client: copr.v3.Client,
    github_client: github.Github,
) -> bool:
    """Runs a performance test for the two given configurations.

    NOTE: We will only run tests for the those chroots that are shared by both configurations.

    A github issue will be created that contains links and hidden HTML comments
    testing-farm request info for all chroot configs that were tested.

    If such a github issue already exists, this function will return immediately.

    Args:
        conf_a (config.Config): Configuration for build strategy A that we want to test
        conf_b (config.Config): Configuration for build strategy B that we want to test
        github_repo (str): Which repo to use for creating the the new issue for tracking the performance
        copr_client (copr.v3.Client): Copr client to use for inspecting which chroots are ready to be compared
        github_client (github.Github): Github client to use when creating issue for tracking the performance

    Returns:
        bool: If the operation was successful or not
    """
    # Check if we already have a performance issue for this combination
    issue = get_performance_github_issue(
        github_client=github_client,
        github_repo=github_repo,
        conf_a=conf_a,
        conf_b=conf_b,
    )
    if issue is not None:
        logging.info(
            f"Not starting new performance tests. Performance issue found: {issue.html_url}"
        )
        return False

    # Determine overlapping chroots of strategy A and B
    chroots_overlap = set(conf_a.chroots).intersection(set(conf_b.chroots))
    if chroots_overlap is None or len(chroots_overlap) == 0:
        logging.error(
            f"There are no overlapping chroots in for both strategies: {conf_a.build_strategy} ({conf_a.chroots}) and {conf_b.build_strategy} ({conf_b.chroots}"
        )
        return False

    states_a = copr_util.get_all_build_states(
        client=copr_client,
        ownername=conf_a.copr_ownername,
        projectname=conf_a.copr_projectname,
    )

    states_b = copr_util.get_all_build_states(
        client=copr_client,
        ownername=conf_b.copr_ownername,
        projectname=conf_b.copr_projectname,
    )

    # Make testing farm requests for each overlapping chroot with good builds.
    reqs: list[tf.Request] = []
    for chroot in chroots_overlap:
        # Only run performance comparison if both build strategies have
        # successful builds for the respective chroot
        successful_a = [
            state.package_name
            for state in states_a
            if state.chroot == chroot and state.success
        ]
        successful_b = [
            state.package_name
            for state in states_b
            if state.chroot == chroot and state.success
        ]
        if (len(successful_a) == 0 or len(successful_b) == 0) or (
            set(successful_a) != set(successful_b)
        ):
            logging.info(
                f"Skipping performance test for chroot {chroot} because not all builds were ready"
            )
            continue

        # TODO(kwk): Only run performance comparison if not already run.
        logging.info(f"Making performance request for chroot {chroot}")
        req = tf.make_compare_compile_time_request(
            config_a=conf_a, config_b=conf_b, chroot=chroot
        )
        logging.info(f"testing-farm request ID for {chroot}: {req.request_id}")
        reqs.append(req)

    if len(reqs) == 0:
        logging.info("No performance requests were made")
        return False

    # Create the performance issue
    comment_body = f"""
This issue exists to store the testing-farm request IDs that are later used for
fetching the artifacts of the performance runs.

{tf.requests_to_html_list(reqs)}

{tf.requests_to_html_comment(reqs)}
"""
    repo = github_client.get_repo(github_repo)
    issue = repo.create_issue(
        title=f"Performance comparison: {conf_a.build_strategy} vs. {conf_b.build_strategy} - {conf_a.yyyymmdd}",
        assignees=[conf_a.maintainer_handle, conf_b.maintainer_handle],
        labels=[
            f"strategy/{conf_a.build_strategy}",
            f"strategy/{conf_b.build_strategy}",
            "performance-comparison",
        ],
        body=comment_body,
    )

    logging.info(f"Performance issue created: {issue.html_url}")

    return True


def get_req_for_chroot(requests: list[tf.Request], chroot: str) -> tf.Request | None:
    """Returns the first request in the list that was made for the given chroot or None if no such request exists.

    Args:
        requests (list[tf.Request]): A list of requests to search
        chroot (str): A chroot to look for

    Returns:
        tf.Request|None: The first request that was made for the given chroot or None.
    """
    for req in requests:
        if req.chroot == chroot:
            return req
    return None


def collect_performance_comparison_results(
    conf_a: config.Config,
    conf_b: config.Config,
    github_repo: str,
    github_client: github.Github,
    csv_file_in: pathlib.Path | str,
    csv_file_out: pathlib.Path | str,
) -> bool:
    """Collect performance comparison results from testing-farm.

    If a "performance issue" was found in the given github repository we
    will recover any testing-farm requests from the issue's comment body.

    For every testing-farm request we're going to download the "results.csv"
    file from the overall test plan's artifact ("data/") directory.

    These "results.csv" files will be merged with the data in "csv_file_in"
    and then written to the "csv_file_out" file.

    Args:
        conf_a (config.Config): Configuration for build strategy A
        conf_b (config.Config): Configuration for build strategy B
        github_repo (str): Which repo to use for searching for the the issue that was created to track testing-farm request IDs
        github_client (github.Github): Github client to use when searching for the issue that was created to track testing-farm request IDs
        csv_file_in (pathlib.Path | str): Path to a CSV file that you want to merge with all the results coming in
        csv_file_out (pathlib.Path | str): Path to a CSV file that the merged result is written to.

    Returns:
        bool: If the operation was successful or not
    """

    # Check that we have a performance issue for this combination
    issue = get_performance_github_issue(
        github_client=github_client,
        github_repo=github_repo,
        conf_a=conf_a,
        conf_b=conf_b,
    )
    if issue is None:
        logging.info(
            f"Performance issue not found for {conf_a.build_strategy} vs {conf_b.build_strategy} - {conf_a.yyyymmdd}"
        )
        return False

    # Read the CSV file (if any) to which we want to append:
    df = pd.DataFrame()

    if isinstance(csv_file_in, str):
        csv_file_in = pathlib.Path(csv_file_in)
    if isinstance(csv_file_out, str):
        csv_file_out = pathlib.Path(csv_file_out)

    if csv_file_in.exists():
        df = pd.read_csv(csv_file_in)

    # Get list of requests
    requests = tf.Request.parse(issue.body)

    logging.info(requests)
    for req in requests:
        req_file = tf.get_request_file(tfutil.sanitize_request_id(req.request_id))
        xunit_file = tf.get_xunit_file_from_request_file(
            request_file=req_file, request_id=tfutil.sanitize_request_id(req.request_id)
        )
        if xunit_file is None:
            # This is not necessarily an error. It could b that the xuint URL
            # points to inside Red Hat.
            continue
        data_url = tf.get_testsuite_data_url_from_xunit_file(xunit_file=xunit_file)
        if data_url == "":
            logging.info("No data URL found in xunit file.")
            continue
        # Finally download the CSV file

        results_url = data_url + "/results.csv"
        logging.info(f"Downloading CSV file from {results_url}")
        if not tfutil._IN_TEST_MODE:
            csv_filepath = util.read_url_response_into_file(results_url)
        else:
            csv_filepath = tfutil._test_path(f"{req.request_id}/results.csv")

        # Append CSV rows from just downloaded CSV file to dataframe
        df_new = pd.read_csv(csv_filepath)
        df = pd.concat(objs=[df, df_new])

    # Write CSV file
    logging.info(f"Writing merged CSV file to {csv_file_out}")
    df.to_csv(csv_file_out, index=False)

    return True


def get_performance_github_issue(
    github_client: github.Github,
    github_repo: str,
    conf_a: config.Config,
    conf_b: config.Config,
    creator: str = "github-actions[bot]",
) -> github.Issue.Issue | None:
    """Search the github repo for a performance issue for the given configurations.

    run_performance_comparison() creates the performance issue and this function
    aims to retrieve it.

    Args:
        github_client (github.Github): The github client to use when searching
        github_repo (str): The repository to search
        conf_a (config.Config): The configuration for strategy A
        conf_b (config.Config): The configuration for strategy B
        creator (str, optional): The original creator of the github issue. Defaults to "github-actions[bot]".

    Returns:
        github.Issue.Issue | None: The performance issue or None if nothing was found.
    """
    # See https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests
    # label:broken_snapshot_detected
    query = f"is:issue repo:{github_repo} author:{creator} label:strategy/{conf_a.build_strategy} label:strategy/{conf_b.build_strategy} label:performance-comparison {conf_a.yyyymmdd} in:title"
    issues = github_client.search_issues(query)
    if issues is None:
        logging.info(f"Found no issue for query ({query})")
        return None

    # This is a hack: normally the PaginagedList[Issue] type handles this
    # for us but without this hack no issue being found.
    issues.get_page(0)
    if issues.totalCount > 0:
        issue: github.Issue.Issue = issues[0]
        return issue
    return None
