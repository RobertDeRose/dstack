#!/usr/bin/env python3
# ruff: noqa: EM101, EM102, S603, S607
"""Safely reconcile append-only Beads interaction evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
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


def require_interaction_only_status(worktree: Path, *, allow_clean: bool, staged: bool = False) -> bool:
    entries = status_entries(worktree)
    if not entries and allow_clean:
        return False
    expected_status = "M " if staged else " M"
    expected = [(expected_status, INTERACTIONS.as_posix())]
    if entries != expected:
        rendered = ", ".join(f"{status} {path}" for status, path in entries) or "clean"
        location = "a staged" if staged else "an unstaged"
        raise ReconciliationError(f"worktree must contain only {location} {INTERACTIONS} change; found: {rendered}")
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


def classify_records(
    worktree: Path,
    additions: list[tuple[str, str, bytes]],
    root_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lineage_cache: dict[str, bool] = {}
    selected: list[dict[str, Any]] = []
    foreign: list[dict[str, Any]] = []
    for interaction_id, issue_id, raw in additions:
        try:
            value: Any = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReconciliationError(f"interaction {interaction_id} is not valid JSON") from error
        issue = bd_show(worktree, issue_id)
        row = {
            "interaction_id": interaction_id,
            "issue_id": issue_id,
            "title": issue.get("title", issue_id),
            "actor": value.get("actor"),
            "created_at": value.get("created_at"),
        }
        if belongs_to_feature_lineage(
            worktree,
            issue_id,
            root_id,
            cache=lineage_cache,
            visiting=set(),
        ):
            selected.append(row)
        else:
            foreign.append(row)
    return selected, foreign


def appended_records(worktree: Path, root_id: str) -> tuple[list[tuple[str, str, bytes]], bytes]:
    require_interaction_only_status(worktree, allow_clean=False)
    head = git(worktree, "show", f"HEAD:{INTERACTIONS.as_posix()}")
    current = (worktree / INTERACTIONS).read_bytes()
    if not current.startswith(head):
        raise ReconciliationError(f"{INTERACTIONS} is not an append-only change in {worktree}")
    additions, _ = parse_records(current[len(head) :], source=f"{worktree}/{INTERACTIONS} additions")
    if not additions:
        raise ReconciliationError(f"{INTERACTIONS} has no appended records in {worktree}")
    _selected, foreign = classify_records(worktree, additions, root_id)
    if foreign:
        details = "; ".join(f"{row['interaction_id']} references {row['issue_id']} ({row['title']})" for row in foreign)
        raise ReconciliationError(f"foreign interaction records outside selected feature lineage {root_id}: {details}")
    return additions, current


def inspect_worktree(worktree: Path, root_id: str) -> dict[str, Any]:
    entries = status_entries(worktree)
    if not entries:
        return {
            "clean": True,
            "foreign": [],
            "root_id": root_id,
            "selected": [],
        }
    require_interaction_only_status(worktree, allow_clean=False)
    path = worktree / INTERACTIONS
    head = git(worktree, "show", f"HEAD:{INTERACTIONS.as_posix()}")
    current = path.read_bytes()
    if not current.startswith(head):
        raise ReconciliationError(f"{INTERACTIONS} is not an append-only change in {worktree}")
    additions, _ = parse_records(current[len(head) :], source=f"{worktree}/{INTERACTIONS} additions")
    if not additions:
        raise ReconciliationError(f"{INTERACTIONS} has no appended records in {worktree}")
    selected, foreign = classify_records(worktree, additions, root_id)
    return {
        "clean": False,
        "foreign": foreign,
        "root_id": root_id,
        "selected": selected,
        "snapshot_sha256": hashlib.sha256(current).hexdigest(),
        "snapshot_mode": interaction_worktree_mode(worktree),
    }


def preflight(worktree: Path, root_id: str) -> dict[str, Any]:
    entries = status_entries(worktree)
    if entries:
        if entries == [(" M", INTERACTIONS.as_posix())]:
            report = inspect_worktree(worktree, root_id)
            details = "; ".join(
                f"{row['interaction_id']} -> {row['issue_id']}" for row in [*report["selected"], *report["foreign"]]
            )
            raise ReconciliationError(
                f"preflight requires a clean worktree before closeout; uncommitted interaction records: {details}"
            )
        rendered = ", ".join(f"{status} {path}" for status, path in entries)
        raise ReconciliationError(f"preflight requires a clean worktree before closeout; found: {rendered}")
    return {"clean": True, "root_id": root_id}


def resolve_baseline_commit(worktree: Path, revision: str) -> str:
    try:
        commit = git(worktree, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
    except ReconciliationError as error:
        raise ReconciliationError(f"invalid work-unit baseline: {revision}") from error
    try:
        git(worktree, "merge-base", "--is-ancestor", commit, "HEAD")
    except ReconciliationError as error:
        raise ReconciliationError(f"work-unit baseline {commit} is not an ancestor of HEAD") from error
    return commit


def parse_interaction_entry(data: bytes, *, source: str, index: bool) -> str | None:
    if not data:
        return None
    entries = data.rstrip(b"\0").split(b"\0")
    if len(entries) != 1:
        raise ReconciliationError(f"{source} returned multiple {INTERACTIONS} entries")
    metadata, separator, raw_path = entries[0].partition(b"\t")
    fields = metadata.split()
    path = raw_path.decode(errors="surrogateescape")
    expected_middle = b"0" if index else b"blob"
    middle = fields[2] if index and len(fields) == 3 else fields[1] if len(fields) == 3 else b""
    if separator != b"\t" or len(fields) != 3 or middle != expected_middle or path != INTERACTIONS.as_posix():
        raise ReconciliationError(f"{source} returned an invalid {INTERACTIONS} entry")
    return fields[0].decode()


def interaction_revision_mode(worktree: Path, revision: str) -> str | None:
    data = git(worktree, "ls-tree", "-z", revision, "--", INTERACTIONS.as_posix())
    return parse_interaction_entry(data, source=f"git ls-tree {revision}", index=False)


def interaction_index_mode(worktree: Path) -> str | None:
    data = git(worktree, "ls-files", "--stage", "-z", "--", INTERACTIONS.as_posix())
    return parse_interaction_entry(data, source="git ls-files --stage", index=True)


def interaction_worktree_mode(worktree: Path) -> str:
    path = worktree / INTERACTIONS
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ReconciliationError(f"unable to inspect {path}: {error}") from error
    if not stat.S_ISREG(mode):
        raise ReconciliationError(f"{path} must remain a regular file")
    return "100755" if mode & 0o111 else "100644"


def interaction_blob(worktree: Path, revision: str) -> bytes | None:
    if interaction_revision_mode(worktree, revision) is None:
        return None
    return git(worktree, "show", f"{revision}:{INTERACTIONS.as_posix()}")


def verify_work_unit(
    worktree: Path,
    issue_id: str,
    baseline_revision: str,
    *,
    root_id: str | None = None,
    staged: bool = False,
    allow_clean: bool = False,
    lineage_only: bool = False,
    expected_content_sha256: str | None = None,
    expected_mode: str | None = None,
) -> dict[str, object]:
    interaction_dirty = require_interaction_only_status(worktree, allow_clean=not staged, staged=staged)
    baseline_commit = resolve_baseline_commit(worktree, baseline_revision)
    interaction_commits = (
        git(
            worktree,
            "log",
            "--format=%H",
            "--full-history",
            f"{baseline_commit}..HEAD",
            "--",
            INTERACTIONS.as_posix(),
        )
        .decode()
        .splitlines()
    )
    if interaction_commits:
        raise ReconciliationError(
            f"{INTERACTIONS} must remain uncommitted until work-unit finalization in {worktree}; "
            f"touched by {interaction_commits[0]}"
        )

    baseline_mode = interaction_revision_mode(worktree, baseline_commit)
    head_mode = interaction_revision_mode(worktree, "HEAD")
    baseline = interaction_blob(worktree, baseline_commit)
    head = interaction_blob(worktree, "HEAD")
    if head != baseline or head_mode != baseline_mode:
        raise ReconciliationError(f"{INTERACTIONS} differs from the work-unit baseline in HEAD")
    output: dict[str, object] = {
        "dirty": False,
        "issue_id": issue_id,
        "tracked": baseline is not None,
        "verified": 0,
    }
    if root_id is not None:
        output["root_id"] = root_id
    if baseline is None:
        return output

    current_mode = interaction_index_mode(worktree) if staged else interaction_worktree_mode(worktree)
    if current_mode != baseline_mode:
        location = "index" if staged else "worktree"
        raise ReconciliationError(f"{INTERACTIONS} mode or type differs from the work-unit baseline in the {location}")
    current = git(worktree, "show", f":{INTERACTIONS.as_posix()}") if staged else (worktree / INTERACTIONS).read_bytes()
    parse_records(baseline, source=f"{worktree}/{baseline_commit}/{INTERACTIONS}")
    if current == baseline:
        if interaction_dirty:
            raise ReconciliationError(f"{INTERACTIONS} is not an append-only content change in {worktree}")
        if root_id is not None and not allow_clean:
            raise ReconciliationError(f"no appended interaction references selected feature work unit {issue_id}")
        return output
    if not interaction_dirty:
        raise ReconciliationError(
            f"{INTERACTIONS} changed from the work-unit baseline but is not an unstaged finalization change"
        )
    if not current.startswith(baseline):
        raise ReconciliationError(f"{INTERACTIONS} is not an append-only change since {baseline_commit} in {worktree}")
    parse_records(current, source=f"{worktree}/{INTERACTIONS}")
    if expected_content_sha256 is not None:
        actual_content_sha256 = hashlib.sha256(current).hexdigest()
        if actual_content_sha256 != expected_content_sha256:
            raise ReconciliationError(
                f"{INTERACTIONS} content changed after work-unit verification; expected "
                f"{expected_content_sha256}, found {actual_content_sha256}"
            )
    if expected_mode is not None and current_mode != expected_mode:
        raise ReconciliationError(
            f"{INTERACTIONS} mode changed after work-unit verification; expected {expected_mode}, found {current_mode}"
        )
    additions, _ = parse_records(
        current[len(baseline) :],
        source=f"{worktree}/{INTERACTIONS} additions",
    )
    if not additions:
        raise ReconciliationError(f"{INTERACTIONS} has no appended records in {worktree}")
    lineage_cache: dict[str, bool] = {}
    selected_issue_found = False
    for interaction_id, recorded_issue_id, _raw in additions:
        selected_issue_found |= recorded_issue_id == issue_id
        if root_id is None:
            if recorded_issue_id != issue_id:
                raise ReconciliationError(
                    f"interaction {interaction_id} references {recorded_issue_id}, "
                    f"outside selected standalone issue {issue_id}"
                )
        elif not belongs_to_feature_lineage(
            worktree,
            recorded_issue_id,
            root_id,
            cache=lineage_cache,
            visiting=set(),
        ):
            raise ReconciliationError(
                f"interaction {interaction_id} references {recorded_issue_id}, "
                f"outside selected feature lineage {root_id}"
            )
    if root_id is not None and not lineage_only and not selected_issue_found:
        raise ReconciliationError(f"no appended interaction references selected feature work unit {issue_id}")
    output["dirty"] = True
    output["verified"] = len(additions)
    if root_id is not None:
        output["snapshot_sha256"] = hashlib.sha256(current).hexdigest()
        output["snapshot_mode"] = current_mode
    return output


def verify_standalone(
    worktree: Path,
    issue_id: str,
    baseline_revision: str,
    *,
    staged: bool = False,
) -> dict[str, object]:
    return verify_work_unit(worktree, issue_id, baseline_revision, staged=staged)


def verify_feature(
    worktree: Path,
    root_id: str,
    issue_id: str,
    baseline_revision: str,
    *,
    staged: bool = False,
    expected_content_sha256: str | None = None,
    expected_mode: str | None = None,
    allow_clean: bool = False,
    lineage_only: bool = False,
) -> dict[str, object]:
    if staged and (expected_content_sha256 is None or expected_mode is None):
        raise ReconciliationError("staged feature verification requires the previously verified interaction snapshot")
    if not belongs_to_feature_lineage(worktree, issue_id, root_id, cache={}, visiting=set()):
        raise ReconciliationError(f"selected work unit {issue_id} is outside selected feature lineage {root_id}")
    return verify_work_unit(
        worktree,
        issue_id,
        baseline_revision,
        root_id=root_id,
        staged=staged,
        allow_clean=allow_clean,
        lineage_only=lineage_only,
        expected_content_sha256=expected_content_sha256,
        expected_mode=expected_mode,
    )


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
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--worktree", type=Path, required=True)
    inspect.add_argument("--root-id", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--worktree", type=Path, required=True)
    preflight_parser.add_argument("--root-id", required=True)
    post_merge = subparsers.add_parser("verify-post-merge")
    post_merge.add_argument("--base-worktree", type=Path, required=True)
    post_merge.add_argument("--root-id", required=True)
    standalone = subparsers.add_parser("verify-standalone")
    standalone.add_argument("--worktree", type=Path, required=True)
    standalone.add_argument("--issue-id", required=True)
    standalone.add_argument("--baseline-commit", required=True)
    standalone.add_argument("--staged", action="store_true")
    feature = subparsers.add_parser("verify-feature")
    feature.add_argument("--worktree", type=Path, required=True)
    feature.add_argument("--root-id", required=True)
    feature.add_argument("--issue-id", required=True)
    feature.add_argument("--baseline-commit", required=True)
    feature.add_argument("--lineage-only", action="store_true")
    feature.add_argument("--expected-content-sha256")
    feature.add_argument("--expected-mode")
    feature.add_argument("--allow-clean", action="store_true")
    feature.add_argument("--staged", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command in {"inspect", "preflight", "verify-feature", "verify-standalone"}:
            worktree = validate_worktree(args.worktree)
            if args.command == "inspect":
                output = inspect_worktree(worktree, args.root_id)
            elif args.command == "preflight":
                output = preflight(worktree, args.root_id)
            elif args.command == "verify-feature":
                output = verify_feature(
                    worktree,
                    args.root_id,
                    args.issue_id,
                    args.baseline_commit,
                    staged=args.staged,
                    expected_content_sha256=args.expected_content_sha256,
                    expected_mode=args.expected_mode,
                    allow_clean=args.allow_clean,
                    lineage_only=args.lineage_only,
                )
            else:
                output = verify_standalone(worktree, args.issue_id, args.baseline_commit, staged=args.staged)
        else:
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
