#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from dstack_commands import DstackError, fail
from dstack_feature import (
    cmd_feature_resolve,
    cmd_feature_inspect,
    cmd_feature_initialize,
    cmd_feature_scaffold_design,
    cmd_feature_add_task,
    cmd_feature_claim_spec,
    cmd_feature_approve_spec,
    cmd_feature_claim_next,
    cmd_feature_finish_task,
    cmd_feature_finish_workstream,
    cmd_feature_claim_closeout,
    cmd_feature_finish_closeout,
)
from dstack_alignment import (
    cmd_alignment_inspect,
    cmd_alignment_initialize,
    cmd_alignment_add_correction,
    cmd_alignment_finish_plan,
    cmd_alignment_approve,
    cmd_alignment_claim_next,
    cmd_alignment_finish_task,
    cmd_alignment_finish_workstream,
    cmd_alignment_claim_landing,
    cmd_alignment_finish_landing,
)
from dstack_delivery import (
    cmd_git_commit,
    cmd_git_amend,
    cmd_evidence_commits,
    cmd_evidence_audit_feature,
    cmd_docs_check,
    cmd_delivery_inspect,
    cmd_delivery_pr_preflight,
    cmd_delivery_register_pr,
    cmd_delivery_merge,
    cmd_delivery_finalize_pr,
)
from dstack_compat import cmd_adopt_inspect, cmd_adopt_apply

HELP_BY_DEST = {
    "root": "Repository root; defaults to the current directory.",
    "selector": "Feature, alignment, or legacy selector (ID, slug, or title).",
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
    "spec_note_file": "Read the legacy specification note from this file.",
    "closeout_note_file": "Read the legacy closeout note from this file.",
}


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mechanics: stateless deterministic controller for dstack workflows.")
    add_common_root(parser)
    top = parser.add_subparsers(dest="area", required=True)

    feature = mechanical_parser(top, "feature", "feature lifecycle commands")
    feature_sub = feature.add_subparsers(dest="command", required=True)
    resolve = mechanical_parser(feature_sub, "resolve", "resolve a feature selector")
    resolve.add_argument("selector", nargs="?")
    resolve.set_defaults(func=cmd_feature_resolve)
    inspect = mechanical_parser(feature_sub, "inspect", "inspect feature state and ready work")
    inspect.add_argument("selector", nargs="?")
    inspect.set_defaults(func=cmd_feature_inspect)
    initialize = mechanical_parser(feature_sub, "initialize", "create or reuse a feature branch and worktree")
    initialize.add_argument("selector", nargs="?")
    initialize.add_argument("--title")
    initialize.add_argument("--slug")
    initialize.add_argument("--base-branch", default="main")
    initialize.add_argument("--design-path")
    initialize.set_defaults(func=cmd_feature_initialize)
    scaffold_design = mechanical_parser(
        feature_sub, "scaffold-design", "create a missing design file without overwriting"
    )
    scaffold_design.add_argument("selector")
    scaffold_design.set_defaults(func=cmd_feature_scaffold_design)
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
    alignment_inspect = mechanical_parser(alignment_sub, "inspect", "inspect project-alignment state")
    alignment_inspect.add_argument("selector")
    alignment_inspect.set_defaults(func=cmd_alignment_inspect)
    alignment_init = mechanical_parser(alignment_sub, "initialize", "create a project-alignment workstream")
    alignment_init.add_argument("--title", required=True)
    alignment_init.add_argument("--slug")
    alignment_init.add_argument("--target-branch", default="main")
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
    finish_plan = mechanical_parser(alignment_sub, "finish-plan", "finish the alignment plan before execution")
    finish_plan.add_argument("selector")
    finish_plan.add_argument("--summary-file", type=Path)
    finish_plan.set_defaults(func=cmd_alignment_finish_plan)
    alignment_approve = mechanical_parser(alignment_sub, "approve", "approve the alignment plan and resolve its gate")
    alignment_approve.add_argument("selector")
    alignment_approve.set_defaults(func=cmd_alignment_approve)
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

    docs = mechanical_parser(top, "docs", "run documentation policy checks")
    docs_sub = docs.add_subparsers(dest="command", required=True)
    docs_check_parser = mechanical_parser(docs_sub, "check", "check changed documentation for transient bookkeeping")
    docs_check_parser.add_argument("--base", required=True)
    docs_check_parser.add_argument("--head", required=True)
    docs_check_parser.set_defaults(func=cmd_docs_check)

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
    register = mechanical_parser(delivery_sub, "register-pr", "register a merged pull request as a native gate")
    register.add_argument("selector")
    register.add_argument("--pr-number", type=int, required=True)
    register.set_defaults(func=cmd_delivery_register_pr)
    merge = mechanical_parser(delivery_sub, "merge", "fast-forward a clean delivery target")
    merge.add_argument("selector")
    merge.set_defaults(func=cmd_delivery_merge)
    finalize = mechanical_parser(delivery_sub, "finalize-pr", "finalize Beads after a merged pull request")
    finalize.add_argument("selector")
    finalize.set_defaults(func=cmd_delivery_finalize_pr)

    adopt = mechanical_parser(top, "adopt", "explicitly inspect or adopt legacy workflow data")
    adopt_sub = adopt.add_subparsers(dest="command", required=True)
    adopt_inspect = mechanical_parser(adopt_sub, "inspect", "inspect legacy workflow data without mutation")
    adopt_inspect.add_argument("selector")
    adopt_inspect.set_defaults(func=cmd_adopt_inspect)
    adopt_apply = mechanical_parser(adopt_sub, "apply", "adopt selected legacy work through native Beads")
    adopt_apply.add_argument("selector")
    adopt_apply.add_argument("--title")
    adopt_apply.add_argument("--slug")
    adopt_apply.add_argument("--base-branch")
    adopt_apply.add_argument("--design-path")
    adopt_apply.add_argument("--remaining", action="append", default=[])
    adopt_apply.add_argument("--spec-ceremony", action="append", default=[])
    adopt_apply.add_argument("--implementation-coordinator", action="append", default=[])
    adopt_apply.add_argument("--closeout-ceremony", action="append", default=[])
    adopt_apply.add_argument("--spec-note-file", type=Path)
    adopt_apply.add_argument("--closeout-note-file", type=Path)
    adopt_apply.set_defaults(func=cmd_adopt_apply)

    fill_argument_help(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DstackError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
