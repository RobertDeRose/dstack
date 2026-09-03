#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from .audit import cmd_audit_evidence
from .commands import (
    DstackError,
    cmd_formula_check,
    cmd_init,
    cmd_formula_install,
    cmd_plan_check,
    cmd_task_check,
    cmd_worktree_ensure,
)
from .docs import cmd_docs_validate
from .git_ops import cmd_evidence_commits, cmd_git_amend, cmd_git_commit
from .installer import main as install_skills_main
from .output import fail


def _leaf(parent: argparse._SubParsersAction, name: str, description: str) -> argparse.ArgumentParser:
    return parent.add_parser(name, help=description, description=description)


def build_init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize and validate dStack's Beads workspace contract.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root; defaults to the current directory.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Replace a different project formula or prime after reviewing the packaged changes.",
    )
    parser.set_defaults(func=cmd_init)
    return parser


def init_main(argv: Sequence[str] | None = None) -> int:
    parser = build_init_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DstackError as exc:
        return fail(str(exc))
    except (OSError, UnicodeError) as exc:
        return fail(f"filesystem operation failed: {exc}")


def build_ctl_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic repository mechanics for a Beads-owned software workflow."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root; defaults to the current directory.",
    )
    areas = parser.add_subparsers(dest="area", required=True)

    formula = _leaf(areas, "formula", "Install or verify the packaged dStack Beads formula and scoped prime.")
    formula_commands = formula.add_subparsers(dest="command", required=True)
    install = _leaf(
        formula_commands, "install", "Install the packaged formula and scoped prime into an existing Beads workspace."
    )
    install.add_argument(
        "--update",
        action="store_true",
        help="Replace a different project formula after the caller has reviewed the packaged change.",
    )
    install.set_defaults(func=cmd_formula_install)
    check = _leaf(formula_commands, "check", "Verify the installed formula, scoped prime, and native Beads parsing.")
    check.set_defaults(func=cmd_formula_check)

    plan = _leaf(areas, "plan", "Validate the structure of a native Beads feature plan.")
    plan_commands = plan.add_subparsers(dest="command", required=True)
    plan_check = _leaf(plan_commands, "check", "Check required plan sections, resolved questions, and audiences.")
    plan_check.add_argument("bead", help="Plan-step Bead ID.")
    plan_check.set_defaults(func=cmd_plan_check)

    worktree = _leaf(areas, "worktree", "Apply feature branch and worktree policy using native Beads worktree support.")
    worktree_commands = worktree.add_subparsers(dest="command", required=True)
    worktree_ensure = _leaf(worktree_commands, "ensure", "Create or verify the selected feature worktree.")
    worktree_ensure.add_argument("feature", help="Feature root or descendant Bead ID.")
    worktree_ensure.set_defaults(func=cmd_worktree_ensure)

    git = _leaf(areas, "git", "Create deterministic Conventional Commits from implementation Beads.")
    git_commands = git.add_subparsers(dest="command", required=True)
    for name, func, description in (
        ("commit", cmd_git_commit, "Commit staged changes with a generated subject and Beads footer."),
        ("amend", cmd_git_amend, "Amend HEAD while preserving its exact Beads ownership."),
    ):
        command = _leaf(git_commands, name, description)
        command.add_argument("--bead", required=True, help="Implementation Bead ID.")
        command.add_argument("--body-file", type=Path, help="Optional UTF-8 commit body file.")
        command.set_defaults(func=func)

    evidence = _leaf(areas, "evidence", "Inspect Git evidence without changing Beads or Git.")
    evidence_commands = evidence.add_subparsers(dest="command", required=True)
    commits = _leaf(evidence_commands, "commits", "Find commits with one exact Beads footer.")
    commits.add_argument("--bead", required=True, help="Bead ID to locate.")
    commits.add_argument("--ref", required=True, help="Git ref or range to inspect.")
    commits.set_defaults(func=cmd_evidence_commits)

    task = _leaf(areas, "task", "Validate an implementation Bead and its repository evidence.")
    task_commands = task.add_subparsers(dest="command", required=True)
    task_check = _leaf(
        task_commands,
        "check",
        "Check native graph membership, documentation impact, Git evidence, validation, and cleanliness.",
    )
    task_check.add_argument("bead", help="Implementation Bead ID.")
    task_check.set_defaults(func=cmd_task_check)

    audit = _leaf(areas, "audit", "Collect bounded repository facts for a semantic audit skill.")
    audit_commands = audit.add_subparsers(dest="command", required=True)
    audit_evidence = _leaf(
        audit_commands,
        "evidence",
        "Collect compact plan, task, decision, Git, docs, and validation evidence.",
    )
    audit_evidence.add_argument("feature", help="Feature root or descendant Bead ID.")
    audit_evidence.add_argument("--include-plan", action="store_true", help="Include the full native plan issue.")
    audit_evidence.add_argument(
        "--include-task",
        action="append",
        default=[],
        metavar="ID",
        help="Include one full implementation issue; repeat for additional tasks.",
    )
    audit_evidence.add_argument(
        "--include-decision",
        action="append",
        default=[],
        metavar="ID",
        help="Include one full decision issue; repeat for additional decisions.",
    )
    audit_evidence.add_argument(
        "--history-for",
        action="append",
        default=[],
        metavar="ID",
        help="Include native Beads history for one feature issue; repeat as needed.",
    )
    audit_evidence.add_argument(
        "--include-commit-paths",
        action="store_true",
        help="Include per-commit and aggregate changed paths.",
    )
    audit_evidence.set_defaults(func=cmd_audit_evidence)

    docs = _leaf(areas, "docs", "Validate current project documentation.")
    docs_commands = docs.add_subparsers(dest="command", required=True)
    docs_validate = _leaf(docs_commands, "validate", "Validate mdBook navigation, links, decisions, and build output.")
    docs_validate.set_defaults(func=cmd_docs_validate)

    return parser


def ctl_main(argv: Sequence[str] | None = None) -> int:
    parser = build_ctl_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DstackError as exc:
        return fail(str(exc))
    except (OSError, UnicodeError) as exc:
        return fail(f"filesystem operation failed: {exc}")


def _package_version() -> str:
    try:
        return version("dstack")
    except PackageNotFoundError:
        return "development"


def _print_root_help() -> None:
    print(
        "usage: dstack {init,install_skills,ctl} ...\n\n"
        "commands:\n"
        "  init            initialize and validate the dStack Beads workspace contract\n"
        "  install_skills  install/update the four targeted Pi skills and prompts\n"
        "  ctl             run deterministic repository mechanics\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] in {"-h", "--help"}:
        _print_root_help()
        return 0
    if values[0] in {"-V", "--version"}:
        print(_package_version())
        return 0
    command, rest = values[0], values[1:]
    if command == "init":
        return init_main(rest)
    if command == "install_skills":
        return install_skills_main(rest)
    if command == "ctl":
        return ctl_main(rest)
    print(f"dstack: unknown command: {command}", file=sys.stderr)
    _print_root_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
