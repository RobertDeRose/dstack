#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from .audit import cmd_audit_feature
from .commands import DstackError, cmd_infra_check
from .core import canonical_positive_integer
from .docs import cmd_docs_validate
from .output import fail
from .feature import (
    cmd_feature_resolve,
    cmd_feature_plan,
    cmd_feature_inspect,
    cmd_feature_audit_complete,
    cmd_feature_initialize,
    cmd_feature_scaffold_design,
    cmd_feature_scaffold_reconciliation,
    cmd_feature_add_task,
    cmd_feature_claim_spec,
    cmd_feature_approve_spec,
    cmd_feature_reauthorize,
    cmd_feature_claim_next,
    cmd_feature_finish_task,
    cmd_feature_finish_workstream,
    cmd_feature_claim_closeout,
    cmd_feature_finish_closeout,
)
from .alignment import (
    cmd_alignment_inspect,
    cmd_alignment_initialize,
    cmd_alignment_scaffold_record,
    cmd_alignment_add_correction,
    cmd_alignment_finish_plan,
    cmd_alignment_approve,
    cmd_alignment_reauthorize,
    cmd_alignment_claim_next,
    cmd_alignment_finish_task,
    cmd_alignment_finish_workstream,
    cmd_alignment_claim_landing,
    cmd_alignment_finish_landing,
)
from .delivery import (
    cmd_git_commit,
    cmd_git_amend,
    cmd_evidence_commits,
    cmd_evidence_audit_feature,
    cmd_docs_check,
    cmd_delivery_inspect,
    cmd_delivery_pr_preflight,
    cmd_delivery_register_pr,
    cmd_delivery_replace_pr,
    cmd_delivery_cancel_pr_gate,
    cmd_delivery_merge,
    cmd_delivery_finalize_pr,
)
from .installer import main as install_skills_main

HELP_BY_DEST = {
    "root": "Repository root; defaults to the current directory.",
    "selector": "Feature or alignment selector (ID, slug, or title).",
    "title": "Human-readable title for the created or submitted item.",
    "slug": "Stable slug used for derived paths and branch names.",
    "base_branch": "Git branch from which the feature is based.",
    "design_path": "Must equal docs/src/features/<slug>/design.md.",
    "description": "Durable description of the work or correction.",
    "description_file": "Read the durable description from this file.",
    "acceptance": "Observable acceptance criteria for the work.",
    "acceptance_file": "Read acceptance criteria from this file.",
    "priority": "Native Beads priority for the created item.",
    "depends_on": "Additional native Beads dependency; repeat for multiple items.",
    "task": "Implementation or correction task to claim or finish.",
    "summary_file": "Read a durable Beads summary from this file.",
    "reason": "Native Beads close reason.",
    "no_repository_change": "Close without Git evidence using an explicit reason.",
    "target_branch": "Git branch being audited or targeted for delivery.",
    "scope": "Human-readable project-alignment scope.",
    "bead": "Beads ID to reference in the Git footer.",
    "subject": "One-line Git commit subject.",
    "body_file": "Read the Git or PR body from this file.",
    "ref": "Git ref or range to inspect.",
    "base": "Base Git ref for documentation comparison.",
    "head": "Candidate Git ref for documentation comparison.",
    "fetch": "Fetch the target remote before inspecting delivery.",
    "pr_number": "External pull-request number for the native gate.",
    "remaining": "Legacy item representing remaining product work; repeat as needed.",
    "spec_ceremony": "Legacy specification item to preserve; repeat as needed.",
    "implementation_coordinator": "Legacy implementation item to preserve; repeat as needed.",
    "closeout_ceremony": "Legacy closeout item to preserve; repeat as needed.",
}


def positive_integer(value: str) -> int:
    try:
        return canonical_positive_integer(value, field="integer")
    except DstackError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def add_common_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=Path.cwd(), help=HELP_BY_DEST["root"])


def mechanical_parser(
    parent: argparse._SubParsersAction,
    name: str,
    description: str,
) -> argparse.ArgumentParser:
    return parent.add_parser(
        name,
        help=description,
        description=f"Mechanics: {description}",
    )


def fill_argument_help(parser: argparse.ArgumentParser) -> None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                fill_argument_help(child)
            continue
        if action.dest == "help" or action.help:
            continue
        action.help = HELP_BY_DEST.get(
            action.dest,
            f"Value for {action.dest.replace('_', ' ')}.",
        )


def build_ctl_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mechanics: stateless deterministic controller for dstack workflows.")
    add_common_root(parser)
    top = parser.add_subparsers(dest="area", required=True)

    infra = mechanical_parser(top, "infra", "initialize Beads and validate packaged dStack formula contracts")
    infra_sub = infra.add_subparsers(dest="command", required=True)
    infra_check = mechanical_parser(infra_sub, "check", "ensure the local dStack infrastructure is current")
    infra_check.set_defaults(func=cmd_infra_check)

    feature = mechanical_parser(top, "feature", "feature lifecycle commands")
    feature_sub = feature.add_subparsers(dest="command", required=True)
    plan_feature = mechanical_parser(feature_sub, "plan", "create or update durable planned feature intent")
    plan_feature.add_argument("selector", nargs="?")
    plan_feature.add_argument("--title", required=True)
    plan_feature.add_argument("--slug")
    plan_feature.add_argument("--body-file", type=Path, required=True)
    plan_feature.add_argument("--acceptance", required=True)
    plan_feature.add_argument("--priority", type=int, default=2)
    plan_feature.add_argument("--depends-on", action="append", default=[])
    plan_feature.set_defaults(func=cmd_feature_plan)
    resolve = mechanical_parser(feature_sub, "resolve", "resolve a feature selector")
    resolve.add_argument("selector", nargs="?")
    resolve.set_defaults(func=cmd_feature_resolve)
    inspect = mechanical_parser(feature_sub, "inspect", "inspect the feature Bead and deterministic Git/worktree facts")
    inspect.add_argument("selector", nargs="?")
    inspect.add_argument("--verbose", action="store_true", help="emit the full live feature view")
    inspect.set_defaults(func=cmd_feature_inspect)
    audit_complete = mechanical_parser(
        feature_sub, "audit-complete", "record that existing approved work satisfies the current formula contract"
    )
    audit_complete.add_argument("selector")
    audit_complete.set_defaults(func=cmd_feature_audit_complete)
    initialize = mechanical_parser(feature_sub, "initialize", "create or reuse a feature branch and worktree")
    initialize.add_argument("selector", nargs="?")
    initialize.add_argument("--title")
    initialize.add_argument("--slug")
    initialize.add_argument("--base-branch")
    initialize.add_argument("--design-path")
    initialize.set_defaults(func=cmd_feature_initialize)
    scaffold_design = mechanical_parser(
        feature_sub, "scaffold-design", "create a missing design file without overwriting"
    )
    scaffold_design.add_argument("selector")
    scaffold_design.set_defaults(func=cmd_feature_scaffold_design)
    scaffold_reconciliation = mechanical_parser(
        feature_sub,
        "scaffold-reconciliation",
        "create a missing feature reconciliation without overwriting",
    )
    scaffold_reconciliation.add_argument("selector")
    scaffold_reconciliation.set_defaults(func=cmd_feature_scaffold_reconciliation)
    add_task = mechanical_parser(feature_sub, "add-task", "create an implementation task through native Beads")
    add_task.add_argument("selector")
    add_task.add_argument("--title", required=True)
    add_task.add_argument("--description")
    add_task.add_argument("--description-file", type=Path)
    add_task.add_argument("--acceptance")
    add_task.add_argument("--acceptance-file", type=Path)
    add_task.add_argument("--priority", type=int, default=2)
    add_task.add_argument("--depends-on", action="append", default=[])
    add_task.set_defaults(func=cmd_feature_add_task)
    claim_spec = mechanical_parser(feature_sub, "claim-spec", "claim the feature specification task")
    claim_spec.add_argument("selector", nargs="?")
    claim_spec.set_defaults(func=cmd_feature_claim_spec)
    approve = mechanical_parser(feature_sub, "approve-spec", "approve the design digest and authorize implementation")
    approve.add_argument("selector", nargs="?")
    approve.add_argument("--summary-file", type=Path)
    approve.set_defaults(func=cmd_feature_approve_spec)
    reauthorize = mechanical_parser(feature_sub, "reauthorize", "reopen feature authorization before scope changes")
    reauthorize.add_argument("selector")
    reauthorize.add_argument("--reason", required=True)
    reauthorize.set_defaults(func=cmd_feature_reauthorize)
    claim = mechanical_parser(feature_sub, "claim-next", "claim one native ready implementation task")
    claim.add_argument("selector", nargs="?")
    claim.add_argument("--task")
    claim.set_defaults(func=cmd_feature_claim_next)
    finish = mechanical_parser(feature_sub, "finish-task", "finish one implementation task after evidence checks")
    finish.add_argument("selector")
    finish.add_argument("--task", required=True)
    finish.add_argument("--reason")
    finish.add_argument("--summary-file", type=Path)
    finish.add_argument("--no-repository-change", action="store_true")
    finish.set_defaults(func=cmd_feature_finish_task)
    finish_workstream = mechanical_parser(
        feature_sub, "finish-workstream", "close the implementation epic when children are complete"
    )
    finish_workstream.add_argument("selector")
    finish_workstream.set_defaults(func=cmd_feature_finish_workstream)
    claim_closeout = mechanical_parser(
        feature_sub, "claim-closeout", "claim feature closeout after implementation fan-in"
    )
    claim_closeout.add_argument("selector", nargs="?")
    claim_closeout.set_defaults(func=cmd_feature_claim_closeout)
    finish_closeout = mechanical_parser(
        feature_sub, "finish-closeout", "finish feature closeout and record its summary"
    )
    finish_closeout.add_argument("selector", nargs="?")
    finish_closeout.add_argument("--reason", default="Closeout completed")
    finish_closeout.add_argument("--summary-file", type=Path)
    finish_closeout.set_defaults(func=cmd_feature_finish_closeout)

    alignment = mechanical_parser(top, "alignment", "project-alignment lifecycle commands")
    alignment_sub = alignment.add_subparsers(dest="command", required=True)
    alignment_inspect = mechanical_parser(
        alignment_sub,
        "inspect",
        "inspect the alignment Bead and deterministic Git/worktree facts",
    )
    alignment_inspect.add_argument("selector")
    alignment_inspect.add_argument("--verbose", action="store_true", help="emit the full live alignment view")
    alignment_inspect.set_defaults(func=cmd_alignment_inspect)
    alignment_scaffold = mechanical_parser(
        alignment_sub,
        "scaffold-record",
        "create an alignment reconciliation scaffold without overwriting",
    )
    alignment_scaffold.add_argument("kind", choices=("reconciliation",))
    alignment_scaffold.add_argument("--path", type=Path, required=True)
    alignment_scaffold.set_defaults(func=cmd_alignment_scaffold_record)
    alignment_init = mechanical_parser(alignment_sub, "initialize", "create a project-alignment workstream")
    alignment_init.add_argument("--title", required=True)
    alignment_init.add_argument("--slug")
    alignment_init.add_argument("--target-branch")
    alignment_init.add_argument("--scope", default="whole repository")
    alignment_init.set_defaults(func=cmd_alignment_initialize)
    correction = mechanical_parser(alignment_sub, "add-correction", "create a correction through native Beads")
    correction.add_argument("selector")
    correction.add_argument("--title", required=True)
    correction.add_argument("--description")
    correction.add_argument("--description-file", type=Path)
    correction.add_argument("--acceptance")
    correction.add_argument("--acceptance-file", type=Path)
    correction.add_argument("--priority", type=int, default=2)
    correction.add_argument("--depends-on", action="append", default=[])
    correction.set_defaults(func=cmd_alignment_add_correction)
    finish_plan = mechanical_parser(alignment_sub, "finish-plan", "finish the alignment review before execution")
    finish_plan.add_argument("selector")
    finish_plan.add_argument("--summary-file", type=Path, required=True)
    finish_plan.set_defaults(func=cmd_alignment_finish_plan)
    alignment_approve = mechanical_parser(alignment_sub, "approve", "approve the alignment review and resolve its gate")
    alignment_approve.add_argument("selector")
    alignment_approve.set_defaults(func=cmd_alignment_approve)
    alignment_reauthorize = mechanical_parser(
        alignment_sub, "reauthorize", "reopen alignment authorization before scope changes"
    )
    alignment_reauthorize.add_argument("selector")
    alignment_reauthorize.add_argument("--reason", required=True)
    alignment_reauthorize.set_defaults(func=cmd_alignment_reauthorize)
    alignment_claim = mechanical_parser(alignment_sub, "claim-next", "claim one native ready correction")
    alignment_claim.add_argument("selector")
    alignment_claim.add_argument("--task")
    alignment_claim.set_defaults(func=cmd_alignment_claim_next)
    alignment_finish = mechanical_parser(alignment_sub, "finish-task", "finish one correction after evidence checks")
    alignment_finish.add_argument("selector")
    alignment_finish.add_argument("--task", required=True)
    alignment_finish.add_argument("--reason")
    alignment_finish.add_argument("--summary-file", type=Path)
    alignment_finish.add_argument("--no-repository-change", action="store_true")
    alignment_finish.set_defaults(func=cmd_alignment_finish_task)
    alignment_workstream = mechanical_parser(
        alignment_sub, "finish-workstream", "close the correction epic when children are complete"
    )
    alignment_workstream.add_argument("selector")
    alignment_workstream.set_defaults(func=cmd_alignment_finish_workstream)
    claim_landing = mechanical_parser(alignment_sub, "claim-landing", "claim alignment landing after correction fan-in")
    claim_landing.add_argument("selector")
    claim_landing.set_defaults(func=cmd_alignment_claim_landing)
    finish_landing = mechanical_parser(
        alignment_sub, "finish-landing", "finish alignment landing and record its summary"
    )
    finish_landing.add_argument("selector")
    finish_landing.add_argument("--reason", default="Alignment landing completed")
    finish_landing.add_argument("--summary-file", type=Path)
    finish_landing.set_defaults(func=cmd_alignment_finish_landing)

    git_parser = mechanical_parser(top, "git", "create or amend commits with Beads footers")
    git_sub = git_parser.add_subparsers(dest="command", required=True)
    for name, handler, description in (
        ("commit", cmd_git_commit, "create a commit with a Beads footer"),
        ("amend", cmd_git_amend, "amend a commit while preserving its Beads footer"),
    ):
        item = mechanical_parser(git_sub, name, description)
        item.add_argument("--bead", required=True)
        item.add_argument("--subject", required=True)
        item.add_argument("--body-file", type=Path)
        item.set_defaults(func=handler)

    evidence = mechanical_parser(top, "evidence", "inspect reachable Git evidence")
    evidence_sub = evidence.add_subparsers(dest="command", required=True)
    commits = mechanical_parser(evidence_sub, "commits", "list commits carrying one Beads footer")
    commits.add_argument("--bead", required=True)
    commits.add_argument("--ref", default="HEAD")
    commits.set_defaults(func=cmd_evidence_commits)
    audit = mechanical_parser(evidence_sub, "audit-feature", "audit implementation footer evidence")
    audit.add_argument("selector")
    audit.set_defaults(func=cmd_evidence_audit_feature)

    audit_view = mechanical_parser(top, "audit", "emit read-only audit views")
    audit_view_sub = audit_view.add_subparsers(dest="command", required=True)
    audit_feature = mechanical_parser(
        audit_view_sub,
        "feature",
        "inspect the feature boundary; add --verbose for full audit facts",
    )
    audit_feature.add_argument("selector")
    audit_feature.add_argument("--format", choices=("json", "markdown"), default="json")
    audit_feature.add_argument("--verbose", action="store_true", help="emit complete Beads/Git/docs audit facts")
    audit_feature.set_defaults(func=cmd_audit_feature)

    docs = mechanical_parser(top, "docs", "run documentation policy checks")
    docs_sub = docs.add_subparsers(dest="command", required=True)
    docs_check_parser = mechanical_parser(docs_sub, "check", "check changed documentation for transient bookkeeping")
    docs_check_parser.add_argument("--base", required=True)
    docs_check_parser.add_argument("--head", required=True)
    docs_check_parser.set_defaults(func=cmd_docs_check)
    docs_validate_parser = mechanical_parser(docs_sub, "validate", "validate the current mdBook documentation")
    docs_validate_parser.set_defaults(func=cmd_docs_validate)

    delivery = mechanical_parser(top, "delivery", "inspect and execute safe delivery operations")
    delivery_sub = delivery.add_subparsers(dest="command", required=True)
    delivery_inspect = mechanical_parser(delivery_sub, "inspect", "inspect a delivery candidate")
    delivery_inspect.add_argument("selector")
    delivery_inspect.add_argument("--fetch", action="store_true")
    delivery_inspect.set_defaults(func=cmd_delivery_inspect)
    preflight = mechanical_parser(delivery_sub, "pr-preflight", "validate a candidate before creating a pull request")
    preflight.add_argument("selector")
    preflight.add_argument("--title")
    preflight.add_argument("--body-file", type=Path)
    preflight.set_defaults(func=cmd_delivery_pr_preflight)
    register = mechanical_parser(
        delivery_sub,
        "register-pr",
        "register an open, unmerged pull request as a native pre-merge gate",
    )
    register.add_argument("selector")
    register.add_argument("--pr-number", type=positive_integer, required=True)
    register.set_defaults(func=cmd_delivery_register_pr)
    replace = mechanical_parser(delivery_sub, "replace-pr", "replace conflicting pull-request gates")
    replace.add_argument("selector")
    replace.add_argument("--pr-number", type=positive_integer, required=True)
    replace.add_argument("--reason", required=True)
    replace.set_defaults(func=cmd_delivery_replace_pr)
    cancel_pr = mechanical_parser(
        delivery_sub,
        "cancel-pr-gate",
        "replace one active pull-request blocker with nonblocking audit context",
    )
    cancel_pr.add_argument("selector")
    cancel_pr.add_argument("--reason", required=True)
    cancel_pr.set_defaults(func=cmd_delivery_cancel_pr_gate)
    merge = mechanical_parser(delivery_sub, "merge", "fast-forward a clean delivery target")
    merge.add_argument("selector")
    merge.set_defaults(func=cmd_delivery_merge)
    finalize = mechanical_parser(delivery_sub, "finalize-pr", "finalize Beads after a merged pull request")
    finalize.add_argument("selector")
    finalize.set_defaults(func=cmd_delivery_finalize_pr)

    fill_argument_help(parser)
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
        "usage: dstack {install_skills,ctl} ...\n\n"
        "commands:\n"
        "  install_skills  install/update Pi skills, prompts, and dStack system guidance\n"
        "  ctl             run deterministic dStack workflow mechanics\n"
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
    if command == "install_skills":
        return install_skills_main(rest)
    if command == "ctl":
        return ctl_main(rest)
    print(f"dstack: unknown command: {command}", file=sys.stderr)
    _print_root_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
