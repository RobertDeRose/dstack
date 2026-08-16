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
    if item.get("type") in {"gate", "molecule"}:
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


def iter_formula_steps(steps: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for step in steps:
        yield step
        yield from iter_formula_steps(step.get("children", []))


def formula_step_is_epic(step: dict[str, Any]) -> bool:
    """Match Beads cooking: a step with children is promoted to an epic."""

    return step.get("type", "task") == "epic" or bool(step.get("children"))


def validate_blocking_kinds(*, source_is_epic: bool, target_is_epic: bool) -> None:
    """Model Beads 1.2.2 cross-type ``blocks`` validation exactly."""

    if source_is_epic == target_is_epic:
        return
    if source_is_epic:
        raise RuntimeError("epics can only block other epics, not tasks")
    raise RuntimeError("tasks can only block other tasks, not epics")


def validate_formula_dependencies(formula: dict[str, Any]) -> None:
    """Model Beads' blocking constraints during formula cooking.

    ``needs`` and ``depends_on`` become ordinary ``blocks`` dependencies.
    Formula gates create another ``blocks`` dependency from the guarded step to
    a non-epic gate issue. ``waits_for`` is a separate fan-in relationship and
    is not subject to the task/epic equality rule.
    """

    steps = list(iter_formula_steps(formula.get("steps", [])))
    by_id = {step["id"]: step for step in steps}
    for dependent in steps:
        dependent_is_epic = formula_step_is_epic(dependent)
        for blocker_id in (
            *dependent.get("needs", []),
            *dependent.get("depends_on", []),
        ):
            blocker = by_id.get(blocker_id)
            if blocker is None:
                raise RuntimeError(f"unknown formula dependency: {blocker_id}")
            validate_blocking_kinds(
                source_is_epic=dependent_is_epic,
                target_is_epic=formula_step_is_epic(blocker),
            )

        if dependent.get("gate"):
            validate_blocking_kinds(
                source_is_epic=dependent_is_epic,
                target_is_epic=False,
            )


def load_formula(cwd: Path, state: dict[str, Any], name: str) -> dict[str, Any]:
    if name in state["protos"]:
        return state["protos"][name]
    return tomllib.loads(find_formula(cwd, name).read_text())


def persist_proto_graph(name: str, formula: dict[str, Any], state: dict[str, Any]) -> None:
    """Model the target pollution produced by ``bd cook --persist``."""

    for item_id in [name, *[item["id"] for item in descendants(state, name)]]:
        state["issues"].pop(item_id, None)

    state["issues"][name] = {
        "id": name,
        "title": name,
        "type": "molecule",
        "issue_type": "molecule",
        "status": "open",
        "parent_id": None,
        "labels": ["template"],
        "metadata": {},
        "dependencies": [],
        "gate_ids": [],
        "is_template": True,
    }

    raw_steps = formula.get("steps", [])
    step_ids = {step["id"]: f"{name}.{step['id']}" for step in raw_steps}
    for step in raw_steps:
        step_id = step_ids[step["id"]]
        dependencies = [step_ids[item] for item in step.get("needs", [])]
        dependencies.extend(step_ids[item] for item in step.get("depends_on", []))
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
            "issue_type": step.get("type", "task"),
            "status": "open",
            "parent_id": name,
            "labels": step.get("labels", []),
            "metadata": step.get("metadata", {}),
            "dependencies": dependencies,
            "gate_ids": [],
            "waits_for": waits_for,
            "is_template": True,
        }

    for step in raw_steps:
        gate = step.get("gate")
        if not gate:
            continue
        gate_id = f"{name}.gate-{step['id']}"
        waiter_id = step_ids[step["id"]]
        state["issues"][gate_id] = {
            "id": gate_id,
            "title": gate.get("id") or f"gate-{step['id']}",
            "type": "gate",
            "issue_type": "gate",
            "status": "open",
            "parent_id": name,
            "labels": [f"gate:{gate['type']}"],
            "metadata": {},
            "dependencies": [],
            "gate_ids": [],
            "gate_type": gate["type"],
            "await_id": gate.get("await_id") or gate.get("id"),
            "waiter_id": waiter_id,
            "is_template": True,
        }
        state["issues"][waiter_id]["gate_ids"].append(gate_id)


def command_cook(args: list[str], cwd: Path, state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("formula name required")
    name = args[0]
    data = tomllib.loads(find_formula(cwd, name).read_text())
    validate_formula_dependencies(data)
    if "--persist" in args:
        state["protos"][name] = data
        persist_proto_graph(name, data, state)
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


def command_pour(args: list[str], cwd: Path, state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("formula or proto required")
    name = args[0]
    formula = load_formula(cwd, state, name)
    validate_formula_dependencies(formula)
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
        "issue_type": "epic",
        "status": "open",
        "parent_id": None,
        "labels": [],
        "metadata": {"formula": name, "variables": variables},
        "dependencies": [],
        "gate_ids": [],
        "is_template": False,
    }

    raw_steps = [substitute(step, variables) for step in formula.get("steps", [])]
    step_ids = {step["id"]: new_id(state) for step in raw_steps}
    for step in raw_steps:
        step_id = step_ids[step["id"]]
        dependencies = [step_ids[item] for item in step.get("needs", [])]
        dependencies.extend(step_ids[item] for item in step.get("depends_on", []))
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
            "issue_type": step.get("type", "task"),
            "status": "open",
            "parent_id": root_id,
            "labels": step.get("labels", []),
            "metadata": step.get("metadata", {}),
            "dependencies": dependencies,
            "gate_ids": [],
            "waits_for": waits_for,
            "is_template": False,
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
            "issue_type": "gate",
            "status": "open",
            "parent_id": root_id,
            "labels": [f"gate:{gate['type']}"],
            "metadata": {},
            "dependencies": [],
            "gate_ids": [],
            "gate_type": gate["type"],
            "await_id": gate.get("await_id") or gate.get("id"),
            "waiter_id": waiter_id,
            "is_template": False,
        }
        state["issues"][waiter_id]["gate_ids"].append(gate_id)

    save_state(state)
    emit({"root_id": root_id, "step_ids": step_ids, "gate_ids": gate_ids})
    return 0


def command_mol(args: list[str], cwd: Path, state: dict[str, Any]) -> int:
    if not args:
        raise RuntimeError("mol subcommand required")
    subcommand = args[0]
    rest = args[1:]
    if subcommand == "seed":
        if not rest:
            raise RuntimeError("formula required")
        name = rest[0]
        formula = load_formula(cwd, state, name)
        validate_formula_dependencies(formula)
        emit({"formula": name, "available": True})
        return 0
    if subcommand == "pour":
        return command_pour(rest, cwd, state)
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
    dependencies = csv_values(rest, "--deps")
    item_type = value(rest, "--type", "task")

    for blocker_id in dependencies:
        blocker = issue(state, blocker_id)
        validate_blocking_kinds(
            source_is_epic=item_type == "epic",
            target_is_epic=blocker.get("type") == "epic",
        )

    waits_for_id = value(rest, "--waits-for")
    waits_for: str | None = None
    if waits_for_id:
        gate_mode = value(rest, "--waits-for-gate", "all-children")
        if gate_mode not in {"all-children", "any-children"}:
            raise RuntimeError(
                f"invalid --waits-for-gate value '{gate_mode}' "
                "(valid: all-children, any-children)"
            )
        waits_for = f"{gate_mode}({waits_for_id})"

    item = {
        "id": item_id,
        "title": title,
        "description": value(rest, "--description", ""),
        "acceptance": value(rest, "--acceptance", ""),
        "type": item_type,
        "status": "open",
        "parent_id": parent_id,
        "labels": csv_values(rest, "--labels"),
        "metadata": {},
        "dependencies": dependencies,
        "gate_ids": [],
        "waits_for": waits_for,
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


def command_delete(args: list[str], state: dict[str, Any]) -> int:
    issue_ids = [item for item in args if not item.startswith("-")]
    if not issue_ids:
        raise RuntimeError("issue ID required")
    cascade = "--cascade" in args
    deleted: list[str] = []
    for root_id in issue_ids:
        if root_id not in state["issues"]:
            raise RuntimeError(f"issue not found: {root_id}")
        targets = [root_id]
        if cascade:
            targets.extend(item["id"] for item in descendants(state, root_id))
        for target in targets:
            if target in state["issues"]:
                state["issues"].pop(target)
                deleted.append(target)
            state["comments"].pop(target, None)
            state["protos"].pop(target, None)
        target_set = set(targets)
        for item in state["issues"].values():
            item["dependencies"] = [
                dependency
                for dependency in item.get("dependencies", [])
                if dependency not in target_set
            ]
            item["gate_ids"] = [
                gate_id for gate_id in item.get("gate_ids", []) if gate_id not in target_set
            ]
        state["relations"] = [
            relation
            for relation in state["relations"]
            if relation.get("from") not in target_set and relation.get("to") not in target_set
        ]
    save_state(state)
    emit({"deleted": deleted, "deleted_count": len(deleted)})
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
            return command_mol(rest, cwd, state)
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
        if command == "delete":
            return command_delete(rest, state)
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
