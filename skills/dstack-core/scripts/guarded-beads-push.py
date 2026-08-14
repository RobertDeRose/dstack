#!/usr/bin/env python3
# ruff: noqa: EM101, EM102, S603
"""Publish Beads without replacing history on its fixed remote."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, cast, NoReturn

from beads_workflow_lock import canonical_repository_root, WorkflowLock, WorkflowLockError


AUTHORITY_PATHS = (Path(".beads/metadata.json"), Path(".beads/config.yaml"))
REMOTE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class PublicationError(RuntimeError):
    """Raised before an unsafe Beads publication."""

    def __init__(self, kind: str, message: str, *, evidence: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.evidence = evidence or {}


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def require(command: list[str], *, cwd: Path, operation: str) -> str:
    result = run(command, cwd=cwd)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise PublicationError(f"{operation}-failed", f"{operation} failed: {detail}")
    return result.stdout


def json_command(command: list[str], *, cwd: Path, operation: str) -> Any:
    output = require(command, cwd=cwd, operation=operation)
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise PublicationError(f"{operation}-failed", f"{operation} returned invalid JSON") from error


def validate_canonical_worktree(worktree: Path) -> Path:
    resolved = worktree.expanduser().resolve()
    top = Path(
        require(["git", "rev-parse", "--show-toplevel"], cwd=resolved, operation="git-worktree").strip()
    ).resolve()
    canonical = canonical_repository_root(top)
    if top != canonical:
        raise PublicationError(
            "non-canonical-worktree",
            f"publication requires the canonical worktree {canonical}; received {top}",
        )
    status = require(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=top,
        operation="git-status",
    )
    if status:
        raise PublicationError(
            "dirty-worktree",
            "publication requires a clean canonical worktree; preserve and reconcile every dirty or foreign "
            "interaction path",
            evidence={"dirty_entries": status.splitlines()},
        )
    return top


def authority_snapshot(worktree: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for relative in AUTHORITY_PATHS:
        path = worktree / relative
        if path.is_symlink() or not path.is_file():
            raise PublicationError("invalid-authority", f"Beads authority must be a regular file: {relative}")
        snapshot[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def remotes(worktree: Path) -> list[dict[str, object]]:
    payload = json_command(
        ["bd", "-C", str(worktree), "dolt", "remote", "list", "--json"],
        cwd=worktree,
        operation="remote-list",
    )
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise PublicationError("remote-list-failed", "remote-list returned an invalid remote collection")
    records = cast(list[dict[str, object]], payload)
    return sorted(records, key=lambda item: str(item.get("name", "")))


def selected_remote(snapshot: list[dict[str, object]], name: str) -> dict[str, object]:
    if not REMOTE_NAME.fullmatch(name):
        raise PublicationError("invalid-remote", f"invalid Dolt remote name: {name!r}")
    matches = [item for item in snapshot if item.get("name") == name]
    if len(matches) != 1:
        raise PublicationError("invalid-remote", f"configured Dolt remote {name!r} was not found exactly once")
    remote = matches[0]
    if remote.get("status") != "ok" or not remote.get("url"):
        raise PublicationError("invalid-remote", f"configured Dolt remote {name!r} is unavailable")
    return remote


def dolt_prefix(worktree: Path) -> list[str]:
    payload = json_command(
        ["bd", "-C", str(worktree), "dolt", "show", "--json"],
        cwd=worktree,
        operation="dolt-show",
    )
    if not isinstance(payload, dict):
        raise PublicationError("dolt-show-failed", "dolt-show returned an invalid configuration")
    data_dir = payload.get("data_dir")
    database = payload.get("database")
    if not isinstance(data_dir, str) or not data_dir or not isinstance(database, str) or not database:
        raise PublicationError("dolt-show-failed", "dolt-show omitted the data directory or database")
    return ["dolt", "--data-dir", data_dir, "--use-db", database]


def dolt_state(prefix: list[str], worktree: Path, remote: str) -> dict[str, str | None]:
    payload = json_command(
        [
            *prefix,
            "sql",
            "-r",
            "json",
            "-q",
            "select active_branch() as branch, hashof(active_branch()) as local_head;",
        ],
        cwd=worktree,
        operation="dolt-heads",
    )
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise PublicationError("dolt-heads-failed", "Dolt did not return one local head")
    state = rows[0]
    if not all(isinstance(state.get(key), str) and state[key] for key in ("branch", "local_head")):
        raise PublicationError("dolt-heads-failed", "Dolt returned an incomplete local head")

    remote_payload = json_command(
        [*prefix, "sql", "-r", "json", "-q", "select name, hash from dolt_remote_branches;"],
        cwd=worktree,
        operation="dolt-remote-heads",
    )
    remote_rows = remote_payload.get("rows", []) if isinstance(remote_payload, dict) else None
    if not isinstance(remote_rows, list) or any(not isinstance(row, dict) for row in remote_rows):
        raise PublicationError("dolt-remote-heads-failed", "Dolt returned invalid remote branches")
    expected_name = f"remotes/{remote}/{state['branch']}"
    matches = [row.get("hash") for row in remote_rows if row.get("name") == expected_name]
    if len(matches) > 1 or (matches and (not isinstance(matches[0], str) or not matches[0])):
        raise PublicationError("dolt-remote-heads-failed", "Dolt returned an invalid remote head")
    return {
        "branch": str(state["branch"]),
        "local_head": str(state["local_head"]),
        "remote_head": str(matches[0]) if matches else None,
    }


def require_clean_dolt(prefix: list[str], worktree: Path) -> None:
    payload = json_command(
        [*prefix, "sql", "-r", "json", "-q", "select * from dolt_status;"],
        cwd=worktree,
        operation="dolt-status",
    )
    if payload not in ({}, {"rows": []}):
        raise PublicationError(
            "dirty-dolt", "Dolt has uncommitted Beads changes; commit or recover them before publication"
        )


def history_evidence(prefix: list[str], worktree: Path, state: dict[str, str | None], remote: str) -> dict[str, object]:
    remote_head = state["remote_head"]
    if remote_head is None:
        merge_base = None
    else:
        remote_ref = f"remotes/{remote}/{state['branch']}"
        result = run([*prefix, "merge-base", str(state["branch"]), remote_ref], cwd=worktree)
        merge_base = result.stdout.strip() if result.returncode == 0 else None
    return {
        **state,
        "merge_base": merge_base,
        "remote": remote,
    }


def fail_history(kind: str, evidence: dict[str, object]) -> NoReturn:
    raise PublicationError(
        kind,
        f"refusing {kind} Beads publication; local and remote evidence was preserved",
        evidence=evidence,
    )


def push_bound_remote(
    prefix: list[str],
    worktree: Path,
    before: list[dict[str, object]],
    remote_url: str,
    branch: str,
) -> None:
    alias = f"dstack-publication-{secrets.token_hex(16)}"
    require([*prefix, "remote", "add", alias, remote_url], cwd=worktree, operation="bind-remote")
    try:
        bound = remotes(worktree)
        aliases = [item for item in bound if item.get("name") == alias]
        remaining = [item for item in bound if item.get("name") != alias]
        if len(aliases) != 1 or aliases[0].get("url") != remote_url or remaining != before:
            raise PublicationError(
                "remote-replacement",
                "remote configuration changed while binding the immutable publication target; no push was attempted",
            )
        require([*prefix, "push", alias, branch], cwd=worktree, operation="beads-push")
    finally:
        require([*prefix, "remote", "remove", alias], cwd=worktree, operation="unbind-remote")


def publish(worktree: Path, remote_name: str) -> dict[str, object]:
    authority = authority_snapshot(worktree)
    before = remotes(worktree)
    remote = selected_remote(before, remote_name)
    prefix = dolt_prefix(worktree)
    require_clean_dolt(prefix, worktree)
    require([*prefix, "fetch", remote_name], cwd=worktree, operation="dolt-fetch")
    if remotes(worktree) != before or authority_snapshot(worktree) != authority:
        raise PublicationError(
            "remote-replacement",
            "remote configuration changed during publication preflight; no push was attempted",
        )

    state = dolt_state(prefix, worktree, remote_name)
    evidence = history_evidence(prefix, worktree, state, remote_name)
    remote_url = str(remote["url"])
    evidence["remote_url_sha256"] = hashlib.sha256(remote_url.encode()).hexdigest()
    local_head = state["local_head"]
    remote_head = state["remote_head"]
    merge_base = evidence["merge_base"]
    if remote_head is not None:
        if merge_base is None:
            fail_history("no-common-ancestor", evidence)
        if merge_base == local_head and local_head != remote_head:
            fail_history("behind", evidence)
        if merge_base != remote_head:
            fail_history("divergent", evidence)

    if remotes(worktree) != before or authority_snapshot(worktree) != authority:
        raise PublicationError(
            "remote-replacement",
            "remote configuration changed after history verification; no push was attempted",
            evidence=evidence,
        )
    push_bound_remote(prefix, worktree, before, remote_url, str(state["branch"]))
    if remotes(worktree) != before or authority_snapshot(worktree) != authority:
        raise PublicationError(
            "remote-replacement",
            "remote configuration changed during publication; inspect the recorded heads before recovery",
            evidence=evidence,
        )
    return {"schema": "dstack.beads-publication.v1", "status": "pushed", **evidence}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--worktree", type=Path, required=True)
    result.add_argument("--remote", default="origin")
    result.add_argument("--run-id", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        repository = canonical_repository_root(args.worktree)
        with WorkflowLock(repository, run_id=args.run_id):
            worktree = validate_canonical_worktree(args.worktree)
            output = publish(worktree, args.remote)
    except (PublicationError, WorkflowLockError) as error:
        payload = {
            "schema": "dstack.beads-publication.v1",
            "status": "blocked",
            "kind": error.kind if isinstance(error, PublicationError) else "workflow-lock-busy",
            "error": str(error),
            "evidence": error.evidence if isinstance(error, PublicationError) else {},
            "recovery": [
                "Do not force push or replace the configured Dolt remote.",
                "Inspect the recorded local, remote, and merge-base evidence.",
                "Make an explicit evidence-preserving recovery decision outside this guarded publication, then rerun.",
            ],
        }
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
