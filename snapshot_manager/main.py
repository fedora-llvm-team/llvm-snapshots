import argparse
import datetime
import logging
import sys

import snapshot_manager.config as config
import snapshot_manager.copr_util as copr_util
import snapshot_manager.snapshot_manager as snapshot_manager
import snapshot_manager.util as util


def add_strategy_argument(argparser: argparse.ArgumentParser) -> argparse.Action:
    argparser.add_argument(
        "--strategy",
        dest="strategy",
        type=str,
        default="",
        help=f"Strategy to use",
    )


def add_yyyymmdd_argument(argparser: argparse.ArgumentParser) -> argparse.Action:
    return argparser.add_argument(
        "--yyyymmdd",
        type=lambda s: datetime.datetime.strptime(s, "%Y%m%d"),
        dest="datetime",
        default=datetime.datetime.now().strftime("%Y%m%d"),
        help="Default day for which to run command",
    )


def main():
    cfg = config.Config()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d %(funcName)s] %(message)s",
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
        "--github-repo",
        metavar="OWNER/REPO",
        type=str,
        dest="github_repo",
        default=cfg.github_repo,
        help="Repo where to open or update issues.",
    )

    subparsers = mainparser.add_subparsers(help="Command to run", dest="command")

    # region retest
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
        type=int,
        dest="trigger_comment_id",
        required=True,
        help="ID of the comment that contains the /retest <CHROOT> string",
    )

    subparser_retest.add_argument(
        "--issue-number",
        type=int,
        dest="issue_number",
        required=True,
        help="In what issue number did the comment appear in.",
    )
    # endregion retest

    # region get-chroots
    subparser_get_chroots = subparsers.add_parser(
        "get-chroots",
        description="Prints a space separated list of chroots for a given strategy",
        **parser_args,
    )
    add_strategy_argument(subparser_get_chroots)
    # endregion get-chroots

    # region delete-project
    subparser_delete_project = subparsers.add_parser(
        "delete-project",
        description="Deletes a project for the given day and strategy",
        **parser_args,
    )
    add_strategy_argument(subparser_delete_project)
    add_yyyymmdd_argument(subparser_delete_project)
    # endregion delete-project

    # region github-matrix
    subparser_github_matrix = subparsers.add_parser(
        "github-matrix",
        description="Prints the github workflow matrix for a given or all strategies",
        **parser_args,
    )
    add_strategy_argument(subparser_github_matrix)
    subparser_github_matrix.add_argument(
        "--lookback",
        metavar="DAY",
        type=int,
        nargs="+",
        dest="lookback_days",
        default=0,
        help="Integers for how many days to look back (0 means just today)",
    )
    # endregion github-matrix

    # region check
    subparser_check = subparsers.add_parser(
        "check",
        description="Check Copr status and update today's github issue",
        **parser_args,
    )
    add_strategy_argument(subparser_check)
    add_yyyymmdd_argument(subparser_check)
    # endregion check

    copr_client = None

    args = mainparser.parse_args()

    if args.command in ("get-chroots", "has-all-good-builds", "delete-project"):
        copr_client = copr_util.make_client()
        all_chroots = copr_util.get_all_chroots(client=copr_client)
        config_map = config.build_config_map()
        util.augment_config_map_with_chroots(
            config_map=config_map, all_chroots=all_chroots
        )
        if args.strategy not in config_map:
            logging.error(
                f"No strategy with name '{args.strategy}' found in list of strategies: {config_map.keys()}"
            )
            sys.exit(1)
        cfg = config_map[args.strategy]

    if args.command == "check":
        cfg.github_repo = args.github_repo
        cfg.datetime = args.datetime
        cfg.strategy = args.strategy
        snapshot_manager.SnapshotManager(config=cfg).check_todays_builds()
    elif args.command == "retest":
        cfg.github_repo = args.github_repo
        snapshot_manager.SnapshotManager(config=cfg).retest(
            issue_number=args.issue_number,
            trigger_comment_id=args.trigger_comment_id,
            chroots=args.chroots,
        )
    elif args.command == "github-matrix":
        copr_client = copr_util.make_client()
        all_chroots = copr_util.get_all_chroots(client=copr_client)
        config_map = config.build_config_map()
        util.augment_config_map_with_chroots(
            config_map=config_map, all_chroots=all_chroots
        )
        json = util.serialize_config_map_to_github_matrix(
            config_map=config_map,
            strategy=args.strategy,
            lookback_days=args.lookback_days,
        )
        print(json)
    elif args.command == "get-chroots":
        print(" ".join(cfg.chroots))
    elif args.command == "delete-project":
        cfg.datetime = args.datetime
        copr_util.delete_project(
            client=copr_client,
            ownername=cfg.copr_ownername,
            projectname=cfg.copr_projectname,
        )
    elif args.command == "has-all-good-builds":
        states = copr_util.get_all_build_states(
            client=copr_client,
            ownername=cfg.copr_ownername,
            projectname=cfg.copr_projectname,
        )
        builds_succeeded = copr_util.has_all_good_builds(
            required_chroots=cfg.chroots,
            required_packages=args.packages,
            states=states,
        )
        if not builds_succeeded:
            logging.warning("Not all builds were successful")
            sys.exit(1)
    else:
        logging.error(f"Unsupported argument: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
