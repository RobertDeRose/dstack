#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
from typing import Any, Mapping

from .adoption import (
    SCHEMA as ADOPTION_CLASSIFICATION_SCHEMA,
    adoption_graph_snapshot,
    adoption_plan_graph_matches,
    canonicalize_classification,
    plan_adoption,
    reconcile_adoption_graph,
)
from .adoption_apply import (
    execute_adoption_plan,
    validate_adoption_preflight,
    validate_target_topology,
)
from .core import (
    BeadsClient,
    DstackError,
    canonical_feature_design_path,
    display_title,
    feature_context,
    feature_roots,
    feature_slug,
    issue_labels,
    issue_metadata,
    is_current_feature,
    resolve_legacy_feature,
    root_metadata_value,
    slugify,
)

from .formula import FEATURE_FORMULA, pour_current_formula
from .commands import (
    client_for,
    superseded_target,
    update_root_identity,
)
from .output import emit

COMPATIBILITY_SHIMS = (
    {
        "name": "like-kind-approval-milestone",
        "pinned_version": "bd version 1.2.2 (6c124203e)",
        "reproducer": "tests/acceptance/test_bd_contract.py::test_bd_contract_covers_native_primitives",
        "reason": "Beads rejects blocking dependencies between unlike issue kinds.",
        "behavior": "A task-sized approval milestone carries the human gate and blocks dynamic tasks.",
        "upstream": None,
        "retirement": "The supported Beads build accepts and preserves the intended cross-kind topology.",
    },
    {
        "name": "dynamic-child-fan-in-veto",
        "pinned_version": "bd version 1.2.2 (6c124203e)",
        "reproducer": "tests/acceptance/test_bd_contract.py::test_bd_contract_covers_native_primitives",
        "reason": "Native terminal readiness can miss an open dynamic direct child.",
        "behavior": "dStack only vetoes terminal transitions while a direct child is nonterminal.",
        "upstream": None,
        "retirement": "The pinned real-Beads reproducer natively blocks the terminal.",
    },
    {
        "name": "terminal-root-reopen",
        "pinned_version": "bd version 1.2.2 (6c124203e)",
        "reproducer": "tests/acceptance/test_feature_smoke.py::test_feature_smoke_runs_shipped_lifecycle",
        "reason": "Completing a terminal step can close the molecule before Git delivery.",
        "behavior": "Reopen only an automatically closed root while delivery remains pending.",
        "upstream": None,
        "retirement": "The supported Beads lifecycle preserves an open root until delivery.",
    },
)


def classify_legacy_item(item: Mapping[str, Any]) -> str:
    title = str(item.get("title", "")).casefold()
    labels = set(issue_labels(item))
    metadata = issue_metadata(item)
    phase = str(metadata.get("workflow_phase") or "").casefold()
    if "phase:implementation" in labels or phase == "implementation" or " t00" in title:
        return "implementation"
    if title.startswith("implement:"):
        return "implementation-coordinator"
    if any(label.startswith("review:") for label in labels) or title.startswith("review "):
        return "spec-ceremony" if phase in {"spec-review", "specification"} else "closeout-ceremony"
    if any(word in title for word in ("validate:", "deliver:", "reconcile documentation", "documentation drift")):
        return "closeout-ceremony"
    if "reconcile specification" in title:
        return "spec-ceremony"
    return "ambiguous"


def _selection_pair(value: str, option: str) -> tuple[str, str]:
    issue_id, separator, detail = value.partition("=")
    issue_id = issue_id.strip()
    detail = detail.strip()
    if not separator or not issue_id or not detail:
        raise DstackError(f"{option} must use ISSUE_ID=VALUE")
    return issue_id, detail


def _replacement_for(item: Mapping[str, Any]) -> dict[str, Any]:
    priority = item.get("priority")
    return {
        "title": str(item.get("title") or item["id"]),
        "description": str(item.get("description") or "Legacy work retained during adoption."),
        "acceptance": str(
            item.get("acceptance_criteria")
            or item.get("acceptance")
            or "Existing acceptance criteria must be revalidated before completion."
        ),
        "priority": priority if isinstance(priority, int) and not isinstance(priority, bool) else 2,
    }


def _classification_from_args(
    client: BeadsClient,
    args: argparse.Namespace,
    *,
    legacy_root_id: str,
    design_path: str,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    records = {
        str(item["id"]): dict(item)
        for item in snapshot.get("legacy_records", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    entries: dict[str, dict[str, Any]] = {}

    def record_for(issue_id: str) -> dict[str, Any]:
        if issue_id == legacy_root_id or issue_id not in records:
            raise DstackError(f"adoption selection is not a descendant of {legacy_root_id}: {issue_id}")
        return records[issue_id]

    def add(issue_id: str, entry: dict[str, Any]) -> None:
        record_for(issue_id)
        if issue_id in entries:
            raise DstackError(f"adoption item was classified more than once: {issue_id}")
        entries[issue_id] = {"legacy_id": issue_id, **entry}

    for issue_id in args.remaining:
        add(
            issue_id,
            {
                "classification": "remaining-implementation",
                "reason": "Explicitly selected as remaining implementation work.",
                "replacement": _replacement_for(record_for(issue_id)),
            },
        )
    for issue_id in args.spec_ceremony:
        add(
            issue_id,
            {"classification": "obsolete-specification-ceremony", "reason": "Covered by current specification review."},
        )
    for issue_id in args.implementation_coordinator:
        add(
            issue_id,
            {
                "classification": "obsolete-implementation-ceremony",
                "reason": "Covered by the current implementation workstream.",
            },
        )
    for issue_id in args.closeout_ceremony:
        add(
            issue_id,
            {
                "classification": "obsolete-closeout-delivery-ceremony",
                "reason": "Covered by current closeout and delivery.",
            },
        )
    for issue_id in args.preserve:
        add(
            issue_id,
            {
                "classification": "preserved-unchanged",
                "reason": "Explicitly preserved under the legacy root.",
                "strategy": "keep-legacy-root",
                "surviving_parent": None,
                "replacement": None,
            },
        )
    for value in args.reparent:
        issue_id, parent_id = _selection_pair(value, "--reparent")
        add(
            issue_id,
            {
                "classification": "preserved-unchanged",
                "reason": "Explicitly reparented to a surviving native container.",
                "strategy": "reparent",
                "surviving_parent": parent_id,
                "replacement": None,
            },
        )
    for issue_id in args.recreate:
        add(
            issue_id,
            {
                "classification": "preserved-unchanged",
                "reason": "Explicitly recreated under the current implementation workstream.",
                "strategy": "recreate",
                "surviving_parent": None,
                "replacement": _replacement_for(record_for(issue_id)),
            },
        )
    for value in args.incorporated_decision:
        issue_id, section = _selection_pair(value, "--incorporated-decision")
        add(
            issue_id,
            {
                "classification": "unresolved-decision",
                "reason": "Decision is incorporated into the approved specification.",
                "strategy": "incorporated",
                "specification_section": section,
                "blocking_target": None,
            },
        )
    for value in args.decision_blocker:
        issue_id, target = _selection_pair(value, "--decision-blocker")
        add(
            issue_id,
            {
                "classification": "unresolved-decision",
                "reason": "Decision remains an explicit native blocker.",
                "strategy": "preserve-blocker",
                "specification_section": None,
                "blocking_target": target,
            },
        )
    for issue_id in args.completed:
        add(
            issue_id,
            {
                "classification": "completed-history",
                "reason": "Explicitly selected as completed historical work.",
                "evidence": [
                    {
                        "kind": "git-footer",
                        "reference": "HEAD",
                        "explanation": "Reachable Git history contains the legacy Beads footer.",
                    }
                ],
                "evidence_assessment": "verified",
                "accepted_risk_reason": None,
            },
        )

    payload = {
        "schema": ADOPTION_CLASSIFICATION_SCHEMA,
        "legacy_root_id": legacy_root_id,
        "entries": [entries[item_id] for item_id in sorted(entries)],
    }
    return canonicalize_classification(
        payload,
        root=client.root,
        legacy_root_id=legacy_root_id,
        design_path=design_path,
    )


def cmd_adopt_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root, initialize=False)
    root = resolve_legacy_feature(client, args.selector)
    if root.get("status") == "closed":
        raise DstackError(f"legacy feature is already closed: {root['id']}")
    if is_current_feature(client, root):
        raise DstackError(f"feature already uses current dstack workflow: {root['id']}")
    snapshot = adoption_graph_snapshot(client, str(root["id"]))
    items = [
        item
        for item in snapshot["legacy_records"]
        if str(item.get("id")) != str(root["id"]) and item.get("status") != "closed"
    ]
    classified: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        classified.setdefault(classify_legacy_item(item), []).append(item)
    emit(
        {
            "status": "ok",
            "legacy_root": root,
            "classified": classified,
            "selection_help": {
                "implementation": "--remaining ID",
                "specification_ceremony": "--spec-ceremony ID",
                "implementation_ceremony": "--implementation-coordinator ID",
                "closeout_ceremony": "--closeout-ceremony ID",
                "preserve": "--preserve ID",
                "reparent": "--reparent ID=PARENT",
                "recreate": "--recreate ID",
                "incorporated_decision": "--incorporated-decision ID=PATH#HEADING",
                "decision_blocker": "--decision-blocker ID=STEP",
                "completed_history": "--completed ID",
            },
        }
    )
    return 0


def current_feature_for_slug(
    client: BeadsClient,
    slug: str,
    *,
    exclude_id: str,
) -> dict[str, Any] | None:
    matches = [
        root
        for root in feature_roots(client)
        if str(root.get("id")) != exclude_id
        and root.get("status") != "closed"
        and feature_slug(root) == slug
        and feature_context(client, str(root["id"]))["current"]
    ]
    if len(matches) > 1:
        raise DstackError(
            "multiple current feature roots already exist for slug "
            f"{slug}: " + ", ".join(str(item["id"]) for item in matches)
        )
    return matches[0] if matches else None


def cmd_adopt_apply(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    legacy = resolve_legacy_feature(client, args.selector)
    existing_replacement = superseded_target(legacy)
    if legacy.get("status") == "closed":
        if existing_replacement:
            emit(
                {
                    "status": "ok",
                    "already_adopted": True,
                    "legacy_root": legacy["id"],
                    "new_root": existing_replacement,
                    **feature_context(client, existing_replacement),
                }
            )
            return 0
        raise DstackError("legacy feature is already closed")
    if is_current_feature(client, legacy):
        raise DstackError("feature already uses current dStack workflow")

    title = args.title or display_title(str(legacy.get("title", "")))
    slug = args.slug or feature_slug(legacy) or slugify(title)
    base = args.base_branch or root_metadata_value(legacy, "base_branch") or "main"
    design = canonical_feature_design_path(slug)
    if args.design_path and args.design_path != design:
        raise DstackError(f"feature design path must be {design} for the mdBook layout")
    planned_graph = adoption_graph_snapshot(client, str(legacy["id"]))
    classification = _classification_from_args(
        client,
        args,
        legacy_root_id=str(legacy["id"]),
        design_path=design,
        snapshot=planned_graph,
    )
    # Selection validation and graph drift checks occur before pour/create.
    plan = plan_adoption(
        client,
        str(legacy["id"]),
        classification,
        target_design_path=design,
        snapshot=planned_graph,
    )
    if not adoption_plan_graph_matches(plan, planned_graph):
        raise DstackError("legacy adoption graph drifted during planning")
    validate_adoption_preflight(
        client,
        plan,
        legacy_root_id=str(legacy["id"]),
    )

    current = current_feature_for_slug(client, slug, exclude_id=str(legacy["id"]))
    if current is None:
        reconcile_adoption_graph(client, planned_graph, str(legacy["id"]))
        pour = pour_current_formula(
            client,
            FEATURE_FORMULA,
            {
                "feature_title": title,
                "feature_slug": slug,
                "design_path": design,
            },
        )
        root_id = str(pour.get("root_id") or pour.get("new_epic_id") or "")
        if not root_id:
            raise DstackError("bd mol pour returned no feature root")
        validate_target_topology(client, root_id)
        reconcile_adoption_graph(client, planned_graph, str(legacy["id"]))
        update_root_identity(
            client,
            root_id,
            title=title,
            slug=slug,
            base_branch=base,
            design_path=design,
        )
    else:
        root_id = str(current["id"])
    view = feature_context(client, root_id)
    reconcile_adoption_graph(client, planned_graph, str(legacy["id"]))
    validate_adoption_preflight(
        client,
        plan,
        legacy_root_id=str(legacy["id"]),
        target_view=view,
    )

    result = execute_adoption_plan(
        client,
        plan,
        legacy_root_id=str(legacy["id"]),
        new_root_id=root_id,
        view=view,
        expected_graph=planned_graph,
    )
    emit({**result, **feature_context(client, root_id)})
    return 0
