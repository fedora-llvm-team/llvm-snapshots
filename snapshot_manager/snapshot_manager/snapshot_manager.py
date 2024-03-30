"""
SnapshotManager
"""

import datetime
import logging

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

        logging.info(
            "Extract and sanitize testing-farm information out of the last comment body."
        )
        testing_farm_requests = tf.parse_comment_for_request_ids(comment_body)
        logging.info(testing_farm_requests)

        logging.info("Add a build matrix")
        build_status_matrix = build_status.markdown_build_status_matrix(
            chroots=all_chroots,
            packages=self.config.packages,
            build_states=states,
        )

        logging.info("Append ordered list of errors to the issue's body comment")
        errors = build_status.list_only_errors(states=states)
        errors_as_markdown = build_status.render_as_markdown(errors)

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

        for chroot in all_chroots:
            if not tf.is_chroot_supported(chroot):
                # see https://docs.testing-farm.io/Testing%20Farm/0.1/test-environment.html#_supported_architectures
                logging.debug(
                    f"Ignoring chroot {chroot} because testing-farm doesn't support it."
                )
                continue
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

            failed_test_cases: tf.FailedTestCaseList = []

            testing_farm_comment = None
            for comment in issue.get_comments():
                if tf.results_html_comment() in comment.body:
                    testing_farm_comment = comment

            # Check for current status of testing-farm request
            if chroot in testing_farm_requests:
                request_id = testing_farm_requests[chroot]
                watch_result, artifacts_url = tf.watch_testing_farm_request(
                    request_id=request_id
                )

                if artifacts_url is not None:
                    vpn = ""
                    if tf.select_ranch(chroot) == "redhat":
                        vpn = " :lock: "
                    build_status_matrix = build_status_matrix.replace(
                        chroot,
                        f'{chroot}<br /><a href="{artifacts_url}">{watch_result.to_icon()} {watch_result}{vpn}</a>',
                    )

                if watch_result.is_error:
                    failed_test_cases.extend(
                        tf.fetch_failed_test_cases(
                            request_id=request_id, artifacts_url=artifacts_url
                        )
                    )

                logging.info(
                    f"Chroot {chroot} testing-farm watch result: {watch_result} (URL: {artifacts_url})"
                )
                if watch_result in [
                    tf.TestingFarmWatchResult.TESTS_ERROR,
                    tf.TestingFarmWatchResult.TESTS_FAILED,
                ]:
                    if f"in_testing/{chroot}" in labels_on_issue:
                        issue.remove_from_labels(f"in_testing/{chroot}")
                    if f"tested_on/{chroot}" in labels_on_issue:
                        issue.remove_from_labels(f"tested_on/{chroot}")
                    issue.add_to_labels(f"failed_on/{chroot}")
                elif watch_result == tf.TestingFarmWatchResult.TESTS_PASSED:
                    if f"in_testing/{chroot}" in labels_on_issue:
                        issue.remove_from_labels(f"in_testing/{chroot}")
                    if f"failed_on/{chroot}" in labels_on_issue:
                        issue.remove_from_labels(f"failed_on/{chroot}")
                    issue.add_to_labels(f"tested_on/{chroot}")
            else:
                logging.info(f"Starting tests for chroot {chroot}")
                request_id = tf.make_testing_farm_request(
                    chroot=chroot,
                    config=self.config,
                    issue=issue,
                )
                logging.info(f"Request ID: {request_id}")
                testing_farm_requests[chroot] = request_id
                issue.add_to_labels(f"in_testing/{chroot}")

            if len(failed_test_cases) > 0:
                testing_farm_comment_body = f"""
{tf.results_html_comment()}

<h1>Test results are in!</h1>

<p><b>Last updated: {datetime.datetime.now().isoformat()}</b></p>

Some (if not all) results from testing-farm are in. This comment will be updated over time and is detached from the main issue comment because we want to preserve the logs entirely and not shorten them.

> [!NOTE]
> Please be aware that testing-farm the artifact links a valid for no longer than 90 days. That is why we persists the log outputs here.

> [!WARNING]
> This list is not extensive if test have been run in the Red Hat internal testing-farm ranch and failed. For those, take a look in the "chroot" column of the build matrix above and look for failed tests that show a :lock: symbol.

{tf.render_as_markdown(failed_test_cases)}
"""
                if testing_farm_comment is None:
                    issue.create_comment(body=testing_farm_comment_body)
                else:
                    testing_farm_comment.edit(body=testing_farm_comment_body)

        logging.info("Reconstructing issue comment body")
        comment_body = f"""
{self.github.initial_comment}
{build_status_matrix}
{errors_as_markdown}
{tf.chroot_request_ids_to_html_comment(testing_farm_requests)}
"""
        issue.edit(body=comment_body)

        logging.info("Checking if issue can be closed")
        # issue.update()
        tested_chroot_labels = [
            label.name for label in issue.labels if label.name.startswith("tested_on/")
        ]
        required_chroot_abels = [
            "tested_on/{chroot}"
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
