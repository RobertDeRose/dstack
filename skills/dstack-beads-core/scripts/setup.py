#!/usr/bin/env python3
"""Install, validate, and explicitly repair dstack's Beads integration."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence, cast
from contextlib import contextmanager
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
    SUPPORTED_BEADS_VERSION_OUTPUT,
    alignment_identity_values,
    alignment_roots_from_inventory,
    canonical_feature_design_path,
    dependency_records,
    ensure_clean_worktree,
    feature_identity_values,
    feature_roots_from_inventory,
    feature_slug,
    git_common_dir,
    git_root,
    has_label,
    issue_labels,
    issue_metadata,
    issue_parent,
    issue_type,
    is_alignment_root,
    is_feature_root,
    is_legacy_feature_root,
    parse_json,
    root_metadata_value,
    run,
    require_locked_runtime,
    worktree_records,
)

from dstack_commands import (
    BEADS_RUNTIME_DIR_PREFIXES,
    BEADS_RUNTIME_TOP_LEVEL_PATTERNS,
    BEADS_SENSITIVE_BASENAMES,
    DSTACK_UNTRACKED_BEADS_FILES,
)

FORMULA_NAMES = ("dstack-feature", "dstack-project-alignment")
SUPPORTED_MDBOOK_VERSION_OUTPUT = "mdbook v0.5.3"
SUPPORTED_PYTHON_VERSION_OUTPUT = "Python 3.14.7"
SETUP_PLAN_SCHEMA = "dstack.setup-plan/v4"
SETUP_PLAN_FIELDS = {
    "schema",
    "authority",
    "initialization",
    "beads_issues",
    "dependencies",
    "supersessions",
    "template_deletions",
    "filesystem",
    "git_index",
    "formulas",
    "navigation_references",
}
SETUP_PLAN_ENVELOPE_FIELDS = {
    "schema",
    "status",
    "root",
    "request",
    "preconditions",
    "authority",
    "mutation_plan",
    "plan_sha256",
    "filesystem",
    "git_index",
    "beads",
    "formulas",
    "documentation",
}
SETUP_RELATIONS = {"blocks", "parent-child", "relates-to", "supersedes", "superseded-by"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_BEADS_CLIENT_TYPE = BeadsClient


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


def _setup_authority(value: Any) -> dict[str, str]:
    item = _setup_fields(
        value,
        {
            "controller_sha256",
            "controller_state",
            "python_version",
            "beads_version",
            "mdbook_version",
        },
        "authority",
    )
    result = {
        key: _setup_text(item[key], f"authority.{key}")
        for key in (
            "controller_sha256",
            "controller_state",
            "python_version",
            "beads_version",
            "mdbook_version",
        )
    }
    _setup_hash(result["controller_sha256"], "authority.controller_sha256")
    if result["controller_state"] not in {"clean", "dirty", "unversioned"}:
        raise SetupError("setup controller authority state is invalid")
    expected = {
        "python_version": SUPPORTED_PYTHON_VERSION_OUTPUT,
        "beads_version": SUPPORTED_BEADS_VERSION_OUTPUT,
        "mdbook_version": SUPPORTED_MDBOOK_VERSION_OUTPUT,
    }
    for key, supported in expected.items():
        if result[key] != supported:
            raise SetupError(f"setup authority {key} must be {supported}")
    return result


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


def _setup_template_deletions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SetupError("setup plan template_deletions must be an array")
    result: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        item = _setup_fields(
            raw,
            {"action", "issue_id", "precondition"},
            f"template_deletions[{index}]",
        )
        issue_id = _setup_id(item["issue_id"], f"template_deletions[{index}].issue_id")
        if not any(issue_id == name or issue_id.startswith(f"{name}.") for name in FORMULA_NAMES):
            raise SetupError(f"setup template deletion uses non-reserved ID: {issue_id}")
        if item["action"] != "delete" or item["precondition"] != "is-template":
            raise SetupError("setup template deletion record is invalid")
        result.append({"action": "delete", "issue_id": issue_id, "precondition": "is-template"})
    if len({item["issue_id"] for item in result}) != len(result):
        raise SetupError("duplicate setup template deletion")
    return sorted(result, key=lambda item: item["issue_id"])


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
        "authority": _setup_authority(value["authority"]),
        "initialization": _setup_initialization(value["initialization"]),
        "beads_issues": _setup_beads_issues(value["beads_issues"]),
        "dependencies": _setup_dependencies(value["dependencies"]),
        "supersessions": _setup_supersessions(value["supersessions"]),
        "template_deletions": _setup_template_deletions(value["template_deletions"]),
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


def _setup_migration_paths(root_arg: Path, digest: str) -> tuple[Path, Path]:
    if not SHA256_RE.fullmatch(digest):
        raise SetupError("setup migration ID must be a SHA-256 digest")
    root = git_root(root_arg)
    common = git_common_dir(root)
    artifacts = common / "dstack" / "setup" / digest.lower()
    worktree = root.parent / f"{root.name}.dstack-setup-{digest.lower()}"
    try:
        artifacts.resolve(strict=False).relative_to(common)
        worktree.resolve(strict=False).relative_to(root.parent.resolve())
    except ValueError as exc:
        raise SetupError("setup migration paths are not repository-contained") from exc
    return artifacts, worktree


def _setup_plan_request(*, initialize: bool, force: bool) -> dict[str, bool]:
    return {"initialize": initialize, "force": force}


def _canonicalize_setup_plan_envelope(
    value: Any,
    *,
    root: Path,
    initialize: bool,
    force: bool,
    expected_digest: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SETUP_PLAN_ENVELOPE_FIELDS:
        raise SetupError("saved setup plan has invalid fields")
    if value["schema"] != SETUP_PLAN_SCHEMA:
        raise SetupError(f"saved setup plan schema must be {SETUP_PLAN_SCHEMA}")
    if value["status"] != "ready":
        raise SetupError("saved setup plan is not ready")
    request = value["request"]
    if not isinstance(request, dict) or set(request) != {"initialize", "force"}:
        raise SetupError("saved setup plan request is invalid")
    if request != _setup_plan_request(initialize=initialize, force=force):
        raise SetupError("saved setup plan requested mode differs from apply")
    saved_root = value["root"]
    if not isinstance(saved_root, str) or Path(saved_root).resolve() != root.resolve():
        raise SetupError("saved setup plan root differs from apply")
    preconditions = value["preconditions"]
    if (
        not isinstance(preconditions, dict)
        or set(preconditions) != {"clean_worktree", "blocked"}
        or preconditions["clean_worktree"] is not True
        or preconditions["blocked"] != []
    ):
        raise SetupError("saved setup plan preconditions are not ready")
    mutation = canonicalize_setup_plan(value["mutation_plan"])
    if value["authority"] != mutation["authority"]:
        raise SetupError("saved setup plan authority does not match its mutation")
    digest = setup_plan_digest(mutation)
    if digest != expected_digest.lower() or value["plan_sha256"] != digest:
        raise SetupError("saved setup plan digest does not match the reviewed digest")
    return {**value, "mutation_plan": mutation, "plan_sha256": digest}


def _read_reviewed_setup_plan(
    path: Path,
    *,
    root: Path,
    initialize: bool,
    force: bool,
    expected_digest: str,
) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise SetupError(f"saved setup plan is not a regular file: {path}")
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupError(f"saved setup plan cannot be read: {path}") from exc
    return (
        _canonicalize_setup_plan_envelope(
            value,
            root=root,
            initialize=initialize,
            force=force,
            expected_digest=expected_digest,
        ),
        content,
    )


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


class SetupSignal(KeyboardInterrupt):
    def __init__(self, signum: int):
        super().__init__(f"setup interrupted by signal {signal.Signals(signum).name}")
        self.signum = signum


@contextmanager
def _setup_signal_boundary():
    previous = {}

    def interrupt(signum: int, _frame: Any) -> None:
        raise SetupSignal(signum)

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, interrupt)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _setup_repo_path(root: Path, relative: str) -> Path:
    """Resolve one setup-managed path without leaving its repository root."""

    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise SetupError(f"setup managed path {relative!r} escapes the repository")
    normalized = "/".join(part for part in pure.parts if part not in {"", "."})
    if not normalized:
        raise SetupError("setup managed path is empty")
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*PurePosixPath(normalized).parts)
    try:
        candidate.resolve(strict=False).relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise SetupError(
            f"setup managed path {normalized!r} is not physically contained within repository {resolved_root}"
        ) from exc
    return candidate


def _validate_setup_tree(root: Path, relative: str) -> Path:
    base = _setup_repo_path(root, relative)
    if base.is_dir():
        for path in base.rglob("*"):
            _setup_repo_path(root, path.relative_to(root.resolve()).as_posix())
    return base


def package_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _controller_authority() -> dict[str, str]:
    root = package_root()
    scripts = root / "skills/dstack-beads-core/scripts"
    sources = sorted(scripts.glob("*.py"))
    formulas = sorted((root / "formulas").glob("*.formula.toml"))
    authority_paths = [root / name for name in ("bin/dstack", "mise.toml", "mise.lock", "pyproject.toml")]
    authority_paths.extend([*sources, *formulas])
    invalid = [path for path in authority_paths if path.is_symlink() or not path.is_file()]
    if invalid:
        raise SetupError(
            "controller authority source is missing or invalid: " + ", ".join(str(path) for path in invalid)
        )

    digest = hashlib.sha256()
    for path in authority_paths:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    repository = run(["git", "rev-parse", "--show-toplevel"], cwd=root, check=False)
    if repository.returncode:
        state = "unversioned"
    else:
        repository_root = Path(repository.stdout.strip()).resolve()
        try:
            package_relative = root.relative_to(repository_root)
        except ValueError as exc:
            raise SetupError("controller package is outside its reported Git repository") from exc
        pathspecs = [
            (package_relative / "skills/dstack-beads-core/scripts").as_posix(),
            (package_relative / "formulas").as_posix(),
            *(
                (package_relative / name).as_posix()
                for name in ("bin/dstack", "mise.toml", "mise.lock", "pyproject.toml")
            ),
        ]
        if run(["git", "ls-files", "-u", "--", *pathspecs], cwd=repository_root).stdout.strip():
            raise SetupError("unmerged controller authority source; resolve the package checkout before setup")
        status = run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *pathspecs],
            cwd=repository_root,
        ).stdout.strip()
        state = "dirty" if status else "clean"
    return {"controller_sha256": digest.hexdigest(), "controller_state": state}


def _setup_beads_command(command: Sequence[str], database: Path | None) -> list[str]:
    result = list(command)
    if database is not None:
        result.extend(["--db", str(database)])
    return result


def _setup_run(command: Sequence[str], *, cwd: Path, metrics: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    if metrics is not None and command and Path(str(command[0])).name == "bd":
        metrics["beads_command_count"] = int(metrics.get("beads_command_count", 0)) + 1
    return run(command, cwd=cwd, **kwargs)


def _setup_command_hook(metrics: dict[str, Any] | None) -> Any:
    if metrics is None:
        return None

    def count(command: Sequence[str]) -> None:
        if command and Path(str(command[0])).name == "bd":
            metrics["beads_command_count"] = int(metrics.get("beads_command_count", 0)) + 1

    return count


def _setup_client(
    root: Path,
    database: Path | None = None,
    *,
    command_hook: Any = None,
) -> BeadsClient:
    if database is None and command_hook is None:
        return BeadsClient(root)
    return BeadsClient(root, database=database, command_hook=command_hook)


def _setup_database_path(root: Path, *, initialize: bool = False) -> Path:
    beads = _setup_repo_path(root, ".beads")
    candidates: list[Path] = []
    if beads.is_dir():
        for name in ("embeddeddolt", "dolt", "proxieddb"):
            candidate = beads / name
            if candidate.is_symlink():
                raise SetupError(f"Beads database runtime must not be a symlink: {candidate}")
            if candidate.is_dir():
                candidates.append(candidate)
    if len(candidates) > 1:
        raise SetupError("multiple contained Beads database runtimes found: " + ", ".join(map(str, candidates)))
    if candidates:
        return candidates[0].resolve()
    if initialize:
        return _setup_repo_path(root, ".beads/embeddeddolt")
    raise SetupError(f"contained Beads database runtime is missing under {beads}")


def _validate_setup_database(root: Path, database: Path, *, allow_absent: bool = False) -> Path:
    beads = _setup_repo_path(root, ".beads").resolve()
    target = database.resolve()
    try:
        target.relative_to(beads)
    except ValueError as exc:
        raise SetupError(f"Beads database must be contained under {beads}: {database}") from exc
    if database.is_symlink():
        raise SetupError(f"Beads database runtime must not be a symlink: {database}")
    if not allow_absent and not target.is_dir():
        raise SetupError(f"Beads database runtime is missing: {target}")
    return target


def _runtime_authority(
    root: Path,
    *,
    database: Path | None = None,
    command_hook: Any = None,
) -> dict[str, str]:
    python_version = f"Python {platform.python_version()}"
    if python_version != SUPPORTED_PYTHON_VERSION_OUTPUT:
        raise SetupError(
            f"unsupported Python version; expected {SUPPORTED_PYTHON_VERSION_OUTPUT}, found {python_version}; "
            "run through `mise --cd <dstack-package-root> exec --locked`"
        )
    beads_version = _setup_client(root, database, command_hook=command_hook).check_version()
    mdbook = require_mdbook()
    mdbook_version = run([mdbook, "--version"], cwd=root).stdout.strip()
    if mdbook_version != SUPPORTED_MDBOOK_VERSION_OUTPUT:
        raise SetupError(
            f"unsupported mdBook version; expected {SUPPORTED_MDBOOK_VERSION_OUTPUT}, found {mdbook_version}"
        )
    return {
        "python_version": python_version,
        "beads_version": beads_version,
        "mdbook_version": mdbook_version,
    }


def _current_setup_authority(
    root: Path,
    *,
    database: Path | None = None,
    command_hook: Any = None,
) -> dict[str, str]:
    return _setup_authority(
        {
            **_controller_authority(),
            **_runtime_authority(root, database=database, command_hook=command_hook),
        }
    )


def ensure_beads(
    root: Path,
    *,
    initialize: bool,
    database: Path | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    if database is None and (root / ".beads").is_dir():
        return
    if database is not None and database.is_dir():
        return
    if not initialize:
        raise SetupError("Beads is not initialized; rerun setup after authorization")
    _setup_run(
        _setup_beads_command(
            [
                "bd",
                "init",
                "--quiet",
                "--skip-agents",
                "--skip-hooks",
                "--non-interactive",
                *(["--prefix", "beads"] if database is not None else []),
            ],
            database,
        ),
        cwd=root,
        metrics=metrics,
    )
    if database is not None:
        if not database.is_dir():
            raise SetupError("bd init completed without creating the selected Beads database")
    elif not (root / ".beads").is_dir():
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
    database: Path | None = None,
    seed: bool = True,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _setup_run(
        _setup_beads_command(["bd", "formula", "show", name, "--json"], database),
        cwd=root,
        env=env,
        metrics=metrics,
    )
    payload = parse_json(result.stdout, context=f"bd formula show {name}")
    if not isinstance(payload, dict):
        raise SetupError(f"bd formula show returned a non-object for {name}")
    validate_formula_contract(name, payload)
    if seed:
        _setup_run(
            _setup_beads_command(["bd", "mol", "seed", name, *formula_vars(name)], database),
            cwd=root,
            env=env,
            metrics=metrics,
        )
    return payload


def validate_bundle(source_dir: Path, *, metrics: dict[str, Any] | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="dstack-preflight-") as raw:
        scratch = Path(raw)
        run(["git", "init", "-q"], cwd=scratch)
        scratch_database = scratch / ".beads/embeddeddolt"
        _setup_run(
            _setup_beads_command(
                [
                    "bd",
                    "init",
                    "--quiet",
                    "--skip-agents",
                    "--skip-hooks",
                    "--non-interactive",
                ],
                scratch_database,
            ),
            cwd=scratch,
            metrics=metrics,
        )
        formula_dir = scratch / ".beads" / "formulas"
        formula_dir.mkdir(parents=True, exist_ok=True)
        for name in FORMULA_NAMES:
            shutil.copyfile(
                source_dir / f"{name}.formula.toml",
                formula_dir / f"{name}.formula.toml",
            )
        for name in FORMULA_NAMES:
            validate_formula(scratch, name, database=scratch_database, metrics=metrics)
            result = _setup_run(
                _setup_beads_command(["bd", "mol", "pour", name, *formula_vars(name), "--json"], scratch_database),
                cwd=scratch,
                metrics=metrics,
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


def _prepare_setup_artifacts(path: Path, plan_bytes: bytes) -> Path:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise SetupError(f"setup artifact path is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    plan_path = path / "plan.json"
    if plan_path.exists() and (plan_path.is_symlink() or not plan_path.is_file()):
        raise SetupError(f"saved setup plan artifact is not a regular file: {plan_path}")
    if plan_path.exists() and plan_path.read_bytes() != plan_bytes:
        raise SetupError(f"saved setup plan artifact differs from input: {plan_path}")
    if not plan_path.exists():
        atomic_replace(plan_path, plan_bytes)
    plan_path.chmod(0o600)
    return plan_path


def _setup_migration_worktree_record(root_arg: Path, digest: str) -> tuple[Path, dict[str, str | bool] | None]:
    root = git_root(root_arg)
    _, worktree = _setup_migration_paths(root, digest)
    records = [
        record
        for record in worktree_records(root)
        if isinstance(record.get("worktree"), str) and Path(str(record["worktree"])).resolve() == worktree.resolve()
    ]
    if len(records) > 1:
        raise SetupError(f"setup migration worktree registration is ambiguous: {worktree}")
    return worktree, records[0] if records else None


def _prepare_setup_worktree(root_arg: Path, digest: str) -> Path:
    root = git_root(root_arg)
    _, worktree = _setup_migration_paths(root, digest)
    head = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    records = worktree_records(root)
    matching = [
        record
        for record in records
        if isinstance(record.get("worktree"), str) and Path(str(record["worktree"])).resolve() == worktree.resolve()
    ]
    if len(matching) > 1:
        raise SetupError(f"setup migration worktree registration is ambiguous: {worktree}")
    if worktree.is_symlink():
        raise SetupError(f"setup migration worktree path must not be a symlink: {worktree}")
    if matching:
        record = matching[0]
        if not record.get("detached") or record.get("branch") or record.get("HEAD") != head:
            raise SetupError(f"setup migration worktree identity changed: {worktree}")
        if not worktree.is_dir():
            raise SetupError(f"setup migration worktree is missing: {worktree}")
        ensure_clean_worktree(worktree)
        return worktree.resolve()
    if worktree.exists():
        raise SetupError(f"setup migration worktree path exists but is not registered: {worktree}")
    run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], cwd=root)
    records = worktree_records(root)
    matching = [
        record
        for record in records
        if isinstance(record.get("worktree"), str) and Path(str(record["worktree"])).resolve() == worktree.resolve()
    ]
    if len(matching) != 1 or not matching[0].get("detached") or matching[0].get("branch"):
        raise SetupError(f"created setup migration worktree is not detached: {worktree}")
    if matching[0].get("HEAD") != head:
        raise SetupError(f"created setup migration worktree has unexpected HEAD: {worktree}")
    return worktree.resolve()


def _relocate_initialized_beads_files(root: Path, database: Path) -> None:
    source = database.parent
    destination = _setup_repo_path(root, ".beads")
    if source.resolve() == destination.resolve():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.resolve() == database.resolve():
            continue
        target = destination / path.name
        if target.exists():
            if path.is_file() and target.is_file() and path.read_bytes() == target.read_bytes():
                path.unlink()
                continue
            raise SetupError(f"initialized Beads file collides in migration worktree: {target}")
        if path.is_symlink() or not path.is_file():
            raise SetupError(f"initialized Beads file is not a regular file: {path}")
        path.replace(target)


def _backup_pointer_snapshots(beads: Path) -> dict[Path, bytes]:
    if beads.is_symlink() or not beads.is_dir():
        raise SetupError(f"Beads directory is not a contained directory: {beads}")
    snapshots: dict[Path, bytes] = {}
    for path in beads.glob("dolt-backup*.json"):
        if path.is_symlink() or not path.is_file():
            raise SetupError(f"Beads backup pointer is not a regular file: {path}")
        snapshots[path] = path.read_bytes()
    return snapshots


def _restore_backup_pointers(beads: Path, snapshots: Mapping[Path, bytes]) -> None:
    expected = set(snapshots)
    for path in beads.glob("dolt-backup*.json"):
        if path not in expected:
            if path.is_dir() and not path.is_symlink():
                raise SetupError(f"unexpected Beads backup pointer directory: {path}")
            path.unlink(missing_ok=True)
    for path, content in snapshots.items():
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise SetupError(f"Beads backup pointer cannot be restored safely: {path}")
        atomic_replace(path, content)


def _normalize_beads_value(value: Any) -> Any:
    transient = {
        "closed_at",
        "comment_count",
        "created_at",
        "created_by",
        "dependency_count",
        "dependent_count",
        "updated_at",
    }
    if isinstance(value, dict):
        return {
            str(key): _normalize_beads_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in transient
        }
    if isinstance(value, list):
        normalized = [_normalize_beads_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    return value


def _normalize_setup_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_beads_value(issue)
    if not isinstance(normalized, dict):
        raise SetupError("Beads issue did not normalize to an object")
    normalized.pop("dependencies", None)
    normalized.pop("dependency_count", None)
    normalized.pop("dependent_count", None)
    normalized["description"] = str(issue.get("description") or "")
    normalized["acceptance_criteria"] = str(issue.get("acceptance_criteria") or "")
    normalized["issue_type"] = issue_type(issue)
    normalized["owner"] = str(issue.get("owner") or "")
    normalized["labels"] = sorted(issue_labels(issue))
    normalized["metadata"] = issue_metadata(issue)
    normalized["parent"] = issue_parent(issue)
    normalized["relationships"] = [list(item) for item in _setup_relationships(issue)]
    return normalized


def _setup_inventory_core_complete(issue: Mapping[str, Any]) -> bool:
    issue_type_value = issue.get("issue_type") or issue.get("type")
    return (
        isinstance(issue.get("id"), str)
        and bool(issue["id"])
        and isinstance(issue.get("title"), str)
        and isinstance(issue.get("status"), str)
        and isinstance(issue.get("priority"), int)
        and not isinstance(issue.get("priority"), bool)
        and isinstance(issue_type_value, str)
        and bool(issue_type_value)
    )


def _validate_setup_inventory_issue(issue: Any) -> Mapping[str, Any]:
    if not isinstance(issue, Mapping) or not _setup_inventory_core_complete(issue):
        issue_id = issue.get("id") if isinstance(issue, Mapping) else None
        raise SetupError("Beads inventory omitted required semantic fields" + (f" for {issue_id}" if issue_id else ""))
    for field in ("description", "acceptance_criteria", "owner"):
        if field in issue and not isinstance(issue[field], str):
            raise SetupError(f"Beads inventory has an invalid {field} field for {issue['id']}")
    for field in ("labels", "dependencies"):
        if field in issue and not isinstance(issue[field], list):
            raise SetupError(f"Beads inventory has an invalid {field} field for {issue['id']}")
    if "metadata" in issue and not isinstance(issue["metadata"], dict):
        raise SetupError(f"Beads inventory has an invalid metadata field for {issue['id']}")
    for field in ("parent", "parent_id"):
        if field in issue and issue[field] is not None and not isinstance(issue[field], str):
            raise SetupError(f"Beads inventory has an invalid {field} field for {issue['id']}")
    return issue


def _setup_exact_inventory(client: BeadsClient) -> list[Mapping[str, Any]] | None:
    """Read the pinned list shape, focusing only issues missing core fields.

    Beads omits optional empty fields from list output; the core identity and
    comparison fields are always present. A different or incomplete client
    shape gets one focused read and fails closed if that read is also incomplete.
    """
    list_method = getattr(client, "list", None)
    if not callable(list_method):
        return None
    raw_inventory = all_issue_inventory(client)
    if not isinstance(raw_inventory, list):
        raise SetupError("Beads inventory is not a list")
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for summary in raw_inventory:
        if not isinstance(summary, Mapping):
            raise SetupError("Beads inventory contains a non-object")
        issue_id = summary.get("id")
        if not isinstance(issue_id, str) or not issue_id:
            raise SetupError("Beads inventory contains an issue without an ID")
        issue: Any = summary
        if not _setup_inventory_core_complete(summary):
            show = getattr(client, "show", None)
            if not callable(show):
                raise SetupError(f"Beads inventory omitted required semantic fields for {issue_id}")
            try:
                issue = show(issue_id)
            except Exception as exc:
                raise SetupError(f"Beads focused read failed for {issue_id}: {exc}") from exc
        _validate_setup_inventory_issue(issue)
        normalized_id = str(issue["id"])
        if normalized_id != issue_id:
            raise SetupError(f"Beads focused read changed issue ID: {issue_id}")
        if issue_id in seen:
            raise SetupError(f"Beads inventory contains a duplicate issue ID: {issue_id}")
        seen.add(issue_id)
        result.append(issue)
    return result


def _normalized_beads_inventory(client: BeadsClient) -> list[Any]:
    inventory = _setup_exact_inventory(client)
    if inventory is None:
        raise SetupError("Beads client cannot provide an exact inventory")
    return sorted(
        [_normalize_setup_issue(issue) for issue in inventory],
        key=lambda item: str(item.get("id", "")),
    )


def _native_backup_inventory(backup: Path, *, metrics: dict[str, Any] | None = None) -> list[Any]:
    if (
        not backup.is_dir()
        or backup.is_symlink()
        or (backup / "manifest").is_symlink()
        or not (backup / "manifest").is_file()
    ):
        raise SetupError(f"native Beads backup is incomplete: {backup}")
    with tempfile.TemporaryDirectory(prefix="dstack-setup-restore-") as raw:
        disposable_root = Path(raw) / "repo"
        disposable_root.mkdir()
        run(["git", "init", "-q"], cwd=disposable_root)
        disposable_database = disposable_root / ".beads/embeddeddolt"
        _setup_run(
            _setup_beads_command(
                [
                    "bd",
                    "init",
                    "--quiet",
                    "--skip-agents",
                    "--skip-hooks",
                    "--non-interactive",
                ],
                disposable_database,
            ),
            cwd=disposable_root,
            metrics=metrics,
        )
        _setup_run(
            _setup_beads_command(
                ["bd", "backup", "restore", str(backup), "--force", "--json"],
                disposable_database,
            ),
            cwd=disposable_root,
            metrics=metrics,
        )
        return _normalized_beads_inventory(
            BeadsClient(
                disposable_root,
                database=disposable_database,
                command_hook=_setup_command_hook(metrics),
            )
        )


def _verify_native_setup_backup(
    backup: Path,
    before: Sequence[Any],
    *,
    metrics: dict[str, Any] | None = None,
) -> None:
    if _native_backup_inventory(backup, metrics=metrics) != list(before):
        raise SetupError("native Beads backup verification inventory mismatch")


def _create_verified_setup_backup(
    source_root: Path,
    database: Path,
    artifacts: Path,
    *,
    metrics: dict[str, Any] | None = None,
) -> Path:
    backup = artifacts / "backup"
    if backup.exists() and (backup.is_symlink() or not backup.is_dir()):
        raise SetupError(f"native Beads backup path is not a directory: {backup}")
    before = _normalized_beads_inventory(
        _setup_client(source_root, database, command_hook=_setup_command_hook(metrics))
    )
    pointers = _backup_pointer_snapshots(database.parent)
    try:
        if not (backup / "manifest").is_file():
            _setup_run(
                _setup_beads_command(["bd", "backup", "init", str(backup), "--json"], database),
                cwd=source_root,
                metrics=metrics,
            )
            _setup_run(
                _setup_beads_command(["bd", "backup", "sync", "--json"], database),
                cwd=source_root,
                metrics=metrics,
            )
        _verify_native_setup_backup(backup, before, metrics=metrics)
    finally:
        _restore_backup_pointers(database.parent, pointers)
    return backup


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


def _ambiguous_workflow(issue_id: str, reason: str) -> SetupError:
    return SetupError(f"ambiguous workflow topology for {issue_id}: {reason}; repair native Beads parentage/identity")


def _setup_normalization_plan(
    client: BeadsClient,
    *,
    inventory: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    issues = list(inventory) if inventory is not None else client.list(all_statuses=True)
    by_id: dict[str, Mapping[str, Any]] = {}
    children: dict[str, list[Mapping[str, Any]]] = {}
    for issue in issues:
        issue_id = str(issue.get("id") or "")
        if not issue_id or issue_id in by_id:
            raise SetupError(f"setup workflow inventory has invalid or duplicate issue ID: {issue_id or '<missing>'}")
        by_id[issue_id] = issue
        parent = issue_parent(issue)
        if parent:
            children.setdefault(parent, []).append(issue)

    feature_roots = feature_roots_from_inventory(issues)
    alignment_roots = alignment_roots_from_inventory(issues)
    legacy_feature_roots = [issue for issue in issues if is_legacy_feature_root(issue) and not is_feature_root(issue)]
    roots = {str(root["id"]): ("feature", root) for root in feature_roots}
    roots.update({str(root["id"]): ("alignment", root) for root in alignment_roots})

    for issue in issues:
        issue_id = str(issue["id"])
        feature_workflow = has_label(issue, "workflow:feature")
        alignment_workflow = has_label(issue, "workflow:project-alignment")
        if feature_workflow and alignment_workflow:
            raise _ambiguous_workflow(issue_id, "issue carries both workflow kinds")
        if issue_parent(issue) is None and feature_workflow and not is_feature_root(issue):
            raise _ambiguous_workflow(issue_id, "feature root lacks one compatible identity or root type")
        if issue_parent(issue) is None and alignment_workflow and not is_alignment_root(issue):
            raise _ambiguous_workflow(issue_id, "alignment root lacks one compatible identity or root type")

    result: list[dict[str, Any]] = []
    assigned: set[str] = set()
    feature_descendant_metadata = {
        "dstack_step",
        "dstack.feature_slug",
        "dstack.base_branch",
        "dstack.design_path",
        "dstack.pending_design_sha256",
        "dstack.approved_design_sha256",
        "feature_slug",
        "base_branch",
        "design_path",
        "branch",
        "worktree_path",
        "adopted_from",
    }
    alignment_descendant_metadata = {
        "dstack_step",
        "dstack.audit_slug",
        "dstack.target_branch",
        "dstack.scope",
        "dstack.pending_alignment_plan_sha256",
        "dstack.approved_alignment_plan_sha256",
        "audit_slug",
        "target_branch",
        "scope",
        "branch",
        "worktree_path",
    }

    for root_id, (kind, root) in sorted(roots.items()):
        identity = feature_slug(root) if kind == "feature" else next(iter(alignment_identity_values(root)))
        if identity is None:
            raise _ambiguous_workflow(root_id, "workflow root identity is missing")
        metadata = issue_metadata(root)
        set_metadata: dict[str, str | None] = {}
        materialized_feature = kind == "feature" and has_label(root, "workflow:feature")
        if materialized_feature:
            base = root_metadata_value(root, "dstack.base_branch", "base_branch")
            if base and not metadata.get("dstack.base_branch"):
                set_metadata["dstack.base_branch"] = base
            canonical = canonical_feature_design_path(identity)
            if metadata.get("dstack.design_path") != canonical:
                set_metadata["dstack.design_path"] = canonical
            unset = [
                key
                for key in ("feature_slug", "base_branch", "branch", "worktree_path", "adopted_from")
                if key in metadata
            ]
        elif kind == "feature":
            unset = []
        else:
            target = root_metadata_value(root, "dstack.target_branch", "target_branch")
            scope = root_metadata_value(root, "dstack.scope", "scope")
            if target and not metadata.get("dstack.target_branch"):
                set_metadata["dstack.target_branch"] = target
            if scope and not metadata.get("dstack.scope"):
                set_metadata["dstack.scope"] = scope
            unset = [key for key in ("audit_slug", "target_branch", "branch", "worktree_path") if key in metadata]
        mutation = _setup_issue_mutation(
            root,
            set_metadata=set_metadata,
            unset_metadata=unset,
            remove_labels=(
                [label for label in issue_labels(root) if label == "dstack:delivery-ready"]
                if kind != "feature" or materialized_feature
                else []
            ),
        )
        if mutation:
            result.append(mutation)

        stack = list(reversed(children.get(root_id, [])))
        while stack:
            issue = stack.pop()
            issue_id = str(issue["id"])
            if issue_id in assigned:
                raise _ambiguous_workflow(issue_id, "issue is reachable from competing workflow roots")
            assigned.add(issue_id)
            stack.extend(reversed(children.get(issue_id, [])))
            labels = issue_labels(issue)
            feature_values = feature_identity_values(issue)
            alignment_values = alignment_identity_values(issue)
            root_capable = issue_type(issue) in {"epic", "molecule"}
            if kind == "feature":
                if has_label(issue, "workflow:project-alignment") or alignment_values:
                    raise _ambiguous_workflow(issue_id, "feature descendant carries alignment identity")
                concrete_values = feature_values - {"{{feature_slug}}"}
                if concrete_values and concrete_values != {identity}:
                    raise _ambiguous_workflow(issue_id, f"feature identity does not match {identity}")
                if (
                    (has_label(issue, "workflow:feature") or has_label(issue, "dstack:feature-idea"))
                    and root_capable
                    and not (
                        concrete_values == {identity} or (not concrete_values and "{{feature_slug}}" in feature_values)
                    )
                ):
                    raise _ambiguous_workflow(issue_id, "nested feature workflow identity is missing or mismatched")
                remove = [
                    label
                    for label in labels
                    if label
                    in {"workflow:feature", "dstack:feature-idea", f"feature:{identity}", "feature:{{feature_slug}}"}
                ]
                unset = [key for key in feature_descendant_metadata if key in issue_metadata(issue)]
            else:
                if has_label(issue, "workflow:feature") or has_label(issue, "dstack:feature-idea") or feature_values:
                    raise _ambiguous_workflow(issue_id, "alignment descendant carries feature identity")
                concrete_values = alignment_values - {"{{audit_slug}}"}
                if concrete_values and concrete_values != {identity}:
                    raise _ambiguous_workflow(issue_id, f"alignment identity does not match {identity}")
                if (
                    has_label(issue, "workflow:project-alignment")
                    and root_capable
                    and not (
                        concrete_values == {identity} or (not concrete_values and "{{audit_slug}}" in alignment_values)
                    )
                ):
                    raise _ambiguous_workflow(issue_id, "nested alignment workflow identity is missing or mismatched")
                remove = [
                    label
                    for label in labels
                    if label in {"workflow:project-alignment", f"audit:{identity}", "audit:{{audit_slug}}"}
                ]
                unset = [key for key in alignment_descendant_metadata if key in issue_metadata(issue)]
            mutation = _setup_issue_mutation(issue, unset_metadata=unset, remove_labels=remove)
            if mutation:
                result.append(mutation)

    preserved_legacy: set[str] = {str(root["id"]) for root in legacy_feature_roots}
    for root in legacy_feature_roots:
        identity = feature_slug(root)
        if identity is None:
            raise _ambiguous_workflow(str(root["id"]), "legacy feature identity is missing")
        stack = list(reversed(children.get(str(root["id"]), [])))
        while stack:
            issue = stack.pop()
            issue_id = str(issue["id"])
            if issue_id in assigned or issue_id in preserved_legacy:
                raise _ambiguous_workflow(issue_id, "issue is reachable from competing workflow roots")
            preserved_legacy.add(issue_id)
            stack.extend(reversed(children.get(issue_id, [])))
            if has_label(issue, "workflow:project-alignment") or alignment_identity_values(issue):
                raise _ambiguous_workflow(issue_id, "legacy feature descendant carries alignment identity")
            concrete_values = feature_identity_values(issue) - {"{{feature_slug}}"}
            if concrete_values and concrete_values != {identity}:
                raise _ambiguous_workflow(issue_id, f"legacy feature identity does not match {identity}")

    for issue in issues:
        issue_id = str(issue["id"])
        if (
            issue_id in roots
            or issue_id in assigned
            or issue_id in preserved_legacy
            or is_feature_root(issue)
            or is_alignment_root(issue)
        ):
            continue
        if not (
            has_label(issue, "workflow:feature")
            or has_label(issue, "workflow:project-alignment")
            or has_label(issue, "dstack:feature-idea")
            or feature_identity_values(issue)
            or alignment_identity_values(issue)
        ):
            continue
        labels = issue_labels(issue)
        identity_metadata = root_metadata_value(
            issue,
            "dstack.feature_slug",
            "feature_slug",
            "dstack.audit_slug",
            "audit_slug",
        )
        identity_labels = [
            label
            for label in labels
            if (label.startswith("feature:") and label != "feature:")
            or (label.startswith("audit:") and label != "audit:")
        ]
        if (
            issue_parent(issue) is None
            and issue_type(issue) not in {"epic", "molecule"}
            and not identity_metadata
            and len(identity_labels) == 1
            and not any(
                has_label(issue, marker)
                for marker in ("workflow:feature", "workflow:project-alignment", "dstack:feature-idea")
            )
        ):
            mutation = _setup_issue_mutation(issue, remove_labels=identity_labels)
            if mutation:
                result.append(mutation)
                continue
        seen: set[str] = set()
        cursor: Mapping[str, Any] = issue
        reason = "no compatible parentless workflow root"
        while True:
            cursor_id = str(cursor["id"])
            if cursor_id in seen:
                reason = "parentage cycle detected"
                break
            seen.add(cursor_id)
            parent = issue_parent(cursor)
            if parent is None:
                break
            if parent not in by_id:
                reason = f"parent {parent} is absent from the inventory"
                break
            cursor = by_id[parent]
        raise _ambiguous_workflow(issue_id, reason)

    return _setup_beads_issues(result)


def _setup_feature_design_moves(
    client: BeadsClient,
    *,
    inventory: Sequence[Mapping[str, Any]] | None = None,
) -> list[tuple[str, str]]:
    moves: list[tuple[str, str]] = []
    issues = list(inventory) if inventory is not None else client.list(all_statuses=True)
    for feature in feature_roots_from_inventory(issues):
        if not has_label(feature, "workflow:feature"):
            continue
        slug = feature_slug(feature)
        design = root_metadata_value(feature, "dstack.design_path", "design_path")
        canonical = canonical_feature_design_path(slug) if slug else ""
        if design and design != canonical and canonical:
            source = _setup_repo_path(client.root, design)
            _setup_repo_path(client.root, canonical)
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
    root: Path, *, force: bool, design_moves: Sequence[tuple[str, str]], validation_errors: list[str] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs = _validate_setup_tree(root, "docs")
    before = (
        {path.relative_to(root).as_posix(): path.read_bytes() for path in docs.rglob("*") if path.is_file()}
        if docs.is_dir()
        else {}
    )
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
        if force and validation_errors is not None:
            try:
                validate_docs(scratch)
            except DstackError as exc:
                validation_errors.append(str(exc))
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


def _setup_status(root: Path) -> tuple[str, set[str], bool]:
    status = run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
    ).stdout
    paths: set[str] = set()
    unmerged = False
    records = status.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            raise SetupError("Git returned invalid porcelain status during setup preflight")
        code = record[:2]
        paths.add(record[3:])
        unmerged = unmerged or "U" in code or code in {"AA", "DD"}
        if "R" in code or "C" in code:
            if index >= len(records) or not records[index]:
                raise SetupError("Git returned an incomplete rename during setup preflight")
            paths.add(records[index])
            index += 1
    return status, paths, unmerged


def _setup_index_entries(root: Path, path: str) -> str:
    return run(["git", "ls-files", "--stage", "--", path], cwd=root).stdout


def _is_beads_runtime_path(path: str) -> bool:
    if path in DSTACK_UNTRACKED_BEADS_FILES or any(path.startswith(prefix) for prefix in BEADS_RUNTIME_DIR_PREFIXES):
        return True
    relative = path.removeprefix(".beads/")
    if not path.startswith(".beads/"):
        return False
    if ".corrupt.backup/" in relative or relative.rsplit("/", 1)[-1] in BEADS_SENSITIVE_BASENAMES:
        return True
    return "/" not in relative and any(
        fnmatch.fnmatch(relative, pattern) for pattern in BEADS_RUNTIME_TOP_LEVEL_PATTERNS
    )


def _supported_interaction_index(root: Path, path: str) -> bool:
    entries = _setup_index_entries(root, path).splitlines()
    if len(entries) != 1 or "\t" not in entries[0]:
        return False
    fields = entries[0].split("\t", 1)[0].split()
    if (
        len(fields) != 3
        or fields[0] != "100644"
        or fields[2] != "0"
        or not fields[1].strip("0")
        or _setup_repo_path(root, path).is_symlink()
    ):
        return False
    return (
        run(["git", "ls-files", "-v", "--", path], cwd=root).stdout == f"H {path}\n"
        and re.search(r"\bflags: 0\s*\Z", run(["git", "ls-files", "--debug", "--", path], cwd=root).stdout) is not None
    )


def _require_supported_interaction_index(root: Path) -> None:
    path = ".beads/interactions.jsonl"
    if tracked(root, path) and not _supported_interaction_index(root, path):
        raise SetupError(f"{path} has unsupported Git-index state; repair it with native Git before setup")


def _setup_preflight(root: Path, *, force: bool) -> tuple[str, bool]:
    status, paths, unmerged = _setup_status(root)
    interaction = ".beads/interactions.jsonl"
    relevant_paths = {path for path in paths if not _is_beads_runtime_path(path) or path == interaction}
    allowed = (
        bool(status)
        and force
        and not unmerged
        and (
            not relevant_paths or (relevant_paths == {interaction} and _supported_interaction_index(root, interaction))
        )
    )
    return status, allowed


def _setup_plan_object(
    root: Path,
    *,
    initialize: bool,
    force: bool,
    authority: Mapping[str, str],
    formula_actions: Mapping[str, str],
    git_index: list[dict[str, str]],
    client: BeadsClient | None,
    inventory: Sequence[Mapping[str, Any]],
    template_artifacts: Sequence[Mapping[str, Any]],
    projected_validation_errors: list[str] | None = None,
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
    design_moves = _setup_feature_design_moves(client, inventory=inventory) if client and force else []
    filesystem, navigation = _setup_doc_filesystem_plan(
        root,
        force=force,
        design_moves=design_moves,
        validation_errors=projected_validation_errors,
    )
    policy = _setup_repo_path(root, ".beads/.gitignore")
    if initialization or _setup_repo_path(root, ".beads").is_dir():
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
    for name, action in formula_actions.items():
        if action not in {"create", "update"}:
            continue
        source = _setup_repo_path(package_root(), f"formulas/{name}.formula.toml")
        try:
            source_relative = source.relative_to(root).as_posix()
        except ValueError:
            source_relative = f"formulas/{source.name}"
        destination = _setup_repo_path(root, f".beads/formulas/{source.name}")
        formulas.append(
            {
                "name": name,
                "action": action,
                "source": source_relative,
                "destination": destination.relative_to(root).as_posix(),
                "source_sha256": _setup_sha256(source),
                "expected_destination_sha256": (_setup_sha256(destination) if destination.is_file() else None),
                "conflict_policy": "replace-reviewed" if action == "update" else "fail-if-different",
            }
        )
    return canonicalize_setup_plan(
        {
            "schema": SETUP_PLAN_SCHEMA,
            "authority": dict(authority),
            "initialization": initialization,
            "beads_issues": (_setup_normalization_plan(client, inventory=inventory) if client and force else []),
            "dependencies": [],
            "supersessions": [],
            "template_deletions": [
                {
                    "action": "delete",
                    "issue_id": str(item["id"]),
                    "precondition": "is-template",
                }
                for item in template_artifacts
            ],
            "filesystem": filesystem,
            "git_index": git_index,
            "formulas": formulas,
            "navigation_references": navigation,
        }
    )


def setup_plan(
    root_arg: Path,
    *,
    initialize: bool,
    force: bool,
    database: Path | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = git_root(root_arg)
    if database is not None:
        database = _validate_setup_database(root, database, allow_absent=initialize)
    _require_supported_interaction_index(root)
    status, allowed_interaction_change = _setup_preflight(root, force=force)
    command_hook = _setup_command_hook(metrics)
    if command_hook is None:
        authority = (
            _current_setup_authority(root) if database is None else _current_setup_authority(root, database=database)
        )
    else:
        authority = (
            _current_setup_authority(root, command_hook=command_hook)
            if database is None
            else _current_setup_authority(root, database=database, command_hook=command_hook)
        )
    if status and not allowed_interaction_change:
        mutation_plan = canonicalize_setup_plan(
            {
                "schema": SETUP_PLAN_SCHEMA,
                "authority": authority,
                "initialization": [],
                "beads_issues": [],
                "dependencies": [],
                "supersessions": [],
                "template_deletions": [],
                "filesystem": [],
                "git_index": [],
                "formulas": [],
                "navigation_references": [],
            }
        )
        return {
            "schema": SETUP_PLAN_SCHEMA,
            "status": "blocked",
            "root": str(root),
            "request": _setup_plan_request(initialize=initialize, force=force),
            "preconditions": {"clean_worktree": False, "blocked": ["worktree has unrelated changes"]},
            "authority": authority,
            "mutation_plan": mutation_plan,
            "plan_sha256": setup_plan_digest(mutation_plan),
            "filesystem": [],
            "git_index": [],
            "beads": [],
            "formulas": {},
            "documentation": {},
        }

    beads_path = _setup_repo_path(root, ".beads")
    _setup_repo_path(root, ".beads/formulas")
    _validate_setup_tree(root, "docs")
    beads_exists = beads_path.is_dir()
    blocked: list[str] = []
    if not beads_exists and not initialize:
        blocked.append("Beads initialization is not authorized")

    formulas: dict[str, str] = {}
    for name in FORMULA_NAMES:
        source = _setup_repo_path(package_root(), f"formulas/{name}.formula.toml")
        destination = _setup_repo_path(root, f".beads/formulas/{source.name}")
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

    client: BeadsClient | None = None
    git_index: list[dict[str, str]] = []
    inventory: list[dict[str, Any]] = []
    template_artifacts: list[dict[str, Any]] = []
    if not beads_exists:
        git_index.append({"path": ".beads/interactions.jsonl", "action": "remove-cached"})
    else:
        client = _setup_client(root, database, command_hook=command_hook)
        if tracked(root, ".beads/interactions.jsonl"):
            git_index.append({"path": ".beads/interactions.jsonl", "action": "remove-cached"})
        if force:
            exact_inventory = _setup_exact_inventory(client)
            inventory = list(exact_inventory) if exact_inventory is not None else all_issue_inventory(client)
            if metrics is not None:
                metrics["inventory_reads"] = int(metrics.get("inventory_reads", 0)) + 1
            template_artifacts = legacy_template_artifacts(client, inventory=inventory)

    migration = (
        legacy_documentation_plan(root)
        if force
        else {
            "configured_source_moves": [],
            "referenced_content_moves": [],
            "unresolved_outside_markdown": [],
            "non_reader_paths": [],
            "manual_actions": [],
        }
    )
    for action in migration.get("manual_actions", []):
        blocked.append(f"documentation requires manual disposition: {action['path']}; {action['action']}")
    projected_validation_errors: list[str] = []
    mutation_plan = _setup_plan_object(
        root,
        initialize=initialize,
        force=force,
        authority=authority,
        formula_actions=formulas,
        git_index=git_index,
        client=client,
        inventory=inventory,
        template_artifacts=template_artifacts,
        projected_validation_errors=projected_validation_errors,
    )
    blocked.extend(f"projected documentation validation failed: {error}" for error in projected_validation_errors)
    display_filesystem = [
        {
            "path": str(operation["destination"] or operation["source"]),
            "action": str(operation["action"]),
        }
        for operation in mutation_plan["filesystem"]
    ]
    display_filesystem.extend(
        {
            "path": str(operation["destination"]),
            "action": str(operation["action"]),
        }
        for operation in mutation_plan["formulas"]
    )
    beads = [
        *([{"action": "initialize", "target": ".beads"}] if mutation_plan["initialization"] else []),
        *(
            {"action": "delete-template", "target": operation["issue_id"]}
            for operation in mutation_plan["template_deletions"]
        ),
        *({"action": "normalize", "target": mutation["issue_id"]} for mutation in mutation_plan["beads_issues"]),
    ]
    payload = {
        "schema": SETUP_PLAN_SCHEMA,
        "status": "blocked" if blocked else "ready",
        "root": str(root),
        "request": _setup_plan_request(initialize=initialize, force=force),
        "preconditions": {"clean_worktree": not status or allowed_interaction_change, "blocked": blocked},
        "authority": authority,
        "mutation_plan": mutation_plan,
        "plan_sha256": setup_plan_digest(mutation_plan),
        "filesystem": sorted(display_filesystem, key=lambda item: (item["path"], item["action"])),
        "git_index": git_index,
        "beads": beads,
        "formulas": formulas,
        "documentation": {
            **migration,
            "projected_validation_errors": projected_validation_errors,
        },
    }
    return payload


def _restore_setup_files(root: Path, snapshots: Mapping[str, bytes | None]) -> None:
    for relative, content in snapshots.items():
        path = _setup_repo_path(root, relative)
        if content is None:
            path.unlink(missing_ok=True)
            continue
        atomic_replace(path, content)


def _setup_resolve_source(root: Path, relative: str) -> Path:
    candidate = _setup_repo_path(root, relative)
    if candidate.is_file():
        return candidate
    package_candidate = _setup_repo_path(package_root(), relative)
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
    source_path = _setup_repo_path(root, str(source)) if source else None
    destination_path = _setup_repo_path(root, str(destination)) if destination else None
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
        _setup_repo_path(root, str(source)).unlink()
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
        source_path = _setup_repo_path(root, str(source))
        destination_path = _setup_repo_path(root, str(destination))
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
    destination_path = _setup_repo_path(root, str(destination))
    atomic_replace(destination_path, content)


def _validate_setup_plan_paths(root: Path, plan: Mapping[str, Any]) -> None:
    for record in plan["initialization"]:
        _setup_repo_path(root, str(record["target"]))
    for operation in plan["filesystem"]:
        for relative in (operation["source"], operation["destination"]):
            if relative:
                _setup_repo_path(root, str(relative))
    for operation in plan["formulas"]:
        _setup_resolve_source(root, str(operation["source"]))
        _setup_repo_path(root, str(operation["destination"]))
    for operation in plan["git_index"]:
        _setup_repo_path(root, str(operation["path"]))
    for operation in plan["navigation_references"]:
        _setup_repo_path(root, str(operation["affected_path"]))


def _setup_relationships(issue: Mapping[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for record in dependency_records(issue):
        target = record.get("depends_on_id") or record.get("id")
        if not isinstance(target, str) or not target:
            raise SetupError(f"setup issue has an invalid relationship: {issue.get('id')}")
        relation = str(record.get("type") or record.get("dependency_type") or "blocks")
        result.append((relation.replace("superseded_by", "superseded-by"), target))
    return sorted(result)


def _setup_expected_inventory(
    baseline: Sequence[Mapping[str, Any]],
    mutation: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    expected = {str(issue["id"]): copy.deepcopy(dict(issue)) for issue in baseline}
    for operation in mutation["beads_issues"]:
        issue_id = str(operation["issue_id"])
        if issue_id not in expected:
            raise SetupError(f"reviewed setup issue is absent from the backup baseline: {issue_id}")
        issue = expected[issue_id]
        metadata = issue.setdefault("metadata", {})
        for key, value in operation["set_metadata"].items():
            if value is None:
                metadata.pop(key, None)
            else:
                metadata[key] = value
        for key in operation["unset_metadata"]:
            metadata.pop(key, None)
        labels = set(issue.get("labels", []))
        labels.update(operation["add_labels"])
        labels.difference_update(operation["remove_labels"])
        issue["labels"] = sorted(labels)
    for operation in mutation["dependencies"]:
        source = str(operation["source_id"])
        destination = str(operation["destination_id"])
        if source not in expected or destination not in expected:
            raise SetupError(
                f"reviewed setup relationship is absent from the backup baseline: {source} -> {destination}"
            )
        relationships = [list(item) for item in expected[source].get("relationships", [])]
        relationship = [str(operation["relationship_type"]), destination]
        if operation["action"] == "add":
            if relationship not in relationships:
                relationships.append(relationship)
        else:
            relationships = [item for item in relationships if item != relationship]
        expected[source]["relationships"] = sorted(relationships)
        if operation["relationship_type"] == "parent-child":
            expected[source]["parent"] = destination if operation["action"] == "add" else None
    for operation in mutation["supersessions"]:
        source = str(operation["source_id"])
        destination = str(operation["destination_id"])
        if source not in expected or destination not in expected:
            raise SetupError(
                f"reviewed setup supersession is absent from the backup baseline: {source} -> {destination}"
            )
        relationships = [list(item) for item in expected[source].get("relationships", [])]
        relationship = ["superseded-by", destination]
        if relationship not in relationships:
            relationships.append(relationship)
        expected[source]["relationships"] = sorted(relationships)
        expected[source]["status"] = "closed"
    for operation in mutation["template_deletions"]:
        expected.pop(str(operation["issue_id"]), None)
    return expected


def _verify_setup_beads_delta(
    database: Path,
    backup: Path | None,
    mutation: Mapping[str, Any],
    *,
    metrics: dict[str, Any] | None = None,
) -> None:
    baseline = _native_backup_inventory(backup, metrics=metrics) if backup is not None else []
    expected = _setup_expected_inventory(baseline, mutation)
    observed = _normalized_beads_inventory(
        _setup_client(database.parent.parent, database, command_hook=_setup_command_hook(metrics))
    )
    observed_by_id = {str(issue["id"]): issue for issue in observed}
    expected_ids = set(expected)
    observed_ids = set(observed_by_id)
    differences = sorted(expected_ids ^ observed_ids)
    for issue_id in sorted(expected_ids & observed_ids):
        if expected[issue_id] != observed_by_id[issue_id]:
            differences.append(issue_id)
    if differences:
        raise SetupError("setup Beads verification found unexpected changes: " + ", ".join(sorted(set(differences))))


def _setup_issue_state(issue: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metadata": issue_metadata(issue),
        "labels": sorted(issue_labels(issue)),
        "relationships": _setup_relationships(issue),
        "parent": issue_parent(issue),
        "status": str(issue.get("status") or ""),
    }


def _setup_expected_beads_states(
    client: BeadsClient,
    mutation: Mapping[str, Any],
    *,
    inventory: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    issue_ids = (
        {str(operation["issue_id"]) for operation in mutation["beads_issues"]}
        | {str(operation["source_id"]) for operation in mutation["dependencies"]}
        | {str(operation["source_id"]) for operation in mutation["supersessions"]}
    )
    by_id = {str(issue["id"]): issue for issue in inventory} if inventory is not None else {}
    expected = {
        issue_id: _setup_issue_state(by_id[issue_id] if issue_id in by_id else client.show(issue_id))
        for issue_id in sorted(issue_ids)
    }
    operations: dict[str, list[str]] = {issue_id: [] for issue_id in issue_ids}
    for operation in mutation["beads_issues"]:
        issue_id = str(operation["issue_id"])
        state = expected[issue_id]
        operations[issue_id].append("beads_issue")
        for key, value in operation["set_metadata"].items():
            if value is None:
                state["metadata"].pop(key, None)
            else:
                state["metadata"][key] = value
        for key in operation["unset_metadata"]:
            state["metadata"].pop(key, None)
        labels = set(state["labels"])
        labels.update(operation["add_labels"])
        labels.difference_update(operation["remove_labels"])
        state["labels"] = sorted(labels)
    for operation in mutation["dependencies"]:
        source = str(operation["source_id"])
        destination = str(operation["destination_id"])
        relation = str(operation["relationship_type"])
        action = str(operation["action"])
        state = expected[source]
        operations[source].append(f"dependency:{action}")
        relationship = (relation, destination)
        if action == "add":
            state["relationships"].append(relationship)
            if relation == "parent-child":
                state["parent"] = destination
        else:
            if relationship in state["relationships"]:
                state["relationships"].remove(relationship)
            if relation == "parent-child" and state["parent"] == destination:
                state["parent"] = None
        state["relationships"].sort()
    for operation in mutation["supersessions"]:
        source = str(operation["source_id"])
        destination = str(operation["destination_id"])
        state = expected[source]
        operations[source].append("supersession")
        relationship = ("superseded-by", destination)
        if relationship not in state["relationships"]:
            state["relationships"].append(relationship)
            state["relationships"].sort()
        state["status"] = "closed"
    return expected, operations


def _verify_setup_beads_postconditions(
    client: BeadsClient,
    expected: Mapping[str, Mapping[str, Any]],
    operations: Mapping[str, Sequence[str]],
    *,
    inventory: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    by_id = {str(issue["id"]): issue for issue in inventory} if inventory is not None else {}
    for issue_id in sorted(expected):
        observed_issue = by_id.get(issue_id) if inventory is not None else None
        observed = _setup_issue_state(observed_issue if observed_issue is not None else client.show(issue_id))
        if observed == expected[issue_id]:
            continue
        expected_json = json.dumps(expected[issue_id], sort_keys=True, separators=(",", ":"))
        observed_json = json.dumps(observed, sort_keys=True, separators=(",", ":"))
        raise SetupError(
            "setup Beads postcondition failed: "
            f"operation={','.join(operations[issue_id])}; "
            f"target_issue={issue_id}; expected_post_state={expected_json}; "
            f"observed_post_state={observed_json}; rollback_completed=false; "
            "mutation_state_uncertain=true"
        )


def _execute_setup_plan(
    root: Path,
    plan: Mapping[str, Any],
    *,
    database: Path | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mutation = plan
    command_hook = _setup_command_hook(metrics)
    if command_hook is None:
        observed_authority = (
            _current_setup_authority(root) if database is None else _current_setup_authority(root, database=database)
        )
    else:
        observed_authority = (
            _current_setup_authority(root, command_hook=command_hook)
            if database is None
            else _current_setup_authority(root, database=database, command_hook=command_hook)
        )
    if observed_authority != mutation["authority"]:
        raise SetupError("setup controller/runtime authority changed since plan; rerun setup plan and review it")
    _validate_setup_tree(package_root(), "formulas")
    _validate_setup_plan_paths(root, mutation)
    for operation in mutation["formulas"]:
        source = _setup_resolve_source(root, str(operation["source"]))
        if _setup_sha256(source) != operation["source_sha256"]:
            raise SetupError(f"setup formula source changed: {source}")
    if metrics is None:
        validate_bundle(package_root() / "formulas")
    else:
        validate_bundle(package_root() / "formulas", metrics=metrics)
    initialization = mutation["initialization"]
    if initialization:
        record = initialization[0]
        target = _setup_repo_path(root, str(record["target"]))
        if target.exists():
            raise SetupError("setup initialization precondition changed")
        database_created = database is not None and not database.is_dir()
        ensure_beads(root, initialize=True, database=database, metrics=metrics)
        if database_created:
            _relocate_initialized_beads_files(root, database)
        if database is None:
            initialized = _setup_repo_path(root, str(record["target"])).is_dir()
        else:
            initialized = database.is_dir()
        if not initialized:
            raise SetupError("setup initialization postcondition failed")
    elif database is None and not _setup_repo_path(root, ".beads").is_dir():
        raise SetupError("Beads is not initialized and the reviewed plan omits initialization")
    elif database is not None and not database.is_dir():
        raise SetupError("Beads database is not initialized and the reviewed plan omits initialization")

    client = _setup_client(root, database, command_hook=command_hook)
    version = str(mutation["authority"]["beads_version"])
    inventory = _setup_exact_inventory(client)
    if metrics is not None and inventory is not None:
        metrics["inventory_reads"] = int(metrics.get("inventory_reads", 0)) + 1
    inventory_by_id = {str(issue["id"]): issue for issue in inventory or []}
    for operation in mutation["template_deletions"]:
        issue_id = str(operation["issue_id"])
        issue = inventory_by_id.get(issue_id) if inventory is not None else client.show(issue_id)
        if issue is None or (issue.get("is_template") is not True and not has_label(issue, "template")):
            raise SetupError(f"reviewed setup template is no longer a template: {issue_id}")
    expected_beads, beads_operations = _setup_expected_beads_states(client, mutation, inventory=inventory)
    groups: dict[tuple[str, ...], list[str]] = {}
    for operation in mutation["beads_issues"]:
        arguments = tuple(_setup_mutation_arguments(operation))
        groups.setdefault(arguments, []).append(str(operation["issue_id"]))
    if metrics is not None:
        metrics["beads_update_batches"] = len(groups)
        metrics["beads_updates"] = len(mutation["beads_issues"])
    for arguments, issue_ids in sorted(groups.items(), key=lambda item: item[1][0]):
        if len(issue_ids) > 1 and isinstance(client, _BEADS_CLIENT_TYPE):
            client.update_many(issue_ids, *arguments)
        else:
            for issue_id in issue_ids:
                client.update(issue_id, *arguments)

    for operation in mutation["dependencies"]:
        if operation["action"] == "add":
            client.add_dependency(
                str(operation["source_id"]),
                str(operation["destination_id"]),
                relation_type=str(operation["relationship_type"]),
            )
        else:
            client.remove_dependency(str(operation["source_id"]), str(operation["destination_id"]))

    template_ids = [str(operation["issue_id"]) for operation in mutation["template_deletions"]]
    if template_ids:
        _setup_run(
            _setup_beads_command(["bd", "delete", *template_ids, "--dry-run", "--json"], database),
            cwd=root,
            metrics=metrics,
        )
        _setup_run(
            _setup_beads_command(["bd", "delete", *template_ids, "--force", "--json"], database),
            cwd=root,
            metrics=metrics,
        )

    for operation in sorted(
        mutation["filesystem"],
        key=lambda item: (item["action"] == "delete", item["source"] or item["destination"] or ""),
    ):
        _setup_write_filesystem(root, operation)

    for operation in mutation["formulas"]:
        source = _setup_resolve_source(root, str(operation["source"]))
        destination = _setup_repo_path(root, str(operation["destination"]))
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
        _setup_repo_path(root, str(operation["path"]))
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
    post_inventory = _setup_exact_inventory(client)
    if metrics is not None and post_inventory is not None:
        metrics["inventory_reads"] = int(metrics.get("inventory_reads", 0)) + 1
    _verify_setup_beads_postconditions(
        client,
        expected_beads,
        beads_operations,
        inventory=post_inventory,
    )
    observed_template_ids = {str(item.get("id") or "") for item in post_inventory or []} if template_ids else set()
    remaining_templates = observed_template_ids.intersection(template_ids)
    if remaining_templates:
        raise SetupError(
            "setup template deletion postcondition failed: "
            + ", ".join(sorted(remaining_templates))
            + "; rollback_completed=false; mutation_state_uncertain=true"
        )

    for operation in mutation["navigation_references"]:
        path = _setup_repo_path(root, str(operation["affected_path"]))
        _setup_check_hash(path, operation["expected_after_sha256"], "navigation result")

    for operation in mutation["formulas"]:
        destination = _setup_repo_path(root, str(operation["destination"]))
        if not destination.is_file() or _setup_sha256(destination) != _setup_sha256(
            _setup_resolve_source(root, str(operation["source"]))
        ):
            raise SetupError(f"setup formula postcondition failed: {destination}")
    for name in FORMULA_NAMES:
        if database is None:
            validate_formula(root, name)
        else:
            validate_formula(root, name, database=database, metrics=metrics)
    return {"status": "ok", "beads_version": version, "metrics": metrics if metrics is not None else {}}


def _restore_setup_index(root: Path, snapshots: Mapping[str, str]) -> None:
    for path, entries in snapshots.items():
        run(["git", "update-index", "--force-remove", "--", path], cwd=root)
        if entries:
            run(["git", "update-index", "--index-info"], cwd=root, input_text=entries)
        if _setup_index_entries(root, path) != entries:
            raise SetupError(f"setup Git-index restore postcondition failed: {path}")


def _fresh_setup_plan_for_migration(
    root: Path,
    *,
    initialize: bool,
    force: bool,
    database: Path,
    reviewed: Mapping[str, Any],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fresh = setup_plan(
        root,
        initialize=initialize,
        force=force,
        database=database,
        metrics=metrics,
    )
    if fresh["status"] != "ready":
        raise SetupError("setup migration preconditions changed: " + "; ".join(fresh["preconditions"]["blocked"]))
    fresh_mutation = canonicalize_setup_plan(fresh["mutation_plan"])
    if fresh_mutation != reviewed["mutation_plan"] or fresh["authority"] != reviewed["authority"]:
        raise SetupError("setup migration plan changed since review; rerun setup plan and review it")
    if fresh["plan_sha256"] != reviewed["plan_sha256"]:
        raise SetupError("setup migration digest changed since review; rerun setup plan and review it")
    return fresh


_INITIALIZED_BEADS_FILES = (
    ".beads/.gitignore",
    ".beads/.local_version",
    ".beads/config.yaml",
    ".beads/README.md",
    ".beads/metadata.json",
    ".beads/interactions.jsonl",
)


def _setup_allowed_worktree_paths(mutation: Mapping[str, Any]) -> set[str]:
    paths = {
        str(relative)
        for operation in mutation["filesystem"]
        for relative in (operation["source"], operation["destination"])
        if relative
    }
    paths.update(str(operation["affected_path"]) for operation in mutation["navigation_references"])
    paths.update(str(operation["destination"]) for operation in mutation["formulas"])
    paths.update(str(operation["path"]) for operation in mutation["git_index"])
    if mutation["initialization"]:
        paths.update(_INITIALIZED_BEADS_FILES)
    return paths


def _verify_setup_worktree_files(
    source_root: Path,
    worktree: Path,
    mutation: Mapping[str, Any],
    *,
    require_source_head: bool = True,
) -> None:
    _, record = _setup_migration_worktree_record(source_root, setup_plan_digest(mutation))
    if record is None or not record.get("detached") or record.get("branch"):
        raise SetupError("setup migration worktree is not detached")
    source_head = run(["git", "rev-parse", "HEAD"], cwd=source_root).stdout.strip()
    worktree_head = run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()
    if record.get("HEAD") != worktree_head:
        raise SetupError("setup migration worktree record does not match its HEAD")
    if require_source_head and worktree_head != source_head:
        raise SetupError("setup migration worktree no longer starts at the source HEAD")
    _, paths, _ = _setup_status(worktree)
    allowed = _setup_allowed_worktree_paths(mutation)
    unexpected = sorted(paths - allowed)
    if unexpected:
        raise SetupError("setup migration worktree has unexpected changes: " + ", ".join(unexpected))
    for operation in mutation["filesystem"]:
        action = str(operation["action"])
        source = operation["source"]
        destination = operation["destination"]
        source_path = _setup_repo_path(worktree, str(source)) if source else None
        destination_path = _setup_repo_path(worktree, str(destination)) if destination else None
        if action == "delete":
            if source_path is not None and source_path.exists():
                raise SetupError(f"setup migration delete did not converge: {source}")
        elif action == "move":
            if (
                source_path is None
                or destination_path is None
                or source_path.exists()
                or not destination_path.is_file()
            ):
                raise SetupError(f"setup migration move did not converge: {source} -> {destination}")
            _setup_check_hash(destination_path, operation["expected_source_sha256"], "migration destination")
        elif destination_path is None or not destination_path.is_file():
            raise SetupError(f"setup migration write did not converge: {destination}")
        elif operation["content_source"] == "generated":
            expected = str(operation["generated_content"]).encode("utf-8")
            if destination_path.read_bytes() != expected:
                raise SetupError(f"setup migration generated content changed: {destination}")
        else:
            source_path = _setup_resolve_source(worktree, str(source))
            if destination_path.read_bytes() != source_path.read_bytes():
                raise SetupError(f"setup migration copied content changed: {destination}")
    for operation in mutation["formulas"]:
        destination = _setup_repo_path(worktree, str(operation["destination"]))
        source = _setup_resolve_source(worktree, str(operation["source"]))
        if not destination.is_file() or destination.read_bytes() != source.read_bytes():
            raise SetupError(f"setup migration formula did not converge: {destination}")
    for operation in mutation["navigation_references"]:
        path = _setup_repo_path(worktree, str(operation["affected_path"]))
        _setup_check_hash(path, operation["expected_after_sha256"], "migration navigation result")
    for operation in mutation["git_index"]:
        if _setup_index_entries(worktree, str(operation["path"])):
            raise SetupError(f"setup migration Git-index operation did not converge: {operation['path']}")


def _reset_setup_migration_worktree(root: Path, worktree: Path, mutation: Mapping[str, Any]) -> None:
    _, record = _setup_migration_worktree_record(root, setup_plan_digest(mutation))
    if record is None or not record.get("detached") or record.get("branch"):
        raise SetupError("setup migration worktree registration is missing or attached to a branch")
    source_head = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    if record.get("HEAD") != source_head:
        raise SetupError("source already contains or replaced the setup migration result")
    run(["git", "reset", "--hard", "HEAD"], cwd=worktree)
    allowed = _setup_allowed_worktree_paths(mutation)
    for _ in range(2):
        _, paths, _ = _setup_status(worktree)
        unexpected = sorted(paths - allowed)
        if unexpected:
            raise SetupError("cannot remove unexpected migration worktree changes: " + ", ".join(unexpected))
        for relative in sorted(paths & allowed):
            if tracked(worktree, relative):
                continue
            path = _setup_repo_path(worktree, relative)
            if path.is_dir() and not path.is_symlink():
                raise SetupError(f"setup rollback refuses to remove a directory path: {relative}")
            path.unlink(missing_ok=True)
        if not paths:
            break
    remaining = run(["git", "status", "--short", "--untracked-files=all"], cwd=worktree).stdout.strip()
    if remaining:
        raise SetupError(f"setup migration worktree rollback did not converge: {remaining}")


def _restore_setup_database(
    root: Path,
    database: Path,
    backup: Path | None,
    mutation: Mapping[str, Any],
) -> None:
    if mutation["initialization"]:
        if database.is_symlink():
            raise SetupError(f"setup rollback database is a symlink: {database}")
        if database.exists():
            if not database.is_dir():
                raise SetupError(f"setup rollback database is not a directory: {database}")
            shutil.rmtree(database)
        for relative in _INITIALIZED_BEADS_FILES:
            path = _setup_repo_path(root, relative)
            if path.exists() and not tracked(root, relative):
                if path.is_dir() and not path.is_symlink():
                    raise SetupError(f"setup rollback refuses to remove directory: {relative}")
                path.unlink()
        parent = database.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
        return
    if backup is None:
        raise SetupError("setup rollback has no native Beads backup")
    pointers = _backup_pointer_snapshots(database.parent) if database.parent.is_dir() else {}
    try:
        if not database.is_dir():
            ensure_beads(root, initialize=True, database=database)
        run(
            _setup_beads_command(["bd", "backup", "restore", str(backup), "--force", "--json"], database),
            cwd=root,
        )
    finally:
        _restore_backup_pointers(database.parent, pointers)
    expected = _native_backup_inventory(backup)
    observed = _normalized_beads_inventory(_setup_client(root, database))
    if observed != expected:
        raise SetupError("setup rollback Beads inventory does not match the native backup")


def _rollback_setup_migration(
    root: Path,
    database: Path,
    backup: Path | None,
    worktree: Path,
    mutation: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        _restore_setup_database(root, database, backup, mutation)
    except Exception as exc:
        errors.append(f"Beads restore failed: {exc}")
    try:
        _reset_setup_migration_worktree(root, worktree, mutation)
    except Exception as exc:
        errors.append(f"migration worktree restore failed: {exc}")
    if errors:
        raise SetupError("; ".join(errors))
    return {
        "status": "rollback_verified",
        "database": str(database),
        "worktree": str(worktree),
        "backup": str(backup) if backup is not None else None,
    }


def _setup_migration_context(root: Path, digest: str) -> tuple[dict[str, Any], Path, Path, Path | None]:
    artifacts, expected_worktree = _setup_migration_paths(root, digest)
    plan_path = artifacts / "plan.json"
    if artifacts.is_symlink() or not artifacts.is_dir() or not plan_path.is_file() or plan_path.is_symlink():
        raise SetupError(f"saved setup migration artifacts are missing: {artifacts}")
    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        request = raw.get("request") if isinstance(raw, dict) else None
        initialize = request.get("initialize") if isinstance(request, dict) else False
        if not isinstance(initialize, bool):
            raise SetupError("saved setup migration request is invalid")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupError(f"saved setup migration plan cannot be read: {plan_path}") from exc
    reviewed, _ = _read_reviewed_setup_plan(
        plan_path,
        root=root,
        initialize=initialize,
        force=True,
        expected_digest=digest,
    )
    database = _setup_database_path(root, initialize=initialize)
    worktree, record = _setup_migration_worktree_record(root, digest)
    if record is None or not worktree.is_dir():
        raise SetupError(f"saved setup migration worktree is missing or unregistered: {expected_worktree}")
    backup = artifacts / "backup"
    if backup.is_symlink():
        raise SetupError(f"saved setup migration backup is a symlink: {backup}")
    backup_path = backup if backup.is_dir() else None
    if not reviewed["mutation_plan"]["initialization"] and backup_path is None:
        raise SetupError(f"saved setup migration backup is missing: {backup}")
    return reviewed, database, worktree, backup_path


def verify_setup(root_arg: Path, *, migration_id: str, delivery_mode: str) -> dict[str, Any]:
    root = git_root(root_arg)
    if not SHA256_RE.fullmatch(migration_id):
        raise SetupError("setup migration ID must be a SHA-256 digest")
    reviewed, database, worktree, backup = _setup_migration_context(root, migration_id)
    status, allowed_interaction_change = _setup_preflight(root, force=True)
    if status and not allowed_interaction_change:
        raise SetupError("source worktree has changes outside the forced interaction-log boundary")
    mutation = reviewed["mutation_plan"]
    _verify_setup_worktree_files(root, worktree, mutation)
    _verify_setup_beads_delta(database, backup, mutation)
    documentation = validate_docs(worktree)
    doctor_result = doctor(worktree, delivery_mode=delivery_mode, database=database)
    if doctor_result["status"] != "ok":
        raise SetupError("setup migration doctor failed: " + ", ".join(doctor_result["failed"]))
    return {
        "status": "ok",
        "verification": "passed",
        "migration_id": migration_id.lower(),
        "artifacts": str(_setup_migration_paths(root, migration_id)[0]),
        "worktree": str(worktree),
        "database": str(database),
        "backup": str(backup) if backup is not None else None,
        "documentation": documentation,
        "doctor": doctor_result,
    }


def rollback_setup(root_arg: Path, *, migration_id: str) -> dict[str, Any]:
    root = git_root(root_arg)
    if not SHA256_RE.fullmatch(migration_id):
        raise SetupError("setup migration ID must be a SHA-256 digest")
    reviewed, database, worktree, backup = _setup_migration_context(root, migration_id)
    status, allowed_interaction_change = _setup_preflight(root, force=True)
    if status and not allowed_interaction_change:
        raise SetupError("source worktree has changes outside the forced interaction-log boundary")
    result = _rollback_setup_migration(root, database, backup, worktree, reviewed["mutation_plan"])
    return {
        **result,
        "migration_id": migration_id.lower(),
        "artifacts": str(_setup_migration_paths(root, migration_id)[0]),
    }


def _setup_worktree_start_head(worktree: Path) -> str:
    entries = run(["git", "reflog", "--format=%H", "HEAD"], cwd=worktree).stdout.splitlines()
    if entries:
        return entries[-1].strip()
    return run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()


def cleanup_setup(root_arg: Path, *, migration_id: str) -> dict[str, Any]:
    root = git_root(root_arg)
    if not SHA256_RE.fullmatch(migration_id):
        raise SetupError("setup migration ID must be a SHA-256 digest")
    reviewed, database, worktree, backup = _setup_migration_context(root, migration_id)
    artifacts, expected_worktree = _setup_migration_paths(root, migration_id)
    _, record = _setup_migration_worktree_record(root, migration_id)
    if record is None or not expected_worktree.is_dir():
        raise SetupError("setup migration worktree registration is missing or ambiguous")
    source_head = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    worktree_head = run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()
    start_head = _setup_worktree_start_head(worktree)
    if start_head == worktree_head:
        raise SetupError("setup migration is not integrated; commit and integrate the detached worktree first")
    if run(["git", "merge-base", "--is-ancestor", worktree_head, source_head], cwd=root, check=False).returncode:
        raise SetupError("setup migration worktree result is not integrated into the source branch")
    changed = set(
        run(["git", "diff", "--name-only", f"{start_head}..{worktree_head}"], cwd=worktree).stdout.splitlines()
    )
    unexpected = sorted(changed - _setup_allowed_worktree_paths(reviewed["mutation_plan"]))
    if unexpected:
        raise SetupError("integrated setup migration contains unexpected paths: " + ", ".join(unexpected))
    ensure_clean_worktree(worktree)
    _verify_setup_worktree_files(
        root,
        worktree,
        reviewed["mutation_plan"],
        require_source_head=False,
    )
    _verify_setup_beads_delta(database, backup, reviewed["mutation_plan"])
    removal = run(["git", "worktree", "remove", str(worktree)], cwd=root, check=False)
    if removal.returncode:
        raise SetupError(removal.stderr.strip() or removal.stdout.strip() or "setup migration worktree removal failed")
    _, remaining = _setup_migration_worktree_record(root, migration_id)
    if remaining is not None or worktree.exists():
        raise SetupError("setup migration worktree removal could not be verified")
    if artifacts.is_symlink() or not artifacts.is_dir():
        raise SetupError(f"setup migration artifact directory is not removable: {artifacts}")
    shutil.rmtree(artifacts)
    if artifacts.exists():
        raise SetupError("setup migration artifact cleanup could not be verified")
    return {
        "status": "cleaned",
        "migration_id": migration_id.lower(),
        "worktree": str(worktree),
        "artifacts": str(artifacts),
    }


def _apply_forced_setup(
    root: Path,
    *,
    initialize: bool,
    plan_file: Path,
    expected_plan_sha256: str,
) -> dict[str, Any]:
    database = _setup_database_path(root, initialize=initialize)
    reviewed, plan_bytes = _read_reviewed_setup_plan(
        plan_file,
        root=root,
        initialize=initialize,
        force=True,
        expected_digest=expected_plan_sha256,
    )
    artifacts, _ = _setup_migration_paths(root, expected_plan_sha256)
    artifact_plan = _prepare_setup_artifacts(artifacts, plan_bytes)
    metrics: dict[str, Any] = {"phase_seconds": {}}
    phase_started = time.monotonic()
    backup = None
    if database.is_dir():
        backup = _create_verified_setup_backup(root, database, artifacts, metrics=metrics)
    metrics["phase_seconds"]["backup"] = round(time.monotonic() - phase_started, 6)
    phase_started = time.monotonic()
    worktree = _prepare_setup_worktree(root, expected_plan_sha256)
    metrics["phase_seconds"]["worktree"] = round(time.monotonic() - phase_started, 6)
    phase_started = time.monotonic()
    fresh = _fresh_setup_plan_for_migration(
        root,
        initialize=initialize,
        force=True,
        database=database,
        reviewed=reviewed,
        metrics=metrics,
    )
    metrics["phase_seconds"]["recheck"] = round(time.monotonic() - phase_started, 6)
    phase_started = time.monotonic()
    try:
        with _setup_signal_boundary():
            applied = _execute_setup_plan(
                worktree,
                reviewed["mutation_plan"],
                database=database,
                metrics=metrics,
            )
            if reviewed["mutation_plan"]["initialization"]:
                _relocate_initialized_beads_files(worktree, database)
            validate_docs(worktree)
            policy = _setup_repo_path(worktree, ".beads/.gitignore")
            if not policy.is_file() or "interactions.jsonl" not in policy.read_text().splitlines():
                raise SetupError("setup migration postcondition failed for interaction-log policy")
            if reviewed["mutation_plan"]["initialization"]:
                _relocate_initialized_beads_files(worktree, database)
            _verify_setup_beads_delta(
                database,
                backup,
                reviewed["mutation_plan"],
                metrics=metrics,
            )
        metrics["phase_seconds"]["execute_verify"] = round(time.monotonic() - phase_started, 6)
    except (Exception, KeyboardInterrupt) as exc:
        try:
            rollback = _rollback_setup_migration(
                root,
                database,
                backup,
                worktree,
                reviewed["mutation_plan"],
            )
        except Exception as rollback_exc:
            raise SetupError(
                f"setup migration failed: {exc}; rollback failed: {rollback_exc}; "
                f"migration_id={expected_plan_sha256.lower()}; artifacts={artifacts}; "
                f"worktree={worktree}; database={database}; recovery_required=true; "
                "retain all migration artifacts and do not repair Beads manually"
            ) from exc
        raise SetupError(
            f"setup migration failed: {exc}; rollback_verified=true; recovery_required=false; "
            f"migration_id={expected_plan_sha256.lower()}; artifacts={artifacts}; "
            f"worktree={worktree}; database={database}; rollback={rollback}"
        ) from exc
    return {
        "status": applied.get("status", "ok"),
        "migration_id": expected_plan_sha256.lower(),
        "artifacts": str(artifacts),
        "plan_file": str(artifact_plan),
        "worktree": str(worktree),
        "database": str(database),
        "backup": str(backup) if backup is not None else None,
        "plan": fresh,
        "applied": applied,
        "metrics": metrics,
    }


def apply_setup(
    root_arg: Path,
    *,
    initialize: bool,
    force: bool,
    expected_plan_sha256: str | None = None,
    plan_file: Path | None = None,
) -> dict[str, Any]:
    if not expected_plan_sha256:
        raise SetupError("setup plan digest is required")
    if force:
        if plan_file is None:
            raise SetupError("setup plan file is required for forced setup")
        if not SHA256_RE.fullmatch(expected_plan_sha256):
            raise SetupError("setup plan digest must be a SHA-256 digest")
        root = git_root(root_arg)
        _require_supported_interaction_index(root)
        status, allowed_interaction_change = _setup_preflight(root, force=True)
        if status and not allowed_interaction_change:
            raise SetupError("worktree changes are present outside the forced interaction-log repair boundary")
        return _apply_forced_setup(
            root,
            initialize=initialize,
            plan_file=plan_file,
            expected_plan_sha256=expected_plan_sha256,
        )
    root = git_root(root_arg)
    _require_supported_interaction_index(root)
    ensure_clean_worktree(root)
    plan = setup_plan(root, initialize=initialize, force=force)
    if plan["status"] != "ready":
        raise SetupError("setup apply preconditions changed: " + "; ".join(plan["preconditions"]["blocked"]))
    mutation = canonicalize_setup_plan(plan["mutation_plan"])
    digest = setup_plan_digest(mutation)
    if digest != expected_plan_sha256 or digest != plan["plan_sha256"]:
        raise SetupError("setup authority state changed since plan; rerun setup plan and review it")

    beads_existed = _setup_repo_path(root, ".beads").is_dir()
    snapshot_paths = {
        path for operation in mutation["filesystem"] for path in (operation["source"], operation["destination"]) if path
    }
    snapshot_paths.update(operation["affected_path"] for operation in mutation["navigation_references"])
    snapshot_paths.update(path for operation in mutation["formulas"] for path in (operation["destination"],))
    snapshot_paths.update(str(operation["path"]) for operation in mutation["git_index"])
    snapshot_destinations = {path: _setup_repo_path(root, path) for path in snapshot_paths}
    snapshots = {
        path: destination.read_bytes() if destination.is_file() else None
        for path, destination in snapshot_destinations.items()
    }
    index_snapshots = {
        str(operation["path"]): _setup_index_entries(root, str(operation["path"]))
        for operation in mutation["git_index"]
    }
    try:
        result = _execute_setup_plan(root, mutation)
        for operation in mutation["git_index"]:
            path = str(operation["path"])
            if _setup_index_entries(root, path):
                raise SetupError(f"setup Git-index postcondition failed: {path} remains tracked")
            if snapshots[path] is not None and _setup_repo_path(root, path).read_bytes() != snapshots[path]:
                raise SetupError(f"setup Git-index operation changed worktree bytes: {path}")
        if plan.get("documentation", {}).get("unresolved_outside_markdown"):
            result["status"] = "manual-action-required"
        validate_docs(root)
        policy = _setup_repo_path(root, ".beads/.gitignore")
        if "interactions.jsonl" not in policy.read_text().splitlines():
            raise SetupError("setup postcondition failed for interaction-log policy")
    except Exception as exc:
        recovery: list[str] = []
        recovery_errors: list[str] = []
        try:
            _restore_setup_files(root, snapshots)
            recovery.append("restored setup-owned files")
        except Exception as recovery_exc:
            recovery_errors.append(f"setup-owned file restore failed: {recovery_exc}")
        beads_path = _setup_repo_path(root, ".beads")
        if not beads_existed and beads_path.exists():
            shutil.rmtree(beads_path, ignore_errors=True)
            if _setup_repo_path(root, ".beads").exists():
                recovery_errors.append("internally created .beads directory removal failed")
            else:
                recovery.append("removed internally created .beads directory")
        try:
            _restore_setup_index(root, index_snapshots)
            recovery.append("restored setup-owned Git index")
        except Exception as recovery_exc:
            recovery_errors.append(f"setup-owned Git-index restore failed: {recovery_exc}")
        graph_mutation = bool(mutation["template_deletions"]) or any(
            mutation[field] for field in ("beads_issues", "dependencies", "supersessions")
        )
        rollback_completed = not graph_mutation and not recovery_errors
        if force:
            recovery.append("inspect documented migration moves and Beads normalization before retry")
        details = recovery + recovery_errors
        raise SetupError(
            f"setup apply failed: {exc}; observed recovery: "
            + "; ".join(details)
            + f"; rollback_completed={str(rollback_completed).lower()}"
            + f"; mutation_state_uncertain={str(graph_mutation or bool(recovery_errors)).lower()}"
        ) from exc
    return {"status": result.get("status", "ok"), "plan": plan, "applied": result}


def install(root_arg: Path, *, initialize: bool, force: bool) -> dict[str, Any]:
    root = git_root(root_arg)
    _setup_repo_path(root, ".beads")
    _setup_repo_path(root, ".beads/formulas")
    _validate_setup_tree(root, "docs")
    ensure_beads(root, initialize=initialize)
    client = BeadsClient(root)
    version = client.check_version()
    source_dir = _validate_setup_tree(package_root(), "formulas")
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
            _setup_repo_path(package_root(), f"formulas/{name}.formula.toml"),
            _setup_repo_path(root, f".beads/formulas/{name}.formula.toml"),
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
        if _is_beads_runtime_path(path):
            result.append(path)
    return sorted(result)


def _remote_host(remote: str) -> str | None:
    if "://" in remote:
        return urlsplit(remote).hostname
    authority, separator, _ = remote.partition(":")
    if separator and "/" not in authority:
        return authority.rsplit("@", 1)[-1] or None
    return None


def workflow_topology_diagnostics(client: BeadsClient) -> list[str]:
    inventory = client.list(all_statuses=True)
    mutations = _setup_normalization_plan(client, inventory=inventory)
    polluted = [
        mutation["issue_id"]
        for mutation in mutations
        if set(mutation["remove_labels"]) & {"workflow:feature", "workflow:project-alignment"}
    ]
    if polluted:
        raise SetupError("legacy workflow root identity on descendants: " + ", ".join(polluted))
    return [
        f"active legacy feature: run /adopt-feature {issue['id']}"
        for issue in sorted(inventory, key=lambda item: str(item["id"]))
        if is_legacy_feature_root(issue) and not is_feature_root(issue) and issue.get("status") != "closed"
    ]


def doctor(
    root_arg: Path,
    *,
    delivery_mode: str,
    database: Path | None = None,
) -> dict[str, Any]:
    if delivery_mode not in {"merge", "pr"}:
        raise SetupError("delivery_mode must be explicitly merge or pr")
    root = git_root(root_arg)
    beads_path = _setup_repo_path(root, ".beads")
    _setup_repo_path(root, ".beads/formulas")
    ignore_path = _setup_repo_path(root, ".beads/.gitignore")
    source_dir = _validate_setup_tree(package_root(), "formulas")
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
    if beads_path.is_dir() or database is not None:
        client = _setup_client(root, database)
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
    for name in FORMULA_NAMES:

        def formula_check(name=name) -> str:
            if client is None:
                raise SetupError("Beads is not initialized")
            installed = _setup_repo_path(root, f".beads/formulas/{name}.formula.toml")
            source = source_dir / f"{name}.formula.toml"
            if not installed.is_file():
                raise SetupError(f"missing installed formula: {installed}")
            if installed.read_bytes() != source.read_bytes():
                raise SetupError(f"installed formula differs from package: {installed}")
            if database is None:
                validate_formula(root, name)
            else:
                validate_formula(root, name, database=database, seed=False)
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
        if not ignore_path.is_file() or "interactions.jsonl" not in ignore_path.read_text().splitlines():
            raise SetupError(".beads/.gitignore does not ignore interactions.jsonl")
        return "local-only"

    check(
        "interaction_policy",
        "run setup apply --force to restore the local interaction-log policy",
        interaction_policy,
    )

    def workflow_topology_check() -> list[str]:
        if client is None:
            raise SetupError("Beads is not initialized")
        return workflow_topology_diagnostics(client)

    check(
        "workflow_topology",
        "repair the reported native topology or run setup apply --force for mechanically proven pollution",
        workflow_topology_check,
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
    return client.list(
        all_statuses=True,
        include_templates=True,
        include_gates=True,
    )


def legacy_template_artifacts(
    client: BeadsClient,
    *,
    inventory: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for summary in inventory if inventory is not None else all_issue_inventory(client):
        issue_id = str(summary.get("id") or "")
        if not any(issue_id == name or issue_id.startswith(f"{name}.") for name in FORMULA_NAMES):
            continue
        issue = summary
        if "is_template" not in summary and not has_label(summary, "template"):
            issue = client.show(issue_id)
        if issue.get("is_template") is not True and not has_label(issue, "template"):
            raise SetupError(f"reserved dstack template ID is used by non-template issue {issue_id}")
        result.append(dict(issue))
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
        _setup_repo_path(root, ".beads/.gitignore"),
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
    destination = _setup_repo_path(root, canonical)
    title = str(feature.get("title") or slug).removeprefix("Feature: ")
    ensure_feature_navigation(
        root,
        slug=slug,
        title=title,
        reconciled=destination.with_name("index.md").is_file(),
    )


def missing_feature_reconciliations(client: BeadsClient) -> list[str]:
    missing: list[str] = []
    inventory = client.list(all_statuses=True)
    for feature in feature_roots_from_inventory(inventory):
        if not has_label(feature, "workflow:feature") or feature.get("status") != "closed":
            continue
        slug = feature_slug(feature)
        if not slug:
            continue
        design = client.root / canonical_feature_design_path(slug)
        reconciliation = design.with_name("index.md")
        if design.is_file() and not reconciliation.is_file():
            missing.append(reconciliation.relative_to(client.root).as_posix())
    return sorted(set(missing))


def _setup_mutation_arguments(mutation: Mapping[str, Any]) -> list[str]:
    arguments: list[str] = []
    for key, value in mutation["set_metadata"].items():
        if value is None:
            arguments.extend(["--unset-metadata", key])
        else:
            arguments.extend(["--set-metadata", f"{key}={value}"])
    for key in mutation["unset_metadata"]:
        arguments.extend(["--unset-metadata", key])
    for label in mutation["add_labels"]:
        arguments.extend(["--add-label", label])
    for label in mutation["remove_labels"]:
        arguments.extend(["--remove-label", label])
    return arguments


def _workflow_descendant_ids(
    inventory: Sequence[Mapping[str, Any]],
    roots: Sequence[Mapping[str, Any]],
) -> set[str]:
    children: dict[str, list[str]] = {}
    for issue in inventory:
        parent = issue_parent(issue)
        issue_id = str(issue.get("id") or "")
        if parent and issue_id:
            children.setdefault(parent, []).append(issue_id)
    selected = {str(root["id"]) for root in roots}
    stack = list(selected)
    while stack:
        issue_id = stack.pop()
        for child_id in children.get(issue_id, []):
            if child_id not in selected:
                selected.add(child_id)
                stack.append(child_id)
    return selected


def _normalize_current_workflows(
    client: BeadsClient,
    *,
    force: bool,
    kinds: set[str],
) -> list[str]:
    inventory = client.list(all_statuses=True)
    feature_roots = [root for root in feature_roots_from_inventory(inventory) if has_label(root, "workflow:feature")]
    alignment_roots = alignment_roots_from_inventory(inventory)
    selected_roots = [
        *(feature_roots if "feature" in kinds else []),
        *(alignment_roots if "alignment" in kinds else []),
    ]
    selected_ids = _workflow_descendant_ids(inventory, selected_roots)
    mutations = [
        mutation
        for mutation in _setup_normalization_plan(client, inventory=inventory)
        if mutation["issue_id"] in selected_ids
    ]
    if force and "feature" in kinds:
        for root in feature_roots:
            slug = feature_slug(root)
            if not slug:
                continue
            canonical = canonical_feature_design_path(slug)
            design = root_metadata_value(root, "dstack.design_path", "design_path") or canonical
            if design != canonical:
                migrate_feature_design(client.root, root, slug=slug, design_path=design)
            elif not (client.root / canonical).is_file():
                raise SetupError("canonical feature design is missing")
    if force:
        for mutation in mutations:
            client.update(str(mutation["issue_id"]), *_setup_mutation_arguments(mutation))
    return sorted(str(mutation["issue_id"]) for mutation in mutations)


def normalize_current_features(client: BeadsClient, *, force: bool) -> list[str]:
    return _normalize_current_workflows(client, force=force, kinds={"feature"})


def normalize_current_alignments(client: BeadsClient, *, force: bool) -> list[str]:
    return _normalize_current_workflows(client, force=force, kinds={"alignment"})


def repair_legacy(root_arg: Path, *, force: bool) -> dict[str, Any]:
    root = git_root(root_arg)
    _setup_repo_path(root, ".beads")
    _setup_repo_path(root, ".beads/.gitignore")
    _validate_setup_tree(root, "docs")
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

    normalized = _normalize_current_workflows(
        client,
        force=force,
        kinds={"feature", "alignment"},
    )
    missing_reconciliations = missing_feature_reconciliations(client)
    interaction_tracked = tracked(root, ".beads/interactions.jsonl")
    beads_ignore = _setup_repo_path(root, ".beads/.gitignore")
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
            setup_parser.add_argument("--plan-file", type=Path)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, default=Path.cwd())
    verify_parser.add_argument("--migration-id", required=True)
    verify_parser.add_argument(
        "--delivery-mode",
        choices=("merge", "pr"),
        required=True,
        help="delivery mode to validate explicitly",
    )

    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("--root", type=Path, default=Path.cwd())
    rollback_parser.add_argument("--migration-id", required=True)

    cleanup_parser = sub.add_parser("cleanup")
    cleanup_parser.add_argument("--root", type=Path, default=Path.cwd())
    cleanup_parser.add_argument("--migration-id", required=True)

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--root", type=Path, default=Path.cwd())
    doctor_parser.add_argument(
        "--delivery-mode",
        choices=("merge", "pr"),
        required=True,
        help="delivery profile to validate explicitly",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        require_locked_runtime()
    except DstackError as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
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
                plan_file=args.plan_file,
            )
        elif args.command == "verify":
            payload = verify_setup(args.root, migration_id=args.migration_id, delivery_mode=args.delivery_mode)
        elif args.command == "rollback":
            payload = rollback_setup(args.root, migration_id=args.migration_id)
        elif args.command == "cleanup":
            payload = cleanup_setup(args.root, migration_id=args.migration_id)
        else:
            payload = doctor(args.root, delivery_mode=args.delivery_mode)
    except DstackError as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if payload.get("status") in {"ok", "ready", "rollback_verified", "cleaned"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
