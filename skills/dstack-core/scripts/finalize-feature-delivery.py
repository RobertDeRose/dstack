#!/usr/bin/env python3
# ruff: noqa: EM101, EM102, S603, S607
"""Close a feature delivery only after verified merge finalization evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from beads_workflow_lock import WorkflowLock, WorkflowLockError


class DeliveryFinalizationError(RuntimeError):
    """Raised when delivery closure evidence is incomplete or unsafe."""


def load_delivery_verifier() -> Any:
    path = Path(__file__).with_name("verify-delivery-state.py")
    spec = importlib.util.spec_from_file_location("dstack_verify_delivery_state", path)
    if spec is None or spec.loader is None:
        raise DeliveryFinalizationError(f"unable to load delivery verifier: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise DeliveryFinalizationError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def bd_show(repository: Path, issue_id: str) -> dict[str, Any]:
    result = subprocess.run(
        ["bd", "show", issue_id, "--json"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise DeliveryFinalizationError(f"bd show failed for {issue_id}: {detail}")
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DeliveryFinalizationError(f"bd show returned invalid JSON for {issue_id}") from error
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise DeliveryFinalizationError(f"bd show returned an unexpected record for {issue_id}")
    return payload[0]


def require_clean_worktree(repository: Path) -> None:
    status = git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise DeliveryFinalizationError(
            "delivery closure requires a clean worktree; resolve unrelated changes before closing delivery/root"
        )


def verify_finalizer(repository: Path, base_branch: str, merge_sha: str, finalizer_sha: str, record: str) -> None:
    current_branch = git(repository, "branch", "--show-current")
    if current_branch != base_branch:
        raise DeliveryFinalizationError(f"base worktree is on {current_branch}, expected {base_branch}")
    merge = git(repository, "rev-parse", "--verify", f"{merge_sha}^{{commit}}")
    finalizer = git(repository, "rev-parse", "--verify", f"{finalizer_sha}^{{commit}}")
    if finalizer == merge:
        raise DeliveryFinalizationError("finalizer commit must be strictly after the confirmed merge")
    base_head = git(repository, "rev-parse", "--verify", f"{base_branch}^{{commit}}")
    for ancestor, descendant, label in (
        (merge, finalizer, "finalizer"),
        (finalizer, base_head, "base branch"),
    ):
        result = subprocess.run(
            ["git", "-C", str(repository), "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise DeliveryFinalizationError(f"{label} commit is not after the confirmed merge")
    changed = set(git(repository, "diff-tree", "--no-commit-id", "--name-only", "-r", finalizer).splitlines())
    if record not in changed:
        raise DeliveryFinalizationError(f"finalizer commit {finalizer} does not update {record}")


def close_delivery(
    repository: Path,
    *,
    base_branch: str,
    record: str,
    merge_sha: str,
    finalizer_sha: str,
    paths: list[str],
    delivery_id: str,
    root_id: str,
    lock_dir: Path | None = None,
    lock_timeout: float = 0.0,
) -> dict[str, Any]:
    verifier = load_delivery_verifier()
    with WorkflowLock(repository, lock_dir=lock_dir, timeout=lock_timeout):
        require_clean_worktree(repository)
        verifier.verify_delivery(
            repository,
            base_branch=base_branch,
            record=record,
            merge_sha=merge_sha,
            paths=paths,
        )
        verify_finalizer(repository, base_branch, merge_sha, finalizer_sha, record)
        delivery = bd_show(repository, delivery_id)
        root = bd_show(repository, root_id)
        if delivery.get("status") == "closed" or root.get("status") == "closed":
            raise DeliveryFinalizationError("delivery/root must remain open until this guarded finalization")
        reason = (
            f"Delivery finalized after confirmed merge {merge_sha} and post-merge finalizer {finalizer_sha}; "
            "semantic delivery verification passed."
        )
        result = subprocess.run(
            ["bd", "close", delivery_id, root_id, "--reason", reason, "--json"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise DeliveryFinalizationError(f"bd close failed: {detail}")
    return {
        "base_branch": base_branch,
        "delivery_id": delivery_id,
        "finalizer_sha": finalizer_sha,
        "merge_sha": merge_sha,
        "root_id": root_id,
        "status": "closed",
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--base-worktree", type=Path, required=True)
    result.add_argument("--base-branch", required=True)
    result.add_argument("--record", required=True)
    result.add_argument("--merge-sha", required=True)
    result.add_argument("--finalizer-sha", required=True)
    result.add_argument("--path", action="append", required=True)
    result.add_argument("--delivery-id", required=True)
    result.add_argument("--root-id", required=True)
    result.add_argument("--lock-dir", type=Path)
    result.add_argument("--lock-timeout", type=float, default=0.0)
    result.add_argument("--json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output = close_delivery(
            args.base_worktree.resolve(),
            base_branch=args.base_branch,
            record=args.record,
            merge_sha=args.merge_sha,
            finalizer_sha=args.finalizer_sha,
            paths=args.path,
            delivery_id=args.delivery_id,
            root_id=args.root_id,
            lock_dir=args.lock_dir,
            lock_timeout=args.lock_timeout,
        )
    except (DeliveryFinalizationError, WorkflowLockError, OSError) as error:
        if args.json:
            print(json.dumps({"error": str(error), "status": "blocked"}))
        else:
            print(f"Delivery finalization blocked: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(output, sort_keys=True))
    else:
        print(f"Delivery closed: {output['delivery_id']} and {output['root_id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
