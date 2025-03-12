import argparse
import datetime
import logging
import sys

import snapshot_manager.config as config
import snapshot_manager.copr_util as copr_util
import snapshot_manager.snapshot_manager as snapshot_manager
import snapshot_manager.util as util

# This shows the default value of arguments in the help text.
# See https://docs.python.org/3/library/argparse.html#argparse.ArgumentDefaultsHelpFormatter
ARG_PARSE_SHOW_DEFAULT_VALUE = {
    "formatter_class": argparse.ArgumentDefaultsHelpFormatter
}


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d %(funcName)s] %(message)s",
        datefmt="%d/%b/%Y %H:%M:%S",
        stream=sys.stderr,
    )

    cfg = config.Config()
    args = build_argument_parser(cfg=cfg).parse_args()
    cmd = args.command

    copr_client = None
    all_chroots = []
    config_map = config.build_config_map()

    # For some commands we need a copr client and a config map set up.
    if cmd in (
        "check",
        "get-chroots",
        "has-all-good-builds",
        "delete-project",
        "github-matrix",
    ):
        copr_client = copr_util.make_client()
        all_chroots = copr_util.get_all_chroots(client=copr_client)
        util.augment_config_map_with_chroots(
            config_map=config_map, all_chroots=all_chroots
        )

    if cmd in ("check", "get-chroots", "has-all-good-builds", "delete-project"):
        if args.strategy not in config_map:
            logging.error(
                f"No strategy with name '{args.strategy}' found in list of strategies: {config_map.keys()}"
            )
            sys.exit(1)
        cfg = config_map[args.strategy]

    if cmd == "check":
        cfg.github_repo = args.github_repo
        cfg.datetime = args.datetime
        snapshot_manager.SnapshotManager(config=cfg).check_todays_builds()
    elif cmd == "retest":
        cfg.github_repo = args.github_repo
        snapshot_manager.SnapshotManager(config=cfg).retest(
            issue_number=args.issue_number,
            trigger_comment_id=args.trigger_comment_id,
            chroots=args.chroots,
        )
    elif cmd == "github-matrix":
        json = util.serialize_config_map_to_github_matrix(
            config_map=config_map,
            strategy=args.strategy,
            lookback_days=args.lookback_days,
        )
        print(json)
    elif cmd == "get-chroots":
        print(" ".join(cfg.chroots))
    elif cmd == "delete-project":
        cfg.datetime = args.datetime
        copr_util.delete_project(
            client=copr_client,
            ownername=cfg.copr_ownername,
            projectname=cfg.copr_projectname,
        )
    elif cmd == "has-all-good-builds":
        cfg.datetime = args.datetime
        states = copr_util.get_all_build_states(
            client=copr_client,
            ownername=cfg.copr_ownername,
            projectname=cfg.copr_projectname,
        )
        cfg.packages = args.packages
        builds_succeeded = copr_util.has_all_good_builds(
            required_chroots=cfg.chroots,
            required_packages=cfg.packages,
            states=states,
        )
        if not builds_succeeded:
            logging.warning("Not all builds were successful")
            sys.exit(1)
        logging.info("All required builds were successful")
    else:
        logging.error(f"Unsupported command: {cmd}")
        sys.exit(1)


def build_argument_parser(cfg: config.Config) -> argparse.ArgumentParser:
    mainparser = argparse.ArgumentParser(
        description="Program for managing LLVM snapshots",
        **ARG_PARSE_SHOW_DEFAULT_VALUE,
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

    argument_parser_retest(cfg, subparsers=subparsers)
    argument_parser_get_chroots(cfg, subparsers=subparsers)
    argument_parser_delete_project(cfg, subparsers=subparsers)
    argument_parser_github_matrix(cfg, subparsers=subparsers)
    argument_parser_check(cfg=cfg, subparsers=subparsers)
    argument_parser_has_all_good_builds(cfg=cfg, subparsers=subparsers)

    return mainparser


def add_strategy_argument(argparser: argparse.ArgumentParser) -> argparse.Action:
    argparser.add_argument(
        "--strategy",
        dest="strategy",
        type=str,
        required=True,
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


def argument_parser_has_all_good_builds(cfg: config.Config, subparsers) -> None:
    sp = subparsers.add_parser(
        "has-all-good-builds",
        description="Checks if the given ",
        **ARG_PARSE_SHOW_DEFAULT_VALUE,
    )
    sp.add_argument(
        "--packages",
        metavar="PKG",
        type=str,
        nargs="+",
        dest="packages",
        default=["llvm"],
        help="Which packages check (e.g. llvm)",
    )
    add_strategy_argument(sp)
    add_yyyymmdd_argument(sp)


def argument_parser_retest(cfg: config.Config, subparsers) -> None:
    sp = subparsers.add_parser(
        "retest",
        description="Issues a new testing-farm request for one or more chroots",
        **ARG_PARSE_SHOW_DEFAULT_VALUE,
    )
    sp.add_argument(
        "--chroots",
        metavar="CHROOT",
        type=str,
        nargs="+",
        dest="chroots",
        required=True,
        help="Which chroots to retest (e.g. fedora-rawhide-x86_64)",
    )
    sp.add_argument(
        "--trigger-comment-id",
        type=int,
        dest="trigger_comment_id",
        required=True,
        help="ID of the comment that contains the /retest <CHROOT> string",
    )
    sp.add_argument(
        "--issue-number",
        type=int,
        dest="issue_number",
        required=True,
        help="In what issue number did the comment appear in.",
    )


def argument_parser_get_chroots(cfg: config.Config, subparsers) -> None:
    sp = subparsers.add_parser(
        "get-chroots",
        description="Prints a space separated list of chroots for a given strategy",
        **ARG_PARSE_SHOW_DEFAULT_VALUE,
    )
    add_strategy_argument(sp)


def argument_parser_delete_project(cfg: config.Config, subparsers) -> None:
    sp = subparsers.add_parser(
        "delete-project",
        description="Deletes a project for the given day and strategy",
        **ARG_PARSE_SHOW_DEFAULT_VALUE,
    )
    add_strategy_argument(sp)
    add_yyyymmdd_argument(sp)


def argument_parser_github_matrix(cfg: config.Config, subparsers) -> None:
    sp = subparsers.add_parser(
        "github-matrix",
        description="Prints the github workflow matrix for a given or all strategies",
        **ARG_PARSE_SHOW_DEFAULT_VALUE,
    )
    add_strategy_argument(sp)
    sp.add_argument(
        "--lookback-days",
        metavar="DAY",
        type=int,
        nargs="+",
        dest="lookback_days",
        default=[0],
        help="Integers for how many days to look back (0 means just today)",
    )


def argument_parser_check(cfg: config.Config, subparsers) -> None:
    sp = subparsers.add_parser(
        "check",
        description="Check Copr status and update today's github issue",
        **ARG_PARSE_SHOW_DEFAULT_VALUE,
    )
    add_strategy_argument(sp)
    add_yyyymmdd_argument(sp)


if __name__ == "__main__":
    main()
