"""
SnapshotManager
"""

import datetime
import logging
import os
import re

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
            maintainer_handle=self.config.maintainer_handle
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

        logging.info(
            "Shorten the issue body comment to the update marker so that we can append to it"
        )
        comment_body = comment_body[: comment_body.find(self.config.update_marker)]
        comment_body += self.config.update_marker
        comment_body += (
            f"<p><b>Last Updated: {datetime.datetime.now().isoformat()}</b></p>"
        )

        logging.info("Add a build matrix")
        comment_body += build_status.markdown_build_status_matrix(
            chroots=all_chroots,
            packages=self.config.packages,
            build_states=states,
        )

        logging.info("Append ordered list of errors to the issue's body comment")
        errors = build_status.list_only_errors(states=states)
        comment_body += build_status.render_as_markdown(errors)

        logging.info(f"Update the issue comment body")
        # See https://github.com/fedora-llvm-team/llvm-snapshots/issues/205#issuecomment-1902057639
        max_length = 65536
        logging.info(f"Checking for maximum length of comment body: {max_length}")
        if len(comment_body) >= max_length:
            logging.info(
                f"Github only allows {max_length} characters on a comment body and we have reached {len(comment_body)} characters."
            )
        issue.edit(body=comment_body)

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

            if f"in_testing/{chroot}" in labels_on_issue:
                logging.info(
                    f"Chroot {chroot} is currently in testing! Not kicking off new tests."
                )
                if chroot in testing_farm_requests:
                    request_id = testing_farm_requests[chroot]
                    watch_result, artifacts_url = self.watch_testing_farm_request(
                        request_id=request_id
                    )
                    if watch_result in [
                        tf.TestingFarmWatchResult.TESTS_ERROR,
                        tf.TestingFarmWatchResult.TESTS_FAILED,
                    ]:
                        issue.remove_from_labels(f"in_testing/{chroot}")
                        issue.add_to_labels(f"failed_on/{chroot}")
                    elif watch_result == tf.TestingFarmWatchResult.TESTS_PASSED:
                        issue.remove_from_labels(f"in_testing/{chroot}")
                        issue.add_to_labels(f"tested_on/{chroot}")

            elif f"tested_on/{chroot}" in labels_on_issue:
                logging.info(
                    f"Chroot {chroot} has passed tests testing! Not kicking off new tests."
                )
            elif f"failed_on/{chroot}" in labels_on_issue:
                logging.info(
                    f"Chroot {chroot} has unsuccessful tests! Not kicking off new tests."
                )
            else:
                logging.info(f"chroot {chroot} has no tests associated yet.")
                request_id = self.make_testing_farm_request(chroot=chroot)
                testing_farm_requests[chroot] = request_id
                issue.add_to_labels(f"in_testing/{chroot}")

        logging.info("Appending testing farm requests to the comment body.")
        comment_body += "\n\n" + tf.chroot_request_ids_to_html_comment(
            testing_farm_requests
        )
        issue.edit(body=comment_body)

        logging.info("Checking if issue can be closed")
        issue.update()
        tested_chroot_labels = [
            label.name for label in issue.labels if label.name.startswith("tested_on/")
        ]
        required_chroot_abels = ["tested_on/{chroot}" for chroot in all_chroots]
        if set(tested_chroot_labels) == set(required_chroot_abels):
            msg = f"@{self.config.maintainer_handle}, all required packages have been successfully built and tested on all required chroots. We'll close this issue for you now as completed. Congratulations!"
            logging.info(msg)
            issue.create_comment(body=msg)
            issue.edit(state="closed", state_reason="completed")
            # TODO(kwk): Promotion of issue goes here.
        else:
            logging.info("Cannot close issue yet.")

        logging.info(f"Updated today's issue: {issue.html_url}")

    def watch_testing_farm_request(
        self, request_id: str
    ) -> tuple[tf.TestingFarmWatchResult, str]:
        request_id = tf.sanitize_request_id(request_id=request_id)
        cmd = f"testing-farm watch --no-wait --id {request_id}"
        exit_code, stdout, stderr = util.run_cmd(cmd=cmd)
        if exit_code != 0:
            raise SystemError(
                f"failed to watch 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
            )

        watch_result, artifacts_url = tf.parse_for_watch_result(stdout)
        if watch_result is None:
            raise SystemError(
                f"failed to watch 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
            )
        return (watch_result, artifacts_url)

    def make_testing_farm_request(self, chroot: str) -> str:
        """Runs a "testing-farm request" command and returns the request ID.

        The request is made without waiting for the result.
        It is the responsibility of the caller of this function to run "testing-farm watch --id <REQUEST_ID>",
        where "<REQUEST_ID>" is the result of this function.

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
            str: Request ID
        """
        logging.info(f"Kicking off new tests for chroot {chroot}.")
        all_tests_succeeded = False

        # TODO(kwk): Add testing-farm code here, something like this:
        # TODO(kwk): Decide how if we want to wait for test results (probably not) and if not how we can check for the results later.
        ranch = tf.select_ranch(chroot)
        logging.info(f"Using testing-farm ranch: {ranch}")
        if ranch == "public":
            os.environ["TESTING_FARM_API_TOKEN"] = os.getenv(
                "TESTING_FARM_API_TOKEN_PUBLIC_RANCH"
            )
        if ranch == "redhat":
            os.environ["TESTING_FARM_API_TOKEN"] = os.getenv(
                "TESTING_FARM_API_TOKEN_REDHAT_RANCH"
            )
        cmd = f"""testing-farm \
            request \
            --compose {util.chroot_os(chroot).capitalize()} \
            --git-url {self.config.test_repo_url} \
            --arch {util.chroot_arch(chroot)} \
            --plan /tests/snapshot-gating \
            --environment COPR_PROJECT={self.config.copr_projectname} \
            --context distro={util.chroot_os(chroot)} \
            --context arch=${util.chroot_arch(chroot)} \
            --no-wait \
            --context snapshot={self.config.yyyymmdd}"""
        exit_code, stdout, stderr = util.run_cmd(cmd, timeout_secs=None)
        if exit_code == 0:
            return tf.parse_output_for_request_id(stdout)
        raise SystemError(
            f"failed to run 'testing-farm request': {cmd}\n\nstdout: {stdout}\n\nstderr: {stderr}"
        )
