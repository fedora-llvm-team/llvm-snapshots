"""
github_util
"""

import datetime
import enum
import logging
import os
import pathlib

import fnc
import github
import github.GithubException
import github.Issue
import github.IssueComment
import github.Label
import github.PaginatedList
import github.Repository

import snapshot_manager.build_status as build_status
import snapshot_manager.config as config
import snapshot_manager.github_graphql as github_graphql
import snapshot_manager.util as util


@enum.unique
class Reaction(enum.StrEnum):
    """An enum to represent the possible comment reactions"""

    THUMBS_UP = "THUMBS_UP"  # Represents the :+1: emoji.
    THUMBS_DOWN = "THUMBS_DOWN"  # Represents the :-1: emoji.
    LAUGH = "LAUGH"  # Represents the :laugh: emoji.
    HOORAY = "HOORAY"  # Represents the :hooray: emoji.
    CONFUSED = "CONFUSED"  # Represents the :confused: emoji.
    HEART = "HEART"  # Represents the :heart: emoji.
    ROCKET = "ROCKET"  # Represents the :rocket: emoji.
    EYES = "EYES"  # Represents the :eyes: emoji.


class MissingToken(Exception):
    """Could not retrieve a Github token."""


class GithubClient:
    dirname = pathlib.Path(os.path.dirname(__file__))

    def __init__(
        self,
        config: config.Config,
        github_token: str | None = None,
    ):
        """
        Keyword Arguments:
            config (config.Config): A config object to be used to get the name of the github token environment variable.
            github_token (str, optional): github personal access token.
        """
        self.config = config
        if github_token != "" or github_token is not None:
            logging.info(
                f"Reading Github token from this environment variable: {self.config.github_token_env}"
            )
            github_token = os.getenv(self.config.github_token_env)
        if github_token is None or len(github_token) == 0:
            # We can't proceed without a Github token, otherwise we'll trigger
            # an assertion failure.
            raise MissingToken("Could not retrieve the token")
        auth = github.Auth.Token(github_token)
        self.github = github.Github(auth=auth)
        self.gql = github_graphql.GithubGraphQL(token=github_token, raise_on_error=True)
        self._label_cache = None
        self.__repo_cache: github.Repository.Repository | None = None

    @classmethod
    def abspath(cls, p: str | pathlib.Path) -> pathlib.Path:
        return cls.dirname.joinpath(str(p))

    @property
    def gh_repo(self) -> github.Repository.Repository:
        if self.__repo_cache is None:
            self.__repo_cache = self.github.get_repo(self.config.github_repo)
        return self.__repo_cache

    def get_todays_github_issue(
        self,
        strategy: str,
        creator: str = "github-actions[bot]",
        github_repo: str | None = None,
    ) -> github.Issue.Issue | None:
        """Returns the github issue (if any) for today's snapshot that was build with the given strategy.

        If no issue was found, `None` is returned.

        Args:
            strategy (str): The build strategy to pick (e.g. "standalone", "big-merge").
            creator (str|None, optional): The author who should have created the issue. Defaults to github-actions[bot]
            repo (str|None, optional): The repo to use. This is only useful for testing purposes. Defaults to None which will result in whatever the github_repo property has.

        Raises:
            ValueError if the strategy is empty

        Returns:
            github.Issue.Issue|None: The found issue or None.
        """
        if not strategy:
            raise ValueError("parameter 'strategy' must not be empty")

        if github_repo is None:
            github_repo = self.config.github_repo

        # See https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests
        # label:broken_snapshot_detected
        query = f"is:issue repo:{github_repo} author:{creator} label:strategy/{strategy} {self.config.yyyymmdd} in:title"
        issues = self.github.search_issues(query)
        if issues is None:
            logging.info(f"Found no issue for today ({self.config.yyyymmdd})")
            return None

        # This is a hack: normally the PaginagedList[Issue] type handles this
        # for us but without this hack no issue being found.
        issues.get_page(0)
        if issues.totalCount > 0:
            logging.info(
                f"Found today's ({self.config.yyyymmdd}) issue: {issues[0].html_url}"
            )
            return issues[0]
        return None

    @property
    def initial_comment(self) -> str:
        llvm_release = util.get_release_for_yyyymmdd(self.config.yyyymmdd)
        llvm_git_revision = util.get_git_revision_for_yyyymmdd(self.config.yyyymmdd)
        return f"""
<p>
This issue exists to let you know that we are about to monitor the builds
of the LLVM (v{llvm_release}, <a href="https://github.com/llvm/llvm-project/commit/{llvm_git_revision}">llvm/llvm-project@ {llvm_git_revision[:7]}</a>) snapshot for <a href="{self.config.copr_monitor_url}">{self.config.yyyymmdd}</a>.
<details>
<summary>At certain intervals the CI system will update this very comment over time to reflect the progress of builds.</summary>
<dl>
<dt>Log analysis</dt>
<dd>For example if a build fails on the <code>fedora-rawhide-x86_64</code> platform,
we'll analyze the build log (if any) to identify the cause of the failure. The cause can be any of <code>{build_status.ErrorCause.list()}</code>.
For each cause we will list the packages and the relevant log excerpts.</dd>
<dt>Use of labels</dt>
<dd>Let's assume a unit test test in upstream LLVM was broken.
We will then add these labels to this issue: <code>error/test</code>, <code>build_failed_on/fedora-rawhide-x86_64</code>.
If you manually restart a build in Copr and can bring it to a successful state, we will automatically
remove the aforementioned labels.
</dd>
</dl>
</details>
</p>

{self.config.update_marker}

{self.last_updated_html()}
"""

    @classmethod
    def last_updated_html(cls) -> str:
        return f"<p><b>Last updated: {datetime.datetime.now().isoformat()}</b></p>"

    def issue_title(self, strategy: str = "", yyyymmdd: str = "") -> str:
        """Constructs the issue title we want to use"""
        if strategy == "":
            strategy = self.config.build_strategy
        if yyyymmdd == "":
            yyyymmdd = self.config.yyyymmdd
        llvm_release = util.get_release_for_yyyymmdd(yyyymmdd)
        llvm_git_revision = util.get_git_revision_for_yyyymmdd(yyyymmdd)
        return f"Snapshot for {yyyymmdd}, v{llvm_release}, {llvm_git_revision[:7]} ({strategy})"

    def create_or_get_todays_github_issue(
        self,
        creator: str = "github-actions[bot]",
    ) -> tuple[github.Issue.Issue, bool]:
        issue = self.get_todays_github_issue(
            strategy=self.config.build_strategy,
            creator=creator,
            github_repo=self.config.github_repo,
        )
        if issue is not None:
            return (issue, False)

        strategy = self.config.build_strategy
        logging.info("Creating issue for today")

        issue = self.gh_repo.create_issue(
            title=self.issue_title(), body=self.initial_comment
        )
        self.create_labels_for_strategies(labels=[strategy])

        issue.add_to_labels(f"strategy/{strategy}")
        return (issue, True)

    @property
    def label_cache(self, refresh: bool = False) -> github.PaginatedList.PaginatedList:
        """Will query the labels of a github repo only once and return it afterwards.

        Args:
            refresh (bool, optional): The cache will be emptied. Defaults to False.

        Returns:
            github.PaginatedList.PaginatedList: An enumerable list of github.Label.Label objects
        """
        if self._label_cache is None or refresh:
            self._label_cache = self.gh_repo.get_labels()
        return self._label_cache

    def is_label_in_cache(self, name: str, color: str) -> bool:
        """Returns True if the label exists in the cache.

        Args:
            name (str): Name of the label to look for
            color (str): Color string of the label to look for

        Returns:
            bool: True if the label is in the cache
        """
        for label in self.label_cache:
            if label.name == name and label.color == color:
                return True
        return False

    def create_labels(
        self,
        prefix: str,
        color: str,
        labels: list[str] = [],
    ) -> list[github.Label.Label]:
        """Iterates over the given labels and creates or edits each label in the list
        with the given prefix and color."""
        if labels is None or len(labels) == 0:
            return []

        labels = list(set(labels))
        labels.sort()
        res = []
        for label in labels:
            labelname = label
            if not labelname.startswith(prefix):
                labelname = f"{prefix}{label}"
            if self.is_label_in_cache(name=labelname, color=color):
                continue
            logging.info(
                f"Creating label: repo={self.config.github_repo} name={labelname} color={color}",
            )
            try:
                res.append(self.gh_repo.create_label(color=color, name=labelname))
            except:  # noqa: E722
                self.gh_repo.get_label(name=labelname).edit(
                    name=labelname, color=color, description=""
                )
        return res

    @classmethod
    def get_label_names_on_issue(
        cls, issue: github.Issue.Issue, prefix: str
    ) -> list[str]:
        return [
            label.name for label in issue.get_labels() if label.name.startswith(prefix)
        ]

    @classmethod
    def get_error_label_names_on_issue(cls, issue: github.Issue.Issue) -> list[str]:
        return cls.get_label_names_on_issue(issue, prefix="error/")

    @classmethod
    def get_build_failed_on_names_on_issue(cls, issue: github.Issue.Issue) -> list[str]:
        return cls.get_label_names_on_issue(issue, prefix="build_failed_on/")

    def create_labels_for_error_causes(
        self,
        labels: list[str],
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix="error/",
            color="FBCA04",
        )

    def create_labels_for_build_failed_on(
        self,
        labels: list[str],
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix="build_failed_on/",
            color="F9D0C4",
        )

    def create_labels_for_strategies(
        self,
        labels: list[str],
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix="strategy/",
            color="FFFFFF",
        )

    def create_labels_for_in_testing(
        self,
        labels: list[str],
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix=self.config.label_prefix_in_testing,
            color="FEF2C0",
        )

    def create_labels_for_tested_on(
        self,
        labels: list[str],
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix=self.config.label_prefix_tested_on,
            color="0E8A16",
        )

    def create_labels_for_tests_failed_on(
        self,
        labels: list[str],
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix=self.config.label_prefix_tests_failed_on,
            color="D93F0B",
        )

    def create_labels_for_llvm_releases(
        self,
        labels: list[str],
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix=self.config.label_prefix_llvm_release,
            color="2F3950",
        )

    @classmethod
    def get_comment(
        cls, issue: github.Issue.Issue, marker: str
    ) -> github.IssueComment.IssueComment | None:
        """Walks through all comments associated with the `issue` and returns the first one that has the `marker` in its body.

        Args:
            issue (github.Issue.Issue): The github issue to look for
            marker (str): The text to look for in the comment's body. (e.g. `"<!--MY MARKER-->"`)

        Returns:
            github.IssueComment.IssueComment: The comment containing the marker or `None`.
        """
        for comment in issue.get_comments():
            if marker in comment.body:
                return comment
        return None

    @classmethod
    def create_or_update_comment(
        cls, issue: github.Issue.Issue, marker: str, comment_body: str
    ) -> github.IssueComment.IssueComment:
        comment = cls.get_comment(issue=issue, marker=marker)
        if comment is None:
            return issue.create_comment(body=comment_body)
        try:
            comment.edit(body=comment_body)
        except github.GithubException as ex:
            raise ValueError(
                f"Failed to update github comment with marker {marker} and comment body: {comment_body}"
            ) from ex
        return comment

    @classmethod
    def remove_labels_safe(
        cls, issue: github.Issue.Issue, label_names_to_be_removed: list[str]
    ) -> None:
        """Removes all of the given labels from the issue.

        Args:
            issue (github.Issue.Issue): The issue from which to remove the labels
            label_names_to_be_removed (list[str]): A list of label names that shall be removed if they exist on the issue.
        """
        current_set = {label.name for label in issue.get_labels()}

        remove_set = set(label_names_to_be_removed)
        intersection = current_set.intersection(remove_set)
        for label in intersection:
            logging.info(f"Removing label '{label}' from issue: {issue.title}")
            issue.remove_from_labels(label)

    def minimize_comment_as_outdated(
        self,
        issue_comment_or_node_id: github.IssueComment.IssueComment | str,
    ) -> bool:
        """Minimizes a comment identified by the `issue_comment_or_node_id` argument with the reason `OUTDATED`.

        Args:
            issue_comment_or_node_id (str | github.IssueComment.IssueComment): The comment object or its node ID to add minimize.

        Raises:
            ValueError: If the `issue_comment_or_node_id` has a wrong type.

        Returns:
            bool: True if the comment was properly minimized.
        """
        node_id = ""
        if isinstance(issue_comment_or_node_id, github.IssueComment.IssueComment):
            node_id = issue_comment_or_node_id.raw_data["node_id"]
        elif isinstance(issue_comment_or_node_id, str):
            node_id = issue_comment_or_node_id
        else:
            raise ValueError(
                f"invalid comment object passed: {issue_comment_or_node_id}"
            )

        res = self.gql.run_from_file(
            variables={
                "classifier": "OUTDATED",
                "id": node_id,
            },
            filename=self.abspath("graphql/minimize_comment.gql"),
        )

        return bool(
            fnc.get(
                "data.minimizeComment.minimizedComment.isMinimized", res, default=False
            )
        )

    def unminimize_comment(
        self,
        issue_comment_or_node_id: github.IssueComment.IssueComment | str,
    ) -> bool:
        """Unminimizes a comment with the given `issue_comment_or_node_id`.

        Args:
            issue_comment_or_node_id (str): The comment object or its node ID to add unminimize.

        Raises:
            ValueError: If the `issue_comment_or_node_id` has a wrong type.

        Returns:
            bool: True if the comment was unminimized
        """

        node_id = ""
        if isinstance(issue_comment_or_node_id, github.IssueComment.IssueComment):
            node_id = issue_comment_or_node_id.raw_data["node_id"]
        elif isinstance(issue_comment_or_node_id, str):
            node_id = issue_comment_or_node_id
        else:
            raise ValueError(
                f"invalid comment object passed: {issue_comment_or_node_id}"
            )

        res = self.gql.run_from_file(
            variables={
                "id": node_id,
            },
            filename=self.abspath("graphql/unminimize_comment.gql"),
        )

        is_minimized = fnc.get(
            "data.unminimizeComment.unminimizedComment.isMinimized", res, default=True
        )
        return not is_minimized

    def add_comment_reaction(
        self,
        issue_comment_or_node_id: github.IssueComment.IssueComment | str,
        reaction: Reaction,
    ) -> bool:
        """Adds a reaction to a comment with the given emoji name

        Args:
            issue_comment_or_node_id (github.IssueComment.IssueComment|str): The comment object or its node ID to add reaction to.
            reaction (Reaction): The name of the reaction.

        Raises:
            ValueError: If the the `issue_comment_or_node_id` has a wrong type.

        Returns:
            bool: True if the comment reaction was added successfully.
        """
        node_id = ""
        if isinstance(issue_comment_or_node_id, github.IssueComment.IssueComment):
            node_id = issue_comment_or_node_id.raw_data["node_id"]
        elif isinstance(issue_comment_or_node_id, str):
            node_id = issue_comment_or_node_id
        else:
            raise ValueError(
                f"invalid comment object passed: {issue_comment_or_node_id}"
            )

        res = self.gql.run_from_file(
            variables={
                "comment_id": node_id,
                "reaction": reaction,
            },
            filename=self.abspath("graphql/add_comment_reaction.gql"),
        )

        actual_reaction = fnc.get(
            "data.addReaction.reaction.content", res, default=None
        )
        actual_comment_id = fnc.get("data.addReaction.subject.id", res, default=None)

        return str(actual_reaction) == str(reaction) and str(actual_comment_id) == str(
            node_id
        )

    def label_in_testing(self, chroot: str) -> str:
        return f"{self.config.label_prefix_in_testing}{chroot}"

    def label_failed_on(self, chroot: str) -> str:
        return f"{self.config.label_prefix_tests_failed_on}{chroot}"

    def label_tested_on(self, chroot: str) -> str:
        return f"{self.config.label_prefix_tested_on}{chroot}"

    def flip_test_label(
        self, issue: github.Issue.Issue, chroot: str, new_label: str | None
    ) -> None:
        """Let's you change the label on an issue for a specific chroot.

         If `new_label` is `None`, then all test labels will be removed.

        Args:
            issue (github.Issue.Issue): The issue to modify
            chroot (str): The chroot for which you want to flip the test label
            new_label (str | None): The new label or `None`.
        """
        in_testing = self.label_in_testing(chroot)
        tested_on = self.label_tested_on(chroot)
        failed_on = self.label_failed_on(chroot)

        all_states = [in_testing, tested_on, failed_on]
        existing_test_labels = [
            label.name for label in issue.get_labels() if label.name in all_states
        ]

        new_label_already_present = False
        for label in existing_test_labels:
            if label != new_label:
                issue.remove_from_labels(label)
            else:
                new_label_already_present = True

        if not new_label_already_present:
            if new_label is not None:
                issue.add_to_labels(new_label)
