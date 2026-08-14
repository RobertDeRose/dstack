#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# ruff: noqa: EM101, EM102, S603
"""Build and verify a transient feature-review graph projection from Beads."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA = "dstack.beads-review-projection.v1"
LIFECYCLE_METADATA_KEYS = (
    "design_id",
    "review_specification_clarity_id",
    "review_execution_readiness_id",
    "spec_reconcile_id",
    "implementation_id",
    "docs_reconcile_id",
    "validation_id",
    "review_implementation_integrity_id",
    "review_delivery_integrity_id",
    "delivery_id",
)
Runner = Callable[..., object]


def run_json(command: list[str], *, cwd: Path) -> object:
    completed = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): item for key, item in parsed.items()}
    return {}


def issues(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("Beads returned a non-list issue payload")
    return [mapping(item) for item in value]


def first_issue(value: object, issue_id: str) -> dict[str, Any]:
    found = issues(value)
    if len(found) != 1 or str(found[0].get("id") or "") != issue_id:
        raise ValueError(f"Beads did not return exactly one issue for {issue_id}")
    return found[0]


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def markdown_section(text: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", text)
    return match.group(1).strip() if match else ""


def inferred_validation_commands(text: str) -> list[str]:
    prefixes = (
        "actionlint ",
        "cargo ",
        "git diff ",
        "go test ",
        "mdbook ",
        "mise ",
        "npm ",
        "pytest ",
        "python3 ",
        "ruff ",
        "ty ",
        "uv ",
    )
    return sorted({value for value in re.findall(r"`([^`\n]+)`", text) if value.startswith(prefixes)})


def node(issue: Mapping[str, Any]) -> dict[str, Any]:
    metadata = mapping(issue.get("metadata"))
    issue_id = str(issue.get("id") or "").strip()
    title = str(issue.get("title") or "").strip()
    description = str(issue.get("description") or "")
    if not issue_id or not title:
        raise ValueError("Every projected issue requires an ID and title")
    validation = metadata.get("validation_commands") or metadata.get("validation_command") or metadata.get("validation")
    return {
        "id": issue_id,
        "title": title,
        "status": str(issue.get("status") or ""),
        "issue_type": str(issue.get("issue_type") or issue.get("type") or ""),
        "parent": issue.get("parent"),
        "owner": issue.get("owner") or issue.get("assignee"),
        "description": description,
        "acceptance_criteria": str(issue.get("acceptance_criteria") or ""),
        "validation_commands": string_list(validation) or inferred_validation_commands(description),
        "commit_boundary": (
            metadata.get("commit_boundary")
            or metadata.get("owned_paths")
            or markdown_section(description, "Boundaries")
            or None
        ),
        "labels": sorted(string_list(issue.get("labels"))),
        "metadata": metadata,
    }


def edge_records(issue: Mapping[str, Any]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    raw = issue.get("dependencies") or []
    if not isinstance(raw, list):
        raise ValueError(f"Issue {issue.get('id')} has invalid dependencies")
    for dependency in raw:
        item = mapping(dependency)
        source = str(item.get("issue_id") or issue.get("id") or "").strip()
        target = str(item.get("depends_on_id") or item.get("id") or "").strip()
        kind = str(item.get("type") or item.get("dependency_type") or "").strip()
        if not source or not target or not kind:
            raise ValueError(f"Issue {issue.get('id')} has an incomplete dependency edge")
        records.append({"from": source, "to": target, "type": kind})
    return records


def validate_source_boundary(boundary: Mapping[str, Any]) -> dict[str, Any]:
    required = ("reviewed_commit", "reviewed_diff_base", "reviewed_diff_digest", "allowed_paths")
    if any(key not in boundary for key in required):
        raise ValueError("Source boundary is incomplete")
    for key in ("reviewed_commit", "reviewed_diff_base"):
        if re.fullmatch(r"[0-9a-f]{40,64}", str(boundary[key])) is None:
            raise ValueError(f"Invalid source revision: {key}")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", str(boundary["reviewed_diff_digest"])) is None:
        raise ValueError("Invalid reviewed diff digest")
    paths = string_list(boundary["allowed_paths"])
    for value in paths:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe allowed path: {value}")
    return {
        "reviewed_commit": str(boundary["reviewed_commit"]),
        "reviewed_diff_base": str(boundary["reviewed_diff_base"]),
        "reviewed_diff_digest": str(boundary["reviewed_diff_digest"]),
        "allowed_paths": sorted(paths),
    }


def digest(payload: Mapping[str, Any]) -> str:
    content = {key: value for key, value in payload.items() if key != "projection_digest"}
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_projection(
    *,
    repository_root: Path,
    root_id: str,
    source_boundary: Mapping[str, Any],
    runner: Runner = run_json,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    if re.fullmatch(r"[A-Za-z0-9._-]+", root_id) is None:
        raise ValueError("Invalid feature root ID")
    root_issue = first_issue(runner(["bd", "show", root_id, "--json"], cwd=repository_root), root_id)
    root_metadata = mapping(root_issue.get("metadata"))
    missing_metadata = [key for key in LIFECYCLE_METADATA_KEYS if not str(root_metadata.get(key) or "").strip()]
    if missing_metadata:
        raise ValueError(f"Feature root has incomplete lifecycle metadata: {', '.join(missing_metadata)}")
    lifecycle_ids = {key: str(root_metadata[key]).strip() for key in LIFECYCLE_METADATA_KEYS}
    if len(set(lifecycle_ids.values())) != len(lifecycle_ids):
        raise ValueError("Feature root repeats lifecycle issue IDs")
    implementation_id = lifecycle_ids["implementation_id"]

    lifecycle_issues = issues(
        runner(["bd", "list", "--parent", root_id, "--all", "--json", "--limit", "0"], cwd=repository_root)
    )
    lifecycle_by_id = {str(item.get("id") or ""): item for item in lifecycle_issues}
    if len(lifecycle_by_id) != len(lifecycle_issues):
        raise ValueError("Feature graph repeats a lifecycle issue ID")
    unresolved_lifecycle = sorted(set(lifecycle_ids.values()) - set(lifecycle_by_id))
    if unresolved_lifecycle:
        raise ValueError(f"Feature graph is missing lifecycle issues: {', '.join(unresolved_lifecycle)}")
    if any(str(lifecycle_by_id[item].get("parent") or "") != root_id for item in lifecycle_ids.values()):
        raise ValueError("Lifecycle issue parent does not match the feature root")
    coordinators = [lifecycle_by_id[implementation_id]]
    task_issues = issues(
        runner(
            ["bd", "list", "--parent", implementation_id, "--all", "--json", "--limit", "0"],
            cwd=repository_root,
        )
    )
    if not task_issues:
        raise ValueError("Feature graph has no implementation tasks")
    if any(str(item.get("parent") or "") != implementation_id for item in task_issues):
        raise ValueError("Implementation task parent does not match the coordinator")
    task_nodes = [node(item) for item in task_issues]
    required_task_fields = ("owner", "description", "acceptance_criteria", "validation_commands", "commit_boundary")
    incomplete_tasks = [item["id"] for item in task_nodes if any(not item[field] for field in required_task_fields)]
    if incomplete_tasks:
        raise ValueError(
            f"Implementation tasks have incomplete readiness fields: {', '.join(sorted(incomplete_tasks))}"
        )

    known = [root_issue, *lifecycle_issues, *task_issues]
    edges = [edge for item in known for edge in edge_records(item)]
    known_ids = {str(item.get("id") or "") for item in known}
    external_ids = sorted({edge["to"] for edge in edges} - known_ids)
    external = [first_issue(runner(["bd", "show", item, "--json"], cwd=repository_root), item) for item in external_ids]

    projection: dict[str, Any] = {
        "schema": SCHEMA,
        "root_id": root_id,
        "source_boundary": validate_source_boundary(source_boundary),
        "root": node(root_issue),
        "implementation_coordinator": node(coordinators[0]),
        "lifecycle": sorted(
            (node(item) for item in lifecycle_issues if str(item.get("id") or "") != implementation_id),
            key=lambda item: item["id"],
        ),
        "implementation_tasks": sorted(task_nodes, key=lambda item: item["id"]),
        "external_dependencies": sorted((node(item) for item in external), key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["from"], item["to"], item["type"])),
    }
    projected_ids = {
        projection["root"]["id"],
        projection["implementation_coordinator"]["id"],
        *(
            item["id"]
            for key in ("lifecycle", "implementation_tasks", "external_dependencies")
            for item in projection[key]
        ),
    }
    if any(edge["from"] not in projected_ids or edge["to"] not in projected_ids for edge in projection["edges"]):
        raise ValueError("Projection contains an unresolved dependency vertex")
    projection["projection_digest"] = digest(projection)
    return projection


def verify_projection(
    projection: Mapping[str, Any], *, repository_root: Path, runner: Runner = run_json
) -> dict[str, Any]:
    if projection.get("schema") != SCHEMA or projection.get("projection_digest") != digest(projection):
        raise ValueError("Projection schema or digest is invalid")
    current = build_projection(
        repository_root=repository_root,
        root_id=str(projection.get("root_id") or ""),
        source_boundary=mapping(projection.get("source_boundary")),
        runner=runner,
    )
    if current != dict(projection):
        raise ValueError("Projection is stale relative to current Beads authority")
    return current


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--root-id")
    parser.add_argument("--reviewed-commit")
    parser.add_argument("--reviewed-diff-base")
    parser.add_argument("--reviewed-diff-digest")
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repository_root.expanduser().resolve()
    if args.verify:
        projection = verify_projection(json.loads(args.verify.read_text(encoding="utf-8")), repository_root=root)
    else:
        if not all((args.root_id, args.reviewed_commit, args.reviewed_diff_base, args.reviewed_diff_digest)):
            raise SystemExit("New projections require root and complete source-boundary arguments")
        projection = build_projection(
            repository_root=root,
            root_id=args.root_id,
            source_boundary={
                "reviewed_commit": args.reviewed_commit,
                "reviewed_diff_base": args.reviewed_diff_base,
                "reviewed_diff_digest": args.reviewed_diff_digest,
                "allowed_paths": args.allowed_path,
            },
        )
    text = json.dumps(projection, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
