#!/usr/bin/env python3
# ruff: noqa: EM101, EM102, S603, S607
"""Verify that post-merge feature documentation records the actual delivery state."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


STALE_DELIVERY_CLAIMS = re.compile(
    r"\b(?:"
    r"merge\s+(?:is\s+|remains\s+|still\s+)?pending|"
    r"pending\s+(?:merge|delivery)|"
    r"(?:not|never)\s+(?:yet\s+)?merged|"
    r"unmerged|"
    r"awaiting\s+(?:merge|delivery)|"
    r"ready\s+for\s+merge"
    r")\b",
    re.IGNORECASE,
)
STATUS_PATTERN = re.compile(r"(?im)^\s*-\s*Status:\s*`?([a-z-]+)`?\s*$")
MERGE_PATTERN = re.compile(r"(?im)^\s*-\s*Merge commit:\s*`?([0-9a-f]{7,40})`?")


class VerificationError(RuntimeError):
    """Raised when delivery evidence is incomplete or inconsistent."""


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VerificationError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def repository_path(repository: Path, value: str) -> Path:
    source = repository / value
    if source.is_symlink():
        raise VerificationError(f"delivery evidence path must not be a symlink: {value}")
    candidate = source.resolve()
    try:
        candidate.relative_to(repository)
    except ValueError as error:
        raise VerificationError(f"path escapes the base worktree: {value}") from error
    if candidate.is_symlink() or not candidate.is_file():
        raise VerificationError(f"delivery evidence path is not a regular file: {value}")
    return candidate


def resolved_commit(repository: Path, value: str) -> str:
    return git(repository, "rev-parse", "--verify", f"{value}^{{commit}}")


def verify_delivery(
    repository: Path,
    *,
    base_branch: str,
    record: str,
    merge_sha: str,
    paths: list[str],
) -> dict[str, Any]:
    if not paths:
        raise VerificationError("at least one reader-facing --path is required")

    record_path = repository_path(repository, record)
    evidence_paths = [record_path, *(repository_path(repository, value) for value in paths)]
    expected_sha = resolved_commit(repository, merge_sha)
    base_sha = resolved_commit(repository, base_branch)
    ancestor = subprocess.run(
        ["git", "-C", str(repository), "merge-base", "--is-ancestor", expected_sha, base_sha],
        capture_output=True,
        check=False,
    )
    if ancestor.returncode:
        raise VerificationError(f"delivery SHA {expected_sha} is not an ancestor of {base_branch} ({base_sha})")

    record_text = record_path.read_text(encoding="utf-8")
    status = STATUS_PATTERN.search(record_text)
    if status is None or status.group(1).casefold() != "delivered":
        raise VerificationError(f"{record} must state `Status: delivered`")
    recorded_merge = MERGE_PATTERN.search(record_text)
    if recorded_merge is None:
        raise VerificationError(f"{record} must record the final merge commit SHA")
    recorded_sha = resolved_commit(repository, recorded_merge.group(1))
    if recorded_sha != expected_sha:
        raise VerificationError(f"{record} records {recorded_sha}, expected delivery SHA {expected_sha}")

    stale_claims: list[str] = []
    for path in evidence_paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if STALE_DELIVERY_CLAIMS.search(line):
                relative = path.relative_to(repository)
                stale_claims.append(f"{relative}:{line_number}: stale delivery claim: {line.strip()}")
    if stale_claims:
        raise VerificationError("\n".join(stale_claims))

    return {
        "base_branch": base_branch,
        "base_sha": base_sha,
        "merge_sha": expected_sha,
        "record": record,
        "paths": [str(path.relative_to(repository)) for path in evidence_paths],
        "status": "delivered",
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--base-worktree", type=Path, default=Path.cwd())
    result.add_argument("--base-branch", required=True)
    result.add_argument("--record", required=True)
    result.add_argument("--merge-sha", required=True)
    result.add_argument("--path", action="append", default=[])
    result.add_argument("--json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repository = args.base_worktree.resolve()
    try:
        result = verify_delivery(
            repository,
            base_branch=args.base_branch,
            record=args.record,
            merge_sha=args.merge_sha,
            paths=args.path,
        )
    except (OSError, VerificationError) as error:
        if args.json:
            print(json.dumps({"error": str(error), "status": "failed"}))
        else:
            print(f"Delivery state verification failed: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Delivery state verified: {result['record']} records {result['merge_sha']} as delivered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
