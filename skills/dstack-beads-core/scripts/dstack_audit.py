#!/usr/bin/env python3
"""Read-only, stateless audit views over live Beads, Git, and mdBook facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, cast

from dstack_commands import client_for
from dstack_delivery import (
    delivered_feature_evidence_audit,
    feature_evidence_audit,
    pr_gate_state,
)
from dstack_docs import HEADING_PATTERN, LINK_PATTERN, _markdown_values, validate_record
from dstack_types import FeatureAuditView
from dstacklib import (
    BeadsClient,
    DstackError,
    ancestry,
    dependency_records,
    feature_authorization_state,
    feature_context,
    feature_design_state,
    gate_type,
    has_label,
    issue_labels,
    issue_metadata,
    issue_parent,
    issue_type,
    ref_exists,
    worktree_for_branch,
)


def issue_fact(item: Mapping[str, Any]) -> dict[str, Any]:
    dependencies = sorted(
        (
            {
                "id": str(record.get("depends_on_id") or record.get("id") or ""),
                "type": str(record.get("type") or record.get("dependency_type") or "blocks"),
            }
            for record in dependency_records(item)
        ),
        key=lambda record: (record["type"], record["id"]),
    )
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or ""),
        "type": issue_type(item),
        "status": str(item.get("status") or "unknown"),
        "parent": issue_parent(item),
        "labels": sorted(issue_labels(item)),
        "dependencies": dependencies,
        "close_reason": item.get("close_reason"),
    }


def record_fact(path: Path, kind: str, root: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": path.relative_to(root).as_posix(),
            "status": "missing",
            "links": [],
            "validation_and_limitations": None,
        }
    text = path.read_text(encoding="utf-8")
    error: str | None = None
    try:
        validate_record(text, kind, source=path, source_root=root)
    except DstackError as exc:
        error = str(exc)
    links = sorted(_markdown_values(text, LINK_PATTERN))
    validation: str | None = None
    headings = list(HEADING_PATTERN.finditer(text))
    for index, heading in enumerate(headings):
        if "validation" not in heading.group(2).casefold():
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        validation = text[heading.end() : end].strip() or None
        break
    return {
        "path": path.relative_to(root).as_posix(),
        "status": "valid" if error is None else "malformed",
        "error": error,
        "links": links,
        "validation_and_limitations": validation,
    }


def feature_audit(client: BeadsClient, selector: str) -> FeatureAuditView:
    view = feature_context(client, selector)
    root = view["root"]
    root_id = str(root["id"])
    current = bool(view.get("current"))
    classification = (
        "planned" if not current else "delivered" if root.get("status") == "closed" else "current"
    )
    metadata = {
        key: value
        for key, value in sorted(issue_metadata(root).items())
        if str(key).startswith("dstack.")
    }
    payload: dict[str, Any] = {
        "audit_version": 1,
        "kind": "feature",
        "classification": classification,
        "root": {
            **issue_fact(root),
            "description": str(root.get("description") or ""),
            "acceptance": str(root.get("acceptance_criteria") or root.get("acceptance") or ""),
            "metadata": metadata,
        },
        "lifecycle": {"current": current, "steps": {}, "approval": None},
        "design": {
            "path": None,
            "pending_sha256": None,
            "approved_sha256": None,
            "current_sha256": None,
            "head_sha256": None,
            "state": "not-materialized",
            "approved": False,
        },
        "work": {"items": [], "remaining_or_deferred": []},
        "git_evidence": {"status": "unavailable", "reason": "not-materialized"},
        "documentation": {
            "design": None,
            "reconciliation": None,
            "current_product_links": [],
            "related_adrs": [],
        },
        "delivery": {
            "root_status": str(root.get("status") or "unknown"),
            "direct_merge_observed": None,
            "pr_gates": [],
        },
        "missing_observations": [],
    }
    if not current:
        payload["missing_observations"] = [
            "stable lifecycle",
            "design",
            "worktree",
            "Git evidence",
            "delivery",
        ]
        return cast(FeatureAuditView, payload)

    design = feature_design_state(client, view)
    authorization = feature_authorization_state(client, view)
    view.update(design)
    view.update(authorization)
    steps = view["steps"]
    payload["lifecycle"] = {
        "current": True,
        "steps": {name: issue_fact(step) for name, step in sorted(steps.items())},
        "approval": {
            "states": authorization.get("authorization_states"),
            "human_gate": (
                {
                    "type": gate_type(authorization["human_gate"]),
                    "status": authorization["human_gate"].get("status"),
                    "await": authorization["human_gate"].get("await_id"),
                }
                if isinstance(authorization.get("human_gate"), Mapping)
                else None
            ),
            "native_approved": bool(authorization.get("native_approved")),
        },
    }
    payload["design"] = {
        "path": view.get("design_path"),
        "pending_sha256": view.get("pending_design_sha256"),
        "approved_sha256": view.get("approved_design_sha256"),
        "current_sha256": design.get("current_design_sha256"),
        "head_sha256": design.get("head_design_sha256"),
        "state": design.get("design_state"),
        "approved": bool(design.get("design_approved")),
    }

    implementation_id = str(steps["implementation"]["id"])
    items = [
        item
        for item in client.children(implementation_id)
        if has_label(item, "dstack:work:implementation")
        or issue_type(item) not in {"epic", "molecule", "gate"}
    ]
    items = sorted(items, key=lambda item: str(item.get("id") or ""))
    payload["work"] = {
        "items": [issue_fact(item) for item in items],
        "remaining_or_deferred": [
            issue_fact(item) for item in items if item.get("status") != "closed"
        ],
    }
    view["work_items"] = items

    slug = str(view.get("slug") or "")
    branch = f"feat/{slug}"
    base = str(view.get("base_branch") or "")
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None and root.get("status") != "closed":
        payload["missing_observations"].append("worktree")
        payload["git_evidence"] = {
            "status": "unavailable",
            "reason": "worktree-missing",
        }
    else:
        try:
            evidence = (
                delivered_feature_evidence_audit(client, view)
                if worktree is None
                else feature_evidence_audit(client, view)
            )
            payload["git_evidence"] = {
                key: value for key, value in evidence.items() if key != "feature"
            }
        except DstackError as exc:
            payload["git_evidence"] = {
                "status": "unavailable",
                "reason": str(exc),
            }

    record_root = worktree
    relative_design = str(view.get("design_path") or "")
    if (
        record_root is None
        and root.get("status") == "closed"
        and (client.root / relative_design).is_file()
    ):
        record_root = client.root
    if record_root is not None:
        design_path = record_root / relative_design
        reconciliation = design_path.with_name("index.md")
        design_record = record_fact(design_path, "feature-design", record_root)
        reconciliation_record = record_fact(
            reconciliation, "feature-reconciliation", record_root
        )
        links = sorted(
            set(design_record["links"]) | set(reconciliation_record["links"])
        )
        payload["documentation"] = {
            "design": design_record,
            "reconciliation": reconciliation_record,
            "current_product_links": [
                link for link in links if "design.md" not in link and "decisions/" not in link
            ],
            "related_adrs": [link for link in links if "decisions/" in link],
        }
        for name, record in (
            ("design", design_record),
            ("reconciliation", reconciliation_record),
        ):
            if record["status"] != "valid":
                payload["missing_observations"].append(
                    f"{name}:{record['status']}"
                )

    direct: bool | None = None
    if base and ref_exists(client.root, base) and ref_exists(client.root, branch):
        direct = ancestry(client.root, branch, base)
    delivery = cast(dict[str, Any], payload["delivery"])
    delivery["direct_merge_observed"] = direct
    try:
        gates = pr_gate_state(client, root_id)
        delivery["pr_gates"] = [
            {
                "type": gate_type(gate),
                "status": gate.get("status"),
                "await": gate.get("await_id"),
            }
            for gate in sorted(gates["all"], key=lambda gate: str(gate.get("id") or ""))
        ]
    except DstackError as exc:
        delivery["pr_gates"] = [{"status": "unavailable", "reason": str(exc)}]
    payload["missing_observations"] = sorted(set(payload["missing_observations"]))
    return cast(FeatureAuditView, payload)


def render_markdown(payload: Mapping[str, Any]) -> str:
    facts = json.dumps(payload, indent=2, sort_keys=True)
    title = str(payload["root"]["title"] or payload["root"]["id"])
    return f"# Feature audit: {title}\n\n```json\n{facts}\n```\n"


def cmd_audit_feature(args: argparse.Namespace) -> int:
    payload = feature_audit(client_for(args.root), args.selector)
    if args.format == "markdown":
        sys.stdout.write(render_markdown(payload))
    else:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0
