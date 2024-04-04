"""
SnapshotManager
"""

import datetime
import logging
import github.Issue

import snapshot_manager.build_status as build_status
import snapshot_manager.copr_util as copr_util
import snapshot_manager.github_util as github_util
import snapshot_manager.config as config
import snapshot_manager.util as util
import snapshot_manager.testing_farm_util as tf


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
        if issue.state == "closed":
            logging.info(
                f"Issue {issue.html_url} was already closed. Not doing anything."
            )
            return

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

        logging.info("Append ordered list of errors to the issue's body comment")
        errors = build_status.list_only_errors(states=states)

        logging.info(
            "Extract and sanitize testing-farm information out of the last comment body."
        )
        testing_farm_requests = tf.TestingFarmRequest.parse(comment_body)
        logging.info(testing_farm_requests)

        # logging.info(f"Update the issue comment body")
        # # See https://github.com/fedora-llvm-team/llvm-snapshots/issues/205#issuecomment-1902057639
        # max_length = 65536
        # logging.info(f"Checking for maximum length of comment body: {max_length}")
        # if len(comment_body) >= max_length:
        #     logging.info(
        #         f"Github only allows {max_length} characters on a comment body and we have reached {len(comment_body)} characters."
        #     )

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
        self.github._create_labels(
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

        # Remove old labels from issue if they no longer apply. This is greate
        # for restarted builds for example to make all builds green and be able
        # to promote this snapshot.

        labels_to_be_removed: list[str] = []
        old_error_labels = self.github.get_error_labels_on_issue(issue=issue)
        old_project_labels = self.github.get_project_labels_on_issue(issue=issue)
        old_arch_labels = self.github.get_arch_labels_on_issue(issue=issue)

        labels_to_be_removed.extend(set(old_error_labels) - set(error_labels))
        labels_to_be_removed.extend(set(old_project_labels) - set(project_labels))
        labels_to_be_removed.extend(set(old_arch_labels) - set(arch_labels))

        for label in labels_to_be_removed:
            logging.info(f"Removing label that no longer applies: {label}")
            issue.remove_from_labels(label=label)

        # Labels must be added or removed manually in order to not remove manually added labels :/
        for label in (
            error_labels
            + project_labels
            + os_labels
            + arch_labels
            + strategy_labels
            + other_labels
        ):
            logging.info(f"Adding label: {label}")
            issue.add_to_labels(label)

        labels_on_issue = [label.name for label in issue.labels]

        failed_test_cases: list[tf.FailedTestCase] = []

        for chroot in all_chroots:
            # Define some label names
            in_testing = f"{self.config.label_prefix_in_testing}{chroot}"
            tested_on = f"{self.config.label_prefix_tested_on}{chroot}"
            failed_on = f"{self.config.label_prefix_tested_on}{chroot}"

            if not tf.is_chroot_supported(chroot):
                # see https://docs.testing-farm.io/Testing%20Farm/0.1/test-environment.html#_supported_architectures
                logging.debug(
                    f"Ignoring chroot {chroot} because testing-farm doesn't support it."
                )
                continue

            # Gather build IDs associated with this chroot.
            current_copr_build_ids = [
                state.build_id for state in states if state.chroot == chroot
            ]

            def flip_test_label(issue: github.Issue.Issue, new_label: str | None):
                all_states = [in_testing, tested_on, failed_on]
                labels_to_be_removed = all_states
                if new_label is not None:
                    labels_to_be_removed = [set(all_states).difference(new_label)]
                self.github.remove_labels_safe(issue, labels_to_be_removed)
                issue.add_to_labels(new_label)

            # Check if we need to invalidate a recovered testing-farm requests.
            # Background: It can be that we have old testing-farm request IDs in the issue comment.
            # But if a package was re-build and failed, the old request ID for that chroot is invalid.
            # To compensate for this scenario that we saw on April 1st 2024 btw., we're gonna
            # delete any request that has a different set of Copr build IDs associated with it.
            if chroot in testing_farm_requests:
                recovered_request = testing_farm_requests[chroot]
                if set(recovered_request.copr_build_ids) != set(current_copr_build_ids):
                    logging.info(
                        "The recovered testing-farm request no longer applies because build IDs have changed"
                    )
                    flip_test_label(issue, None)
                    del testing_farm_requests[chroot]

            tf.TestingFarmRequest(chroot=chroot)

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
            if chroot in testing_farm_requests:
                request = testing_farm_requests[chroot]
                watch_result, artifacts_url = request.watch()

                html = tf.render_html(request, watch_result, artifacts_url)
                build_status_matrix = build_status_matrix.replace(
                    chroot,
                    f"{chroot}<br />{html}",
                )

                # Fetch all failed tests for this request
                if watch_result.is_error:
                    failed_test_cases.extend(
                        request.fetch_failed_test_cases(artifacts_url=artifacts_url)
                    )

                logging.info(
                    f"Chroot {chroot} testing-farm watch result: {watch_result} (URL: {artifacts_url})"
                )

                if watch_result.is_error:
                    flip_test_label(issue, failed_on)
                elif watch_result == tf.TestingFarmWatchResult.TESTS_PASSED:
                    flip_test_label(issue, tested_on)
            else:
                logging.info(f"Starting tests for chroot {chroot}")
                request_id = tf.TestingFarmRequest.make(
                    chroot=chroot,
                    config=self.config,
                    issue=issue,
                    copr_build_ids=current_copr_build_ids,
                )
                logging.info(f"Request ID: {request_id}")
                testing_farm_requests[chroot] = request_id
                flip_test_label(issue, in_testing)

            if len(failed_test_cases) > 0:
                self.github.create_or_update_comment(
                    issue=issue,
                    marker=tf.results_html_comment(),
                    comment_body=tf.FailedTestCase.render_list_as_markdown(
                        failed_test_cases
                    ),
                )

        logging.info("Reconstructing issue comment body")
        comment_body = f"""
{self.github.initial_comment}
{build_status_matrix}
{build_status.render_as_markdown(errors)}
{tf.TestingFarmRequest.dict_to_html_comment(testing_farm_requests)}
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
            if tf.is_chroot_supported(chroot)
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
