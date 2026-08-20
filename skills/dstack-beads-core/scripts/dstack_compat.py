#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from dstacklib import (
    BeadsClient,
    DstackError,
    ancestry,
    blocker_ids,
    branch_exists,
    commit_footer_ids,
    conventional_worktree,
    current_head,
    dependency_records,
    display_title,
    ensure_clean_tracked,
    feature_context,
    feature_slug,
    file_sha256,
    git_root,
    has_label,
    issue_labels,
    issue_type,
    issue_metadata,
    issue_parent,
    read_text_file,
    ref_exists,
    resolve_feature,
    root_metadata_value,
    run,
    slugify,
    worktree_for_branch,
)

from dstack_commands import (
    BEADS_RUNTIME_DIR_PREFIXES,
    BEADS_RUNTIME_TOP_LEVEL_PATTERNS,
    BEADS_SENSITIVE_BASENAMES,
    DESIGN_SCAFFOLD,
    DSTACK_UNTRACKED_BEADS_FILES,
    DURABLE_STATUS_PATTERN,
    FORBIDDEN_DOC_PATTERNS,
    NO_REPOSITORY_CHANGE_PREFIX,
    claim_issue_if_needed,
    client_for,
    completion_reason,
    descendants,
    emit,
    ensure_feature_worktree,
    evidence_for_bead,
    fail,
    feature_branch_context,
    package_root,
    preserve_external_blockers,
    require_approved_design,
    require_installed_formula,
    required_task_text,
    superseded_target,
    task_text,
    update_root_identity,
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


def cmd_adopt_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root = resolve_feature(client, args.selector)
    if root.get("status") == "closed":
        raise DstackError(f"legacy feature is already closed: {root['id']}")
    if feature_context(client, str(root["id"]))["current"]:
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
        for root in client.list(all_statuses=True, labels=["workflow:feature"])
        if issue_type(root) in {"epic", "molecule"}
        and str(root.get("id")) != exclude_id
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
    legacy = resolve_feature(client, args.selector)
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
    if feature_context(client, str(legacy["id"]))["current"]:
        raise DstackError("feature already uses current dStack workflow")

    title = args.title or display_title(str(legacy.get("title", "")))
    slug = args.slug or feature_slug(legacy) or slugify(title)
    base = args.base_branch or root_metadata_value(legacy, "base_branch") or "main"
    design = (
        args.design_path
        or root_metadata_value(legacy, "design_path")
        or f"docs/src/features/{slug}/design.md"
    )

    current = current_feature_for_slug(
        client, slug, exclude_id=str(legacy["id"])
    )
    if current is None:
        require_installed_formula(client.root, "dstack-feature")
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

    mapping: dict[str, str] = {}
    for old_id in args.remaining:
        old = client.show(old_id)
        target = superseded_target(old)
        if target:
            mapping[old_id] = target
            continue
        replacement = client.create(
            str(old.get("title", old_id)),
            parent=str(view["steps"]["implementation"]["id"]),
            labels=["dstack:work:implementation"],
            dependencies=[str(view["steps"]["approval"]["id"])],
            description=str(old.get("description") or ""),
            acceptance=str(
                old.get("acceptance_criteria") or old.get("acceptance") or ""
            ),
            priority=int(old.get("priority") or 2),
        )
        mapping[old_id] = str(replacement["id"])
        client.supersede(old_id, str(replacement["id"]))

    categories = (
        (args.spec_ceremony, str(view["steps"]["specification"]["id"])),
        (args.implementation_coordinator, str(view["steps"]["implementation"]["id"])),
        (args.closeout_ceremony, str(view["steps"]["closeout"]["id"])),
    )
    for old_ids, target in categories:
        for old_id in old_ids:
            mapping[old_id] = target
            client.supersede(old_id, target)

    if args.spec_note_file:
        client.add_comment(
            str(view["steps"]["specification"]["id"]),
            read_text_file(args.spec_note_file),
        )
    if args.closeout_note_file:
        client.add_comment(
            str(view["steps"]["closeout"]["id"]),
            read_text_file(args.closeout_note_file),
        )

    preserved_blockers = preserve_external_blockers(client, legacy, root_id)
    client.supersede(str(legacy["id"]), root_id)
    emit(
        {
            "status": "ok",
            "legacy_root": legacy["id"],
            "new_root": root_id,
            "mapping": mapping,
            "external_blockers_preserved": preserved_blockers,
            **feature_context(client, root_id),
        }
    )
    return 0
