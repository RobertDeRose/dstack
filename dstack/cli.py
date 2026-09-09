#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from .feature_check import cmd_feature_check
from .commands import (
    cmd_formula_check,
    cmd_init,
    cmd_plan_check,
    cmd_review_check,
    cmd_task_check,
    cmd_worktree_ensure,
)
from .core import DstackError
from .docs import cmd_docs_export, cmd_docs_validate
from .git_ops import cmd_git_commit, cmd_git_commit_docs
from .installer import cmd_install_agent_resources, default_agent_dir
from .output import fail


def _package_version() -> str:
    try:
        return version("dstack")
    except PackageNotFoundError:
        return "development"


def _leaf(parent: argparse._SubParsersAction, name: str, description: str) -> argparse.ArgumentParser:
    return parent.add_parser(name, help=description, description=description)


def _root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root; defaults to the current directory.",
    )


def _bead(parser: argparse.ArgumentParser, help: str) -> None:
    parser.add_argument("-b", "--bead", required=True, help=help)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dstack",
        description="Deterministic repository operations for Beads-backed software-engineering workflows.",
    )
    parser.add_argument("-V", "--version", action="version", version=_package_version())
    commands = parser.add_subparsers(dest="top_command", required=True)

    init = _leaf(commands, "init", "Set up dStack in this repository.")
    _root(init)
    init.add_argument(
        "--update",
        action="store_true",
        help="Replace an existing dStack formula or .beads/PRIME.md that differs from the installed package.",
    )
    init.set_defaults(func=cmd_init)

    install = _leaf(commands, "install", "Install or update dStack's Pi workflow commands and skills.")
    install.add_argument(
        "--agent-dir",
        type=Path,
        default=default_agent_dir(),
        help="Pi agent directory; defaults to PI_CODING_AGENT_DIR or ~/.pi/agent.",
    )
    install.set_defaults(func=cmd_install_agent_resources)

    check = _leaf(commands, "check", "Validate dStack policy, feature state, tasks, or documentation.")
    check_commands = check.add_subparsers(dest="command", required=True)

    formula_check = _leaf(
        check_commands,
        "formula",
        "Verify that this repository uses the installed dStack workflow policy.",
    )
    _root(formula_check)
    formula_check.set_defaults(func=cmd_formula_check)

    plan = _leaf(check_commands, "plan", "Validate a feature plan before review.")
    _root(plan)
    _bead(plan, "Feature root or descendant Beads issue ID.")
    plan.set_defaults(func=cmd_plan_check)

    review = _leaf(check_commands, "review", "Validate the reviewed task graph before approval.")
    _root(review)
    _bead(review, "Feature root or descendant Beads issue ID.")
    review.set_defaults(func=cmd_review_check)

    task = _leaf(check_commands, "task", "Validate an implementation task and its Git evidence.")
    _root(task)
    _bead(task, "Implementation task Beads issue ID.")
    task.set_defaults(func=cmd_task_check)

    docs_check = _leaf(check_commands, "docs", "Validate one feature's documentation structure.")
    _root(docs_check)
    docs_check.add_argument("--slug", required=True, help="Kebab-case feature slug.")
    docs_check.set_defaults(func=cmd_docs_validate)

    feature = _leaf(
        check_commands,
        "feature",
        "Validate a completed feature and collect evidence for close.",
    )
    _root(feature)
    _bead(feature, "Feature root or descendant Beads issue ID.")
    feature.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Page task, decision, gate, and commit summaries; validation still checks all evidence.",
    )
    feature.add_argument("--include-plan", action="store_true", help="Include the full feature plan in the result.")
    feature.add_argument(
        "--require-docs",
        action="store_true",
        help="Require valid feature documentation and close ownership when documentation changed.",
    )
    feature.epilog = (
        "Read selected details directly with bd show ID --include-comments --json, "
        "bd history ID --json, or git show COMMIT."
    )
    feature.set_defaults(func=cmd_feature_check)

    docs = _leaf(commands, "docs", "Export and commit reviewed feature documentation.")
    docs_commands = docs.add_subparsers(dest="command", required=True)
    export_design = _leaf(docs_commands, "export-design", "Export the reviewed plan design without rewriting it.")
    _root(export_design)
    _bead(export_design, "Feature root or descendant Beads issue ID.")
    export_design.add_argument(
        "--scaffold",
        action="store_true",
        help="Create missing index sections and SUMMARY link without replacing prose.",
    )
    export_design.set_defaults(func=cmd_docs_export)
    docs_commit = _leaf(docs_commands, "commit", "Commit validated feature documentation for close.")
    _root(docs_commit)
    _bead(docs_commit, "Feature root or descendant Beads issue ID.")
    docs_commit.set_defaults(func=cmd_git_commit_docs)

    commit = _leaf(commands, "commit", "Create or correct the canonical commit for an implementation task.")
    _root(commit)
    _bead(commit, "Implementation task Beads issue ID.")
    commit.set_defaults(func=cmd_git_commit)

    worktree = _leaf(
        commands,
        "worktree",
        "Locate or create a feature worktree and report interrupted Git operations.",
    )
    _root(worktree)
    _bead(worktree, "Feature root or descendant Beads issue ID.")
    worktree.set_defaults(func=cmd_worktree_ensure)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        parser.print_help()
        return 0
    args = parser.parse_args(values)
    try:
        return int(args.func(args))
    except DstackError as exc:
        return fail(str(exc))
    except (OSError, UnicodeError) as exc:
        return fail(f"filesystem operation failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
