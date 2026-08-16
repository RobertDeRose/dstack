#!/usr/bin/env python3
"""Stateful Beads CLI double used by dstack integration tests."""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable

STATE_ENV = "DSTACK_FAKE_BD_STATE"


def state_path() -> Path:
    return Path(os.environ[STATE_ENV])


def initial_state() -> dict[str, Any]:
    return {
        "next_id": 1,
        "issues": {},
        "protos": {},
        "relations": [],
        "comments": {},
    }


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        state = initial_state()
        save_state(state)
        return state
    return json.loads(path.read_text())


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def new_id(state: dict[str, Any]) -> str:
    value = f"bd-{state['next_id']}"
    state["next_id"] += 1
    return value


def values(args: list[str], flag: str) -> list[str]:
    found: list[str] = []
    index = 0
    while index < len(args):
        item = args[index]
        if item == flag and index + 1 < len(args):
            found.append(args[index + 1])
            index += 2
            continue
        if item.startswith(f"{flag}="):
            found.append(item.split("=", 1)[1])
        index += 1
    return found


def value(args: list[str], flag: str, default: str | None = None) -> str | None:
    found = values(args, flag)
    return found[-1] if found else default


def csv_values(args: list[str], flag: str) -> list[str]:
    result: list[str] = []
    for raw in values(args, flag):
        result.extend(part.strip() for part in raw.split(",") if part.strip())
    return result


def substitute(item: Any, variables: dict[str, str]) -> Any:
    if isinstance(item, str):
        result = item
        for key, replacement in variables.items():
            result = result.replace(f"{{{{{key}}}}}", replacement)
        return result
    if isinstance(item, list):
        return [substitute(value, variables) for value in item]
    if isinstance(item, dict):
        return {key: substitute(value, variables) for key, value in item.items()}
    return item


def find_formula(cwd: Path, name: str) -> Path:
    candidate = cwd / ".beads" / "formulas" / f"{name}.formula.toml"
    if not candidate.is_file():
        raise RuntimeError(f"formula not found: {name}")
    return candidate


def issue(state: dict[str, Any], issue_id: str) -> dict[str, Any]:
    try:
        return state["issues"][issue_id]
    except KeyError as exc:
        raise RuntimeError(f"issue not found: {issue_id}") from exc


def descendants(state: dict[str, Any], root_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    queue = [root_id]
    while queue:
        parent = queue.pop(0)
        children = [
            item
            for item in state["issues"].values()
            if item.get("parent_id") == parent
        ]
        result.extend(children)
        queue.extend(child["id"] for child in children)
    return result


def direct_children(
    state: dict[str, Any], parent_id: str, *, include_gates: bool = False
) -> list[dict[str, Any]]:
    return [
        item
        for item in state["issues"].values()
        if item.get("parent_id") == parent_id
        and (include_gates or item.get("type") != "gate")
    ]


def closed(item: dict[str, Any]) -> bool:
    return item.get("status") == "closed"


def is_ready(state: dict[str, Any], item: dict[str, Any]) -> bool:
    if item.get("status") != "open":
        return False
    if item.get("type") == "gate":
        return False
    for blocker_id in item.get("dependencies", []):
        if not closed(issue(state, blocker_id)):
            return False
    for gate_id in item.get("gate_ids", []):
        if not closed(issue(state, gate_id)):
            return False

    waits_for = item.get("waits_for")
    if waits_for:
        match = re.fullmatch(r"children-of\(([^)]+)\)", waits_for)
        if match:
            children = direct_children(state, match.group(1))
        elif waits_for == "all-children":
            children = direct_children(state, item["id"])
        elif waits_for == "any-children":
            children = direct_children(state, item["id"])
            if children and not any(closed(child) for child in children):
                return False
            children = []
        else:
            children = []
        if any(not closed(child) for child in children):
            return False
    return True


def emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def command_formula(args: list[str], cwd: Path) -> int:
    if len(args) < 3 or args[0] != "show":
        raise RuntimeError("unsupported formula command")
    name = args[1]
    data = tomllib.loads(find_formula(cwd, name).read_text())
    emit(data)
    return 0


def command_cook(args: list[str], cwd: Path, state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("formula name required")
    name = args[0]
    data = tomllib.loads(find_formula(cwd, name).read_text())
    if "--persist" in args:
        state["protos"][name] = data
        save_state(state)
    emit({"formula": name, "persisted": "--persist" in args})
    return 0


def parse_vars(args: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in values(args, "--var"):
        key, separator, raw = entry.partition("=")
        if not separator:
            raise RuntimeError(f"invalid --var: {entry}")
        parsed[key] = raw
    return parsed


def command_pour(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("proto required")
    name = args[0]
    try:
        formula = state["protos"][name]
    except KeyError as exc:
        raise RuntimeError(f"proto unavailable: {name}") from exc
    variables = parse_vars(args)
    for key, definition in formula.get("vars", {}).items():
        if key not in variables and "default" in definition:
            variables[key] = str(definition["default"])
        if definition.get("required") and key not in variables:
            raise RuntimeError(f"required variable missing: {key}")

    root_id = new_id(state)
    state["issues"][root_id] = {
        "id": root_id,
        "title": name,
        "type": "epic",
        "status": "open",
        "parent_id": None,
        "labels": [],
        "metadata": {"formula": name, "variables": variables},
        "dependencies": [],
        "gate_ids": [],
    }

    raw_steps = [substitute(step, variables) for step in formula.get("steps", [])]
    step_ids = {step["id"]: new_id(state) for step in raw_steps}
    for step in raw_steps:
        step_id = step_ids[step["id"]]
        dependencies = [step_ids[name] for name in step.get("needs", [])]
        dependencies.extend(step_ids[name] for name in step.get("depends_on", []))
        waits_for = step.get("waits_for")
        if isinstance(waits_for, str):
            match = re.fullmatch(r"children-of\(([^)]+)\)", waits_for)
            if match and match.group(1) in step_ids:
                waits_for = f"children-of({step_ids[match.group(1)]})"
        state["issues"][step_id] = {
            "id": step_id,
            "formula_step_id": step["id"],
            "title": step["title"],
            "description": step.get("description", ""),
            "type": step.get("type", "task"),
            "status": "open",
            "parent_id": root_id,
            "labels": step.get("labels", []),
            "metadata": step.get("metadata", {}),
            "dependencies": dependencies,
            "gate_ids": [],
            "waits_for": waits_for,
        }

    gate_ids: dict[str, str] = {}
    for step in raw_steps:
        gate = step.get("gate")
        if not gate:
            continue
        waiter_id = step_ids[step["id"]]
        gate_id = new_id(state)
        gate_ids[step["id"]] = gate_id
        state["issues"][gate_id] = {
            "id": gate_id,
            "title": gate.get("id") or f"gate-{step['id']}",
            "type": "gate",
            "status": "open",
            "parent_id": root_id,
            "labels": [f"gate:{gate['type']}"],
            "metadata": {},
            "dependencies": [],
            "gate_ids": [],
            "gate_type": gate["type"],
            "await_id": gate.get("await_id") or gate.get("id"),
            "waiter_id": waiter_id,
        }
        state["issues"][waiter_id]["gate_ids"].append(gate_id)

    save_state(state)
    emit({"root_id": root_id, "step_ids": step_ids, "gate_ids": gate_ids})
    return 0


def command_mol(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("mol subcommand required")
    subcommand = args[0]
    rest = args[1:]
    if subcommand == "seed":
        if not rest or rest[0] not in state["protos"]:
            raise RuntimeError("proto unavailable")
        emit({"proto": rest[0], "available": True})
        return 0
    if subcommand == "pour":
        return command_pour(rest, state)
    if subcommand in {"progress", "current"}:
        root_id = rest[0]
        items = descendants(state, root_id)
        ready = [item for item in items if is_ready(state, item)]
        emit(
            {
                "root_id": root_id,
                "open": sum(item["status"] != "closed" for item in items),
                "closed": sum(item["status"] == "closed" for item in items),
                "ready": [item["id"] for item in ready],
            }
        )
        return 0
    raise RuntimeError(f"unsupported mol command: {subcommand}")


def command_update(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("issue ID required")
    item = issue(state, args[0])
    rest = args[1:]
    if "--claim" in rest:
        if not is_ready(state, item):
            raise RuntimeError(f"issue is not ready: {item['id']}")
        item["status"] = "in_progress"
        item["assignee"] = "test-agent"
    for flag, key in (
        ("--title", "title"),
        ("--external-ref", "external_ref"),
        ("--description", "description"),
        ("--acceptance", "acceptance"),
        ("--type", "type"),
    ):
        selected = value(rest, flag)
        if selected is not None:
            item[key] = selected
    for label in csv_values(rest, "--add-label"):
        if label not in item["labels"]:
            item["labels"].append(label)
    metadata = value(rest, "--set-metadata")
    if metadata is not None:
        item["metadata"] = json.loads(metadata)
    status = value(rest, "--status")
    if status is not None:
        item["status"] = status
    save_state(state)
    emit(item)
    return 0


def command_create(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("title required")
    title = args[0]
    rest = args[1:]
    item_id = new_id(state)
    parent_id = value(rest, "--parent")
    gate_id = value(rest, "--waits-for-gate")
    dependencies = csv_values(rest, "--deps")
    item = {
        "id": item_id,
        "title": title,
        "description": value(rest, "--description", ""),
        "acceptance": value(rest, "--acceptance", ""),
        "type": value(rest, "--type", "task"),
        "status": "open",
        "parent_id": parent_id,
        "labels": csv_values(rest, "--labels"),
        "metadata": {},
        "dependencies": dependencies,
        "gate_ids": [gate_id] if gate_id else [],
    }
    state["issues"][item_id] = item
    save_state(state)
    emit(item)
    return 0


def command_list(args: list[str], state: dict[str, Any]) -> int:
    items = list(state["issues"].values())
    parent_id = value(args, "--parent")
    issue_type = value(args, "--type")
    status = value(args, "--status")
    required_labels = set(csv_values(args, "--label"))
    if parent_id is not None:
        items = [item for item in items if item.get("parent_id") == parent_id]
    if issue_type is not None:
        items = [item for item in items if item.get("type") == issue_type]
    if status is not None:
        items = [item for item in items if item.get("status") == status]
    if required_labels:
        items = [item for item in items if required_labels <= set(item.get("labels", []))]
    emit(sorted(items, key=lambda item: item["id"]))
    return 0


def command_ready(args: list[str], state: dict[str, Any]) -> int:
    root_id = value(args, "--mol")
    if root_id is None:
        items = list(state["issues"].values())
    else:
        items = descendants(state, root_id)
    excluded = set(csv_values(args, "--exclude-type"))
    items = [item for item in items if item.get("type") not in excluded and is_ready(state, item)]
    items.sort(key=lambda item: item["id"])
    if "--claim" in args and items:
        items[0]["status"] = "in_progress"
        items[0]["assignee"] = "test-agent"
        save_state(state)
        items = [items[0]]
    emit(items)
    return 0


def command_gate(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("gate subcommand required")
    subcommand = args[0]
    if subcommand == "list":
        emit([item for item in state["issues"].values() if item.get("type") == "gate"])
        return 0
    if subcommand == "resolve":
        item = issue(state, args[1])
        if item.get("type") != "gate":
            raise RuntimeError("not a gate")
        item["status"] = "closed"
        save_state(state)
        emit(item)
        return 0
    if subcommand == "check":
        emit({"checked": True})
        return 0
    raise RuntimeError(f"unsupported gate command: {subcommand}")


def command_close(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("issue ID required")
    item = issue(state, args[0])
    item["status"] = "closed"
    save_state(state)
    emit(item)
    return 0


def command_show(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("issue ID required")
    emit(issue(state, args[0]))
    return 0


def command_todo(args: list[str], state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("todo subcommand required")
    if args[0] == "add":
        return command_create([args[1], "--type", "task", "--labels", "todo"], state)
    if args[0] == "done":
        return command_close(args[1:], state)
    raise RuntimeError(f"unsupported todo command: {args[0]}")


def command_dep(args: list[str], state: dict[str, Any]) -> int:
    if not args or args[0] != "add" or len(args) < 3:
        raise RuntimeError("unsupported dep command")
    subject_id, target_id = args[1], args[2]
    relation_type = value(args[3:], "--type", "blocks")
    if relation_type == "blocks":
        issue(state, subject_id)["dependencies"].append(target_id)
    else:
        state["relations"].append(
            {"from": subject_id, "to": target_id, "type": relation_type}
        )
    save_state(state)
    emit({"from": subject_id, "to": target_id, "type": relation_type})
    return 0


def command_comments(args: list[str], state: dict[str, Any]) -> int:
    if len(args) < 3 or args[0] != "add":
        raise RuntimeError("unsupported comments command")
    issue_id = args[1]
    file_path = value(args[2:], "-f")
    content = Path(file_path).read_text() if file_path else ""
    state["comments"].setdefault(issue_id, []).append(content)
    save_state(state)
    emit({"issue_id": issue_id, "comment": content})
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args in (["--version"], ["version"]):
        print("bd version 1.2.2")
        return 0
    if not args:
        return 2

    cwd = Path.cwd()
    state = load_state()
    command, rest = args[0], args[1:]
    try:
        if command == "init":
            (cwd / ".beads" / "formulas").mkdir(parents=True, exist_ok=True)
            emit({"initialized": True})
            return 0
        if command == "formula":
            return command_formula(rest, cwd)
        if command == "cook":
            return command_cook(rest, cwd, state)
        if command == "mol":
            return command_mol(rest, state)
        if command == "update":
            return command_update(rest, state)
        if command == "create":
            return command_create(rest, state)
        if command == "list":
            return command_list(rest, state)
        if command == "ready":
            return command_ready(rest, state)
        if command == "gate":
            return command_gate(rest, state)
        if command == "close":
            return command_close(rest, state)
        if command == "show":
            return command_show(rest, state)
        if command == "todo":
            return command_todo(rest, state)
        if command == "dep":
            return command_dep(rest, state)
        if command == "comments":
            return command_comments(rest, state)
        raise RuntimeError(f"unsupported command: {command}")
    except (RuntimeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
