import argparse
import logging
import sys
import datetime

import snapshot_manager.config as config
import snapshot_manager.snapshot_manager as snapshot_manager


def main():
    cfg = config.Config()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s [%(pathname)s:%(lineno)d %(funcName)s] %(message)s",
        datefmt="%d/%b/%Y %H:%M:%S",
        stream=sys.stderr,
    )

    # This shows the default value of arguments in the help text.
    # See https://docs.python.org/3/library/argparse.html#argparse.ArgumentDefaultsHelpFormatter
    parser_args = {"formatter_class": argparse.ArgumentDefaultsHelpFormatter}

    mainparser = argparse.ArgumentParser(
        description="Program for managing LLVM snapshots",
        **parser_args,
    )

    mainparser.add_argument(
        "--github-token-env",
        metavar="ENV_NAME",
        type=str,
        dest="github_token_env",
        default=cfg.github_token_env,
        help="Default name of the environment variable which holds the github token",
    )

    mainparser.add_argument(
        "--github-repo",
        metavar="OWNER/REPO",
        type=str,
        dest="github_repo",
        default=cfg.github_repo,
        help="Repo where to open or update issues.",
    )

    # For config file support see:
    # https://newini.wordpress.com/2021/06/11/how-to-import-config-file-to-argparse-using-configparser/
    # subparser_check.add_argument(
    #     "--config-file",
    #     type=str,
    #     nargs="+",
    #     dest="config_file",
    #     help="Path to config file?",
    #     required=False
    # )

    subparsers = mainparser.add_subparsers(help="Command to run", dest="command")

    subparser_retest = subparsers.add_parser(
        "retest",
        description="Issues a new testing-farm request for one or more chroots",
        **parser_args,
    )

    subparser_retest.add_argument(
        "--chroots",
        metavar="CHROOT",
        type=str,
        nargs="+",
        dest="chroots",
        required=True,
        help="Which chroots to retest (e.g. fedora-rawhide-x86_64)",
    )

    subparser_retest.add_argument(
        "--trigger-comment-id",
        type=str,
        dest="trigger_comment_id",
        required=True,
        help="ID of the comment that contains the /retest <CHROOT> string",
    )

    subparser_retest.add_argument(
        "--issue-number",
        type=str,
        dest="issue_number",
        required=True,
        help="In what issue number did the comment appear in.",
    )

    subparser_check = subparsers.add_parser(
        "check",
        description="Check Copr status and update today's github issue",
        **parser_args,
    )

    subparser_check.add_argument(
        "--packages",
        metavar="PKG",
        type=str,
        nargs="+",
        dest="packages",
        default=cfg.packages,
        help="Which packages are required to build?",
    )

    subparser_check.add_argument(
        "--chroot-pattern",
        metavar="REGULAR_EXPRESSION",
        type=str,
        dest="chroot_pattern",
        default=cfg.chroot_pattern,
        help="Chroots regex pattern for required chroots.",
    )

    subparser_check.add_argument(
        "--build-strategy",
        type=str,
        dest="build_strategy",
        default=cfg.build_strategy,
        help="Build strategy to look for (e.g. 'standalone', 'big-merge', 'bootstrap').",
    )

    subparser_check.add_argument(
        "--maintainer-handle",
        metavar="GITHUB_HANDLE_WITHOUT_AT_SIGN",
        type=str,
        dest="maintainer_handle",
        default=cfg.maintainer_handle,
        help="Maintainer handle to use for assigning issues.",
    )

    subparser_check.add_argument(
        "--copr-ownername",
        metavar="COPR-OWNWERNAME",
        type=str,
        dest="copr_ownername",
        default=cfg.copr_ownername,
        help="Copr ownername to check.",
    )

    subparser_check.add_argument(
        "--copr-project-tpl",
        metavar="COPR-PROJECT-TPL",
        type=str,
        dest="copr_project_tpl",
        default=cfg.copr_project_tpl,
        help="Copr project name to check. 'YYYYMMDD' will be replaced, so make sure you have it in there.",
    )

    subparser_check.add_argument(
        "--copr-monitor-tpl",
        metavar="COPR-MONITOR-TPL",
        type=str,
        dest="copr_monitor_tpl",
        default=cfg.copr_monitor_tpl,
        help="URL to the Copr monitor page. We'll use this in the issue comment's body, not for querying Copr.",
        # See https://github.com/python/cpython/issues/113878 for when we can
        # use the __doc__ of a dataclass field.
        # help=config.Config.copr_monitor_tpl.__doc__
    )

    subparser_check.add_argument(
        "--yyyymmdd",
        type=lambda s: datetime.datetime.strptime(s, "%Y%m%d"),
        dest="datetime",
        default=datetime.datetime.now().strftime("%Y%m%d"),
        help="Default day for which to check",
    )

    # if args.config_file:
    #     config = configparser.ConfigParser()
    #     config.read(args.config_file)
    #     defaults = {}
    #     defaults.update(dict(config.items("Defaults")))
    #     mainparser.set_defaults(**defaults)
    #     args = mainparser.parse_args() # Overwrite arguments

    args = mainparser.parse_args()

    cfg.github_token_env = args.github_token_env
    cfg.github_repo = args.github_repo

    if args.command == "check":
        cfg.datetime = args.datetime
        cfg.packages = args.packages
        cfg.chroot_pattern = args.chroot_pattern
        cfg.build_strategy = args.build_strategy
        cfg.maintainer_handle = args.maintainer_handle
        cfg.copr_ownername = args.copr_ownername
        cfg.copr_project_tpl = args.copr_project_tpl
        cfg.copr_monitor_tpl = args.copr_monitor_tpl

        snapshot_manager.SnapshotManager(config=cfg).check_todays_builds()
    elif args.command == "retest":
        snapshot_manager.SnapshotManager(config=cfg).retest(
            issue_number=args.issue_number,
            trigger_comment_id=args.trigger_comment_id,
            chroots=args.chroots,
        )
    else:
        logging.error(f"Unsupported argument: {args.command}")


if __name__ == "__main__":
    main()
