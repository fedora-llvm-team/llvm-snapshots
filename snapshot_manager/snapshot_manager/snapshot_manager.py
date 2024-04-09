"""
SnapshotManager
"""

import datetime
import logging
import os

import github.Issue

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config
import snapshot_manager.copr_util as copr_util
import snapshot_manager.github_graphql as ghgql
import snapshot_manager.github_util as github_util
import snapshot_manager.testing_farm_util as tf
import snapshot_manager.util as util


class SnapshotManager:

    def __init__(self, config: config.Config = config.Config()):
        self.config = config
        self.copr = copr_util.CoprClient(config=config)
        self.github = github_util.GithubClient(config=config)

    def check_todays_builds(self):
        """This method is driven from the config settings"""
        issue, _ = self.github.create_or_get_todays_github_issue(
            maintainer_handle=self.config.maintainer_handle,
            creator=self.config.creator_handle,
        )
        # if issue.state == "closed":
        #     logging.info(
        #         f"Issue {issue.html_url} was already closed. Not doing anything."
        #     )
        #     return

        all_chroots = self.copr.get_copr_chroots()

        logging.info("Get build states from copr")
        states = self.copr.get_build_states_from_copr_monitor(
            copr_ownername=self.config.copr_ownername,
            copr_projectname=self.config.copr_projectname,
        )
        logging.info("Augment the states with information from the build logs")
        states = [state.augment_with_error() for state in states]

        comment_body = issue.body

        logging.info("Add a build matrix")
        build_status_matrix = build_status.markdown_build_status_matrix(
            chroots=all_chroots,
            packages=self.config.packages,
            build_states=states,
        )

        logging.info("Get ordered list of errors to the issue's body comment")
        errors = build_status.list_only_errors(states=states)

        logging.info("Recover testing-farm requests")
        requests = tf.TestingFarmRequest.parse(comment_body)
        if requests is None:
            requests = dict()

        # logging.info(f"Update the issue comment body")
        # # See https://github.com/fedora-llvm-team/llvm-snapshots/issues/205#issuecomment-1902057639
        # max_length = 65536
        # logging.info(f"Checking for maximum length of comment body: {max_length}")
        # if len(comment_body) >= max_length:
        #     logging.info(
        #         f"Github only allows {max_length} characters on a comment body and we have reached {len(comment_body)} characters."
        #     )

        self.handle_labels(issue=issue, all_chroots=all_chroots, errors=errors)

        failed_test_cases: list[tf.FailedTestCase] = []

        for chroot in all_chroots:
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
                build_status_matrix = build_status_matrix.replace(
                    chroot,
                    f'{chroot}<br /> :x: <a href="{comment.html_url}">Copr build(s) failed</a>',
                )
            else:
                # Hide any outdated comments
                comment = self.github.get_comment(issue=issue, marker=marker)
                if comment is not None:
                    self.github.minimize_comment_as_outdated(comment)

        for chroot in all_chroots:
            # Check if we can ignore the chroot because it is not supported by testing-farm
            if not tf.TestingFarmRequest.is_chroot_supported(chroot):
                # see https://docs.testing-farm.io/Testing%20Farm/0.1/test-environment.html#_supported_architectures
                logging.debug(
                    f"Ignoring chroot {chroot} because testing-farm doesn't support it."
                )
                continue

            in_testing = f"{self.config.label_prefix_in_testing}{chroot}"
            tested_on = f"{self.config.label_prefix_tested_on}{chroot}"
            failed_on = f"{self.config.label_prefix_tested_on}{chroot}"

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
                        request.fetch_failed_test_cases_from_url(
                            artifacts_url=artifacts_url
                        )
                    )
                    self.github.flip_test_label(issue, chroot, failed_on)
                elif watch_result == tf.TestingFarmWatchResult.TESTS_PASSED:
                    self.github.flip_test_label(issue, chroot, tested_on)
                else:
                    self.github.flip_test_label(issue, chroot, in_testing)
            else:
                logging.info(f"Starting tests for chroot {chroot}")
                request = tf.TestingFarmRequest.make(
                    chroot=chroot,
                    config=self.config,
                    issue=issue,
                    copr_build_ids=current_copr_build_ids,
                )
                logging.info(f"Request ID: {request.request_id}")
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
        issue.edit(body=comment_body)

        logging.info("Checking if issue can be closed")
        # issue.update()
        tested_chroot_labels = [
            label.name
            for label in issue.labels
            if label.name.startswith("{self.config.label_prefix_tested_on}")
        ]
        required_chroot_abels = [
            "{self.config.label_prefix_tested_on}{chroot}"
            for chroot in all_chroots
            if tf.TestingFarmRequest.is_chroot_supported(chroot)
        ]
        if set(tested_chroot_labels) == set(required_chroot_abels):
            msg = f"@{self.config.maintainer_handle}, all required packages have been successfully built and tested on all required chroots. We'll close this issue for you now as completed. Congratulations!"
            logging.info(msg)
            issue.create_comment(body=msg)
            issue.edit(state="closed", state_reason="completed")
            # TODO(kwk): Promotion of issue goes here.
        else:
            logging.info("Cannot close issue yet.")

        logging.info(f"Updated today's issue: {issue.html_url}")

    def handle_labels(
        self,
        issue: github.Issue.Issue,
        all_chroots: list[str],
        errors: build_status.BuildStateList,
    ):
        logging.info("Gather labels based on the errors we've found")
        error_labels = list({f"error/{err.err_cause}" for err in errors})
        project_labels = list({f"project/{err.package_name}" for err in errors})
        os_labels = list({f"os/{err.os}" for err in errors})
        arch_labels = list({f"arch/{err.arch}" for err in errors})
        strategy_labels = [f"strategy/{self.config.build_strategy}"]
        other_labels: list[str] = []
        if errors is None and len(errors) > 0:
            other_labels.append("broken_snapshot_detected")

        logging.info("Create labels")
        self.github.create_labels(
            labels=["broken_snapshot_detected"], color="F46696", prefix=""
        )
        self.github.create_labels_for_error_causes(error_labels)
        self.github.create_labels_for_oses(os_labels)
        self.github.create_labels_for_projects(project_labels)
        self.github.create_labels_for_archs(arch_labels)
        self.github.create_labels_for_strategies(strategy_labels)
        self.github.create_labels_for_in_testing(all_chroots)
        self.github.create_labels_for_tested_on(all_chroots)
        self.github.create_labels_for_failed_on(all_chroots)

        # Remove old labels from issue if they no longer apply. This is great
        # for restarted builds for example to make all builds green and be able
        # to promote this snapshot.

        labels_to_be_removed: list[str] = []
        old_error_labels = self.github.get_error_label_names_on_issue(issue=issue)
        old_project_labels = self.github.get_project_label_names_on_issue(issue=issue)
        old_arch_labels = self.github.get_arch_label_names_on_issue(issue=issue)

        labels_to_be_removed.extend(set(old_error_labels) - set(error_labels))
        labels_to_be_removed.extend(set(old_project_labels) - set(project_labels))
        labels_to_be_removed.extend(set(old_arch_labels) - set(arch_labels))

        for label in labels_to_be_removed:
            logging.info(f"Removing label that no longer applies: {label}")
            issue.remove_from_labels(label=label)

        # Labels must be added or removed manually in order to not remove manually added labels :/
        labels_to_add = (
            error_labels
            + project_labels
            + os_labels
            + arch_labels
            + strategy_labels
            + other_labels
        )
        logging.info(f"Adding label: {labels_to_add}")
        issue.add_to_labels(*labels_to_add)
