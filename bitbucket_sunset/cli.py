from __future__ import annotations

import argparse
import logging
from typing import Optional

from . import extract_permissions as extract_mod
from . import expand_groups as expand_mod
from . import apply_github_permissions as apply_mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bitbucket-sunset", description="Migrate Bitbucket DC repo permissions to GitHub Enterprise")
    sub = p.add_subparsers(dest="cmd", required=False)

    # extract
    p_extract = sub.add_parser(
        "extract",
        help="Extract Bitbucket permissions to CSVs",
        parents=[extract_mod.build_arg_parser()],
        add_help=False,
    )

    # expand
    p_expand = sub.add_parser(
        "expand",
        help="Expand group permissions to effective per-user permissions",
        parents=[expand_mod.build_arg_parser()],
        add_help=False,
    )

    # apply
    p_apply = sub.add_parser(
        "apply",
        help="Apply effective permissions into GitHub",
        parents=[apply_mod.build_arg_parser()],
        add_help=False,
    )

    return p


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    parser = build_parser()
    # If invoked with no args or just --help, argparse handles help; else we branch on subcommand
    args = parser.parse_args(argv)

    if not args.cmd:
        parser.print_help()
        return

    if args.cmd == "extract":
        extract_mod.main([] if argv is None else argv[1:])
    elif args.cmd == "expand":
        expand_mod.main([] if argv is None else argv[1:])
    elif args.cmd == "apply":
        apply_mod.main([] if argv is None else argv[1:])
    else:
        parser.print_help()
