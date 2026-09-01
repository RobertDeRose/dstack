#!/usr/bin/env python3
"""Read-only, stateless audit views over live Beads, Git, and mdBook facts."""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
from collections import deque
from pathlib import Path
from typing import Any, Mapping, cast
from urllib.parse import unquote, urlsplit

from .commands import client_for
from .delivery import (
    delivered_feature_evidence_audit,
    feature_evidence_audit,
    pr_gate_state,
)
from .docs import HEADING_PATTERN, LINK_PATTERN, markdown_values, validate_record
from .models import FeatureAuditView
from .core import (
    BeadsClient,
    DstackError,
    ancestry,
    dependency_records,
    feature_authorization_state,
    feature_context,
    feature_design_state,
    feature_view,
    gate_type,
    has_label,
    issue_labels,
    issue_metadata,
    issue_parent,
    issue_type,
    git_blob_text,
    git_file_sha256,
    ref_exists,
    safe_repository_path,
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


def record_fact_text(
    relative_path: str,
    text: str | None,
    kind: str | None = None,
    *,
    source: Path | None = None,
    source_root: Path | None = None,
) -> dict[str, Any]:
    if text is None:
        return {
            "path": relative_path,
            "status": "missing",
            "links": [],
            "validation_and_limitations": None,
        }
    error: str | None = None
    if kind is not None:
        try:
            validate_record(text, kind, source=source, source_root=source_root)
        except DstackError as exc:
            error = str(exc)
    links = sorted(markdown_values(text, LINK_PATTERN))
    validation: str | None = None
    headings = list(HEADING_PATTERN.finditer(text))
    for index, heading in enumerate(headings):
        if "validation" not in heading.group(2).casefold():
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        validation = text[heading.end() : end].strip() or None
        break
    return {
        "path": relative_path,
        "status": "valid" if error is None else "malformed",
        "error": error,
        "links": links,
        "validation_and_limitations": validation,
    }


def record_fact(path: Path, kind: str, root: Path) -> dict[str, Any]:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise DstackError(f"documentation path escapes the worktree: {path}") from exc
    safe = safe_repository_path(root, relative, purpose="feature documentation path")
    text = safe.read_text(encoding="utf-8") if safe.is_file() else None
    return record_fact_text(relative, text, kind, source=safe, source_root=root)


_MARKDOWN_SUFFIXES = {".md", ".mdx", ".markdown", ".rst"}


def _is_markdown_path(path: str) -> bool:
    return Path(path).suffix.casefold() in _MARKDOWN_SUFFIXES


def revision_records(
    root: Path, revision: str, paths: Mapping[str, str | None]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Read linked documentation blobs from one immutable revision."""

    records: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    pending = deque(paths.items())
    while pending:
        path, kind = pending.popleft()
        if path in records:
            continue
        if not _is_markdown_path(path):
            if git_file_sha256(root, path, revision) is None:
                missing.append(path)
            else:
                records[path] = {
                    "path": path,
                    "status": "asset",
                    "links": [],
                    "validation_and_limitations": None,
                }
            continue
        text = git_blob_text(root, path, revision)
        record = record_fact_text(path, text, kind)
        records[path] = record
        if text is None:
            missing.append(path)
            continue
        for raw in record["links"]:
            target = raw.strip()
            if target.startswith("<") and ">" in target:
                target = target[1 : target.index(">")]
            else:
                target = target.split(maxsplit=1)[0]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            linked = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(parsed.path)))
            if linked.startswith("../") or linked.startswith("/"):
                missing.append(f"invalid-link:{path}->{target}")
                continue
            pending.append((linked, None))
    return records, sorted(missing)


def _feature_audit_verbose(client: BeadsClient, selector: str) -> FeatureAuditView:
    view = feature_context(client, selector)
    root = view["root"]
    root_id = str(root["id"])
    current = bool(view.get("current"))
    classification = "planned" if not current else "delivered" if root.get("status") == "closed" else "current"
    metadata = {key: value for key, value in sorted(issue_metadata(root).items()) if str(key).startswith("dstack.")}
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
        if has_label(item, "dstack:work:implementation") or issue_type(item) not in {"epic", "molecule", "gate"}
    ]
    items = sorted(items, key=lambda item: str(item.get("id") or ""))
    payload["work"] = {
        "items": [issue_fact(item) for item in items],
        "remaining_or_deferred": [issue_fact(item) for item in items if item.get("status") != "closed"],
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
                if root.get("status") == "closed"
                else feature_evidence_audit(client, view)
            )
            payload["git_evidence"] = {key: value for key, value in evidence.items() if key != "feature"}
        except DstackError as exc:
            payload["git_evidence"] = {
                "status": "unavailable",
                "reason": str(exc),
                "search_ref": base,
                "candidate_revision": None,
                "derivation": "latest reachable closeout Beads footer",
                "evidence_source": None,
            }

    relative_design = str(view.get("design_path") or "")
    git_evidence = cast(dict[str, Any], payload["git_evidence"])
    candidate_revision = git_evidence.get("candidate_revision")
    if candidate_revision:
        relative_reconciliation = str(Path(relative_design).with_name("index.md"))
        records, missing_records = revision_records(
            client.root,
            str(candidate_revision),
            {
                relative_design: "feature-design",
                relative_reconciliation: "feature-reconciliation",
            },
        )
        design_record = records[relative_design]
        reconciliation_record = records[relative_reconciliation]
        linked_records = {
            path: record for path, record in records.items() if path not in {relative_design, relative_reconciliation}
        }
        links = sorted(set(design_record["links"]) | set(reconciliation_record["links"]))
        payload["documentation"] = {
            "source": str(candidate_revision),
            "design": design_record,
            "reconciliation": reconciliation_record,
            "reconciliation_status": reconciliation_record["status"],
            "linked_records": linked_records,
            "missing_records": missing_records,
            "current_product_links": [link for link in links if "design.md" not in link and "decisions/" not in link],
            "related_adrs": [link for link in links if "decisions/" in link],
        }
        for name, record in (
            ("design", design_record),
            ("reconciliation", reconciliation_record),
        ):
            if record["status"] != "valid":
                payload["missing_observations"].append(f"{name}:{record['status']}")
        payload["missing_observations"].extend(f"record:{path}" for path in missing_records)
        if missing_records:
            git_evidence["status"] = "issues"
            git_evidence["missing_records"] = missing_records
    elif worktree is not None and root.get("status") != "closed":
        design_path = safe_repository_path(worktree, relative_design, purpose="feature design path")
        reconciliation = safe_repository_path(
            worktree,
            Path(relative_design).with_name("index.md"),
            purpose="feature reconciliation path",
        )
        design_record = record_fact(design_path, "feature-design", worktree)
        reconciliation_record = record_fact(reconciliation, "feature-reconciliation", worktree)
        links = sorted(set(design_record["links"]) | set(reconciliation_record["links"]))
        payload["documentation"] = {
            "design": design_record,
            "reconciliation": reconciliation_record,
            "reconciliation_status": reconciliation_record["status"],
            "current_product_links": [link for link in links if "design.md" not in link and "decisions/" not in link],
            "related_adrs": [link for link in links if "decisions/" in link],
        }
        for name, record in (
            ("design", design_record),
            ("reconciliation", reconciliation_record),
        ):
            if record["status"] != "valid":
                payload["missing_observations"].append(f"{name}:{record['status']}")
    elif root.get("status") == "closed":
        payload["missing_observations"].append("documentation:immutable-source-unavailable")

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


def feature_audit(client: BeadsClient, selector: str, *, verbose: bool = False) -> dict[str, Any]:
    """Return native feature identity/Git facts by default; expose full audit facts explicitly."""

    if not verbose:
        return feature_view(client, selector)
    return dict(_feature_audit_verbose(client, selector))


def render_markdown(payload: Mapping[str, Any]) -> str:
    facts = json.dumps(payload, indent=2, sort_keys=True)
    root = payload.get("root")
    if isinstance(root, Mapping):
        title = str(root.get("title") or root.get("id") or "feature")
    else:
        title = "feature"
    return f"# Feature audit: {title}\n\n```json\n{facts}\n```\n"


def cmd_audit_feature(args: argparse.Namespace) -> int:
    client = client_for(args.root, initialize=False)
    payload = (
        feature_audit(client, args.selector, verbose=True)
        if getattr(args, "verbose", False)
        else feature_audit(client, args.selector)
    )
    if args.format == "markdown":
        sys.stdout.write(render_markdown(payload))
    else:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0
