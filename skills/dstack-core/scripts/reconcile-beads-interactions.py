#!/usr/bin/env python3
# ruff: noqa: EM101, EM102, S603, S607
"""Safely reconcile append-only Beads interaction evidence across worktrees."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


INTERACTIONS = Path(".beads/interactions.jsonl")
LINEAGE_DEPENDENCY_TYPES = frozenset({"discovered-from", "parent-child"})


class ReconciliationError(RuntimeError):
    """Raised when interaction evidence is unsafe to reconcile."""


def git(worktree: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        stderr = result.stderr.decode(errors="replace").strip()
        raise ReconciliationError(f"git {' '.join(args)} failed in {worktree}: {stderr}")
    return result.stdout


def bd_show(worktree: Path, issue_id: str) -> dict[str, Any]:
    result = subprocess.run(
        ["bd", "show", issue_id, "--json"],
        cwd=worktree,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        stderr = result.stderr.decode(errors="replace").strip()
        raise ReconciliationError(f"bd show failed for {issue_id} in {worktree}: {stderr}")
    try:
        payload: Any = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconciliationError(f"bd show returned invalid JSON for {issue_id}") from error
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ReconciliationError(f"bd show returned an unexpected record for {issue_id}")
    record = payload[0]
    if record.get("id") != issue_id:
        raise ReconciliationError(f"bd show returned the wrong issue for {issue_id}")
    return record


def belongs_to_feature_lineage(
    worktree: Path,
    issue_id: str,
    root_id: str,
    *,
    cache: dict[str, bool],
    visiting: set[str],
) -> bool:
    if issue_id == root_id or issue_id.startswith(f"{root_id}."):
        return True
    if issue_id in cache:
        return cache[issue_id]
    if issue_id in visiting:
        return False
    visiting.add(issue_id)
    record = bd_show(worktree, issue_id)
    dependencies = record.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise ReconciliationError(f"bd show returned invalid dependencies for {issue_id}")
    related = False
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise ReconciliationError(f"bd show returned an invalid dependency for {issue_id}")
        dependency_id = dependency.get("id")
        dependency_type = dependency.get("dependency_type")
        if (
            isinstance(dependency_id, str)
            and dependency_type in LINEAGE_DEPENDENCY_TYPES
            and belongs_to_feature_lineage(
                worktree,
                dependency_id,
                root_id,
                cache=cache,
                visiting=visiting,
            )
        ):
            related = True
            break
    visiting.remove(issue_id)
    cache[issue_id] = related
    return related


def validate_worktree(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ReconciliationError(f"worktree does not exist: {resolved}")
    top = Path(git(resolved, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != resolved:
        raise ReconciliationError(f"path is not a worktree root: {resolved}")
    return resolved


def status_entries(worktree: Path) -> list[tuple[str, str]]:
    fields = git(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(fields) and fields[index]:
        field = fields[index]
        if len(field) < 4:
            raise ReconciliationError(f"unrecognized git status entry in {worktree}")
        status = field[:2].decode(errors="replace")
        path = field[3:].decode(errors="surrogateescape")
        entries.append((status, path))
        index += 2 if status[0] in "RC" else 1
    return entries


def require_interaction_only_status(worktree: Path, *, allow_clean: bool) -> bool:
    entries = status_entries(worktree)
    if not entries and allow_clean:
        return False
    expected = [(" M", INTERACTIONS.as_posix())]
    if entries != expected:
        rendered = ", ".join(f"{status} {path}" for status, path in entries) or "clean"
        raise ReconciliationError(f"worktree must contain only an unstaged {INTERACTIONS} change; found: {rendered}")
    return True


def parse_records(data: bytes, *, source: str) -> tuple[list[tuple[str, str, bytes]], dict[str, bytes]]:
    if data and not data.endswith(b"\n"):
        raise ReconciliationError(f"{source} must end with a newline")
    records: list[tuple[str, str, bytes]] = []
    by_id: dict[str, bytes] = {}
    for line_number, raw in enumerate(data.splitlines(keepends=True), start=1):
        if not raw.strip():
            raise ReconciliationError(f"{source}:{line_number} is blank")
        try:
            value: Any = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReconciliationError(f"{source}:{line_number} is not valid JSON") from error
        if not isinstance(value, dict):
            raise ReconciliationError(f"{source}:{line_number} is not a JSON object")
        interaction_id = value.get("id")
        issue_id = value.get("issue_id")
        if not isinstance(interaction_id, str) or not interaction_id:
            raise ReconciliationError(f"{source}:{line_number} has no interaction id")
        if not isinstance(issue_id, str) or not issue_id:
            raise ReconciliationError(f"{source}:{line_number} has no issue id")
        if interaction_id in by_id:
            raise ReconciliationError(f"{source} repeats interaction id {interaction_id}")
        records.append((interaction_id, issue_id, raw))
        by_id[interaction_id] = raw
    return records, by_id


def appended_records(worktree: Path, root_id: str) -> tuple[list[tuple[str, str, bytes]], bytes]:
    require_interaction_only_status(worktree, allow_clean=False)
    head = git(worktree, "show", f"HEAD:{INTERACTIONS.as_posix()}")
    current = (worktree / INTERACTIONS).read_bytes()
    if not current.startswith(head):
        raise ReconciliationError(f"{INTERACTIONS} is not an append-only change in {worktree}")
    additions, _ = parse_records(current[len(head) :], source=f"{worktree}/{INTERACTIONS} additions")
    if not additions:
        raise ReconciliationError(f"{INTERACTIONS} has no appended records in {worktree}")
    lineage_cache: dict[str, bool] = {}
    for interaction_id, issue_id, _raw in additions:
        if not belongs_to_feature_lineage(
            worktree,
            issue_id,
            root_id,
            cache=lineage_cache,
            visiting=set(),
        ):
            raise ReconciliationError(
                f"interaction {interaction_id} references {issue_id}, outside selected feature lineage {root_id}"
            )
    return additions, current


def prepare(base: Path, feature: Path, root_id: str) -> dict[str, object]:
    additions, _base_current = appended_records(base, root_id)
    feature_dirty = require_interaction_only_status(feature, allow_clean=True)
    feature_head = git(feature, "show", f"HEAD:{INTERACTIONS.as_posix()}")
    feature_current = (feature / INTERACTIONS).read_bytes()
    if not feature_current.startswith(feature_head):
        raise ReconciliationError(f"{INTERACTIONS} is not append-only in {feature}")

    _feature_records, feature_by_id = parse_records(feature_current, source=f"{feature}/{INTERACTIONS}")
    _base_records, base_additions_by_id = parse_records(
        b"".join(raw for _interaction_id, _issue_id, raw in additions),
        source=f"{base}/{INTERACTIONS} additions",
    )
    if feature_dirty:
        dirty_records, _dirty_by_id = parse_records(
            feature_current[len(feature_head) :], source=f"{feature}/{INTERACTIONS} additions"
        )
        for interaction_id, _issue_id, raw in dirty_records:
            if base_additions_by_id.get(interaction_id) != raw:
                raise ReconciliationError(
                    f"feature worktree contains unsourced interaction {interaction_id}; refusing reconciliation"
                )

    missing: list[bytes] = []
    for interaction_id, _issue_id, raw in additions:
        existing = feature_by_id.get(interaction_id)
        if existing is not None and existing != raw:
            raise ReconciliationError(f"interaction {interaction_id} differs between worktrees")
        if existing is None:
            missing.append(raw)
    if missing:
        (feature / INTERACTIONS).write_bytes(feature_current + b"".join(missing))
    return {"copied": len(missing), "preserved": len(additions), "root_id": root_id}


def finalize(base: Path, feature: Path, root_id: str) -> dict[str, object]:
    additions, _base_current = appended_records(base, root_id)
    if status_entries(feature):
        raise ReconciliationError("feature interaction reconciliation must be committed before finalization")
    feature_head = git(feature, "show", f"HEAD:{INTERACTIONS.as_posix()}")
    _records, feature_by_id = parse_records(feature_head, source=f"{feature} HEAD/{INTERACTIONS}")
    for interaction_id, _issue_id, raw in additions:
        if feature_by_id.get(interaction_id) != raw:
            raise ReconciliationError(f"committed feature branch does not preserve interaction {interaction_id}")
    git(base, "restore", "--worktree", "--source=HEAD", "--", INTERACTIONS.as_posix())
    return {"restored": len(additions), "root_id": root_id}


def verify_post_merge(base: Path, root_id: str) -> dict[str, object]:
    additions, _base_current = appended_records(base, root_id)
    return {"verified": len(additions), "root_id": root_id}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    for command in ("prepare", "finalize"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--base-worktree", type=Path, required=True)
        subparser.add_argument("--feature-worktree", type=Path, required=True)
        subparser.add_argument("--root-id", required=True)
    post_merge = subparsers.add_parser("verify-post-merge")
    post_merge.add_argument("--base-worktree", type=Path, required=True)
    post_merge.add_argument("--root-id", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        base = validate_worktree(args.base_worktree)
        if args.command == "verify-post-merge":
            output = verify_post_merge(base, args.root_id)
        else:
            feature = validate_worktree(args.feature_worktree)
            if feature == base:
                raise ReconciliationError("base and feature worktrees must differ")
            operation = prepare if args.command == "prepare" else finalize
            output = operation(base, feature, args.root_id)
    except ReconciliationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
