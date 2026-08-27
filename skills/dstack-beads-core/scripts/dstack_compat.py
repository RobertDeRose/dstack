#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from dstack_adoption import (
    adoption_graph_snapshot,
    adoption_plan_graph_matches,
    parse_classification_file,
    plan_adoption,
    reconcile_adoption_graph,
)
from dstack_adoption_apply import (
    execute_adoption_plan,
    validate_adoption_preflight,
    validate_target_topology,
)
from dstacklib import (
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

from dstack_commands import (
    client_for,
    descendants,
    emit,
    require_installed_formula,
    superseded_target,
    update_root_identity,
)

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


def cmd_adopt_plan(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    legacy = resolve_legacy_feature(client, args.selector)
    if legacy.get("status") == "closed":
        raise DstackError(f"legacy feature is already closed: {legacy['id']}")
    if is_current_feature(client, legacy):
        raise DstackError(f"feature already uses current dStack workflow: {legacy['id']}")
    if not args.classification_file:
        raise DstackError("adoption planning requires --classification-file")
    classification = parse_classification_file(
        Path(args.classification_file), root=client.root, legacy_root_id=str(legacy["id"])
    )
    emit(plan_adoption(client, str(legacy["id"]), classification))
    return 0


def cmd_adopt_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root = resolve_legacy_feature(client, args.selector)
    if root.get("status") == "closed":
        raise DstackError(f"legacy feature is already closed: {root['id']}")
    if is_current_feature(client, root):
        raise DstackError(f"feature already uses current dstack workflow: {root['id']}")
    items = [item for item in descendants(client, str(root["id"])) if item.get("status") != "closed"]
    classified: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        classified.setdefault(classify_legacy_item(item), []).append(item)
    emit({"status": "ok", "legacy_root": root, "classified": classified})
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
    legacy_flags = any(
        getattr(args, name, None)
        for name in (
            "remaining",
            "spec_ceremony",
            "implementation_coordinator",
            "closeout_ceremony",
            "spec_note_file",
            "closeout_note_file",
        )
    )
    if legacy_flags:
        raise DstackError(
            "legacy compatibility flags are not authoritative; use only "
            "--classification-file with complete strict classification"
        )
    if not getattr(args, "classification_file", None):
        raise DstackError(
            "adoption apply requires --classification-file; classify every open executable descendant first"
        )

    classification = parse_classification_file(
        Path(args.classification_file),
        root=client.root,
        legacy_root_id=str(legacy["id"]),
        design_path=design,
    )
    # This is deliberately before pour/create: invalid classifications and graph
    # drift must not mutate Beads.
    plan = plan_adoption(
        client,
        str(legacy["id"]),
        classification,
        target_design_path=design,
    )
    planned_graph = adoption_graph_snapshot(client, str(legacy["id"]))
    if not adoption_plan_graph_matches(plan, planned_graph):
        raise DstackError("legacy adoption graph drifted during planning")
    validate_adoption_preflight(
        client,
        plan,
        legacy_root_id=str(legacy["id"]),
    )

    current = current_feature_for_slug(client, slug, exclude_id=str(legacy["id"]))
    if current is None:
        require_installed_formula(client.root, "dstack-feature")
        reconcile_adoption_graph(client, planned_graph, str(legacy["id"]))
        pour = client.pour(
            "dstack-feature",
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
