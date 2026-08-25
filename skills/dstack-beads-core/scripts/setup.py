#!/usr/bin/env python3
"""Install, validate, and explicitly repair dstack's Beads integration."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from dstack_docs import (
    create_foundation,
    initialize_docs,
    legacy_documentation_plan,
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
    filesystem = documentation_change_plan(root)
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
            filesystem.append(
                {"path": destination.relative_to(root).as_posix(), "action": action}
            )

    git_index: list[dict[str, str]] = []
    beads: list[dict[str, str]] = []
    if not beads_exists:
        beads.append({"action": "initialize", "target": ".beads"})
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
            beads.extend(
                {"action": "delete-template", "target": str(item["id"])} for item in templates
            )
            beads.extend(
                {"action": "normalize", "target": issue_id}
                for issue_id in normalized
            )

    migration = legacy_documentation_plan(root) if force else {
        "configured_source_moves": [],
        "referenced_content_moves": [],
        "unresolved_outside_markdown": [],
    }
    payload = {
        "status": "blocked" if blocked else "ready",
        "root": str(root),
        "preconditions": {"clean_worktree": not status, "blocked": blocked},
        "filesystem": sorted(filesystem, key=lambda item: (item["path"], item["action"])),
        "git_index": git_index,
        "beads": beads,
        "formulas": formulas,
        "documentation": migration,
    }
    payload["plan_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def _restore_setup_files(root: Path, snapshots: Mapping[str, bytes | None]) -> None:
    for relative, content in snapshots.items():
        path = root / relative
        if content is None:
            path.unlink(missing_ok=True)
            continue
        atomic_replace(path, content)


def apply_setup(
    root_arg: Path,
    *,
    initialize: bool,
    force: bool,
    expected_plan_sha256: str | None = None,
) -> dict[str, Any]:
    root = git_root(root_arg)
    ensure_clean_worktree(root)
    plan = setup_plan(root, initialize=initialize, force=force)
    if plan["status"] != "ready":
        raise SetupError(
            "setup apply preconditions changed: " + "; ".join(plan["preconditions"]["blocked"])
        )
    if expected_plan_sha256 and plan["plan_sha256"] != expected_plan_sha256:
        raise SetupError(
            "setup authority state changed since plan; rerun setup plan and review it"
        )

    beads_existed = (root / ".beads").is_dir()
    snapshot_paths = {
        item["path"] for item in plan["filesystem"]
    } | {".beads/.gitignore"}
    snapshots = {
        path: (root / path).read_bytes() if (root / path).is_file() else None
        for path in snapshot_paths
    }
    interaction_was_tracked = tracked(root, ".beads/interactions.jsonl")
    try:
        result = install(root, initialize=initialize, force=force)
        for name in FORMULA_NAMES:
            installed = root / ".beads/formulas" / f"{name}.formula.toml"
            source = package_root() / "formulas" / f"{name}.formula.toml"
            if not installed.is_file() or installed.read_bytes() != source.read_bytes():
                raise SetupError(f"setup postcondition failed for {installed}")
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
    return {"status": "ok", "plan": plan, "applied": result}


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
            "template_artifacts_removed": repair["template_artifacts_removed"],
            "molecule_items_normalized": repair["molecule_items_normalized"],
            "missing_feature_reconciliations": repair["missing_feature_reconciliations"],
        }
    return {
        "status": "ok",
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
        "status": "ok",
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
