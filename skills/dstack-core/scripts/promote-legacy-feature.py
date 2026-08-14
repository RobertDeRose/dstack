#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# ruff: noqa: EM101, EM102, S603
"""Attach the canonical formula lifecycle to an existing roadmap feature root."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "dstack.legacy-feature-promotion.v1"
PROMOTION_SCHEMA = "dstack.legacy-feature-promotion-state.v1"
ROOT_STEP_METADATA = {
    "design": "design_id",
    "review-architecture": "review_architecture_id",
    "review-simplicity": "review_simplicity_id",
    "review-documentation": "review_documentation_id",
    "review-execution": "review_execution_id",
    "spec-reconcile": "spec_reconcile_id",
    "implementation": "implementation_id",
    "docs-reconcile": "docs_reconcile_id",
    "validate": "validation_id",
    "review-delivery": "review_delivery_id",
    "review-drift": "review_drift_id",
    "delivery": "delivery_id",
}
Runner = Callable[..., object]


def run_json(command: list[str], *, cwd: Path) -> object:
    completed = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout) if completed.stdout.strip() else None


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


def issue_list(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [mapping(item) for item in values]


def one_issue(value: object, expected_id: str | None = None) -> dict[str, Any]:
    found = issue_list(value)
    if len(found) != 1:
        raise ValueError("Expected exactly one Beads issue")
    if expected_id is not None and str(found[0].get("id") or "") != expected_id:
        raise ValueError(f"Expected Beads issue {expected_id}")
    return found[0]


def substitute(value: str, variables: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise ValueError(f"Formula references unknown variable {key}")
        return variables[key]

    return re.sub(r"{{\s*([a-zA-Z0-9_]+)\s*}}", replace, value)


def metadata(value: object, variables: Mapping[str, str]) -> dict[str, object]:
    return {key: substitute(str(item), variables) for key, item in mapping(value).items()}


def promotion_digest(formula_bytes: bytes, plan: Mapping[str, Any]) -> str:
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(formula_bytes + b"\0" + encoded).hexdigest()


def validate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != SCHEMA:
        raise ValueError(f"Expected promotion plan schema {SCHEMA}")
    required = (
        "feature_name",
        "feature_slug",
        "design_path",
        "implemented_path",
        "base_branch",
        "implementation_repository",
        "implementation_path",
        "implementation_tasks",
    )
    if any(not plan.get(key) for key in required):
        raise ValueError("Promotion plan identity or task list is incomplete")
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(plan["feature_slug"])) is None:
        raise ValueError("Promotion feature slug is invalid")
    tasks = plan["implementation_tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Promotion requires implementation tasks")
    task_keys: list[str] = []
    for task_value in tasks:
        task = mapping(task_value)
        fields = (
            "task_key",
            "title",
            "description",
            "acceptance_criteria",
            "owner",
            "validation_commands",
            "commit_boundary",
        )
        if any(not task.get(field) for field in fields):
            raise ValueError("Promotion implementation task is incomplete")
        task_keys.append(str(task["task_key"]))
    if len(task_keys) != len(set(task_keys)):
        raise ValueError("Promotion repeats an implementation task key")
    known = set(task_keys)
    dependencies: dict[str, set[str]] = {}
    for task_value in tasks:
        task = mapping(task_value)
        task_key = str(task["task_key"])
        needs = task.get("needs") or []
        if not isinstance(needs, list) or any(str(item) not in known for item in needs):
            raise ValueError("Promotion task has an invalid dependency")
        dependencies[task_key] = {str(item) for item in needs}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_key: str) -> None:
        if task_key in visiting:
            raise ValueError("Promotion implementation task dependencies contain a cycle")
        if task_key in visited:
            return
        visiting.add(task_key)
        for dependency in dependencies[task_key]:
            visit(dependency)
        visiting.remove(task_key)
        visited.add(task_key)

    for task_key in task_keys:
        visit(task_key)
    return dict(plan)


def create_issue(
    *,
    repository_root: Path,
    title: str,
    issue_type: str,
    priority: object,
    parent: str,
    labels: list[str],
    description: str,
    issue_metadata: Mapping[str, object],
    runner: Runner,
    acceptance: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    command = [
        "bd",
        "create",
        title,
        "--type",
        issue_type,
        "--priority",
        str(priority),
        "--parent",
        parent,
        "--labels",
        ",".join(labels),
        "--description",
        description,
        "--metadata",
        json.dumps(issue_metadata, separators=(",", ":")),
        "--json",
    ]
    if acceptance:
        command.extend(("--acceptance", acceptance))
    if owner:
        command.extend(("--assignee", owner))
    return one_issue(runner(command, cwd=repository_root))


def dependency_ids(issue: Mapping[str, Any]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    raw = issue.get("dependencies") or []
    if not isinstance(raw, list):
        raise ValueError("Issue dependencies are invalid")
    for value in raw:
        item = mapping(value)
        target = str(item.get("depends_on_id") or item.get("id") or "")
        kind = str(item.get("type") or item.get("dependency_type") or "")
        if target and kind:
            result.add((target, kind))
    return result


def add_dependency(*, repository_root: Path, issue_id: str, target_id: str, kind: str, runner: Runner) -> None:
    current = one_issue(runner(["bd", "show", issue_id, "--json"], cwd=repository_root), issue_id)
    if (target_id, kind) not in dependency_ids(current):
        runner(["bd", "dep", "add", issue_id, target_id, "--type", kind, "--json"], cwd=repository_root)


def indexed_children(children: Sequence[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for child in children:
        value = str(mapping(child.get("metadata")).get(key) or "")
        if not value:
            continue
        if value in result:
            raise ValueError(f"Promotion repeats {key} {value}")
        result[value] = dict(child)
    return result


def promote_existing_root(
    *,
    repository_root: Path,
    root_id: str,
    formula_path: Path,
    plan: Mapping[str, Any],
    runner: Runner = run_json,
) -> dict[str, Any]:
    root = repository_root.expanduser().resolve()
    if re.fullmatch(r"[A-Za-z0-9._-]+", root_id) is None:
        raise ValueError("Invalid legacy root ID")
    validated_plan = validate_plan(plan)
    formula_bytes = formula_path.read_bytes()
    formula = tomllib.loads(formula_bytes.decode())
    steps = formula.get("steps")
    if not isinstance(steps, list) or {str(mapping(step).get("id") or "") for step in steps} != set(ROOT_STEP_METADATA):
        raise ValueError("Formula does not contain the canonical lifecycle steps")
    digest = promotion_digest(formula_bytes, validated_plan)
    root_issue = one_issue(runner(["bd", "show", root_id, "--json"], cwd=root), root_id)
    if str(root_issue.get("issue_type") or "") != "epic" or "workflow:feature" not in (root_issue.get("labels") or []):
        raise ValueError("Selected root is not a workflow feature epic")
    root_metadata = mapping(root_issue.get("metadata"))
    expected_identity = {
        key: str(validated_plan[key])
        for key in (
            "feature_name",
            "feature_slug",
            "design_path",
            "implemented_path",
            "base_branch",
            "implementation_repository",
            "implementation_path",
        )
    }
    conflicts = sorted(
        key for key, expected in expected_identity.items() if root_metadata.get(key) not in (None, "", expected)
    )
    existing_spec = str(root_issue.get("spec_id") or "")
    if existing_spec and existing_spec != expected_identity["design_path"]:
        conflicts.append("spec_id")
    if conflicts:
        raise ValueError(f"Legacy root identity conflicts with promotion plan: {', '.join(conflicts)}")
    prior_digest = str(root_metadata.get("legacy_promotion_digest") or "")
    if prior_digest and prior_digest != digest:
        raise ValueError("Legacy promotion plan changed after lifecycle creation")

    variables = {
        key: str(validated_plan[key])
        for key in ("feature_name", "feature_slug", "design_path", "implemented_path", "base_branch")
    }
    children = issue_list(runner(["bd", "list", "--parent", root_id, "--all", "--json", "--limit", "0"], cwd=root))
    step_issues = indexed_children(children, "promotion_step_id")
    if prior_digest == digest:
        if set(step_issues) != set(ROOT_STEP_METADATA):
            raise ValueError("Recorded legacy promotion is missing lifecycle children")
        if any(
            str(root_metadata.get(metadata_key) or "") != str(step_issues[step_id].get("id") or "")
            for step_id, metadata_key in ROOT_STEP_METADATA.items()
        ):
            raise ValueError("Recorded legacy promotion lifecycle metadata is stale")
        implementation_id = str(step_issues["implementation"]["id"])
        task_children = issue_list(
            runner(["bd", "list", "--parent", implementation_id, "--all", "--json", "--limit", "0"], cwd=root)
        )
        task_issues = indexed_children(task_children, "task_key")
        expected_task_keys = {str(mapping(item)["task_key"]) for item in validated_plan["implementation_tasks"]}
        if set(task_issues) != expected_task_keys:
            raise ValueError("Recorded legacy promotion implementation tasks are stale")
        return {
            "schema": PROMOTION_SCHEMA,
            "root_id": root_id,
            "promotion_digest": digest,
            "lifecycle": {key: str(step_issues[key]["id"]) for key in ROOT_STEP_METADATA},
            "implementation_tasks": {key: str(value["id"]) for key, value in task_issues.items()},
        }
    unowned_lifecycle = [
        item
        for item in children
        if "workflow:feature-lifecycle" in (item.get("labels") or [])
        and not mapping(item.get("metadata")).get("promotion_step_id")
    ]
    if unowned_lifecycle and not prior_digest:
        raise ValueError("Legacy root already has lifecycle children not owned by this promotion")

    for raw_step in steps:
        step = mapping(raw_step)
        step_id = str(step["id"])
        if step_id in step_issues:
            continue
        step_metadata = metadata(step.get("metadata"), variables)
        step_metadata["promotion_step_id"] = step_id
        step_issues[step_id] = create_issue(
            repository_root=root,
            title=substitute(str(step["title"]), variables),
            issue_type="task" if str(step["type"]) == "human" else str(step["type"]),
            priority=step.get("priority", 2),
            parent=root_id,
            labels=[str(item) for item in step.get("labels") or []],
            description=substitute(str(step.get("description") or ""), variables).strip(),
            issue_metadata=step_metadata,
            runner=runner,
        )

    implementation_id = str(step_issues["implementation"]["id"])
    task_children = issue_list(
        runner(["bd", "list", "--parent", implementation_id, "--all", "--json", "--limit", "0"], cwd=root)
    )
    task_issues = indexed_children(task_children, "task_key")
    for task_value in validated_plan["implementation_tasks"]:
        task = mapping(task_value)
        task_key = str(task["task_key"])
        if task_key in task_issues:
            continue
        task_metadata = {
            "task_key": task_key,
            "validation_commands": task["validation_commands"],
            "commit_boundary": task["commit_boundary"],
        }
        task_issues[task_key] = create_issue(
            repository_root=root,
            title=str(task["title"]),
            issue_type="task",
            priority=task.get("priority", 2),
            parent=implementation_id,
            labels=[str(item) for item in task.get("labels") or []],
            description=str(task["description"]),
            acceptance=str(task["acceptance_criteria"]),
            owner=str(task["owner"]),
            issue_metadata=task_metadata,
            runner=runner,
        )

    for raw_step in steps:
        step = mapping(raw_step)
        issue_id = str(step_issues[str(step["id"])]["id"])
        for dependency in step.get("needs") or []:
            add_dependency(
                repository_root=root,
                issue_id=issue_id,
                target_id=str(step_issues[str(dependency)]["id"]),
                kind="blocks",
                runner=runner,
            )
    for task_value in validated_plan["implementation_tasks"]:
        task = mapping(task_value)
        issue_id = str(task_issues[str(task["task_key"])]["id"])
        for dependency in task.get("needs") or []:
            add_dependency(
                repository_root=root,
                issue_id=issue_id,
                target_id=str(task_issues[str(dependency)]["id"]),
                kind="blocks",
                runner=runner,
            )

    promoted_metadata = {
        "feature_name": variables["feature_name"],
        "feature_slug": variables["feature_slug"],
        "design_path": variables["design_path"],
        "implemented_path": variables["implemented_path"],
        "base_branch": variables["base_branch"],
        "implementation_repository": str(validated_plan["implementation_repository"]),
        "implementation_path": str(validated_plan["implementation_path"]),
        "workflow_kind": "parent-child",
        "legacy_promotion_schema": PROMOTION_SCHEMA,
        "legacy_promotion_digest": digest,
        **{metadata_key: str(step_issues[step_id]["id"]) for step_id, metadata_key in ROOT_STEP_METADATA.items()},
    }
    command = ["bd", "update", root_id, "--spec-id", variables["design_path"]]
    for key, value in promoted_metadata.items():
        command.extend(("--set-metadata", f"{key}={value}"))
    command.append("--json")
    runner(command, cwd=root)
    return {
        "schema": PROMOTION_SCHEMA,
        "root_id": root_id,
        "promotion_digest": digest,
        "lifecycle": {key: str(step_issues[key]["id"]) for key in ROOT_STEP_METADATA},
        "implementation_tasks": {key: str(value["id"]) for key, value in task_issues.items()},
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--root-id", required=True)
    parser.add_argument("--formula", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = promote_existing_root(
        repository_root=args.repository_root,
        root_id=args.root_id,
        formula_path=args.formula.expanduser().resolve(),
        plan=json.loads(args.plan.read_text(encoding="utf-8")),
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
