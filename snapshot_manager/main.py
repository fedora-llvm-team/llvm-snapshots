import argparse
import datetime
import logging
import os
import sys
import pathlib

import github

import snapshot_manager.config as config
import snapshot_manager.copr_util as copr_util
import snapshot_manager.util as util
from snapshot_manager.snapshot_manager import (  # isort:skip_file
    SnapshotManager,
    run_performance_comparison,
    collect_performance_comparison_results,
)
from snapshot_manager.performance_diagrams import build_performance_diagrams


def file_path(path: str) -> pathlib.Path:
    if os.path.isfile(path):
        return pathlib.Path(path)
    else:
        raise argparse.ArgumentTypeError(f"{path} is not a valid file")


def main() -> None:
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
        "run-perf-comparison",
        "collect-perf-comparison-results",
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
        SnapshotManager(config=cfg).check_todays_builds()
    elif cmd == "retest":
        cfg.github_repo = args.github_repo
        SnapshotManager(config=cfg).retest(
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
    elif cmd in ("run-perf-comparison", "collect-perf-results"):
        github_token = os.getenv(config.Config().github_token_env)
        if github_token is None or len(github_token) == 0:
            logging.error(
                f"Could not retrieve github token from environment variable with name '{config.Config().github_token_env}'"
            )
            sys.exit(1)
        auth = github.Auth.Token(github_token)
        github_client = github.Github(auth=auth)
        if args.strategy_a not in config_map or args.strategy_b not in config_map:
            logging.error(
                f"'{args.strategy_a}' and '{args.strategy_b}' need to be a named configuration but currently only these configurations exist: {config_map.keys()}"
            )
            sys.exit(1)
        conf_a = config_map[args.strategy_a]
        conf_b = config_map[args.strategy_b]
        conf_a.datetime = args.datetime
        conf_b.datetime = args.datetime

        if cmd == "run-perf-comparison":
            run_performance_comparison(
                conf_a=conf_a,
                conf_b=conf_b,
                github_repo=args.github_repo,
                copr_client=copr_client,
                github_client=github_client,
            )
        elif cmd == "collect-perf-results":
            collect_performance_comparison_results(
                conf_a=conf_a,
                conf_b=conf_b,
                github_repo=args.github_repo,
                github_client=github_client,
                csv_file_out=args.csv_file_out,
                csv_file_in=args.csv_file_in,
            )
    elif cmd == "perf-diagrams":
        build_performance_diagrams(datafile=args.datafile)
    else:
        logging.error(f"Unsupported command: {cmd}")
        sys.exit(1)


def build_argument_parser(cfg: config.Config) -> argparse.ArgumentParser:
    mainparser = argparse.ArgumentParser(
        description="Program for managing LLVM snapshots",
        # This shows the default value of arguments in the help text.
        # See https://docs.python.org/3/library/argparse.html#argparse.ArgumentDefaultsHelpFormatter
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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

    argument_parser_retest(subparsers)
    argument_parser_get_chroots(subparsers)
    argument_parser_delete_project(subparsers)
    argument_parser_github_matrix(subparsers)
    argument_parser_check(subparsers)
    argument_parser_has_all_good_builds(subparsers)
    argument_parser_perf_comparison(subparsers)
    argument_parser_collect_perf_comparison_results(subparsers)
    argument_parser_performance_diagrams(subparsers)

    return mainparser


def add_strategy_argument(argparser: argparse.ArgumentParser) -> argparse.Action:
    return argparser.add_argument(
        "--strategy",
        dest="strategy",
        type=str,
        required=True,
        help="Strategy to use",
    )


def add_yyyymmdd_argument(argparser: argparse.ArgumentParser) -> argparse.Action:
    return argparser.add_argument(
        "--yyyymmdd",
        type=lambda s: datetime.datetime.strptime(s, "%Y%m%d"),
        dest="datetime",
        default=datetime.datetime.now().strftime("%Y%m%d"),
        help="Default day for which to run command",
    )


def argument_parser_has_all_good_builds(  # type: ignore[no-untyped-def]
    subparsers,
) -> None:
    sp = subparsers.add_parser(
        "has-all-good-builds",
        description="Checks if the given packages were successfully built ",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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


def argument_parser_perf_comparison(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "run-perf-comparison",
        description="Run a performance comparison between two strategies A and B on testing-farm",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    sp.add_argument(
        "--strategy-a",
        dest="strategy_a",
        type=str,
        required=True,
        help="Strategy A",
    )

    sp.add_argument(
        "--strategy-b",
        dest="strategy_b",
        type=str,
        required=True,
        help="Strategy B",
    )

    add_yyyymmdd_argument(sp)


def argument_parser_collect_perf_comparison_results(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "collect-perf-results",
        description="Collect performance comparison results",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    sp.add_argument(
        "--strategy-a",
        dest="strategy_a",
        type=str,
        required=True,
        help="Strategy A",
    )

    sp.add_argument(
        "--strategy-b",
        dest="strategy_b",
        type=str,
        required=True,
        help="Strategy B",
    )

    sp.add_argument(
        "--csv-file-in",
        dest="csv_file_in",
        type=str,
        default="results-in.csv",
        help="CSV file to load and merge with all the collected performance CSV results files",
    )

    sp.add_argument(
        "--csv-file-out",
        dest="csv_file_out",
        type=str,
        default="results-out.csv",
        help="Where to write the collected performance CSV results file",
    )

    add_yyyymmdd_argument(sp)


def argument_parser_performance_diagrams(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "perf-diagrams",
        description="Create performance diagrams for a given CSV file",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    sp.add_argument(
        "--datafile",
        dest="datafile",
        type=file_path,
        required=True,
        help="perf-results.csv",
    )


def argument_parser_retest(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "retest",
        description="Issues a new testing-farm request for one or more chroots",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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


def argument_parser_get_chroots(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "get-chroots",
        description="Prints a space separated list of chroots for a given strategy",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_strategy_argument(sp)


def argument_parser_delete_project(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "delete-project",
        description="Deletes a project for the given day and strategy",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_strategy_argument(sp)
    add_yyyymmdd_argument(sp)


def argument_parser_github_matrix(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "github-matrix",
        description="Prints the github workflow matrix for a given or all strategies",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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


def argument_parser_check(subparsers) -> None:  # type: ignore[no-untyped-def]
    sp = subparsers.add_parser(
        "check",
        description="Check Copr status and update today's github issue",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_strategy_argument(sp)
    add_yyyymmdd_argument(sp)


if __name__ == "__main__":
    main()
