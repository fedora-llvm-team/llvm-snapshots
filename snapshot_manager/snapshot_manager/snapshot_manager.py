"""
SnapshotManager
"""

import datetime
import logging

import snapshot_manager.build_status as build_status
import snapshot_manager.copr_util as copr_util
import snapshot_manager.github_util as github_util
import snapshot_manager.config as config


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

        logging.info("Get build states from copr")
        states = self.copr.get_build_states_from_copr_monitor(
            copr_ownername=self.config.copr_ownername,
            copr_projectname=self.config.copr_projectname,
        )
        logging.info("Augment the states with information from the build logs")
        states = [state.augment_with_error() for state in states]

        comment_body = issue.body

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
            chroots=self.copr.get_copr_chroots(),
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
        if errors is None or len(errors) > 0:
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

        logging.info("Checking if issue can be closed")
        all_good = self.copr.has_all_good_builds(
            copr_ownername=self.config.copr_ownername,
            copr_projectname=self.config.copr_projectname,
            required_chroots=self.copr.get_copr_chroots(),
            required_packages=self.config.packages,
            states=states,
        )
        if all_good:
            msg = f"@{self.config.maintainer_handle}, all required packages have been successfully built in all required chroots. We'll close this issue for you now as completed. Congratulations!"
            logging.info(msg)
            issue.create_comment(body=msg)
            issue.edit(state="closed", state_reason="completed")

        logging.info(f"Updated today's issue: {issue.html_url}")
