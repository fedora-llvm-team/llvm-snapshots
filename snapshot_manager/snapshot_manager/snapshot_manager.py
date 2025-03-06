"""
SnapshotManager
"""

import datetime
import logging
import re

import github.GithubException
import github.Issue
import github.Reaction

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config
import snapshot_manager.copr_util as copr_util
import snapshot_manager.github_graphql as ghgql
import snapshot_manager.github_util as github_util
import snapshot_manager.testing_farm_util as tf
import snapshot_manager.util as util


class SnapshotManager:

    def __init__(self, config: config.Config):
        self.config = config
        self.copr = copr_util.make_client()
        # In case this wasn't done before, augment the config with a list of
        # chroots of interest.
        if self.config.chroots is None:
            all_chroots = copr_util.get_all_chroots(client=self.copr)
            util.augment_config_with_chroots(config=config, all_chroots=all_chroots)
        self.github = github_util.GithubClient(config=config)

    @classmethod
    def remove_chroot_html_comment(cls, comment_body: str, chroot: str):
        """
        >>> chroot="fedora-40-aarch64"
        >>> req1 = f'<!--TESTING_FARM:{chroot}/68b70645-221d-4391-a918-06db7f414a48/7320315,7320317,7320318,7320316,7320314,7320231,7320313-->'
        >>> req2 = '<!--TESTING_FARM:fedora-40-ppc64le/eee0e5d5-2d7a-4cbd-9b7d-7d60a10c40fe/7320327,7320329,7320330,7320328,7320326,7320231,7320325-->'
        >>> input = f'''foo
        ... {req1}
        ... {req2}
        ... bar'''
        >>> expected = f'''foo
        ...
        ... {req2}
        ... bar'''
        >>> actual = SnapshotManager.remove_chroot_html_comment(comment_body=input, chroot=chroot)
        >>> actual == expected
        True
        """
        util.expect_chroot(chroot)
        pattern = re.compile(rf"<!--TESTING_FARM:\s*{chroot}/.*?-->")
        return re.sub(pattern=pattern, repl="", string=comment_body)

    def retest(
        self, issue_number: int, trigger_comment_id: str, chroots: list[str]
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
            trigger_comment_id (str): The ID of the comment in which the user requested a retest
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
        strategy: str = None
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
            f"Checking if all given chroots are really relevant for us or even chroots"
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
            new_comment_body = self.remove_chroot_html_comment(
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
        # if issue.state == "closed":
        #     logging.info(
        #         f"Issue {issue.html_url} was already closed. Not doing anything."
        #     )
        #     return

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
            client=self.copr.copr,
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
            packages=self.config.packages,
            build_states=states,
        )

        logging.info("Get ordered list of errors to the issue's body comment")
        errors = build_status.list_only_errors(states=states)

        logging.info("Recover testing-farm requests")
        requests = tf.TestingFarmRequest.parse(comment_body)
        if requests is None:
            requests = dict()

        # Migrate recovered requests without build IDs.
        # Just assign the build IDs of the current chroot respectively.
        for chroot in requests:
            if requests[chroot].copr_build_ids == []:
                logging.info(
                    f"Migrating request ID {requests[chroot].request_id} to get copr build IDs"
                )
                requests[chroot].copr_build_ids = [
                    state.build_id for state in states if state.chroot == chroot
                ]

        # Immediately update issue comment and maybe later we update it again:
        logging.info("Update issue comment body")
        comment_body = f"""
{self.github.initial_comment}
{build_status_matrix}
{tf.TestingFarmRequest.dict_to_html_comment(requests)}
"""
        issue.edit(body=comment_body, title=self.github.issue_title())

        logging.info("Filter testing-farm requests by chroot of interest")
        new_requests = dict()
        for chroot in requests:
            if chroot in self.config.chroots:
                new_requests[chroot] = requests[chroot]
        requests = new_requests

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
            if not tf.TestingFarmRequest.is_chroot_supported(chroot):
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
            if chroot in requests:
                recovered_request = requests[chroot]
                if set(recovered_request.copr_build_ids) != set(current_copr_build_ids):
                    logging.info(
                        f"Recovered request ({recovered_request.request_id}) invalid (build IDs changed):\\nRecovered: {recovered_request.copr_build_ids}\\nCurrent: {current_copr_build_ids}"
                    )
                    self.github.flip_test_label(
                        issue=issue, chroot=chroot, new_label=None
                    )
                    del requests[chroot]

            logging.info(f"Check if all builds in chroot {chroot} have succeeded")
            builds_succeeded = self.copr.has_all_good_builds(
                copr_ownername=self.config.copr_ownername,
                copr_projectname=self.config.copr_projectname,
                required_chroots=[chroot],
                required_packages=self.config.packages,
                states=states,
            )

            if not builds_succeeded:
                continue

            logging.info(f"All builds in chroot {chroot} have succeeded!")

            # Check for current status of testing-farm request
            if chroot in requests:
                request = requests[chroot]
                watch_result, artifacts_url = request.watch()
                if watch_result is None and artifacts_url is None:
                    continue

                html = tf.render_html(request, watch_result, artifacts_url)
                build_status_matrix = build_status_matrix.replace(
                    chroot,
                    f"{chroot}<br />{html}",
                )

                logging.info(
                    f"Chroot {chroot} testing-farm watch result: {watch_result} (URL: {artifacts_url})"
                )

                if watch_result.is_error:
                    # Fetch all failed test cases for this request
                    failed_test_cases.extend(
                        request.fetch_failed_test_cases(
                            artifacts_url_origin=artifacts_url
                        )
                    )
                    self.github.flip_test_label(issue, chroot, failed_on)
                elif watch_result == tf.TestingFarmWatchResult.TESTS_PASSED:
                    self.github.flip_test_label(issue, chroot, tested_on)
                else:
                    self.github.flip_test_label(issue, chroot, in_testing)
            else:
                logging.info(f"Starting tests for chroot {chroot}")
                try:
                    request = tf.TestingFarmRequest.make(
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
                    requests[chroot] = request
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
{tf.TestingFarmRequest.dict_to_html_comment(requests)}
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
            if tf.TestingFarmRequest.is_chroot_supported(chroot)
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
    ):
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
