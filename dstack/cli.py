#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from .audit import cmd_audit_evidence
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

    install = _leaf(commands, "install", "Install dStack agent resources.")
    install_commands = install.add_subparsers(dest="command", required=True)
    skills = _leaf(install_commands, "skills", "Install or update the five targeted Pi skills and prompts.")
    skills.add_argument(
        "--agent-dir",
        type=Path,
        default=default_agent_dir(),
        help="Pi agent directory; defaults to PI_CODING_AGENT_DIR or ~/.pi/agent.",
    )
    skills.set_defaults(func=cmd_install_skills)
    check = _leaf(commands, "check", "Validate formula policy, plans, tasks, or documentation.")
    check_commands = check.add_subparsers(dest="command", required=True)
    formula_check = _leaf(check_commands, "formula", "Check installed policy against the package and HEAD.")
    _root(formula_check)
    formula_check.set_defaults(func=cmd_formula_check)
    plan = _leaf(check_commands, "plan", "Check native plan fields and publishable section structure.")
    _root(plan)
    _bead(plan, "Plan-step Bead ID.")
    plan.set_defaults(func=cmd_plan_check)
    review = _leaf(check_commands, "review", "Check the complete native graph before human approval.")
    _root(review)
    review.add_argument("-b", "--bead", "--feature", dest="feature", required=True, help="Feature root or descendant Bead ID.")
    review.set_defaults(func=cmd_review_check)
    task = _leaf(
        check_commands,
        "task",
        "Check native graph membership, Git evidence, and worktree cleanliness.",
    )
    _root(task)
    _bead(task, "Implementation Bead ID.")
    task.set_defaults(func=cmd_task_check)
    docs_check = _leaf(check_commands, "docs", "Validate one feature's documentation structure.")
    _root(docs_check)
    docs_check.add_argument("--slug", required=True, help="Kebab-case feature slug.")
    docs_check.set_defaults(func=cmd_docs_validate)

    docs = _leaf(commands, "docs", "Materialize reviewed feature documentation.")
    docs_commands = docs.add_subparsers(dest="command", required=True)
    export_design = _leaf(docs_commands, "export-design", "Export the reviewed plan design without rewriting it.")
    _root(export_design)
    export_design.add_argument("-b", "--bead", "--feature", dest="feature", required=True, help="Feature root or descendant Bead ID.")
    export_design.add_argument(
        "--scaffold",
        action="store_true",
        help="Create missing index sections and SUMMARY link without replacing prose.",
    )
    export_design.set_defaults(func=cmd_docs_export)
    docs_commit = _leaf(docs_commands, "commit", "Commit the validated feature documentation for close.")
    _root(docs_commit)
    docs_commit.add_argument("-b", "--bead", "--feature", dest="feature", required=True, help="Feature root or descendant Bead ID.")
    docs_commit.set_defaults(func=cmd_git_commit_docs)

    commit = _leaf(commands, "commit", "Create or correct the canonical commit for an implementation task.")
    _root(commit)
    _bead(commit, "Implementation Bead ID.")
    commit.set_defaults(func=cmd_git_commit)

    worktree = _leaf(commands, "worktree", "Create or verify the feature worktree for a Bead.")
    _root(worktree)
    _bead(worktree, "Feature root or descendant Bead ID.")
    worktree.set_defaults(func=cmd_worktree_ensure)

    audit = _leaf(commands, "audit", "Collect bounded repository facts for a semantic audit skill.")
    _root(audit)
    _bead(audit, "Feature root or descendant Bead ID.")
    audit.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Page task, decision, gate, and commit summaries; checks remain complete.",
    )
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
    audit.add_argument(
        "--require-docs",
        action="store_true",
        help="Treat missing or invalid feature documentation as a failed close check.",
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
