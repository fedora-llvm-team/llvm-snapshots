"""
github_util
"""

import datetime
import os
import logging
import fnc
import typing
import pathlib

import github
import github.GithubException
import github.Issue
import github.IssueComment
import github.Repository
import github.PaginatedList
import github.Label

import snapshot_manager.config as config
import snapshot_manager.build_status as build_status
import snapshot_manager.github_graphql as github_graphql


class GithubClient:
    dirname = pathlib.Path(os.path.dirname(__file__))

    def __init__(self, config: config.Config, github_token: str = None, **kwargs):
        """
        Keyword Arguments:
            github_token (str, optional): github personal access token.
        """
        self.config = config
        if github_token is None:
            github_token = os.getenv(self.config.github_token_env)
        self.github = github.Github(login_or_token=github_token)
        self.gql = github_graphql.GithubGraphQL(
            token=os.getenv(self.config.github_token_env), raise_on_error=True
        )
        self.__label_cache = None
        self.__repo_cache = None

    @classmethod
    def abspath(cls, p: tuple[str, pathlib.Path]) -> pathlib.Path:
        return cls.dirname.joinpath(p)

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
        if issues is not None and issues.totalCount > 0:
            logging.info(f"Found today's issue: {issues[0].html_url}")
            return issues[0]
        logging.info("Found no issue for today")
        return None

    @property
    def initial_comment(self) -> str:
        return f"""
Hello @{self.config.maintainer_handle}!

<p>
This issue exists to let you know that we are about to monitor the builds
of the LLVM snapshot for <a href="{self.config.copr_monitor_url}">{self.config.yyyymmdd}</a>.
<details>
<summary>At certain intervals the CI system will update this very comment over time to reflect the progress of builds.</summary>
<dl>
<dt>Log analysis</dt>
<dd>For example if a build of the <code>llvm</code> project fails on the <code>fedora-rawhide-x86_64</code> platform,
we'll analyze the build log (if any) to identify the cause of the failure. The cause can be any of <code>{build_status.ErrorCause.list()}</code>.
For each cause we will list the packages and the relevant log excerpts.</dd>
<dt>Use of labels</dt>
<dd>Let's assume a unit test test in upstream LLVM was broken.
We will then add these labels to this issue: <code>error/test</code>, <code>arch/x86_64</code>, <code>os/fedora-rawhide</code>, <code>project/llvm</code>.
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

    def create_or_get_todays_github_issue(
        self,
        maintainer_handle: str,
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
        repo = self.gh_repo
        logging.info("Creating issue for today")
        issue = repo.create_issue(
            assignee=maintainer_handle,
            title=f"Snapshot build for {self.config.yyyymmdd} ({strategy})",
            body=self.initial_comment,
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
        if self.__label_cache is None or refresh:
            self.__label_cache = self.gh_repo.get_labels()
        return self.__label_cache

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
            return None

        labels = set(labels)
        labels = list(labels)
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
            except:
                self.gh_repo.get_label(name=labelname).edit(
                    name=labelname, color=color, description=""
                )
        return res

    def get_label_names_on_issue(
        self, issue: github.Issue.Issue, prefix: str
    ) -> list[str]:
        return [
            label.name for label in issue.get_labels() if label.name.startswith(prefix)
        ]

    def get_error_label_names_on_issue(self, issue: github.Issue.Issue) -> list[str]:
        return self.get_label_names_on_issue(issue, prefix="error/")

    def get_os_label_names_on_issue(self, issue: github.Issue.Issue) -> list[str]:
        return self.get_label_names_on_issue(issue, prefix="os/")

    def get_arch_label_names_on_issue(self, issue: github.Issue.Issue) -> list[str]:
        return self.get_label_names_on_issue(issue, prefix="arch/")

    def get_project_label_names_on_issue(self, issue: github.Issue.Issue) -> list[str]:
        return self.get_label_names_on_issue(issue, prefix="project/")

    def create_labels_for_error_causes(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels, prefix="error/", color="FBCA04", **kw_args
        )

    def create_labels_for_oses(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels, prefix="os/", color="F9D0C4", **kw_args
        )

    def create_labels_for_projects(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels, prefix="project/", color="BFDADC", **kw_args
        )

    def create_labels_for_strategies(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels, prefix="strategy/", color="FFFFFF", *kw_args
        )

    def create_labels_for_archs(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels, prefix="arch/", color="C5DEF5", *kw_args
        )

    def create_labels_for_in_testing(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix=self.config.label_prefix_in_testing,
            color="FEF2C0",
            *kw_args,
        )

    def create_labels_for_tested_on(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix=self.config.label_prefix_tested_on,
            color="0E8A16",
            *kw_args,
        )

    def create_labels_for_failed_on(
        self, labels: list[str], **kw_args
    ) -> list[github.Label.Label]:
        return self.create_labels(
            labels=labels,
            prefix=self.config.label_prefix_failed_on,
            color="D93F0B",
            *kw_args,
        )

    def get_comment(
        self, issue: github.Issue.Issue, marker: str
    ) -> github.IssueComment.IssueComment:
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

    def create_or_update_comment(
        self, issue: github.Issue.Issue, marker: str, comment_body: str
    ) -> github.IssueComment.IssueComment:
        comment = self.get_comment(issue=issue, marker=marker)
        if comment is None:
            return issue.create_comment(body=comment_body)
        comment.edit(body=comment_body)
        return comment

    def remove_labels_safe(
        self, issue: github.Issue.Issue, label_names_to_be_removed: list[str]
    ):
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

    @typing.overload
    def minimize_comment_as_outdated(
        self, comment: github.IssueComment.IssueComment
    ) -> bool: ...

    @typing.overload
    def minimize_comment_as_outdated(self, node_id: str) -> bool: ...

    def minimize_comment_as_outdated(
        self,
        object: str | github.IssueComment.IssueComment,
    ) -> bool:
        """Minimizes a comment with the given `node_id` and the reason `OUTDATED`.

        Args:
            node_id (str): A comment's `node_id`.

        Returns:
            bool: True if the comment was minimized
        """

        node_id = ""
        if isinstance(object, github.IssueComment.IssueComment):
            node_id = object.raw_data["node_id"]
        elif isinstance(object, str):
            node_id = object
        else:
            raise ValueError(f"invalid comment object passed: {object}")

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

    def label_in_testing(self, chroot: str) -> str:
        return f"{self.config.label_prefix_in_testing}{chroot}"

    def label_failed_on(self, chroot: str) -> str:
        return f"{self.config.label_prefix_failed_on}{chroot}"

    def label_tested_on(self, chroot: str) -> str:
        return f"{self.config.label_prefix_tested_on}{chroot}"

    def flip_test_label(
        self, issue: github.Issue.Issue, chroot: str, new_label: str | None
    ):
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
            issue.add_to_labels(new_label)
