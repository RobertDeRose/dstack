#!/usr/bin/env python3
"""Synchronize the optional dstack Pi reviewer definitions into a Pi agent directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


MANIFEST_NAME = ".dstack-pi-reviewers.json"
MANIFEST_SCHEMA = "dstack.pi-reviewer-install.v1"
ROSTER_SCHEMA = "dstack.pi-reviewer-roster.v1"


@dataclass(frozen=True)
class AgentSpec:
    role: str
    async_enabled: bool
    tools: tuple[str, ...]


ROSTER: dict[str, AgentSpec] = {
    "dstack-context-builder": AgentSpec("context-builder", False, ("read", "grep", "find", "ls", "bash", "write")),
    "dstack-architecture-reviewer": AgentSpec("architecture", True, ("read", "grep", "find", "ls")),
    "dstack-simplicity-reviewer": AgentSpec("simplicity", True, ("read", "grep", "find", "ls")),
    "dstack-documentation-reviewer": AgentSpec("documentation", True, ("read", "grep", "find", "ls")),
    "dstack-execution-reviewer": AgentSpec("execution", True, ("read", "grep", "find", "ls")),
    "dstack-task-reviewer": AgentSpec("task", False, ("read", "grep", "find", "ls")),
    "dstack-delivery-reviewer": AgentSpec("delivery", True, ("read", "grep", "find", "ls")),
    "dstack-drift-reviewer": AgentSpec("drift", True, ("read", "grep", "find", "ls")),
}


@dataclass(frozen=True)
class Asset:
    name: str
    path: Path
    digest: str


class SyncError(Exception):
    def __init__(self, message: str, *, status: str = "error") -> None:
        super().__init__(message)
        self.status = status
        self.exit_code = 2 if status == "conflict" else 1


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_version(source: Path) -> str:
    skill = source.parents[1] / "SKILL.md"
    if not skill.is_file():
        return "unknown"
    match = re.search(r'^\s+version:\s+["\']?([^"\'\s]+)', skill.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else "unknown"


def _parse_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        message = f"Agent definition lacks YAML frontmatter: {path}"
        raise SyncError(message)
    end = text.find("\n---\n", 4)
    if end < 0:
        message = f"Agent definition has unterminated YAML frontmatter: {path}"
        raise SyncError(message)
    fields: dict[str, object] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.lower() in {"true", "false"}:
            fields[key.strip()] = value.lower() == "true"
        elif key.strip() == "tools":
            fields[key.strip()] = tuple(item.strip() for item in value.split(",") if item.strip())
        else:
            fields[key.strip()] = value
    return fields


def _validate_asset(name: str, path: Path) -> list[str]:
    spec = ROSTER[name]
    if not path.is_file() or path.is_symlink():
        return [f"missing or unsafe asset: {path.name}"]
    try:
        fields = _parse_frontmatter(path)
    except (OSError, SyncError) as exc:
        return [str(exc)]
    errors: list[str] = []
    expected = {
        "name": name,
        "mode": "interactive",
        "auto-exit": True,
        "async": spec.async_enabled,
        "session-mode": "lineage-only",
        "trust-project": True,
        "tools": spec.tools,
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            errors.append(f"{path.name}: expected frontmatter {key}={value!r}, got {fields.get(key)!r}")
    for forbidden in ("model", "thinking"):
        if forbidden in fields:
            errors.append(f"{path.name}: frontmatter must omit {forbidden}")
    return errors


def _assets(source: Path) -> tuple[dict[str, Asset], str]:
    if not source.is_dir() or source.is_symlink():
        message = f"Reviewer asset directory is missing or unsafe: {source}"
        raise SyncError(message)
    errors: list[str] = []
    assets: dict[str, Asset] = {}
    for name in ROSTER:
        path = source / f"{name}.md"
        errors.extend(_validate_asset(name, path))
        if path.is_file() and not path.is_symlink():
            assets[name] = Asset(name, path, _sha256(path))
    if errors:
        raise SyncError("\n".join(errors))
    return assets, _source_version(source)


def _reject_symlink_components(path: Path) -> Path:
    absolute = path.absolute()
    current = absolute
    missing: list[Path] = []
    while not os.path.lexists(current) and current != current.parent:
        missing.append(current)
        current = current.parent
    if current.is_symlink():
        message = f"Refusing symlinked Pi agent target component: {current}"
        raise SyncError(message)
    for component in missing:
        if os.path.lexists(component) and component.is_symlink():
            message = f"Refusing symlinked Pi agent target component: {component}"
            raise SyncError(message)
    return absolute


def _resolve_target(value: str, project_root: Path) -> Path:
    if value == "project":
        return _reject_symlink_components(project_root / ".pi" / "agents")
    if value == "global":
        configured = os.environ.get("PI_CODING_AGENT_DIR", "").strip()
        config = Path(configured or "~/.pi/agent").expanduser()
        return _reject_symlink_components(config / "agents")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return _reject_symlink_components(candidate)


def _validate_manifest(value: dict[str, Any], path: Path) -> None:
    required = {"schema", "roster_schema", "source_skill", "source_version", "files"}
    if set(value) != required:
        message = f"Installer manifest has unexpected metadata: {path}"
        raise SyncError(message)
    if value["schema"] != MANIFEST_SCHEMA or value["roster_schema"] != ROSTER_SCHEMA:
        message = f"Unsupported installer manifest: {path}"
        raise SyncError(message)
    if value["source_skill"] != "dstack-core" or not isinstance(value["source_version"], str):
        message = f"Installer manifest has invalid source metadata: {path}"
        raise SyncError(message)
    files = value["files"]
    expected = {f"{name}.md" for name in ROSTER}
    if not isinstance(files, dict) or set(files) != expected:
        message = f"Installer manifest has an incomplete file inventory: {path}"
        raise SyncError(message)
    for filename, entry in files.items():
        if not isinstance(entry, dict) or set(entry) != {"sha256", "managed"}:
            message = f"Installer manifest has invalid file metadata: {filename}"
            raise SyncError(message)
        if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            message = f"Installer manifest has an invalid hash: {filename}"
            raise SyncError(message)
        if not isinstance(entry["managed"], bool):
            message = f"Installer manifest has an invalid ownership flag: {filename}"
            raise SyncError(message)


def _load_manifest(target: Path) -> dict[str, Any] | None:
    path = target / MANIFEST_NAME
    if not os.path.lexists(path):
        return None
    if path.is_symlink():
        message = f"Refusing symlinked installer manifest: {path}"
        raise SyncError(message, status="conflict")
    _reject_symlink_components(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        message = f"Unable to read installer manifest {path}: {exc}"
        raise SyncError(message) from exc
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        message = f"Unsupported installer manifest: {path}"
        raise SyncError(message)
    _validate_manifest(value, path)
    return value


def _manifest_files(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if manifest is None:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for filename, entry in manifest["files"].items():
        if not isinstance(filename, str) or not isinstance(entry, dict):
            message = "Installer manifest contains an invalid file entry"
            raise SyncError(message)
        result[filename] = entry
    return result


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_manifest(target: Path, source_version: str, files: dict[str, dict[str, Any]]) -> None:
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "roster_schema": ROSTER_SCHEMA,
        "source_skill": "dstack-core",
        "source_version": source_version,
        "files": {name: files[name] for name in sorted(files)},
    }
    _atomic_write(target / MANIFEST_NAME, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())


def _discovered(target: Path) -> list[str]:
    if not target.is_dir():
        return []
    return sorted(
        name for name in ROSTER if (target / f"{name}.md").is_file() and not (target / f"{name}.md").is_symlink()
    )


def _result_list(result: dict[str, object], key: str) -> list[str]:
    value = result[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        message = f"Result field is not a string list: {key}"
        raise TypeError(message)
    return cast(list[str], value)


def _base_result(status: str, target: Path, source_version: str) -> dict[str, object]:
    return {
        "status": status,
        "target": str(target),
        "source_version": source_version,
        "manifest": str(target / MANIFEST_NAME),
        "installed": [],
        "updated": [],
        "unchanged": [],
        "removed": [],
        "conflicts": [],
        "missing": [],
        "stale": [],
        "discovered": _discovered(target),
    }


def _sync(source: Path, target: Path, *, check: bool, remove: bool) -> tuple[dict[str, object], int]:
    assets, source_version = _assets(source)
    manifest = _load_manifest(target) if target.exists() else None
    old_files = _manifest_files(manifest)

    if remove:
        if manifest is None:
            result = _base_result("missing", target, source_version)
            result["missing"] = [MANIFEST_NAME]
            return result, 1
        result = _base_result("ok", target, source_version)
        remaining: dict[str, dict[str, Any]] = {}
        for filename, entry in old_files.items():
            if not entry.get("managed", False):
                remaining[filename] = entry
                continue
            path = target / filename
            if not os.path.lexists(path):
                remaining[filename] = {"sha256": entry["sha256"], "managed": False}
                continue
            if path.is_symlink() or _sha256(path) != entry["sha256"]:
                _result_list(result, "conflicts").append(filename)
                remaining[filename] = entry
                continue
            path.unlink()
            _result_list(result, "removed").append(filename.removesuffix(".md"))
            remaining[filename] = {"sha256": entry["sha256"], "managed": False}
        if any(entry["managed"] for entry in remaining.values()):
            _write_manifest(target, source_version, remaining)
        else:
            (target / MANIFEST_NAME).unlink(missing_ok=True)
        result["discovered"] = _discovered(target)
        if result["conflicts"]:
            result["status"] = "conflict"
            return result, 2
        return result, 0

    result = _base_result("ok", target, source_version)
    if manifest is not None and manifest["source_version"] != source_version:
        _result_list(result, "stale").append("source_version")
    if not target.is_dir():
        result["missing"] = sorted(ROSTER)
        if check:
            result["status"] = "missing"
            return result, 1
    conflicts: list[str] = []
    actions: dict[str, str] = {}
    new_files: dict[str, dict[str, Any]] = {}
    for name, asset in assets.items():
        filename = f"{name}.md"
        path = target / filename
        old_entry = old_files.get(filename)
        if os.path.lexists(path):
            if path.is_symlink():
                conflicts.append(filename)
                managed = bool(old_entry and old_entry.get("managed", False))
                new_files[filename] = {"sha256": asset.digest, "managed": managed}
                continue
            _reject_symlink_components(path)
            current_digest = _sha256(path)
            if current_digest == asset.digest:
                _result_list(result, "unchanged").append(name)
                if not old_entry or old_entry["sha256"] != asset.digest:
                    _result_list(result, "stale").append(filename)
                managed = bool(old_entry and old_entry.get("managed", False))
            elif old_entry and old_entry.get("managed") and current_digest == old_entry.get("sha256"):
                actions[name] = "update"
                managed = True
            else:
                conflicts.append(filename)
                managed = bool(old_entry and old_entry.get("managed", False))
        else:
            actions[name] = "install"
            _result_list(result, "missing").append(name)
            managed = True
        new_files[filename] = {"sha256": asset.digest, "managed": managed}

    result["conflicts"] = sorted(conflicts)
    if conflicts:
        result["status"] = "conflict"
        return result, 2
    if manifest is None:
        _result_list(result, "missing").append(MANIFEST_NAME)
    if check:
        if result["missing"] or result["stale"] or actions:
            result["status"] = "missing" if result["missing"] else "stale"
            result["installed"] = []
            result["updated"] = sorted(name for name in actions if actions[name] == "update")
            return result, 1
        result["discovered"] = _discovered(target)
        return result, 0

    for name in sorted(actions):
        if actions[name] == "update":
            _result_list(result, "updated").append(name)
        else:
            _result_list(result, "installed").append(name)

    target.mkdir(parents=True, exist_ok=True)
    result["missing"] = []
    for name in actions:
        asset = assets[name]
        _atomic_write(target / f"{name}.md", asset.path.read_bytes())
    _write_manifest(target, source_version, new_files)
    result["discovered"] = _discovered(target)
    return result, 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="project, global, or an explicit agent directory")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path)
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--check", action="store_true", help="validate without writing")
    operations.add_argument(
        "--remove", action="store_true", help="remove unchanged files previously installed by dstack"
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source = (args.source or Path(__file__).resolve().parent.parent / "assets" / "pi-reviewers").expanduser().resolve()
    project_root = args.project_root.expanduser().resolve()
    try:
        target = _resolve_target(args.target, project_root)
        result, code = _sync(source, target, check=args.check, remove=args.remove)
    except (OSError, SyncError) as exc:
        result = {"status": getattr(exc, "status", "error"), "error": str(exc)}
        code = exc.exit_code if isinstance(exc, SyncError) else 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("status") == "ok":
        print(f"Pi reviewer definitions synchronized in {result['target']}")
    else:
        print(f"Pi reviewer synchronization {result.get('status', 'failed')}: {result.get('error', '')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
