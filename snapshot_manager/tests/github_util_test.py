""" Tests for github_util """

import collections
import datetime
from collections.abc import Generator
from unittest import mock

import github.GithubException
import github.Issue
import pytest
import tests.base_test as base_test

import snapshot_manager.config as config
import snapshot_manager.github_util as github_util
import snapshot_manager.util as util


@pytest.fixture
def config_fxt() -> config.Config:
    """Returns an example config"""
    return config.Config(github_repo="fedora-llvm-team/llvm-snapshots")


@pytest.fixture
def github_client_fxt(config_fxt) -> Generator[github_util.GithubClient]:
    """Yields a github client with important parts mocked"""
    gh = github_util.GithubClient(config=config_fxt, github_token="foobar")
    with mock.patch.object(gh.github, "get_repo", autospec=True) as get_repo_mock:
        get_repo_mock.return_value = mock.MagicMock()
        yield gh


# To fake/mock some github objects...
MyComment = collections.namedtuple("MyComment", "body", defaults=(""))
MyLabel = collections.namedtuple("MyLabel", "name, color", defaults=("", ""))


@pytest.fixture
def label_cache_fxt(github_client_fxt) -> github_util.GithubClient:
    """Populates the given github client fixture with labels in its cache"""
    github_client_fxt._label_cache = [
        MyLabel(name="error/srpm_build_issue", color="FBCA04"),
        MyLabel(name="error/copr_timeout", color="FBCA04"),
        MyLabel(name="error/network_issue", color="FBCA04"),
        MyLabel(name="error/dependency_issue", color="FBCA04"),
        #  MyLabel(name= "error/test", color= "FBCA04"),
        MyLabel(name="error/downstream_patch_application", color="FBCA04"),
        MyLabel(name="error/rpm__installed_but_unpackaged_files_found", color="FBCA04"),
        MyLabel(name="error/rpm__file_not_found", color="FBCA04"),
        MyLabel(name="error/cmake_error", color="FBCA04"),
        #  MyLabel(name= "error/unknown", color= "FBCA04"),
    ]
    return github_client_fxt


def test_get_todays_issue(github_client_fxt):
    gh = github_client_fxt
    with pytest.raises(expected_exception=ValueError) as actualCtx:
        gh.get_todays_github_issue(strategy=None)
    assert str(actualCtx.value) == "parameter 'strategy' must not be empty"


def test_get_todays_issue_search_query(github_client_fxt):
    gh = github_client_fxt
    gh.github.search_issues = mock.Mock()
    gh.github.search_issues.return_value = None
    res = gh.get_todays_github_issue(strategy="big-merge")

    assert res is None
    yyyymmdd = datetime.datetime.now().strftime("%Y%m%d")
    query_str = f"is:issue repo:{gh.config.github_repo} author:github-actions[bot] label:strategy/big-merge {yyyymmdd} in:title"
    gh.github.search_issues.assert_called_once_with(query_str)


@mock.patch(
    "snapshot_manager.util.get_release_for_yyyymmdd",
    return_value="20",
    autospec=True,
)
@mock.patch(
    "snapshot_manager.util.get_git_revision_for_yyyymmdd",
    return_value="f5421dcb36572616e8061e51b333196f363a8732",
    autospec=True,
)
def test_initial_comment(revision_mock, release_mock, github_client_fxt):
    comment = github_client_fxt.initial_comment
    assert github_client_fxt.config.update_marker in comment
    assert release_mock.return_value in comment
    assert revision_mock.return_value in comment


@mock.patch.object(util, "get_release_for_yyyymmdd", return_value="20")
@mock.patch.object(
    util,
    "get_git_revision_for_yyyymmdd",
    return_value="f5421dcb36572616e8061e51b333196f363a8732",
)
def test_issue_title(revision_mock, release_mock, github_client_fxt):
    gh = github_client_fxt
    strategy = "myownstrategy"
    yyyymmdd = "20241203"
    expected_title = f"Snapshot for {yyyymmdd}, v{release_mock.return_value}, {revision_mock.return_value[:7]} ({strategy})"
    actual_title = gh.issue_title(strategy=strategy, yyyymmdd=yyyymmdd)
    assert actual_title == expected_title


def test_last_updated_html():
    now = datetime.datetime(year=2024, month=2, day=27)
    with mock.patch("datetime.datetime", wraps=datetime.datetime) as mock_datetime:
        mock_datetime.now.return_value = now
        expected = f"<p><b>Last updated: {now.isoformat()}</b></p>"
        actual = github_util.GithubClient.last_updated_html()
        assert actual == expected


@mock.patch.object(util, "get_release_for_yyyymmdd", return_value="20")
@mock.patch.object(
    util,
    "get_git_revision_for_yyyymmdd",
    return_value="f5421dcb36572616e8061e51b333196f363a8732",
)
def test_create_or_get_todays_github_issue__issue_exists(
    revision_mock, release_mock, github_client_fxt
):
    gh = github_client_fxt
    # Test case in which today's issue DOES exists:
    with mock.patch.object(gh, "get_todays_github_issue", wraps=gh) as gh_mock:
        # An issue for today
        gh_mock.return_value = "foo"
        actual = gh.create_or_get_todays_github_issue()
        expected = ("foo", False)
        assert actual == expected
        gh_mock.assert_called_once_with(
            strategy=gh.config.build_strategy,
            creator="github-actions[bot]",
            github_repo=gh.config.github_repo,
        )


# Cannot find an issue for today
@mock.patch.object(
    github_util.GithubClient,
    "create_labels_for_strategies",
    return_value=mock.MagicMock(),
)
@mock.patch.object(
    github_util.GithubClient, "get_todays_github_issue", return_value=None
)
@mock.patch.object(util, "get_release_for_yyyymmdd", return_value="20")
@mock.patch.object(
    util,
    "get_git_revision_for_yyyymmdd",
    return_value="f5421dcb36572616e8061e51b333196f363a8732",
)
def test_create_or_get_todays_github_issue__issue_created(
    revision_mock: mock.Mock,
    release_mock: mock.Mock,
    get_todays_github_issue_mock: mock.Mock,
    create_labels_for_strategies_mock: mock.Mock,
    github_client_fxt,
):
    """Test creation of a new issue by mocking that no issue exists for today."""
    gh = github_client_fxt
    with mock.patch.object(gh.github, "get_repo") as get_repo_mock:
        get_repo_mock.return_value = mock.MagicMock()

        with mock.patch.object(gh.gh_repo, "create_issue") as create_issue_mock:
            create_issue_mock.return_value = mock.MagicMock()
            create_issue_mock.return_value.return_value = "NewIssue"

            actual = gh.create_or_get_todays_github_issue()
            expected = (create_issue_mock.return_value, True)
            assert actual == expected

            get_todays_github_issue_mock.assert_called_once_with(
                strategy=gh.config.build_strategy,
                creator="github-actions[bot]",
                github_repo=gh.config.github_repo,
            )
            get_repo_mock.assert_called_once()
            create_issue_mock.assert_called_once()

            # TODO(kwk): Check that add_to_labels was called.

            create_labels_for_strategies_mock.assert_called_once_with(
                labels=[gh.config.build_strategy]
            )


def test_label_cache__not_empty(github_client_fxt):
    """Check that the label cache is NOT empty"""
    gh = github_client_fxt
    with mock.patch.object(gh, "_label_cache", return_value=[1, 2, 3]):
        actual = gh.label_cache()
        expected = [1, 2, 3]
        assert actual == expected


def test_label_cache__empty(github_client_fxt):
    """Check that the label IS empty"""
    expected = [2, 3, 4]
    gh = github_client_fxt
    gh._label_cache = None
    with mock.patch.object(
        gh.gh_repo, "get_labels", return_value=[2, 3, 4]
    ) as mock_get_labels:
        actual = gh.label_cache
        assert actual == expected
        mock_get_labels.assert_called_once()


def test_label_in_cache(github_client_fxt):
    gh = github_client_fxt
    MyLabel = collections.namedtuple("MyLabel", "name, color")
    gh._label_cache = [
        MyLabel(name="Red", color="red"),
        MyLabel(name="Blue", color="blue"),
    ]
    assert gh.is_label_in_cache(name="Red", color="red") == True
    assert gh.is_label_in_cache(name="Blue", color="blue") == True
    assert gh.is_label_in_cache(name="Blue", color="blueish") == False
    assert gh.is_label_in_cache(name="Green", color="green") == False


def test_create_labels__empty_list(label_cache_fxt):
    gh = label_cache_fxt
    assert gh.create_labels(prefix="myprefix", color="yellow", labels=[]) is None
    assert gh.create_labels(prefix="myprefix", color="yellow", labels=None) is None


def test_create_labels__already_in_cache(label_cache_fxt):
    gh = label_cache_fxt
    actual = gh.create_labels(
        prefix="error/", color="FBCA04", labels=["network_issue", "cmake_error"]
    )
    expected = []
    assert actual == expected


def test_create_labels__not_in_cache(label_cache_fxt):
    gh = label_cache_fxt
    with mock.patch.object(gh.gh_repo, "create_label") as create_label_mock:
        expected = MyLabel(name="error/test", color="FBCA04")
        create_label_mock.return_value = expected
        actual = gh.create_labels(prefix="error/", color="FBCA04", labels=["test"])
        assert actual == [expected]
        create_label_mock.assert_called_once_with(name="error/test", color="FBCA04")


def test_create_labels__exception(label_cache_fxt):
    gh = label_cache_fxt
    with mock.patch.object(gh.gh_repo, "create_label") as create_label_mock:

        # Simulate the label is not in cache (aka. not loaded) but exists
        create_label_mock.side_effect = Exception("Boom")

        with mock.patch.object(gh.gh_repo, "get_label") as get_label_mock:
            gh.create_labels(prefix="error/", color="FBCA04", labels=["test"])

            create_label_mock.assert_called_once_with(name="error/test", color="FBCA04")
            get_label_mock.assert_called_once_with(name="error/test")

            # Check that the fetched label is edited
            get_label_mock.return_value.edit.assert_called_once_with(
                name="error/test", color="FBCA04", description=""
            )


def label_testdata(only_ids: bool = False):
    # (testid, label, lambda function to create label, lambda function to create expected label)
    testdata = [
        (
            "create_labels_for_error_causes",
            "myerror",
            lambda gh, labels: gh.create_labels_for_error_causes(labels=labels),
            lambda lbl: MyLabel(name=f"error/{lbl}", color="FBCA04"),
        ),
        (
            "create_labels_for_build_failed_on",
            "fedora-41-x86_64",
            lambda gh, labels: gh.create_labels_for_build_failed_on(labels=labels),
            lambda lbl: MyLabel(name=f"build_failed_on/{lbl}", color="F9D0C4"),
        ),
        (
            "create_labels_for_strategies",
            "mystrategy",
            lambda gh, labels: gh.create_labels_for_strategies(labels=labels),
            lambda lbl: MyLabel(name=f"strategy/{lbl}", color="FFFFFF"),
        ),
        (
            "create_labels_for_in_testing",
            "fedora-rawhide-x86_64",
            lambda gh, labels: gh.create_labels_for_in_testing(labels=labels),
            lambda lbl: MyLabel(name=f"in_testing/{lbl}", color="FEF2C0"),
        ),
        (
            "create_labels_for_tested_on",
            "fedora-40-x86_64",
            lambda gh, labels: gh.create_labels_for_tested_on(labels=labels),
            lambda lbl: MyLabel(name=f"tests_succeeded_on/{lbl}", color="0E8A16"),
        ),
        (
            "create_labels_for_tests_failed_on",
            "fedora-39-x86_64",
            lambda gh, labels: gh.create_labels_for_tests_failed_on(labels=labels),
            lambda lbl: MyLabel(name=f"tests_failed_on/{lbl}", color="D93F0B"),
        ),
        (
            "create_labels_for_llvm_releases",
            "24",
            lambda gh, labels: gh.create_labels_for_llvm_releases(labels=labels),
            lambda lbl: MyLabel(name=f"release/{lbl}", color="2F3950"),
        ),
    ]

    if only_ids:
        return [t[0] for t in testdata]

    return testdata


@pytest.mark.parametrize(
    "test_id, label, create_func, expected_func",
    label_testdata(),
    ids=label_testdata(only_ids=True),
)
def test_create_labels(test_id, label, create_func, expected_func, github_client_fxt):
    gh = github_client_fxt
    with mock.patch.object(gh, "create_labels") as create_labels_mock:
        expected = expected_func(label)
        create_labels_mock.return_value = [expected]
        actual = create_func(gh, [label])
        assert actual == [expected]
        create_labels_mock.assert_called_once_with(
            labels=[label],
            color=expected.color,
            prefix=expected.name.split("/")[0] + "/",
        )


@mock.patch("github.Issue.Issue", autospec=True)
def test_get_label_names_on_issue(issue_mock: mock.Mock):
    issue_mock.get_labels.return_value = [
        MyLabel(name="error/foo"),
        MyLabel(name="error/bar"),
        MyLabel(name="tested_on/fedora-rawhide-x86_64"),
    ]
    actual = github_util.GithubClient.get_label_names_on_issue(
        issue=issue_mock, prefix="error/"
    )
    expected = ["error/foo", "error/bar"]
    assert actual == expected


@mock.patch("github.Issue.Issue", autospec=True)
def test_get_error_label_names_on_issue(issue_mock: mock.Mock):
    issue_mock.get_labels.return_value = [
        MyLabel(name="error/foo"),
        MyLabel(name="error/bar"),
        MyLabel(name="tested_on/fedora-rawhide-x86_64"),
    ]
    actual = github_util.GithubClient.get_error_label_names_on_issue(issue=issue_mock)
    expected = ["error/foo", "error/bar"]
    assert actual == expected


@mock.patch("github.Issue.Issue", autospec=True)
def test_get_build_failed_on_names_on_issue(issue_mock: mock.Mock):
    issue_mock.get_labels.return_value = [
        MyLabel(name="build_failed_on/foo"),
        MyLabel(name="build_failed_on/bar"),
        MyLabel(name="tested_on/fedora-rawhide-x86_64"),
    ]
    actual = github_util.GithubClient.get_build_failed_on_names_on_issue(
        issue=issue_mock
    )
    expected = ["build_failed_on/foo", "build_failed_on/bar"]
    assert actual == expected


@mock.patch("github.Issue.Issue", autospec=True)
def test_get_comment__no_comments(issue_mock: mock.Mock, github_client_fxt):
    issue_mock.get_comments = mock.Mock()
    issue_mock.get_comments.return_value = []
    actual = github_util.GithubClient.get_comment(issue=issue_mock, marker="foo")
    assert actual is None


@mock.patch("github.Issue.Issue", autospec=True)
def test_get_comment__found(issue_mock: mock.Mock):
    issue_mock.get_comments = mock.Mock()
    issue_mock.get_comments.return_value = [
        MyComment(body="hello foo"),
        MyComment(body="hello <!--mymarker--> bar"),
    ]
    actual = github_util.GithubClient.get_comment(
        issue=issue_mock, marker="<!--mymarker-->"
    )
    expected = MyComment(body="hello <!--mymarker--> bar")
    assert actual == expected


@mock.patch("github.Issue.Issue", autospec=True)
def test_create_or_update_comment__create(issue_mock: mock.Mock):
    expected = MyComment(body="hello <!--mymarker--> bar")

    # Pretend there is no comment with the marker for the issue yet
    issue_mock.get_comment = mock.Mock()
    issue_mock.get_comment.return_value = None
    # Pretend we've created a comment
    issue_mock.create_comment = mock.Mock()
    issue_mock.create_comment.return_value = expected
    # Run
    actual = github_util.GithubClient.create_or_update_comment(
        issue=issue_mock, marker="<!--mymarker-->", comment_body="my comment"
    )
    assert actual == expected
    issue_mock.create_comment.assert_called_once_with(body="my comment")


@mock.patch("github.Issue.Issue", autospec=True)
@mock.patch(
    "snapshot_manager.github_util.GithubClient.get_comment", return_value=mock.Mock()
)
def test_create_or_update_comment__edit_fails(
    get_comment_mock: mock.Mock, issue_mock: mock.Mock
):
    get_comment_mock.return_value = mock.Mock()  # The comment itself
    get_comment_mock.return_value.edit.side_effect = github.GithubException(
        "failed to update comment"
    )  # The edit() call

    marker = "<!--mymarker-->"
    comment_body = "my comment"

    # Run
    with pytest.raises(expected_exception=ValueError) as ex:
        actual = github_util.GithubClient.create_or_update_comment(
            issue=issue_mock, marker=marker, comment_body=comment_body
        )
    get_comment_mock.return_value.edit.assert_called_once_with(body=comment_body)
    assert marker in str(ex.value)
    assert comment_body in str(ex.value)


@mock.patch("github.Issue.Issue", autospec=True)
@mock.patch(
    "snapshot_manager.github_util.GithubClient.get_comment", return_value=mock.Mock()
)
def test_create_or_update_comment__edit(
    get_comment_mock: mock.Mock, issue_mock: mock.Mock
):
    get_comment_mock.return_value = mock.Mock()  # The comment itself
    get_comment_mock.return_value.edit = mock.Mock()

    marker = "<!--mymarker-->"
    comment_body = "my comment"

    # Run
    actual = github_util.GithubClient.create_or_update_comment(
        issue=issue_mock, marker=marker, comment_body=comment_body
    )

    get_comment_mock.return_value.edit.assert_called_once_with(body=comment_body)
    assert actual == get_comment_mock.return_value


@mock.patch("github.Issue.Issue", autospec=True)
def test_remove_labels_safe(issue_mock: mock.Mock):
    issue_mock.get_labels.return_value = [
        MyLabel(name="build_failed_on/fedora-rawhide-s390x"),
        MyLabel(name="tested_on/fedora-rawhide-x86_64"),
    ]

    github_util.GithubClient.remove_labels_safe(
        issue=issue_mock, label_names_to_be_removed=["tested_on/fedora-rawhide-x86_64"]
    )

    issue_mock.remove_from_labels.assert_called_once_with(
        "tested_on/fedora-rawhide-x86_64"
    )


def test_minimize_comment_as_outdated__with_issue_comment(github_client_fxt):
    gh = github_client_fxt
    node_id = "12345"
    issue_comment_mock = mock.MagicMock(
        spec=github.IssueComment.IssueComment
    )  # Spec parameter is important to pass isinstance()
    with mock.patch.dict(
        issue_comment_mock.raw_data, values={"node_id": node_id}, create=True
    ) as node_id_mock:
        node_id_mock.__getitem__.return_value = node_id
        with mock.patch.object(
            gh.gql, "run_from_file", autospec=True
        ) as run_from_file_mock:
            run_from_file_mock.return_value = {
                "data": {"minimizeComment": {"minimizedComment": {"isMinimized": True}}}
            }

            actual = gh.minimize_comment_as_outdated(object=issue_comment_mock)

            assert actual == True
            run_from_file_mock.assert_called_once_with(
                variables={"classifier": "OUTDATED", "id": node_id},
                filename=gh.abspath("graphql/minimize_comment.gql"),
            )


def test_minimize_comment_as_outdated__with_str(github_client_fxt):
    gh = github_client_fxt
    node_id = "12345"
    with mock.patch.object(
        gh.gql, "run_from_file", autospec=True
    ) as run_from_file_mock:
        run_from_file_mock.return_value = {
            "data": {"minimizeComment": {"minimizedComment": {"isMinimized": True}}}
        }

        actual = gh.minimize_comment_as_outdated(object=node_id)

        assert actual == True
        run_from_file_mock.assert_called_once_with(
            variables={"classifier": "OUTDATED", "id": node_id},
            filename=gh.abspath("graphql/minimize_comment.gql"),
        )


def test_minimize_comment_as_outdated__unsupported_type(github_client_fxt):
    obj = 0.2
    with pytest.raises(expected_exception=ValueError) as ex:
        github_client_fxt.minimize_comment_as_outdated(object=obj)
    assert str(ex.value) == f"invalid comment object passed: {obj}"


def test_unminimize_comment__with_issue_comment(github_client_fxt):
    gh = github_client_fxt
    node_id = "12345"
    issue_comment_mock = mock.MagicMock(
        spec=github.IssueComment.IssueComment
    )  # Spec parameter is important to pass isinstance()
    with mock.patch.dict(
        issue_comment_mock.raw_data, values={"node_id": node_id}, create=True
    ) as node_id_mock:
        node_id_mock.__getitem__.return_value = node_id
        with mock.patch.object(
            gh.gql, "run_from_file", autospec=True
        ) as run_from_file_mock:
            run_from_file_mock.return_value = {
                "data": {
                    "unminimizeComment": {"unminimizedComment": {"isMinimized": False}}
                }
            }

            actual = gh.unminimize_comment(object=issue_comment_mock)

            assert actual == True
            run_from_file_mock.assert_called_once_with(
                variables={"id": node_id},
                filename=gh.abspath("graphql/unminimize_comment.gql"),
            )


def test_unminimize_comment__with_str(github_client_fxt):
    gh = github_client_fxt
    node_id = "12345"
    with mock.patch.object(
        gh.gql, "run_from_file", autospec=True
    ) as run_from_file_mock:
        run_from_file_mock.return_value = {
            "data": {
                "unminimizeComment": {"unminimizedComment": {"isMinimized": False}}
            }
        }

        actual = gh.unminimize_comment(object=node_id)

        assert actual == True
        run_from_file_mock.assert_called_once_with(
            variables={"id": node_id},
            filename=gh.abspath("graphql/unminimize_comment.gql"),
        )


def test_unminimize_comment__unsupported_type(github_client_fxt):
    obj = 0.2
    with pytest.raises(expected_exception=ValueError) as ex:
        github_client_fxt.unminimize_comment(object=obj)
    assert str(ex.value) == f"invalid comment object passed: {obj}"


def test_add_comment_reaction__with_issue_comment(github_client_fxt):
    gh = github_client_fxt
    node_id = "12345"
    reaction = github_util.Reaction.EYES
    issue_comment_mock = mock.MagicMock(
        spec=github.IssueComment.IssueComment
    )  # Spec parameter is important to pass isinstance()
    with mock.patch.dict(
        issue_comment_mock.raw_data, values={"node_id": node_id}, create=True
    ) as node_id_mock:
        node_id_mock.__getitem__.return_value = node_id
        with mock.patch.object(
            gh.gql, "run_from_file", autospec=True
        ) as run_from_file_mock:
            run_from_file_mock.return_value = {
                "data": {
                    "addReaction": {
                        "reaction": {"content": reaction},
                        "subject": {"id": node_id},
                    }
                }
            }

            actual = gh.add_comment_reaction(
                object=issue_comment_mock, reaction=reaction
            )

            assert actual == True
            run_from_file_mock.assert_called_once_with(
                variables={"comment_id": node_id, "reaction": reaction},
                filename=gh.abspath("graphql/add_comment_reaction.gql"),
            )


def test_add_comment_reaction__with_str(github_client_fxt):
    gh = github_client_fxt
    node_id = "12345"
    reaction = github_util.Reaction.EYES
    with mock.patch.object(
        gh.gql, "run_from_file", autospec=True
    ) as run_from_file_mock:
        run_from_file_mock.return_value = {
            "data": {
                "addReaction": {
                    "reaction": {"content": reaction},
                    "subject": {"id": node_id},
                }
            }
        }

        actual = gh.add_comment_reaction(object=node_id, reaction=reaction)

        assert actual == True
        run_from_file_mock.assert_called_once_with(
            variables={"comment_id": node_id, "reaction": reaction},
            filename=gh.abspath("graphql/add_comment_reaction.gql"),
        )


def test_add_comment_reaction__unsupported_type(github_client_fxt):
    obj = 0.2
    with pytest.raises(expected_exception=ValueError) as ex:
        github_client_fxt.add_comment_reaction(
            object=obj, reaction=github_util.Reaction.LAUGH
        )
    assert str(ex.value) == f"invalid comment object passed: {obj}"


@pytest.mark.parametrize(
    "input, expected, func",
    [
        (
            "fedora-rawhide-s390x",
            "in_testing/fedora-rawhide-s390x",
            lambda gh: gh.label_in_testing,
        ),
        (
            "fedora-rawhide-x86_64",
            "tests_failed_on/fedora-rawhide-x86_64",
            lambda gh: gh.label_failed_on,
        ),
        (
            "fedora-rawhide-ppc64le",
            "tests_succeeded_on/fedora-rawhide-ppc64le",
            lambda gh: gh.label_tested_on,
        ),
    ],
)
def test_label(input, expected, func, github_client_fxt):
    assert func(github_client_fxt)(chroot=input) == expected


def test_flip_test_label(github_client_fxt):
    issue_mock = mock.MagicMock(spec=github.Issue.Issue)
    issue_mock.add_to_labels = mock.MagicMock()

    # Flip the test status of this chroot: fedora-rawhide-x86_64
    chroot = "fedora-rawhide-x86_64"
    new_label = f"tests_failed_on/{chroot}"

    issue_mock.get_labels.return_value = [
        MyLabel(name="error/test"),
        # This will be removed
        MyLabel(name="in_testing/fedora-rawhide-x86_64"),
        MyLabel(name="tests_succeeded_on/fedora-rawhide-ppc64le"),
    ]

    github_client_fxt.flip_test_label(
        issue=issue_mock, chroot="fedora-rawhide-x86_64", new_label=new_label
    )

    issue_mock.add_to_labels.assert_called_once_with(new_label)
    issue_mock.remove_from_labels.assert_called_once_with(
        "in_testing/fedora-rawhide-x86_64"
    )


def test_flip_test_label__already_present(github_client_fxt):
    issue_mock = mock.MagicMock(spec=github.Issue.Issue)
    issue_mock.add_to_labels = mock.MagicMock()

    chroot = "fedora-rawhide-x86_64"
    new_label = f"tests_failed_on/{chroot}"

    issue_mock.get_labels.return_value = [
        MyLabel(name="error/tests"),
        MyLabel(name="tests_failed_on/fedora-rawhide-x86_64"),
        MyLabel(name="tests_succeeded_on/fedora-rawhide-ppc64le"),
    ]

    github_client_fxt.flip_test_label(
        issue=issue_mock, chroot="fedora-rawhide-x86_64", new_label=new_label
    )

    # Validate that no label was removed or added
    issue_mock.add_to_labels.assert_not_called()
    issue_mock.remove_from_labels.assert_not_called()


def load_tests(loader, tests, ignore):
    """We want unittest to pick up all of our doctests

    See https://docs.python.org/3/library/unittest.html#load-tests-protocol
    See https://stackoverflow.com/a/27171468
    """
    import doctest

    import snapshot_manager.github_util

    tests.addTests(doctest.DocTestSuite(snapshot_manager.github_util))
    return tests


if __name__ == "__main__":
    base_test.run_tests()
