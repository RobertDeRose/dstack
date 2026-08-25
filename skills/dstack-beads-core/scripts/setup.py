#!/usr/bin/env python3
"""Install, validate, and explicitly repair dstack's Beads integration."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence, cast
from urllib.parse import urlsplit

from dstack_docs import (
    INCLUDE_PATTERN,
    LINK_PATTERN,
    create_foundation,
    initialize_docs,
    legacy_documentation_plan,
    markdown_values,
    migrate_known_documentation_file,
    migrate_legacy_documentation,
    require_mdbook,
    validate_docs,
)
from dstack_feature import ensure_feature_navigation
from dstacklib import (
    ALIGNMENT_STEPS,
    FEATURE_STEPS,
    BeadsClient,
    DstackError,
    as_items,
    canonical_feature_design_path,
    ensure_clean_worktree,
    feature_slug,
    git_root,
    has_label,
    issue_labels,
    issue_metadata,
    parse_json,
    root_metadata_value,
    run,
    worktree_records,
)

from dstack_commands import (
    BEADS_RUNTIME_DIR_PREFIXES,
    BEADS_RUNTIME_TOP_LEVEL_PATTERNS,
    DSTACK_UNTRACKED_BEADS_FILES,
)

FORMULA_NAMES = ("dstack-feature", "dstack-project-alignment")
SUPPORTED_MDBOOK_VERSION_OUTPUT = "mdbook v0.5.3"
SETUP_PLAN_SCHEMA = "dstack.setup-plan/v2"
SETUP_PLAN_FIELDS = {
    "schema",
    "initialization",
    "beads_issues",
    "dependencies",
    "supersessions",
    "filesystem",
    "git_index",
    "formulas",
    "navigation_references",
}
SETUP_RELATIONS = {"blocks", "parent-child", "relates-to", "supersedes", "superseded-by"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _setup_text(value: Any, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise SetupError(f"setup plan field {field!r} must be a string")
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def _setup_id(value: Any, field: str) -> str:
    return _setup_text(value, field)


def _setup_path(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    path = _setup_text(value, field)
    if "\\" in path:
        raise SetupError(f"setup plan path {field!r} must use POSIX separators")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise SetupError(f"setup plan path {field!r} escapes the repository")
    normalized = "/".join(part for part in pure.parts if part not in {"", "."})
    if not normalized:
        raise SetupError(f"setup plan path {field!r} is empty")
    return normalized


def _setup_hash(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    digest = _setup_text(value, field).lower()
    if not SHA256_RE.fullmatch(digest):
        raise SetupError(f"setup plan hash {field!r} must be SHA-256")
    return digest


def _setup_fields(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise SetupError(f"setup plan {field} has invalid fields")
    return value


def _setup_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SetupError(f"setup plan field {field!r} must be an array")
    result = [_setup_text(item, f"{field}[]") for item in value]
    if len(result) != len(set(result)):
        raise SetupError(f"setup plan field {field!r} contains duplicates")
    return sorted(result)


def _setup_metadata(value: Any, field: str) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise SetupError(f"setup plan field {field!r} must be an object")
    result: dict[str, str | None] = {}
    for key, item in value.items():
        name = _setup_text(key, f"{field}.key")
        if not isinstance(item, (str, type(None))):
            raise SetupError(f"setup plan metadata {name!r} must be string or null")
        result[name] = None if item is None else _setup_text(item, f"{field}.{name}", empty=True)
    return {key: result[key] for key in sorted(result)}


def _setup_initialization(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 1:
        raise SetupError("setup plan initialization must contain zero or one record")
    if not value:
        return []
    item = _setup_fields(value[0], {"action", "target", "precondition", "options"}, "initialization[0]")
    options = _setup_fields(item["options"], {"skip_agents", "skip_hooks", "non_interactive"}, "initialization.options")
    if any(options[key] is not True for key in options):
        raise SetupError("setup initialization options must all be true")
    if item["action"] != "initialize-beads" or item["target"] != ".beads" or item["precondition"] != "absent":
        raise SetupError("setup initialization record is invalid")
    return [
        {
            "action": "initialize-beads",
            "target": ".beads",
            "precondition": "absent",
            "options": {key: True for key in sorted(options)},
        }
    ]


def _setup_beads_issues(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SetupError("setup plan beads_issues must be an array")
    result = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _setup_fields(
            raw,
            {"issue_id", "set_metadata", "unset_metadata", "add_labels", "remove_labels"},
            f"beads_issues[{index}]",
        )
        issue_id = _setup_id(item["issue_id"], f"beads_issues[{index}].issue_id")
        if issue_id in seen:
            raise SetupError(f"duplicate setup issue mutation: {issue_id}")
        seen.add(issue_id)
        unset = _setup_strings(item["unset_metadata"], f"beads_issues[{index}].unset_metadata")
        metadata = _setup_metadata(item["set_metadata"], f"beads_issues[{index}].set_metadata")
        if set(unset) & set(metadata):
            raise SetupError(f"setup issue mutation sets and unsets the same metadata: {issue_id}")
        add = _setup_strings(item["add_labels"], f"beads_issues[{index}].add_labels")
        remove = _setup_strings(item["remove_labels"], f"beads_issues[{index}].remove_labels")
        if set(add) & set(remove):
            raise SetupError(f"setup issue mutation adds and removes the same label: {issue_id}")
        result.append(
            {
                "issue_id": issue_id,
                "set_metadata": metadata,
                "unset_metadata": unset,
                "add_labels": add,
                "remove_labels": remove,
            }
        )
    return sorted(result, key=lambda item: item["issue_id"])


def _setup_dependencies(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SetupError("setup plan dependencies must be an array")
    result: list[dict[str, str]] = []
    seen: dict[tuple[str, str, str], str] = {}
    for index, raw in enumerate(value):
        item = _setup_fields(
            raw,
            {"action", "source_id", "destination_id", "relationship_type"},
            f"dependencies[{index}]",
        )
        action = _setup_text(item["action"], f"dependencies[{index}].action")
        if action not in {"add", "remove"}:
            raise SetupError("setup dependency action must be add or remove")
        record = {
            "action": action,
            "source_id": _setup_id(item["source_id"], f"dependencies[{index}].source_id"),
            "destination_id": _setup_id(item["destination_id"], f"dependencies[{index}].destination_id"),
            "relationship_type": _setup_text(item["relationship_type"], f"dependencies[{index}].relationship_type"),
        }
        if record["relationship_type"] not in SETUP_RELATIONS:
            raise SetupError("setup dependency relationship is unsupported")
        key = (record["source_id"], record["destination_id"], record["relationship_type"])
        if key in seen:
            raise SetupError("setup dependency operations contradict or duplicate each other")
        seen[key] = action
        result.append(record)
    return sorted(
        result,
        key=lambda item: (
            item["source_id"],
            item["destination_id"],
            item["relationship_type"],
            item["action"],
        ),
    )


def _setup_supersessions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SetupError("setup plan supersessions must be an array")
    result = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(value):
        item = _setup_fields(raw, {"source_id", "destination_id"}, f"supersessions[{index}]")
        source = _setup_id(item["source_id"], f"supersessions[{index}].source_id")
        destination = _setup_id(item["destination_id"], f"supersessions[{index}].destination_id")
        if source == destination or (source, destination) in seen:
            raise SetupError("setup supersession operations are invalid or duplicated")
        seen.add((source, destination))
        result.append({"source_id": source, "destination_id": destination})
    return sorted(result, key=lambda item: (item["source_id"], item["destination_id"]))


def _setup_filesystem(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SetupError("setup plan filesystem must be an array")
    result = []
    seen: set[tuple[str, str | None, str | None]] = set()
    paths_seen: dict[str, str] = {}
    for index, raw in enumerate(value):
        item = _setup_fields(
            raw,
            {
                "action",
                "source",
                "destination",
                "expected_source_sha256",
                "expected_destination_sha256",
                "content_source",
                "generated_content",
                "content_preservation",
                "conflict_policy",
            },
            f"filesystem[{index}]",
        )
        action = _setup_text(item["action"], f"filesystem[{index}].action")
        if action not in {"create", "update", "move", "delete"}:
            raise SetupError("setup filesystem action is unsupported")
        source = _setup_path(item["source"], f"filesystem[{index}].source", nullable=True)
        destination = _setup_path(item["destination"], f"filesystem[{index}].destination", nullable=True)
        source_hash = _setup_hash(
            item["expected_source_sha256"],
            f"filesystem[{index}].expected_source_sha256",
            nullable=True,
        )
        destination_hash = _setup_hash(
            item["expected_destination_sha256"],
            f"filesystem[{index}].expected_destination_sha256",
            nullable=True,
        )
        content_source = _setup_text(item["content_source"], f"filesystem[{index}].content_source")
        if content_source not in {"package", "existing-source", "generated"}:
            raise SetupError("setup filesystem content source is unsupported")
        generated = item["generated_content"]
        if generated is not None:
            generated = _setup_text(generated, f"filesystem[{index}].generated_content", empty=True)
        preservation = _setup_text(item["content_preservation"], f"filesystem[{index}].content_preservation")
        if preservation not in {"byte-for-byte", "generated", "not-applicable"}:
            raise SetupError("setup filesystem preservation policy is unsupported")
        conflict = _setup_text(item["conflict_policy"], f"filesystem[{index}].conflict_policy")
        if conflict not in {
            "fail-if-exists",
            "require-identical",
            "replace-reviewed",
            "not-applicable",
        }:
            raise SetupError("setup filesystem conflict policy is unsupported")
        if action == "create" and (source is not None or destination is None or source_hash is not None):
            raise SetupError("setup create operation has invalid source fields")
        if action == "move" and (source is None or destination is None or source_hash is None):
            raise SetupError("setup move operation requires source, destination, and source hash")
        if action == "delete" and (source is None or destination is not None or source_hash is None):
            raise SetupError("setup delete operation has invalid source fields")
        if action == "update" and (destination is None or destination_hash is None):
            raise SetupError("setup update operation requires a destination hash")
        if action == "create" and preservation != "generated":
            raise SetupError("setup create operation must use generated preservation")
        if action in {"move", "delete"} and preservation != "byte-for-byte":
            raise SetupError("setup move/delete operation must preserve bytes")
        if content_source == "generated" and generated is None:
            raise SetupError("generated setup filesystem content is missing")
        if content_source != "generated" and generated is not None:
            raise SetupError("non-generated setup filesystem content cannot include bytes")
        if action == "move" and content_source != "existing-source":
            raise SetupError("setup move content must come from the existing source")
        key = (action, source, destination)
        if key in seen:
            raise SetupError("duplicate setup filesystem operation")
        seen.add(key)
        for path in (source, destination):
            if path is not None and path in paths_seen:
                raise SetupError("setup filesystem operations contradict each other")
            if path is not None:
                paths_seen[path] = action
        result.append(
            {
                "action": action,
                "source": source,
                "destination": destination,
                "expected_source_sha256": source_hash,
                "expected_destination_sha256": destination_hash,
                "content_source": content_source,
                "generated_content": generated,
                "content_preservation": preservation,
                "conflict_policy": conflict,
            }
        )
    return sorted(result, key=lambda item: (item["source"] or "", item["destination"] or "", item["action"]))


def _setup_git_index(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SetupError("setup plan git_index must be an array")
    result: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        item = _setup_fields(raw, {"path", "action"}, f"git_index[{index}]")
        path = cast(str, _setup_path(item["path"], f"git_index[{index}].path"))
        action = _setup_text(item["action"], f"git_index[{index}].action")
        if action != "remove-cached":
            raise SetupError("setup Git-index action is unsupported")
        result.append({"path": path, "action": action})
    if len({item["path"] for item in result}) != len(result):
        raise SetupError("duplicate setup Git-index operation")
    return sorted(result, key=lambda item: (str(item["path"]), str(item["action"])))


def _setup_formulas(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SetupError("setup plan formulas must be an array")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        item = _setup_fields(
            raw,
            {
                "name",
                "action",
                "source",
                "destination",
                "source_sha256",
                "expected_destination_sha256",
                "conflict_policy",
            },
            f"formulas[{index}]",
        )
        action = _setup_text(item["action"], f"formulas[{index}].action")
        if action not in {"create", "update"}:
            raise SetupError("setup formula action is unsupported")
        name = _setup_id(item["name"], f"formulas[{index}].name")
        source = cast(str, _setup_path(item["source"], f"formulas[{index}].source"))
        destination = cast(str, _setup_path(item["destination"], f"formulas[{index}].destination"))
        conflict = _setup_text(item["conflict_policy"], f"formulas[{index}].conflict_policy")
        if conflict not in {"fail-if-different", "replace-reviewed"}:
            raise SetupError("setup formula conflict policy is unsupported")
        expected_destination = _setup_hash(
            item["expected_destination_sha256"],
            f"formulas[{index}].expected_destination_sha256",
            nullable=True,
        )
        if action == "update" and expected_destination is None:
            raise SetupError("setup formula update requires a destination hash")
        result.append(
            {
                "name": name,
                "action": action,
                "source": source,
                "destination": destination,
                "source_sha256": cast(str, _setup_hash(item["source_sha256"], f"formulas[{index}].source_sha256")),
                "expected_destination_sha256": expected_destination,
                "conflict_policy": conflict,
            }
        )
    if len({item["name"] for item in result}) != len(result):
        raise SetupError("duplicate setup formula operation")
    return sorted(
        result,
        key=lambda item: (
            str(item["name"]),
            str(item["source"]),
            str(item["destination"]),
            str(item["action"]),
        ),
    )


def _setup_navigation(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SetupError("setup plan navigation_references must be an array")
    result = []
    for index, raw in enumerate(value):
        item = _setup_fields(
            raw,
            {
                "action",
                "affected_path",
                "old_target",
                "new_target",
                "expected_before_sha256",
                "expected_after_sha256",
            },
            f"navigation_references[{index}]",
        )
        action = _setup_text(item["action"], f"navigation_references[{index}].action")
        if action not in {"add-navigation", "rewrite-link", "rewrite-include"}:
            raise SetupError("setup navigation action is unsupported")
        affected = _setup_path(item["affected_path"], f"navigation_references[{index}].affected_path")
        old = (
            None
            if item["old_target"] is None
            else _setup_text(item["old_target"], f"navigation_references[{index}].old_target")
        )
        new = (
            None
            if item["new_target"] is None
            else _setup_text(item["new_target"], f"navigation_references[{index}].new_target")
        )
        before = _setup_hash(item["expected_before_sha256"], f"navigation_references[{index}].expected_before_sha256")
        after = _setup_hash(item["expected_after_sha256"], f"navigation_references[{index}].expected_after_sha256")
        if action == "add-navigation" and (old is not None or new is None):
            raise SetupError("setup add-navigation operation has invalid targets")
        if action != "add-navigation" and (old is None or new is None):
            raise SetupError("setup rewrite operation requires both targets")
        result.append(
            {
                "action": action,
                "affected_path": affected,
                "old_target": old,
                "new_target": new,
                "expected_before_sha256": before,
                "expected_after_sha256": after,
            }
        )
    return sorted(result, key=lambda item: (item["affected_path"], item["new_target"] or "", item["action"]))


def canonicalize_setup_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SetupError("setup plan must be a JSON object")
    if set(value) != SETUP_PLAN_FIELDS:
        missing = sorted(SETUP_PLAN_FIELDS - set(value))
        unknown = sorted(set(value) - SETUP_PLAN_FIELDS)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        raise SetupError("invalid setup plan fields: " + "; ".join(detail))
    if value["schema"] != SETUP_PLAN_SCHEMA:
        raise SetupError(f"setup plan schema must be {SETUP_PLAN_SCHEMA}")
    return {
        "schema": SETUP_PLAN_SCHEMA,
        "initialization": _setup_initialization(value["initialization"]),
        "beads_issues": _setup_beads_issues(value["beads_issues"]),
        "dependencies": _setup_dependencies(value["dependencies"]),
        "supersessions": _setup_supersessions(value["supersessions"]),
        "filesystem": _setup_filesystem(value["filesystem"]),
        "git_index": _setup_git_index(value["git_index"]),
        "formulas": _setup_formulas(value["formulas"]),
        "navigation_references": _setup_navigation(value["navigation_references"]),
    }


def canonical_setup_plan_bytes(value: Any) -> bytes:
    return json.dumps(
        canonicalize_setup_plan(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def setup_plan_digest(value: Any) -> str:
    return hashlib.sha256(canonical_setup_plan_bytes(value)).hexdigest()


PREFLIGHT_VARS: dict[str, dict[str, str]] = {
    "dstack-feature": {
        "feature_title": "Dstack Formula Preflight",
        "feature_slug": "dstack-formula-preflight",
        "design_path": "docs/src/features/dstack-formula-preflight/design.md",
    },
    "dstack-project-alignment": {
        "audit_title": "Dstack Alignment Preflight",
        "audit_slug": "dstack-alignment-preflight",
        "scope": "formula validation",
    },
}


class SetupError(DstackError):
    """Raised when setup or repair cannot proceed safely."""


def package_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ensure_beads(root: Path, *, initialize: bool) -> None:
    if (root / ".beads").is_dir():
        return
    if not initialize:
        raise SetupError("Beads is not initialized; rerun setup after authorization")
    run(
        [
            "bd",
            "init",
            "--quiet",
            "--skip-agents",
            "--skip-hooks",
            "--non-interactive",
        ],
        cwd=root,
    )
    if not (root / ".beads").is_dir():
        raise SetupError("bd init completed without creating .beads")


def formula_vars(name: str) -> list[str]:
    result: list[str] = []
    for key, value in PREFLIGHT_VARS[name].items():
        result.extend(["--var", f"{key}={value}"])
    return result


def step_map(formula: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = formula.get("steps")
    if not isinstance(raw, list):
        raise SetupError("formula steps must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise SetupError("formula contains an invalid step")
        result[str(item["id"])] = item
    return result


def validate_formula_contract(name: str, formula: Mapping[str, Any]) -> None:
    steps = step_map(formula)
    if name == "dstack-feature":
        expected = {
            "specification": ("task", FEATURE_STEPS["specification"]),
            "approval": ("task", FEATURE_STEPS["approval"]),
            "implementation": ("epic", FEATURE_STEPS["implementation"]),
            "closeout": ("task", FEATURE_STEPS["closeout"]),
        }
        planning, approval, workstream, terminal = (
            "specification",
            "approval",
            "implementation",
            "closeout",
        )
    elif name == "dstack-project-alignment":
        expected = {
            "analysis": ("task", ALIGNMENT_STEPS["analysis"]),
            "approval": ("task", ALIGNMENT_STEPS["approval"]),
            "corrections": ("epic", ALIGNMENT_STEPS["corrections"]),
            "landing": ("task", ALIGNMENT_STEPS["landing"]),
        }
        planning, approval, workstream, terminal = (
            "analysis",
            "approval",
            "corrections",
            "landing",
        )
    else:
        raise SetupError(f"unknown dstack formula: {name}")

    if set(steps) != set(expected):
        raise SetupError(f"{name} must contain exactly {sorted(expected)}")
    for step_id, (expected_type, expected_label) in expected.items():
        step = steps[step_id]
        actual_type = str(step.get("type") or "task")
        if actual_type != expected_type:
            raise SetupError(f"{name} step {step_id} must be {expected_type}, got {actual_type}")
        if step.get("labels") != [expected_label]:
            raise SetupError(f"{name} step {step_id} must have only label {expected_label}")
        if step.get("metadata"):
            raise SetupError(f"{name} step {step_id} must not duplicate identity in metadata")
        encoded = json.dumps(step, sort_keys=True)
        labels = json.dumps(step.get("labels", []))
        metadata = json.dumps(step.get("metadata", {}))
        if "{{" in labels or "{{" in metadata:
            raise SetupError(f"{name} step {step_id} templates labels or metadata")
        if not encoded:
            raise SetupError("invalid formula step")

    if steps[approval].get("needs") != [planning]:
        raise SetupError(f"{name} approval must depend only on {planning}")
    gate = steps[approval].get("gate")
    if not isinstance(gate, dict) or gate.get("type") != "human":
        raise SetupError(f"{name} approval must carry a human gate")
    if steps[workstream].get("needs") or steps[workstream].get("gate"):
        raise SetupError(f"{name} workstream must remain an ungated epic container")
    if steps[terminal].get("needs") != [approval]:
        raise SetupError(f"{name} terminal must depend on approval")
    if steps[terminal].get("waits_for") != f"children-of({workstream})":
        raise SetupError(f"{name} terminal must use native dynamic child fan-in")


def validate_formula(
    root: Path,
    name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    result = run(["bd", "formula", "show", name, "--json"], cwd=root, env=env)
    payload = parse_json(result.stdout, context=f"bd formula show {name}")
    if not isinstance(payload, dict):
        raise SetupError(f"bd formula show returned a non-object for {name}")
    validate_formula_contract(name, payload)
    run(["bd", "mol", "seed", name, *formula_vars(name)], cwd=root, env=env)
    return payload


def validate_bundle(source_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="dstack-preflight-") as raw:
        scratch = Path(raw)
        run(["git", "init", "-q"], cwd=scratch)
        run(
            [
                "bd",
                "init",
                "--quiet",
                "--skip-agents",
                "--skip-hooks",
                "--non-interactive",
            ],
            cwd=scratch,
        )
        formula_dir = scratch / ".beads" / "formulas"
        formula_dir.mkdir(parents=True, exist_ok=True)
        for name in FORMULA_NAMES:
            shutil.copyfile(
                source_dir / f"{name}.formula.toml",
                formula_dir / f"{name}.formula.toml",
            )
        for name in FORMULA_NAMES:
            validate_formula(scratch, name)
            result = run(
                ["bd", "mol", "pour", name, *formula_vars(name), "--json"],
                cwd=scratch,
            )
            payload = parse_json(result.stdout, context=f"bd mol pour {name}")
            if not isinstance(payload, dict) or not (payload.get("root_id") or payload.get("new_epic_id")):
                raise SetupError(f"isolated pour returned no root for {name}")


def atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(raw, path)
    finally:
        Path(raw).unlink(missing_ok=True)


def copy_formula(source: Path, destination: Path, *, force: bool) -> str:
    if destination.exists():
        if destination.read_bytes() == source.read_bytes():
            return "unchanged"
        if not force:
            raise SetupError(f"formula differs: {destination}; rerun /setup-project --force")
        state = "updated"
    else:
        state = "installed"
    atomic_replace(destination, source.read_bytes())
    return state


def documentation_change_plan(root: Path) -> list[dict[str, str]]:
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in (root / "docs").rglob("*")
        if path.is_file()
    } if (root / "docs").is_dir() else {}
    with tempfile.TemporaryDirectory(prefix="dstack-docs-plan-") as raw:
        scratch = Path(raw) / root.name
        scratch.mkdir()
        if (root / "docs").exists():
            shutil.copytree(root / "docs", scratch / "docs", symlinks=True)
        create_foundation(scratch)
        after = {
            path.relative_to(scratch).as_posix(): path.read_bytes()
            for path in (scratch / "docs").rglob("*")
            if path.is_file()
        }
    return [
        {"path": path, "action": "create" if path not in before else "update"}
        for path, content in sorted(after.items())
        if before.get(path) != content
    ]


def _setup_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup_issue_mutation(
    issue: Mapping[str, Any],
    *,
    set_metadata: Mapping[str, str | None] = {},
    unset_metadata: Sequence[str] = (),
    add_labels: Sequence[str] = (),
    remove_labels: Sequence[str] = (),
) -> dict[str, Any] | None:
    record = {
        "issue_id": str(issue.get("id") or ""),
        "set_metadata": dict(set_metadata),
        "unset_metadata": list(unset_metadata),
        "add_labels": list(add_labels),
        "remove_labels": list(remove_labels),
    }
    if not record["issue_id"]:
        raise SetupError("setup normalization encountered an issue without an ID")
    if not any(record[key] for key in record if key != "issue_id"):
        return None
    return record


def _setup_normalization_plan(client: BeadsClient) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for root in client.list(all_statuses=True, labels=["workflow:feature"]):
        slug = feature_slug(root)
        metadata = issue_metadata(root)
        set_metadata: dict[str, str | None] = {}
        base = root_metadata_value(root, "dstack.base_branch", "base_branch")
        if base and not metadata.get("dstack.base_branch"):
            set_metadata["dstack.base_branch"] = base
        if slug:
            canonical = canonical_feature_design_path(slug)
            if metadata.get("dstack.design_path") != canonical:
                set_metadata["dstack.design_path"] = canonical
        unset = [
            key for key in ("feature_slug", "base_branch", "branch", "worktree_path", "adopted_from") if key in metadata
        ]
        remove = [label for label in issue_labels(root) if label == "dstack:delivery-ready"]
        mutation = _setup_issue_mutation(
            root,
            set_metadata=set_metadata,
            unset_metadata=unset,
            remove_labels=remove,
        )
        if mutation:
            result.append(mutation)

        children = client.children(str(root["id"]))
        for child in children:
            child_metadata = issue_metadata(child)
            child_unset = [key for key in ("dstack_step", "base_branch", "design_path") if key in child_metadata]
            child_remove = [
                label
                for label in issue_labels(child)
                if label == "feature:{{feature_slug}}" or (slug and label == f"feature:{slug}")
            ]
            mutation = _setup_issue_mutation(
                child,
                unset_metadata=child_unset,
                remove_labels=child_remove,
            )
            if mutation:
                result.append(mutation)

            if has_label(child, FEATURE_STEPS["implementation"]):
                for task in client.children(str(child["id"])):
                    task_remove = [
                        label
                        for label in issue_labels(task)
                        if label == "feature:{{feature_slug}}" or (slug and label == f"feature:{slug}")
                    ]
                    mutation = _setup_issue_mutation(task, remove_labels=task_remove)
                    if mutation:
                        result.append(mutation)

    for root in client.list(all_statuses=True, labels=["workflow:project-alignment"]):
        metadata = issue_metadata(root)
        set_metadata = {}
        target = root_metadata_value(root, "dstack.target_branch", "target_branch")
        scope = root_metadata_value(root, "dstack.scope", "scope")
        if target and not metadata.get("dstack.target_branch"):
            set_metadata["dstack.target_branch"] = target
        if scope and not metadata.get("dstack.scope"):
            set_metadata["dstack.scope"] = scope
        unset = [key for key in ("audit_slug", "target_branch", "branch", "worktree_path") if key in metadata]
        remove = [label for label in issue_labels(root) if label == "dstack:delivery-ready"]
        mutation = _setup_issue_mutation(
            root,
            set_metadata=set_metadata,
            unset_metadata=unset,
            remove_labels=remove,
        )
        if mutation:
            result.append(mutation)
        for child in client.children(str(root["id"])):
            child_metadata = issue_metadata(child)
            child_unset = [key for key in ("dstack_step", "target_branch", "scope") if key in child_metadata]
            child_remove = [label for label in issue_labels(child) if label.startswith("audit:")]
            mutation = _setup_issue_mutation(
                child,
                unset_metadata=child_unset,
                remove_labels=child_remove,
            )
            if mutation:
                result.append(mutation)
    return canonicalize_setup_plan(
        {
            "schema": SETUP_PLAN_SCHEMA,
            "initialization": [],
            "beads_issues": result,
            "dependencies": [],
            "supersessions": [],
            "filesystem": [],
            "git_index": [],
            "formulas": [],
            "navigation_references": [],
        }
    )["beads_issues"]


def _setup_feature_design_moves(client: BeadsClient) -> list[tuple[str, str]]:
    moves: list[tuple[str, str]] = []
    for feature in client.list(all_statuses=True, labels=["workflow:feature"]):
        slug = feature_slug(feature)
        design = root_metadata_value(feature, "dstack.design_path", "design_path")
        canonical = canonical_feature_design_path(slug) if slug else ""
        if design and design != canonical and canonical:
            source = client.root / design
            if source.is_file() and not source.is_symlink():
                moves.append((design, canonical))
    return sorted(set(moves))


def _setup_navigation_plan(
    before: Mapping[str, bytes],
    after: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for relative in sorted(set(before) & set(after)):
        if not relative.casefold().endswith(".md") or before[relative] == after[relative]:
            continue
        try:
            old_text = before[relative].decode("utf-8")
            new_text = after[relative].decode("utf-8")
        except UnicodeDecodeError:
            continue
        before_hash = hashlib.sha256(before[relative]).hexdigest()
        after_hash = hashlib.sha256(after[relative]).hexdigest()
        for pattern, action in (
            (LINK_PATTERN, "rewrite-link"),
            (INCLUDE_PATTERN, "rewrite-include"),
        ):
            old_targets = markdown_values(old_text, pattern)
            new_targets = markdown_values(new_text, pattern)
            for old_target, new_target in zip(old_targets, new_targets):
                if old_target != new_target:
                    result.append(
                        {
                            "action": action,
                            "affected_path": relative,
                            "old_target": old_target,
                            "new_target": new_target,
                            "expected_before_sha256": before_hash,
                            "expected_after_sha256": after_hash,
                        }
                    )
            if action == "rewrite-link" and len(new_targets) > len(old_targets):
                for new_target in new_targets[len(old_targets) :]:
                    result.append(
                        {
                            "action": "add-navigation",
                            "affected_path": relative,
                            "old_target": None,
                            "new_target": new_target,
                            "expected_before_sha256": before_hash,
                            "expected_after_sha256": after_hash,
                        }
                    )
    return result


def _setup_doc_filesystem_plan(
    root: Path, *, force: bool, design_moves: Sequence[tuple[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs = root / "docs"
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in docs.rglob("*")
        if path.is_file()
    } if docs.is_dir() else {}
    with tempfile.TemporaryDirectory(prefix="dstack-docs-plan-v2-") as raw:
        scratch = Path(raw) / root.name
        scratch.mkdir()
        if docs.exists():
            shutil.copytree(docs, scratch / "docs", symlinks=True)
        if force:
            migrate_legacy_documentation(scratch)
            for source, destination in design_moves:
                migrate_known_documentation_file(scratch, source, destination)
        create_foundation(scratch)
        after = {
            path.relative_to(scratch).as_posix(): path.read_bytes()
            for path in (scratch / "docs").rglob("*")
            if path.is_file()
        }
    result: list[dict[str, Any]] = []
    for relative in sorted(set(before) | set(after)):
        old = before.get(relative)
        new = after.get(relative)
        if old == new:
            continue
        if old is None:
            if new is None:
                raise SetupError("generated documentation content is missing")
            result.append(
                {
                    "action": "create",
                    "source": None,
                    "destination": relative,
                    "expected_source_sha256": None,
                    "expected_destination_sha256": None,
                    "content_source": "generated",
                    "generated_content": new.decode("utf-8"),
                    "content_preservation": "generated",
                    "conflict_policy": "fail-if-exists",
                }
            )
        elif new is None:
            result.append(
                {
                    "action": "delete",
                    "source": relative,
                    "destination": None,
                    "expected_source_sha256": hashlib.sha256(old).hexdigest(),
                    "expected_destination_sha256": None,
                    "content_source": "existing-source",
                    "generated_content": None,
                    "content_preservation": "byte-for-byte",
                    "conflict_policy": "not-applicable",
                }
            )
        else:
            result.append(
                {
                    "action": "update",
                    "source": None,
                    "destination": relative,
                    "expected_source_sha256": None,
                    "expected_destination_sha256": hashlib.sha256(old).hexdigest(),
                    "content_source": "generated",
                    "generated_content": new.decode("utf-8"),
                    "content_preservation": "generated",
                    "conflict_policy": "replace-reviewed",
                }
            )
    return result, _setup_navigation_plan(before, after)


def _setup_gitignore_content(path: Path) -> bytes:
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = existing.splitlines()
    if "interactions.jsonl" in lines:
        return existing.encode("utf-8")
    updated = existing
    if updated and lines[-1] != "":
        updated += "\n"
    if "# dStack: local Beads audit state (not repository history)" not in lines:
        updated += "# dStack: local Beads audit state (not repository history)\n"
    updated += "interactions.jsonl\n"
    return updated.encode("utf-8")


def _setup_plan_object(
    root: Path,
    *,
    initialize: bool,
    force: bool,
    formula_actions: Mapping[str, str],
    git_index: list[dict[str, str]],
    client: BeadsClient | None,
) -> dict[str, Any]:
    initialization = []
    if not _setup_repo_path(root, ".beads").is_dir() and initialize:
        initialization = [
            {
                "action": "initialize-beads",
                "target": ".beads",
                "precondition": "absent",
                "options": {"skip_agents": True, "skip_hooks": True, "non_interactive": True},
            }
        ]
    design_moves = _setup_feature_design_moves(client) if client and force else []
    filesystem, navigation = _setup_doc_filesystem_plan(
        root, force=force, design_moves=design_moves
    )
    policy = root / ".beads/.gitignore"
    if initialization or policy.is_file():
        desired = _setup_gitignore_content(policy)
        current = policy.read_bytes() if policy.is_file() else None
        if current != desired:
            filesystem.append(
                {
                    "action": "create" if current is None else "update",
                    "source": None,
                    "destination": ".beads/.gitignore",
                    "expected_source_sha256": None,
                    "expected_destination_sha256": None if current is None else hashlib.sha256(current).hexdigest(),
                    "content_source": "generated",
                    "generated_content": desired.decode("utf-8"),
                    "content_preservation": "generated",
                    "conflict_policy": (
                        "require-identical"
                        if current is None and initialization
                        else "fail-if-exists"
                        if current is None
                        else "replace-reviewed"
                    ),
                }
            )
    formulas = []
    source_dir = package_root() / "formulas"
    for name, action in formula_actions.items():
        if action not in {"create", "update"}:
            continue
        source = source_dir / f"{name}.formula.toml"
        try:
            source_relative = source.relative_to(root).as_posix()
        except ValueError:
            source_relative = f"formulas/{source.name}"
        formulas.append({
            "name": name,
            "action": action,
            "source": source_relative,
            "destination": (root / ".beads/formulas" / source.name).relative_to(root).as_posix(),
            "source_sha256": _setup_sha256(source),
            "expected_destination_sha256": (
                _setup_sha256(root / ".beads/formulas" / source.name)
                if (root / ".beads/formulas" / source.name).is_file()
                else None
            ),
            "conflict_policy": "replace-reviewed" if action == "update" else "fail-if-different",
        })
    return canonicalize_setup_plan({
        "schema": SETUP_PLAN_SCHEMA,
        "initialization": initialization,
        "beads_issues": _setup_normalization_plan(client) if client and force else [],
        "dependencies": [],
        "supersessions": [],
        "filesystem": filesystem,
        "git_index": git_index,
        "formulas": formulas,
        "navigation_references": navigation,
    })


def setup_plan(
    root_arg: Path, *, initialize: bool, force: bool
) -> dict[str, Any]:
    root = git_root(root_arg)
    beads_exists = (root / ".beads").is_dir()
    status = run(["git", "status", "--porcelain"], cwd=root).stdout.strip()
    blocked: list[str] = []
    if status:
        blocked.append("worktree is not clean")
    if not beads_exists and not initialize:
        blocked.append("Beads initialization is not authorized")

    source_dir = package_root() / "formulas"
    display_filesystem = documentation_change_plan(root)
    formulas: dict[str, str] = {}
    for name in FORMULA_NAMES:
        source = source_dir / f"{name}.formula.toml"
        destination = root / ".beads" / "formulas" / source.name
        if not destination.exists():
            action = "create"
        elif destination.read_bytes() == source.read_bytes():
            action = "unchanged"
        elif force:
            action = "update"
        else:
            action = "conflict"
            blocked.append(f"formula differs without --force: {destination}")
        formulas[name] = action
        if action in {"create", "update"}:
            display_filesystem.append({"path": destination.relative_to(root).as_posix(), "action": action})

    client: BeadsClient | None = None
    git_index: list[dict[str, str]] = []
    beads: list[dict[str, str]] = []
    if not beads_exists:
        beads.append({"action": "initialize", "target": ".beads"})
        git_index.append({"path": ".beads/interactions.jsonl", "action": "remove-cached"})
    else:
        client = BeadsClient(root)
        client.check_version()
        if tracked(root, ".beads/interactions.jsonl"):
            git_index.append({"path": ".beads/interactions.jsonl", "action": "remove-cached"})
        ignore = root / ".beads/.gitignore"
        lines = ignore.read_text().splitlines() if ignore.is_file() else []
        if "interactions.jsonl" not in lines:
            display_filesystem.append({"path": ".beads/.gitignore", "action": "update"})
        if force:
            templates = legacy_template_artifacts(client)
            normalized = sorted(
                set(normalize_current_features(client, force=False))
                | set(normalize_current_alignments(client, force=False))
            )
            beads.extend({"action": "delete-template", "target": str(item["id"])} for item in templates)
            beads.extend({"action": "normalize", "target": issue_id} for issue_id in normalized)

    migration = (
        legacy_documentation_plan(root)
        if force
        else {
            "configured_source_moves": [],
            "referenced_content_moves": [],
            "unresolved_outside_markdown": [],
            "manual_actions": [],
        }
    )
    mutation_plan = _setup_plan_object(
        root,
        initialize=initialize,
        force=force,
        formula_actions=formulas,
        git_index=git_index,
        client=client,
    )
    payload = {
        "schema": SETUP_PLAN_SCHEMA,
        "status": "blocked" if blocked else "ready",
        "root": str(root),
        "preconditions": {"clean_worktree": not status, "blocked": blocked},
        "mutation_plan": mutation_plan,
        "plan_sha256": setup_plan_digest(mutation_plan),
        "filesystem": sorted(display_filesystem, key=lambda item: (item["path"], item["action"])),
        "git_index": git_index,
        "beads": beads,
        "formulas": formulas,
        "documentation": migration,
    }
    return payload


def _restore_setup_files(root: Path, snapshots: Mapping[str, bytes | None]) -> None:
    for relative, content in snapshots.items():
        path = root / relative
        if content is None:
            path.unlink(missing_ok=True)
            continue
        atomic_replace(path, content)


def _setup_resolve_source(root: Path, relative: str) -> Path:
    candidate = root / relative
    if candidate.is_file():
        return candidate
    package_candidate = package_root() / relative
    if package_candidate.is_file():
        return package_candidate
    raise SetupError(f"setup source file is missing: {relative}")


def _setup_check_hash(path: Path, expected: str | None, field: str) -> None:
    if expected is None:
        return
    if not path.is_file() or _setup_sha256(path) != expected:
        raise SetupError(f"setup {field} changed: {path}")


def _setup_write_filesystem(root: Path, operation: Mapping[str, Any]) -> None:
    action = str(operation["action"])
    source = operation["source"]
    destination = operation["destination"]
    source_path = root / source if source else None
    destination_path = root / destination if destination else None
    if source_path:
        _setup_check_hash(source_path, operation["expected_source_sha256"], "source")
    if destination_path and operation["expected_destination_sha256"] is not None:
        _setup_check_hash(
            destination_path,
            operation["expected_destination_sha256"],
            "destination",
        )
    if action == "delete":
        if not source_path:
            raise SetupError("setup delete operation has no source")
        source_path.unlink()
        return
    if action == "move":
        if not source_path or not destination_path:
            raise SetupError("setup move operation has incomplete paths")
        if destination_path.exists():
            if (
                operation["conflict_policy"] == "require-identical"
                and destination_path.read_bytes() == source_path.read_bytes()
            ):
                source_path.unlink()
                return
            raise SetupError(f"setup destination already exists: {destination}")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.replace(destination_path)
        return
    if not destination_path:
        raise SetupError("setup write operation has no destination")
    if action == "create" and destination_path.exists():
        if operation["conflict_policy"] == "require-identical":
            expected = str(operation["generated_content"]).encode("utf-8")
            if destination_path.read_bytes() == expected:
                return
            if destination == ".beads/.gitignore":
                current = destination_path.read_bytes()
                updated = _setup_gitignore_content(destination_path)
                if b"interactions.jsonl\n" not in current and updated == current + b"\n" + expected:
                    atomic_replace(destination_path, updated)
                    return
        raise SetupError(f"setup destination already exists: {destination}")
    if action == "update" and operation["expected_destination_sha256"] is None and destination_path.exists():
        raise SetupError(f"setup update destination has no reviewed precondition: {destination}")
    if operation["content_source"] == "generated":
        content = str(operation["generated_content"]).encode("utf-8")
    else:
        if not source_path:
            raise SetupError("setup existing-source write has no source")
        content = source_path.read_bytes()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace(destination_path, content)


def _execute_setup_plan(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    mutation = plan
    initialization = mutation["initialization"]
    if initialization:
        record = initialization[0]
        if (root / str(record["target"])).exists():
            raise SetupError("setup initialization precondition changed")
        ensure_beads(root, initialize=True)
        if not (root / str(record["target"])).is_dir():
            raise SetupError("setup initialization postcondition failed")
    elif not (root / ".beads").is_dir():
        raise SetupError("Beads is not initialized and the reviewed plan omits initialization")

    client = BeadsClient(root)
    version = client.check_version()
    for operation in mutation["beads_issues"]:
        arguments: list[str] = []
        for key, value in operation["set_metadata"].items():
            if value is None:
                arguments.extend(["--unset-metadata", key])
            else:
                arguments.extend(["--set-metadata", f"{key}={value}"])
        for key in operation["unset_metadata"]:
            arguments.extend(["--unset-metadata", key])
        for label in operation["add_labels"]:
            arguments.extend(["--add-label", label])
        for label in operation["remove_labels"]:
            arguments.extend(["--remove-label", label])
        client.update(str(operation["issue_id"]), *arguments)

    for operation in mutation["dependencies"]:
        if operation["action"] == "add":
            client.add_dependency(
                str(operation["source_id"]),
                str(operation["destination_id"]),
                relation_type=str(operation["relationship_type"]),
            )
        else:
            client.remove_dependency(str(operation["source_id"]), str(operation["destination_id"]))

    for operation in sorted(
        mutation["filesystem"],
        key=lambda item: (item["action"] == "delete", item["source"] or item["destination"] or ""),
    ):
        _setup_write_filesystem(root, operation)

    for operation in mutation["formulas"]:
        source = _setup_resolve_source(root, str(operation["source"]))
        if _setup_sha256(source) != operation["source_sha256"]:
            raise SetupError(f"setup formula source changed: {source}")
        destination = root / str(operation["destination"])
        if operation["action"] == "create" and destination.exists():
            raise SetupError(f"setup formula destination already exists: {destination}")
        if operation["action"] == "update":
            _setup_check_hash(
                destination,
                operation["expected_destination_sha256"],
                "formula destination",
            )
            if operation["conflict_policy"] != "replace-reviewed":
                raise SetupError(f"setup formula differs: {destination}")
        atomic_replace(destination, source.read_bytes())

    for operation in mutation["git_index"]:
        run(
            [
                "git",
                "rm",
                "--cached",
                "--force",
                "--ignore-unmatch",
                "--",
                str(operation["path"]),
            ],
            cwd=root,
        )

    for operation in mutation["supersessions"]:
        client.supersede(str(operation["source_id"]), str(operation["destination_id"]))

    for operation in mutation["navigation_references"]:
        path = root / str(operation["affected_path"])
        _setup_check_hash(path, operation["expected_after_sha256"], "navigation result")

    for operation in mutation["formulas"]:
        destination = root / str(operation["destination"])
        if not destination.is_file() or _setup_sha256(destination) != _setup_sha256(_setup_resolve_source(root, str(operation["source"]))):
            raise SetupError(f"setup formula postcondition failed: {destination}")
    validate_bundle(package_root() / "formulas")
    for name in FORMULA_NAMES:
        validate_formula(root, name)
    return {"status": "ok", "beads_version": version}


def apply_setup(
    root_arg: Path,
    *,
    initialize: bool,
    force: bool,
    expected_plan_sha256: str | None = None,
) -> dict[str, Any]:
    if not expected_plan_sha256:
        raise SetupError("setup plan digest is required")
    root = git_root(root_arg)
    ensure_clean_worktree(root)
    plan = setup_plan(root, initialize=initialize, force=force)
    if plan["status"] != "ready":
        raise SetupError("setup apply preconditions changed: " + "; ".join(plan["preconditions"]["blocked"]))
    mutation = canonicalize_setup_plan(plan["mutation_plan"])
    digest = setup_plan_digest(mutation)
    if digest != expected_plan_sha256 or digest != plan["plan_sha256"]:
        raise SetupError("setup authority state changed since plan; rerun setup plan and review it")

    beads_existed = (root / ".beads").is_dir()
    snapshot_paths = {
        path
        for operation in mutation["filesystem"]
        for path in (operation["source"], operation["destination"])
        if path
    }
    snapshot_paths.update(
        operation["affected_path"] for operation in mutation["navigation_references"]
    )
    snapshot_paths.update(
        path
        for operation in mutation["formulas"]
        for path in (operation["destination"],)
    )
    snapshots = {
        path: (root / path).read_bytes() if (root / path).is_file() else None
        for path in snapshot_paths
    }
    interaction_was_tracked = tracked(root, ".beads/interactions.jsonl")
    try:
        result = _execute_setup_plan(root, mutation)
        if plan.get("documentation", {}).get("unresolved_outside_markdown"):
            result["status"] = "manual-action-required"
        validate_docs(root)
        policy = root / ".beads/.gitignore"
        if "interactions.jsonl" not in policy.read_text().splitlines():
            raise SetupError("setup postcondition failed for interaction-log policy")
    except Exception as exc:
        recovery: list[str] = []
        _restore_setup_files(root, snapshots)
        recovery.append("restored setup-owned files")
        if not beads_existed and (root / ".beads").exists():
            shutil.rmtree(root / ".beads", ignore_errors=True)
            recovery.append("removed internally created .beads directory")
        if interaction_was_tracked:
            run(
                ["git", "add", "--force", "--", ".beads/interactions.jsonl"],
                cwd=root,
                check=False,
            )
        if force:
            recovery.append(
                "inspect documented migration moves and Beads normalization before retry"
            )
        raise SetupError(
            f"setup apply failed: {exc}; observed recovery: " + "; ".join(recovery)
        ) from exc
    return {"status": result.get("status", "ok"), "plan": plan, "applied": result}


def install(root_arg: Path, *, initialize: bool, force: bool) -> dict[str, Any]:
    root = git_root(root_arg)
    ensure_beads(root, initialize=initialize)
    client = BeadsClient(root)
    version = client.check_version()
    source_dir = package_root() / "formulas"
    validate_bundle(source_dir)

    # Non-forced setup is deliberately strict. A forced setup is the explicit
    # compatibility boundary and lets repair normalize legacy documentation
    # before the completed book is validated.
    if force:
        require_mdbook()
        documentation_payload: dict[str, Any] = {}
        interaction_policy: dict[str, bool] = {}
    else:
        documentation_payload = initialize_docs(root)
        interaction_policy = ensure_interaction_log_policy(root)

    installed: dict[str, str] = {}
    for name in FORMULA_NAMES:
        installed[name] = copy_formula(
            source_dir / f"{name}.formula.toml",
            root / ".beads" / "formulas" / f"{name}.formula.toml",
            force=force,
        )
        validate_formula(root, name)

    repair_payload: dict[str, Any] = {}
    if force:
        repair = repair_legacy(root, force=True)
        documentation_payload = {
            "created_documentation": repair["created_documentation"],
            "documentation_migration": repair["documentation_migration"],
            "documentation": repair["documentation"],
        }
        interaction_policy = {
            "interaction_log_untracked": bool(repair["interaction_log_untracked"]),
            "beads_gitignore_changed": bool(repair["beads_gitignore_changed"]),
        }
        repair_payload = {
            "status": repair["status"],
            "template_artifacts_removed": repair["template_artifacts_removed"],
            "molecule_items_normalized": repair["molecule_items_normalized"],
            "missing_feature_reconciliations": repair["missing_feature_reconciliations"],
        }
    return {
        "status": repair_payload.get("status", "ok") if force else "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": installed,
        "preflight": "isolated-formula-pour",
        **documentation_payload,
        **interaction_policy,
        **repair_payload,
    }


def _runtime_paths(root: Path) -> list[str]:
    tracked_paths = run(["git", "ls-files", ".beads"], cwd=root).stdout.splitlines()
    result: list[str] = []
    for path in tracked_paths:
        if path in DSTACK_UNTRACKED_BEADS_FILES or any(
            path.startswith(prefix) for prefix in BEADS_RUNTIME_DIR_PREFIXES
        ):
            result.append(path)
            continue
        relative = path.removeprefix(".beads/")
        if "/" not in relative and any(
            fnmatch.fnmatch(relative, pattern) for pattern in BEADS_RUNTIME_TOP_LEVEL_PATTERNS
        ):
            result.append(path)
    return sorted(result)


def _remote_host(remote: str) -> str | None:
    if "://" in remote:
        return urlsplit(remote).hostname
    authority, separator, _ = remote.partition(":")
    if separator and "/" not in authority:
        return authority.rsplit("@", 1)[-1] or None
    return None


def doctor(root_arg: Path, *, delivery_mode: str) -> dict[str, Any]:
    if delivery_mode not in {"merge", "pr"}:
        raise SetupError("delivery_mode must be explicitly merge or pr")
    root = git_root(root_arg)
    checks: dict[str, dict[str, Any]] = {}

    def check(name: str, recovery: str, operation) -> Any:
        try:
            value = operation()
        except (DstackError, OSError, ValueError) as exc:
            checks[name] = {
                "status": "error",
                "error": str(exc),
                "recovery": recovery,
            }
            return None
        checks[name] = {"status": "ok", "value": value}
        return value

    client: BeadsClient | None = None
    if (root / ".beads").is_dir():
        client = BeadsClient(root)
        check("beads_version", "install the pinned Beads 1.2.2 build", client.check_version)
    else:
        checks["beads_version"] = {
            "status": "error",
            "error": "Beads is not initialized",
            "recovery": "run setup apply --init",
        }

    def mdbook_version() -> str:
        version = run(["mdbook", "--version"], cwd=root).stdout.strip()
        if version != SUPPORTED_MDBOOK_VERSION_OUTPUT:
            raise SetupError(f"unsupported mdBook version; expected {SUPPORTED_MDBOOK_VERSION_OUTPUT}, found {version}")
        return version

    check("mdbook_version", "install mdBook 0.5.3", mdbook_version)
    source_dir = package_root() / "formulas"
    for name in FORMULA_NAMES:

        def formula_check(name=name) -> str:
            if client is None:
                raise SetupError("Beads is not initialized")
            installed = root / ".beads/formulas" / f"{name}.formula.toml"
            source = source_dir / f"{name}.formula.toml"
            if not installed.is_file():
                raise SetupError(f"missing installed formula: {installed}")
            if installed.read_bytes() != source.read_bytes():
                raise SetupError(f"installed formula differs from package: {installed}")
            validate_formula(root, name)
            return "available"

        check(
            f"formula:{name}",
            "run setup apply --force to reinstall and validate formulas",
            formula_check,
        )

    check(
        "documentation",
        "repair documentation and rerun docs validate",
        lambda: validate_docs(root),
    )

    def interaction_policy() -> str:
        if tracked(root, ".beads/interactions.jsonl"):
            raise SetupError(".beads/interactions.jsonl is tracked")
        ignore = root / ".beads/.gitignore"
        if not ignore.is_file() or "interactions.jsonl" not in ignore.read_text().splitlines():
            raise SetupError(".beads/.gitignore does not ignore interactions.jsonl")
        return "local-only"

    check(
        "interaction_policy",
        "run setup apply --force to restore the local interaction-log policy",
        interaction_policy,
    )

    def reconciliation_check() -> list[str]:
        if client is None:
            raise SetupError("Beads is not initialized")
        missing = missing_feature_reconciliations(client)
        if missing:
            raise SetupError("missing feature reconciliations: " + ", ".join(missing))
        return []

    check(
        "feature_reconciliations",
        "author the listed delivered-feature index.md records",
        reconciliation_check,
    )

    def worktree_check() -> int:
        records = worktree_records(root)
        branches: set[str] = set()
        anomalies: list[str] = []
        for record in records:
            path = str(record.get("worktree") or "")
            branch = str(record.get("branch") or "")
            if not path or not Path(path).is_dir() or record.get("prunable"):
                anomalies.append(path or "<missing path>")
            if branch and branch in branches:
                anomalies.append(f"duplicate branch {branch}")
            branches.add(branch)
        if anomalies:
            raise SetupError("worktree anomalies: " + ", ".join(anomalies))
        return len(records)

    check("worktrees", "prune or repair the listed native Git worktrees", worktree_check)

    def runtime_check() -> list[str]:
        paths = _runtime_paths(root)
        if paths:
            raise SetupError("tracked Beads runtime paths: " + ", ".join(paths))
        return []

    check("runtime_paths", "remove runtime paths from the Git index", runtime_check)

    def remote_check() -> str:
        result = run(["git", "remote", "get-url", "origin"], cwd=root, check=False)
        remote = result.stdout.strip()
        if result.returncode or not remote:
            raise SetupError("target origin remote is missing")
        if (_remote_host(remote) or "").casefold() != "github.com":
            raise SetupError(f"target remote is not GitHub-compatible: {remote}")
        probe = run(["git", "ls-remote", "--heads", "origin"], cwd=root, check=False)
        if probe.returncode:
            raise SetupError(probe.stderr.strip() or "target origin remote is unreachable")
        return remote

    def github_check() -> str:
        result = run(
            ["gh", "auth", "status", "--hostname", "github.com"],
            cwd=root,
            check=False,
        )
        if result.returncode:
            raise SetupError(result.stderr.strip() or "GitHub CLI authentication failed")
        return "authenticated"

    def pr_gate_check() -> str:
        result = run(["bd", "gate", "create", "--help"], cwd=root, check=False)
        if result.returncode or "gh:pr" not in result.stdout:
            raise SetupError("installed Beads does not advertise native gh:pr gate capability")
        return "gh:pr"

    if delivery_mode == "pr":
        remote = check("remote", "configure a reachable GitHub target remote", remote_check)
        if remote:
            check("github", "install gh and authenticate for the GitHub target", github_check)
        else:
            checks["github"] = {
                "status": "not-applicable",
                "value": "blocked by target remote check",
            }
        check("pr_gate", "install Beads with native gh:pr gate support", pr_gate_check)
    else:
        for name in ("remote", "github", "pr_gate"):
            checks[name] = {
                "status": "not-applicable",
                "value": "merge delivery mode",
            }
    failed = [name for name, result in checks.items() if result["status"] == "error"]
    return {
        "status": "ok" if not failed else "error",
        "root": str(root),
        "delivery_mode": delivery_mode,
        "checks": checks,
        "failed": failed,
    }


def all_issue_inventory(client: BeadsClient) -> list[dict[str, Any]]:
    result = run(
        [
            "bd",
            "list",
            "--all",
            "--include-templates",
            "--include-gates",
            "--limit",
            "0",
            "--json",
        ],
        cwd=client.root,
    )
    return as_items(parse_json(result.stdout, context="bd list repair inventory"))


def legacy_template_artifacts(client: BeadsClient) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for summary in all_issue_inventory(client):
        issue_id = str(summary.get("id") or "")
        if not any(issue_id == name or issue_id.startswith(f"{name}.") for name in FORMULA_NAMES):
            continue
        issue = client.show(issue_id)
        if issue.get("is_template") is not True:
            raise SetupError(f"reserved dstack template ID is used by non-template issue {issue_id}")
        result.append(issue)
    return result


def add_gitignore_line(path: Path, line: str, *, header: str | None = None) -> bool:
    existing = path.read_text().splitlines() if path.exists() else []
    if line in existing:
        return False
    updated = path.read_text(encoding="utf-8") if path.exists() else ""
    if updated and existing[-1] != "":
        updated += "\n"
    if header and header not in existing:
        updated += header + "\n"
    updated += line + "\n"
    atomic_replace(path, updated.encode())
    return True


def ensure_interaction_log_policy(root: Path) -> dict[str, bool]:
    """Keep the Beads audit log local under dStack's Git-decoupling policy."""

    ignore_changed = add_gitignore_line(
        root / ".beads" / ".gitignore",
        "interactions.jsonl",
        header="# dStack: local Beads audit state (not repository history)",
    )
    was_tracked = tracked(root, ".beads/interactions.jsonl")
    if was_tracked:
        run(
            [
                "git",
                "rm",
                "--cached",
                "--force",
                "--ignore-unmatch",
                "--",
                ".beads/interactions.jsonl",
            ],
            cwd=root,
        )
    return {
        "interaction_log_untracked": was_tracked,
        "beads_gitignore_changed": ignore_changed,
    }


def tracked(root: Path, path: str) -> bool:
    return (
        run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=root,
            check=False,
        ).returncode
        == 0
    )


def migrate_feature_design(
    root: Path,
    feature: Mapping[str, Any],
    *,
    slug: str,
    design_path: str,
) -> None:
    legacy = f"docs/features/{slug}/design.md"
    canonical = canonical_feature_design_path(slug)
    if design_path not in (legacy, canonical):
        raise SetupError(f"unsupported feature design migration path: {design_path}; expected {legacy} or {canonical}")

    try:
        migrate_known_documentation_file(root, design_path, canonical)
    except DstackError as exc:
        if design_path == legacy and "source and canonical target are missing" in str(exc):
            raise SetupError("legacy feature design is missing") from exc
        raise SetupError(str(exc)) from exc
    destination = root / canonical
    title = str(feature.get("title") or slug).removeprefix("Feature: ")
    ensure_feature_navigation(
        root,
        slug=slug,
        title=title,
        reconciled=destination.with_name("index.md").is_file(),
    )


def missing_feature_reconciliations(client: BeadsClient) -> list[str]:
    missing: list[str] = []
    for feature in client.list(all_statuses=True, labels=["workflow:feature"]):
        if feature.get("status") != "closed":
            continue
        slug = feature_slug(feature)
        if not slug:
            continue
        design = client.root / canonical_feature_design_path(slug)
        reconciliation = design.with_name("index.md")
        if design.is_file() and not reconciliation.is_file():
            missing.append(reconciliation.relative_to(client.root).as_posix())
    return sorted(missing)


def normalize_current_features(client: BeadsClient, *, force: bool) -> list[str]:
    changed: list[str] = []
    roots = client.list(all_statuses=True, labels=["workflow:feature"])
    for root in roots:
        root_id = str(root.get("id") or "")
        if not root_id:
            continue
        slug = feature_slug(root)
        base = root_metadata_value(root, "dstack.base_branch", "base_branch")
        design = root_metadata_value(root, "dstack.design_path", "design_path")
        root_args: list[str] = []
        root_metadata = issue_metadata(root)
        if base and not root_metadata.get("dstack.base_branch"):
            root_args.extend(["--set-metadata", f"dstack.base_branch={base}"])
        if slug:
            canonical_design = canonical_feature_design_path(slug)
            if design != canonical_design or not root_metadata.get("dstack.design_path"):
                if force:
                    migrate_feature_design(
                        client.root,
                        root,
                        slug=slug,
                        design_path=design or canonical_design,
                    )
                root_args.extend(["--set-metadata", f"dstack.design_path={canonical_design}"])
            elif force and not (client.root / canonical_design).is_file():
                raise SetupError("canonical feature design is missing")
        for key in ("feature_slug", "base_branch", "branch", "worktree_path", "adopted_from"):
            if key in issue_metadata(root):
                root_args.extend(["--unset-metadata", key])
        for label in issue_labels(root):
            if label == "dstack:delivery-ready":
                root_args.extend(["--remove-label", label])
        if root_args:
            if not force:
                changed.append(root_id)
            else:
                client.update(root_id, *root_args)
                changed.append(root_id)

        children = client.children(root_id)
        for child in children:
            child_id = str(child.get("id") or "")
            child_args: list[str] = []
            metadata = issue_metadata(child)
            for key in ("dstack_step", "base_branch", "design_path"):
                if key in metadata:
                    child_args.extend(["--unset-metadata", key])
            for label in issue_labels(child):
                if label == "feature:{{feature_slug}}" or (slug and label == f"feature:{slug}"):
                    child_args.extend(["--remove-label", label])
            if child_args:
                if force:
                    client.update(child_id, *child_args)
                changed.append(child_id)

        implementation = next(
            (child for child in children if has_label(child, FEATURE_STEPS["implementation"])),
            None,
        )
        if implementation:
            for task in client.children(str(implementation["id"])):
                task_args: list[str] = []
                for label in issue_labels(task):
                    if label == "feature:{{feature_slug}}" or (slug and label == f"feature:{slug}"):
                        task_args.extend(["--remove-label", label])
                if task_args:
                    if force:
                        client.update(str(task["id"]), *task_args)
                    changed.append(str(task["id"]))
    return sorted(set(changed))


def normalize_current_alignments(client: BeadsClient, *, force: bool) -> list[str]:
    changed: list[str] = []
    roots = client.list(all_statuses=True, labels=["workflow:project-alignment"])
    for root in roots:
        root_id = str(root.get("id") or "")
        if not root_id:
            continue
        root_args: list[str] = []
        target = root_metadata_value(root, "dstack.target_branch", "target_branch")
        scope = root_metadata_value(root, "dstack.scope", "scope")
        root_metadata = issue_metadata(root)
        if target and not root_metadata.get("dstack.target_branch"):
            root_args.extend(["--set-metadata", f"dstack.target_branch={target}"])
        if scope and not root_metadata.get("dstack.scope"):
            root_args.extend(["--set-metadata", f"dstack.scope={scope}"])
        for key in ("audit_slug", "target_branch", "branch", "worktree_path"):
            if key in issue_metadata(root):
                root_args.extend(["--unset-metadata", key])
        for label in issue_labels(root):
            if label == "dstack:delivery-ready":
                root_args.extend(["--remove-label", label])
        if root_args:
            if force:
                client.update(root_id, *root_args)
            changed.append(root_id)

        for child in client.children(root_id):
            child_args: list[str] = []
            for key in ("dstack_step", "target_branch", "scope"):
                if key in issue_metadata(child):
                    child_args.extend(["--unset-metadata", key])
            for label in issue_labels(child):
                if label.startswith("audit:"):
                    child_args.extend(["--remove-label", label])
            if child_args:
                if force:
                    client.update(str(child["id"]), *child_args)
                changed.append(str(child["id"]))
    return sorted(set(changed))


def repair_legacy(root_arg: Path, *, force: bool) -> dict[str, Any]:
    root = git_root(root_arg)
    client = BeadsClient(root)
    client.check_version()
    templates = legacy_template_artifacts(client)
    documentation_plan = legacy_documentation_plan(root)

    if force:
        documentation_migration = migrate_legacy_documentation(root)
        created_documentation = create_foundation(root)
    else:
        documentation_migration = documentation_plan
        created_documentation = []

    normalized = sorted(
        set(normalize_current_features(client, force=force)) | set(normalize_current_alignments(client, force=force))
    )
    missing_reconciliations = missing_feature_reconciliations(client)
    interaction_tracked = tracked(root, ".beads/interactions.jsonl")
    beads_ignore = root / ".beads" / ".gitignore"
    ignore_lines = beads_ignore.read_text().splitlines() if beads_ignore.exists() else []
    interaction_ignore_missing = "interactions.jsonl" not in ignore_lines
    documentation_repairs = bool(
        documentation_plan["configured_source_moves"]
        or documentation_plan["referenced_content_moves"]
        or documentation_plan["unresolved_outside_markdown"]
    )

    if (
        templates or normalized or interaction_tracked or interaction_ignore_missing or documentation_repairs
    ) and not force:
        return {
            "status": "repair-required",
            "template_artifacts": [item["id"] for item in templates],
            "molecule_items_to_normalize": normalized,
            "interaction_log_tracked": interaction_tracked,
            "interaction_log_ignore_missing": interaction_ignore_missing,
            "missing_feature_reconciliations": missing_reconciliations,
            "documentation_migration": documentation_plan,
        }

    removed: list[str] = []
    if templates:
        ids = sorted(str(item["id"]) for item in templates)
        run(["bd", "delete", *ids, "--dry-run", "--json"], cwd=root)
        run(["bd", "delete", *ids, "--force", "--json"], cwd=root)
        removed = ids

    interaction_policy = ensure_interaction_log_policy(root)
    documentation = validate_docs(root)

    return {
        "status": ("manual-action-required" if documentation_migration["unresolved_outside_markdown"] else "ok"),
        "template_artifacts_removed": removed,
        "molecule_items_normalized": normalized,
        "missing_feature_reconciliations": missing_reconciliations,
        "created_documentation": created_documentation,
        "documentation_migration": documentation_migration,
        "documentation": documentation,
        **interaction_policy,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for command in ("plan", "apply"):
        setup_parser = sub.add_parser(command)
        setup_parser.add_argument("--root", type=Path, default=Path.cwd())
        setup_parser.add_argument("--init", action="store_true")
        setup_parser.add_argument("--force", action="store_true")
        if command == "apply":
            setup_parser.add_argument("--plan-digest", required=True)

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--root", type=Path, default=Path.cwd())
    doctor_parser.add_argument(
        "--delivery-mode",
        choices=("merge", "pr"),
        required=True,
        help="delivery profile to validate explicitly",
    )

    repair_parser = sub.add_parser("repair-legacy")
    repair_parser.add_argument("--root", type=Path, default=Path.cwd())
    repair_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            payload = setup_plan(args.root, initialize=args.init, force=args.force)
        elif args.command == "apply":
            payload = apply_setup(
                args.root,
                initialize=args.init,
                force=args.force,
                expected_plan_sha256=args.plan_digest,
            )
        elif args.command == "doctor":
            payload = doctor(args.root, delivery_mode=args.delivery_mode)
        else:
            payload = repair_legacy(args.root, force=args.force)
    except DstackError as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if payload.get("status") in {"ok", "ready"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
