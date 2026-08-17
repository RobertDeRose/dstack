#!/usr/bin/env python3
"""Small stateful Beads CLI double for deterministic dStack tests.

It models only the supported Beads primitives used by dStack. Real-Beads
integration tests remain the release authority.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable

STATE_ENV = "DSTACK_FAKE_BD_STATE"


def state_path() -> Path:
    return Path(os.environ[STATE_ENV])


def initial_state() -> dict[str, Any]:
    return {"next_id": 1, "issues": {}, "comments": {}, "relations": []}


def load() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        state = initial_state()
        save(state)
        return state
    return json.loads(path.read_text())


def save(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def new_id(state: dict[str, Any]) -> str:
    issue_id = f"bd-{state['next_id']}"
    state["next_id"] += 1
    return issue_id


def values(args: list[str], flag: str) -> list[str]:
    result: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == flag and i + 1 < len(args):
            result.append(args[i + 1])
            i += 2
            continue
        if arg.startswith(flag + "="):
            result.append(arg.split("=", 1)[1])
        i += 1
    return result


def value(args: list[str], flag: str, default: str | None = None) -> str | None:
    found = values(args, flag)
    return found[-1] if found else default


def csv_values(args: list[str], flag: str) -> list[str]:
    result: list[str] = []
    for raw in values(args, flag):
        result.extend(item.strip() for item in raw.split(",") if item.strip())
    return result


def envelope(payload: Any) -> Any:
    if os.environ.get("BD_JSON_ENVELOPE") == "1":
        return {"schema_version": 1, "data": payload}
    return payload


def emit(payload: Any) -> None:
    print(json.dumps(envelope(payload), indent=2, sort_keys=True))


def item(state: dict[str, Any], issue_id: str) -> dict[str, Any]:
    try:
        return state["issues"][issue_id]
    except KeyError as exc:
        raise RuntimeError(f"issue not found: {issue_id}") from exc


def labels(issue: dict[str, Any]) -> list[str]:
    return issue.setdefault("labels", [])


def parent(issue: dict[str, Any]) -> str | None:
    return issue.get("parent")


def children(state: dict[str, Any], parent_id: str) -> list[dict[str, Any]]:
    return [issue for issue in state["issues"].values() if parent(issue) == parent_id]


def descendants(state: dict[str, Any], root_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    queue = [root_id]
    seen = {root_id}
    while queue:
        current = queue.pop(0)
        for child in children(state, current):
            if child["id"] in seen:
                continue
            seen.add(child["id"])
            result.append(child)
            queue.append(child["id"])
    return result


def dependency_records(issue: dict[str, Any]) -> list[dict[str, Any]]:
    result = [
        {
            "issue_id": issue["id"],
            "depends_on_id": dependency,
            "type": "blocks",
        }
        for dependency in issue.get("dependencies", [])
    ]
    if issue.get("parent"):
        result.append(
            {
                "issue_id": issue["id"],
                "depends_on_id": issue["parent"],
                "type": "parent-child",
            }
        )
    result.extend(
        {
            "issue_id": issue["id"],
            "depends_on_id": relation["to"],
            "type": relation["type"],
        }
        for relation in issue.get("relations", [])
    )
    return result


def serialize(state: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    result = dict(issue)
    result["issue_type"] = result.get("type", "task")
    result["dependencies"] = dependency_records(issue)
    result["dependency_count"] = sum(
        1 for dep in issue.get("dependencies", []) if item(state, dep)["status"] != "closed"
    )
    result["dependent_count"] = sum(
        1 for candidate in state["issues"].values() if issue["id"] in candidate.get("dependencies", [])
    )
    result["comment_count"] = len(state["comments"].get(issue["id"], []))
    if issue.get("parent"):
        result["parent"] = issue["parent"]
    return result


def blocked(state: dict[str, Any], issue: dict[str, Any]) -> list[str]:
    blockers = [
        dep
        for dep in issue.get("dependencies", [])
        if item(state, dep).get("status") != "closed"
    ]
    waits_for = issue.get("waits_for")
    if isinstance(waits_for, str):
        match = re.fullmatch(r"children-of\(([^)]+)\)", waits_for)
        if match:
            blockers.extend(
                child["id"]
                for child in children(state, match.group(1))
                if child.get("status") != "closed"
                and child.get("type") not in {"gate", "molecule", "epic"}
            )
    return list(dict.fromkeys(blockers))


def ready(state: dict[str, Any], issue: dict[str, Any]) -> bool:
    return (
        issue.get("status") == "open"
        and issue.get("type") not in {"gate", "molecule"}
        and not blocked(state, issue)
    )


def substitute(value_: Any, variables: dict[str, str]) -> Any:
    if isinstance(value_, str):
        result = value_
        for key, replacement in variables.items():
            result = result.replace("{{" + key + "}}", replacement)
        return result
    if isinstance(value_, list):
        return [substitute(item_, variables) for item_ in value_]
    if isinstance(value_, dict):
        return {key: substitute(item_, variables) for key, item_ in value_.items()}
    return value_


def formula_path(cwd: Path, name: str) -> Path:
    path = cwd / ".beads" / "formulas" / f"{name}.formula.toml"
    if not path.is_file():
        raise RuntimeError(f"formula not found: {name}")
    return path


def load_formula(cwd: Path, name: str, args: list[str]) -> dict[str, Any]:
    variables: dict[str, str] = {}
    for raw in values(args, "--var"):
        key, sep, val = raw.partition("=")
        if not sep:
            raise RuntimeError(f"invalid variable: {raw}")
        variables[key] = val
    return substitute(tomllib.loads(formula_path(cwd, name).read_text()), variables)


def is_epic(step: dict[str, Any]) -> bool:
    return step.get("type", "task") == "epic" or bool(step.get("children"))


def validate_formula(formula: dict[str, Any]) -> None:
    steps = formula.get("steps", [])
    by_id = {step["id"]: step for step in steps}
    for dependent in steps:
        for blocker_id in [*dependent.get("needs", []), *dependent.get("depends_on", [])]:
            blocker = by_id.get(blocker_id)
            if blocker is None:
                raise RuntimeError(f"unknown formula dependency: {blocker_id}")
            if is_epic(dependent) != is_epic(blocker):
                if is_epic(dependent):
                    raise RuntimeError("epics can only block other epics, not tasks")
                raise RuntimeError("tasks can only block other tasks, not epics")
        if dependent.get("gate") and is_epic(dependent):
            raise RuntimeError("epics can only block other epics, not tasks")


def pour(cwd: Path, state: dict[str, Any], name: str, args: list[str]) -> dict[str, Any]:
    formula = load_formula(cwd, name, args)
    validate_formula(formula)
    root_id = new_id(state)
    root = {
        "id": root_id,
        "title": formula.get("formula", name),
        "description": formula.get("description", ""),
        "type": "molecule",
        "status": "open",
        "parent": None,
        "labels": [],
        "metadata": {},
        "dependencies": [],
        "relations": [],
    }
    state["issues"][root_id] = root
    step_ids = {step["id"]: new_id(state) for step in formula.get("steps", [])}
    for step in formula.get("steps", []):
        waits_for = step.get("waits_for")
        if isinstance(waits_for, str):
            match = re.fullmatch(r"children-of\(([^)]+)\)", waits_for)
            if match:
                waits_for = f"children-of({step_ids[match.group(1)]})"
        state["issues"][step_ids[step["id"]]] = {
            "id": step_ids[step["id"]],
            "formula_step_id": step["id"],
            "title": step["title"],
            "description": step.get("description", ""),
            "type": step.get("type", "task"),
            "status": "open",
            "priority": step.get("priority", 2),
            "parent": root_id,
            "labels": step.get("labels", []),
            "metadata": step.get("metadata", {}),
            "dependencies": [step_ids[item_] for item_ in [*step.get("needs", []), *step.get("depends_on", [])]],
            "relations": [],
            "waits_for": waits_for,
        }
    for step in formula.get("steps", []):
        gate = step.get("gate")
        if not gate:
            continue
        gate_id = new_id(state)
        target = state["issues"][step_ids[step["id"]]]
        state["issues"][gate_id] = {
            "id": gate_id,
            "title": f"Gate: {gate['type']}",
            "type": "gate",
            "status": "open",
            "parent": root_id,
            "labels": [],
            "metadata": {},
            "dependencies": [],
            "relations": [],
            "await_type": gate["type"],
            "await_id": gate.get("id", ""),
            "waiter_id": target["id"],
        }
        target["dependencies"].append(gate_id)
    save(state)
    return {"root_id": root_id}


def cmd_formula(args: list[str], cwd: Path) -> int:
    if args[0] != "show":
        raise RuntimeError("unsupported formula command")
    emit(load_formula(cwd, args[1], args[2:]))
    return 0


def cmd_mol(args: list[str], cwd: Path, state: dict[str, Any]) -> int:
    sub = args[0]
    if sub == "seed":
        formula = load_formula(cwd, args[1], args[2:])
        validate_formula(formula)
        emit({"status": "ok", "formula": args[1]})
        return 0
    if sub == "pour":
        emit(pour(cwd, state, args[1], args[2:]))
        return 0
    if sub in {"progress", "current"}:
        root_id = args[1]
        items = descendants(state, root_id)
        emit(
            {
                "root_id": root_id,
                "total": len(items),
                "closed": sum(one.get("status") == "closed" for one in items),
                "ready": [one["id"] for one in items if ready(state, one)],
            }
        )
        return 0
    raise RuntimeError(f"unsupported mol command: {sub}")


def cmd_show(args: list[str], state: dict[str, Any]) -> int:
    emit([serialize(state, item(state, args[0]))])
    return 0


def cmd_list(args: list[str], state: dict[str, Any]) -> int:
    issues = list(state["issues"].values())
    if "--all" not in args:
        issues = [one for one in issues if one.get("status") != "closed"]
    if "--include-templates" not in args:
        issues = [one for one in issues if not one.get("is_template")]
    if "--include-gates" not in args:
        issues = [one for one in issues if one.get("type") != "gate"]
    if (parent_id := value(args, "--parent")) is not None:
        issues = [one for one in issues if one.get("parent") == parent_id]
    if (kind := value(args, "--type")) is not None:
        issues = [one for one in issues if one.get("type") == kind]
    required = set(csv_values(args, "--label"))
    if required:
        issues = [one for one in issues if required <= set(one.get("labels", []))]
    excluded = set(csv_values(args, "--exclude-label"))
    if excluded:
        issues = [one for one in issues if not excluded.intersection(one.get("labels", []))]
    limit = int(value(args, "--limit", "50") or "50")
    issues = sorted(issues, key=lambda one: one["id"])
    if limit > 0:
        issues = issues[:limit]
    emit([serialize(state, one) for one in issues])
    return 0


def cmd_update(args: list[str], state: dict[str, Any]) -> int:
    issue = item(state, args[0])
    rest = args[1:]
    if (title := value(rest, "--title")) is not None:
        issue["title"] = title
    if (status := value(rest, "--status")) is not None:
        issue["status"] = status
    if "--claim" in rest and issue["status"] == "open":
        if blocked(state, issue):
            raise RuntimeError(f"issue is blocked: {issue['id']}")
        issue["status"] = "in_progress"
        issue["assignee"] = "test-agent"
    if (new_parent := value(rest, "--parent")) is not None:
        issue["parent"] = new_parent or None
    for label in csv_values(rest, "--add-label"):
        if label not in labels(issue):
            labels(issue).append(label)
    for label in csv_values(rest, "--remove-label"):
        issue["labels"] = [existing for existing in labels(issue) if existing != label]
    set_labels = csv_values(rest, "--set-labels")
    if set_labels:
        issue["labels"] = set_labels
    for raw in values(rest, "--set-metadata"):
        key, sep, val = raw.partition("=")
        if not sep:
            raise RuntimeError(f"invalid metadata: {raw}")
        issue.setdefault("metadata", {})[key] = val
    for key in values(rest, "--unset-metadata"):
        issue.setdefault("metadata", {}).pop(key, None)
    if (metadata := value(rest, "--metadata")) is not None:
        if metadata.startswith("@"):
            metadata = Path(metadata[1:]).read_text()
        issue["metadata"] = json.loads(metadata)
    save(state)
    emit([serialize(state, issue)])
    return 0


def validate_dependency_kinds(state: dict[str, Any], kind: str, deps: Iterable[str]) -> None:
    for dep in deps:
        dep_kind = item(state, dep).get("type")
        if (kind == "epic") != (dep_kind == "epic"):
            if kind == "epic":
                raise RuntimeError("epics can only block other epics, not tasks")
            raise RuntimeError("tasks can only block other tasks, not epics")


def cmd_create(args: list[str], state: dict[str, Any]) -> int:
    title = args[0]
    rest = args[1:]
    kind = value(rest, "--type", "task") or "task"
    deps = csv_values(rest, "--deps")
    validate_dependency_kinds(state, kind, deps)
    issue_id = new_id(state)
    issue = {
        "id": issue_id,
        "title": title,
        "description": value(rest, "--description", "") or "",
        "acceptance_criteria": value(rest, "--acceptance", "") or "",
        "type": kind,
        "status": "open",
        "priority": int(value(rest, "--priority", "2") or "2"),
        "parent": value(rest, "--parent"),
        "labels": csv_values(rest, "--labels"),
        "metadata": {},
        "dependencies": deps,
        "relations": [],
    }
    state["issues"][issue_id] = issue
    save(state)
    emit([serialize(state, issue)])
    return 0


def cmd_ready(args: list[str], state: dict[str, Any]) -> int:
    if "--claim" in args and value(args, "--mol") is not None:
        raise RuntimeError("--claim cannot be combined with --mol")
    issues = list(state["issues"].values())
    if (parent_id := value(args, "--parent")) is not None:
        issues = [one for one in issues if one.get("parent") == parent_id]
    if (root_id := value(args, "--mol")) is not None:
        ids = {one["id"] for one in descendants(state, root_id)}
        issues = [one for one in issues if one["id"] in ids]
    if (required := set(csv_values(args, "--label"))):
        issues = [one for one in issues if required <= set(one.get("labels", []))]
    excluded = set(csv_values(args, "--exclude-type"))
    issues = [one for one in issues if one.get("type") not in excluded and ready(state, one)]
    issues.sort(key=lambda one: (one.get("priority", 2), one["id"]))
    limit = int(value(args, "--limit", "10") or "10")
    if limit > 0:
        issues = issues[:limit]
    if "--claim" in args and issues:
        issues = [issues[0]]
        issues[0]["status"] = "in_progress"
        issues[0]["assignee"] = "test-agent"
        save(state)
    emit([serialize(state, one) for one in issues])
    return 0


def cmd_close(args: list[str], state: dict[str, Any]) -> int:
    issue = item(state, args[0])
    if issue.get("type") == "epic":
        open_children = [one for one in children(state, issue["id"]) if one["status"] != "closed"]
        if open_children and "--force" not in args:
            raise RuntimeError(f"cannot close epic {issue['id']}: open children")
    blockers = blocked(state, issue)
    if blockers and "--force" not in args:
        raise RuntimeError(f"cannot close {issue['id']}: blocked by {blockers}")
    issue["status"] = "closed"
    issue["close_reason"] = value(args, "--reason", "")
    save(state)
    emit([serialize(state, issue)])
    return 0


def cmd_gate(args: list[str], state: dict[str, Any]) -> int:
    sub = args[0]
    if sub == "list":
        gates = [one for one in state["issues"].values() if one.get("type") == "gate"]
        if "--all" not in args:
            gates = [one for one in gates if one.get("status") != "closed"]
        # Match Beads 1.2.2: ``bd gate list --json`` emits lightweight raw
        # gate issues and does not project the parent-child dependency into a
        # ``parent`` field. Workflow code must resolve the gate from the
        # blocked step or use ``bd list --parent ... --include-gates``.
        payload = []
        for one in gates:
            gate = dict(one)
            gate["issue_type"] = "gate"
            gate.pop("parent", None)
            gate.pop("waiter_id", None)
            gate.pop("dependencies", None)
            payload.append(gate)
        emit(payload)
        return 0
    if sub == "resolve":
        gate = item(state, args[1])
        gate["status"] = "closed"
        save(state)
        # Match Beads 1.2.2: gate resolve emits human-readable output even
        # when the global --json flag is present.
        print(f"Gate resolved: {gate['id']}")
        return 0
    if sub == "create":
        target = value(args, "--blocks")
        if not target:
            raise RuntimeError("--blocks is required")
        gate_id = new_id(state)
        gate = {
            "id": gate_id,
            "title": f"Gate: {value(args, '--type', 'human')}",
            "type": "gate",
            "status": "open",
            "parent": None,
            "labels": [],
            "metadata": {},
            "dependencies": [],
            "relations": [],
            "await_type": value(args, "--type", "human"),
            "await_id": value(args, "--await-id", ""),
            "waiter_id": target,
        }
        state["issues"][gate_id] = gate
        item(state, target).setdefault("dependencies", []).append(gate_id)
        save(state)
        emit([serialize(state, gate)])
        return 0
    if sub == "check":
        # Match Beads 1.2.2's progress-oriented gate check output.
        print("Checked gates")
        return 0
    raise RuntimeError(f"unsupported gate command: {sub}")


def cmd_delete(args: list[str], state: dict[str, Any]) -> int:
    ids = [arg for arg in args if not arg.startswith("-")]
    if not ids:
        raise RuntimeError("issue ID required")
    targets = set(ids)
    if "--cascade" in args:
        for issue_id in list(targets):
            targets.update(one["id"] for one in descendants(state, issue_id))
    if "--dry-run" in args:
        external = [
            one["id"]
            for one in state["issues"].values()
            if one["id"] not in targets
            and any(dep in targets for dep in one.get("dependencies", []))
        ]
        if external:
            raise RuntimeError("dependent issues outside deletion set: " + ", ".join(external))
        emit({"would_delete": sorted(targets)})
        return 0
    for issue_id in targets:
        state["issues"].pop(issue_id, None)
        state["comments"].pop(issue_id, None)
    for one in state["issues"].values():
        one["dependencies"] = [dep for dep in one.get("dependencies", []) if dep not in targets]
    save(state)
    emit({"deleted": sorted(targets)})
    return 0


def cmd_dep(args: list[str], state: dict[str, Any]) -> int:
    if args[0] != "add":
        raise RuntimeError("unsupported dep command")
    source, target = args[1], args[2]
    relation = value(args[3:], "--type", "blocks") or "blocks"
    if relation == "blocks":
        item(state, source).setdefault("dependencies", []).append(target)
    else:
        item(state, source).setdefault("relations", []).append({"to": target, "type": relation})
    save(state)
    emit({"from": source, "to": target, "type": relation})
    return 0


def cmd_comments(args: list[str], state: dict[str, Any]) -> int:
    if args[0] != "add":
        raise RuntimeError("unsupported comments command")
    path = value(args[2:], "-f")
    text = Path(path).read_text() if path else ""
    state["comments"].setdefault(args[1], []).append(text)
    save(state)
    emit({"issue_id": args[1], "comment": text})
    return 0


def cmd_supersede(args: list[str], state: dict[str, Any]) -> int:
    old_id = args[0]
    new_id_ = value(args, "--with")
    if not new_id_:
        raise RuntimeError("--with is required")
    old = item(state, old_id)
    old["status"] = "closed"
    old.setdefault("relations", []).append({"to": new_id_, "type": "superseded-by"})
    item(state, new_id_).setdefault("relations", []).append({"to": old_id, "type": "supersedes"})
    save(state)
    emit({"superseded": old_id, "with": new_id_})
    return 0


def cmd_worktree(args: list[str], cwd: Path) -> int:
    sub = args[0]
    if sub == "list":
        output = subprocess.check_output(["git", "worktree", "list", "--porcelain"], cwd=cwd, text=True)
        records: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for line in output.splitlines() + [""]:
            if not line:
                if current:
                    records.append(current)
                    current = {}
                continue
            key, _, val = line.partition(" ")
            current[key] = val or True
        emit(records)
        return 0
    if sub == "create":
        path = Path(args[1]).resolve()
        branch = value(args, "--branch") or path.name
        existing = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=cwd).returncode == 0
        command = ["git", "worktree", "add"]
        if existing:
            command.extend([str(path), branch])
        else:
            command.extend(["-b", branch, str(path)])
        subprocess.run(command, cwd=cwd, check=True)
        emit({"path": str(path), "branch": branch})
        return 0
    if sub == "remove":
        path = args[1]
        command = ["git", "worktree", "remove"]
        if "--force" in args:
            command.append("--force")
        command.append(path)
        subprocess.run(command, cwd=cwd, check=True)
        emit({"removed": path})
        return 0
    raise RuntimeError(f"unsupported worktree command: {sub}")


def main() -> int:
    args = sys.argv[1:]
    if args in (["--version"], ["version"]):
        print("bd version 1.2.2")
        return 0
    if "--help" in args:
        print("fake help")
        return 0
    if not args:
        return 2
    cwd = Path.cwd()
    state = load()
    command, rest = args[0], args[1:]
    try:
        if command == "init":
            (cwd / ".beads" / "formulas").mkdir(parents=True, exist_ok=True)
            emit({"initialized": True})
            return 0
        if command == "formula":
            return cmd_formula(rest, cwd)
        if command == "mol":
            return cmd_mol(rest, cwd, state)
        if command == "show":
            return cmd_show(rest, state)
        if command == "list":
            return cmd_list(rest, state)
        if command == "update":
            return cmd_update(rest, state)
        if command == "create":
            return cmd_create(rest, state)
        if command == "ready":
            return cmd_ready(rest, state)
        if command == "close":
            return cmd_close(rest, state)
        if command == "gate":
            return cmd_gate(rest, state)
        if command == "delete":
            return cmd_delete(rest, state)
        if command == "dep":
            return cmd_dep(rest, state)
        if command == "comments":
            return cmd_comments(rest, state)
        if command == "supersede":
            return cmd_supersede(rest, state)
        if command == "todo" and rest and rest[0] == "add":
            return cmd_create([rest[1], "--type", "task", "--labels", "todo"], state)
        if command == "worktree":
            return cmd_worktree(rest, cwd)
        raise RuntimeError(f"unsupported command: {command}")
    except (RuntimeError, KeyError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
