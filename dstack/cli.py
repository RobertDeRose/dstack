#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from .audit import cmd_audit_evidence
from .commands import (
    cmd_formula_install,
    cmd_init,
    cmd_plan_check,
    cmd_task_check,
    cmd_worktree_ensure,
)
from .core import DstackError
from .docs import cmd_docs_validate
from .git_ops import cmd_git_amend, cmd_git_commit
from .installer import cmd_install_skills, default_agent_dir
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


def cmd_commit(args: argparse.Namespace) -> int:
    return cmd_git_amend(args) if args.amend else cmd_git_commit(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dstack",
        description="Deterministic repository control plane for Beads-native agent workflows.",
    )
    parser.add_argument("-V", "--version", action="version", version=_package_version())
    commands = parser.add_subparsers(dest="top_command", required=True)

    init = _leaf(commands, "init", "Initialize and validate the dStack Beads workspace contract.")
    _root(init)
    init.add_argument(
        "--update",
        action="store_true",
        help="Replace a different project formula or prime after reviewing the packaged changes.",
    )
    init.set_defaults(func=cmd_init)

    install = _leaf(commands, "install", "Install dStack's project or agent resources.")
    install_commands = install.add_subparsers(dest="command", required=True)
    skills = _leaf(install_commands, "skills", "Install or update the four targeted Pi skills and prompts.")
    skills.add_argument(
        "--agent-dir",
        type=Path,
        default=default_agent_dir(),
        help="Pi agent directory; defaults to PI_CODING_AGENT_DIR or ~/.pi/agent.",
    )
    skills.set_defaults(func=cmd_install_skills)
    formula = _leaf(install_commands, "formula", "Install the packaged formula and scoped prime.")
    _root(formula)
    formula.add_argument(
        "--update",
        action="store_true",
        help="Replace a different project formula after the caller has reviewed the packaged change.",
    )
    formula.set_defaults(func=cmd_formula_install)

    check = _leaf(commands, "check", "Validate plans, implementation tasks, or documentation.")
    check_commands = check.add_subparsers(dest="command", required=True)
    plan = _leaf(check_commands, "plan", "Check required plan sections, resolved questions, and audiences.")
    _root(plan)
    _bead(plan, "Plan-step Bead ID.")
    plan.set_defaults(func=cmd_plan_check)
    task = _leaf(
        check_commands,
        "task",
        "Check native graph membership, documentation impact, Git evidence, validation, and cleanliness.",
    )
    _root(task)
    _bead(task, "Implementation Bead ID.")
    task.set_defaults(func=cmd_task_check)
    docs = _leaf(check_commands, "docs", "Validate mdBook navigation, links, decisions, and build output.")
    _root(docs)
    docs.set_defaults(func=cmd_docs_validate)

    commit = _leaf(commands, "commit", "Create a deterministic Conventional Commit from an implementation Bead.")
    _root(commit)
    commit.add_argument(
        "-a",
        "--amend",
        action="store_true",
        help="Amend HEAD while preserving its exact Beads ownership.",
    )
    _bead(commit, "Implementation Bead ID.")
    commit.add_argument("--body", dest="body_file", type=Path, help="Optional UTF-8 commit body file.")
    commit.set_defaults(func=cmd_commit, amend=False)

    worktree = _leaf(commands, "worktree", "Create or verify the feature worktree for a Bead.")
    _root(worktree)
    _bead(worktree, "Feature root or descendant Bead ID.")
    worktree.set_defaults(func=cmd_worktree_ensure)

    audit = _leaf(commands, "audit", "Collect bounded repository facts for a semantic audit skill.")
    _root(audit)
    audit.add_argument("feature", help="Feature root or descendant Bead ID.")
    audit.add_argument("--include-plan", action="store_true", help="Include the full native plan issue.")
    audit.add_argument(
        "--include-task",
        action="append",
        default=[],
        metavar="ID",
        help="Include one full implementation issue; repeat for additional tasks.",
    )
    audit.add_argument(
        "--include-decision",
        action="append",
        default=[],
        metavar="ID",
        help="Include one full decision issue; repeat for additional decisions.",
    )
    audit.add_argument(
        "--history-for",
        action="append",
        default=[],
        metavar="ID",
        help="Include native Beads history for one feature issue; repeat as needed.",
    )
    audit.add_argument(
        "--include-commit-paths",
        action="store_true",
        help="Include per-commit and aggregate changed paths.",
    )
    audit.set_defaults(func=cmd_audit_evidence)

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
