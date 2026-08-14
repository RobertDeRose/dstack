#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# ruff: noqa: EM101, EM102, S603
"""Append one validated, byte-preserved review record to a Beads issue."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path


SCHEMAS = {
    "review-state": ("Review state:", "dstack.review-state.v3"),
    "finding": ("Finding:", "dstack.review-finding.v1"),
}
Runner = Callable[..., object]


def run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def validate_finding(payload: Mapping[str, object]) -> None:
    required = {
        "schema",
        "finding_id",
        "domain",
        "severity",
        "material",
        "protected",
        "status",
        "source_boundary",
        "summary",
        "resolution",
        "verification",
        "waiver",
        "supersedes_finding_id",
    }
    if set(payload) != required:
        raise ValueError("Finding record fields are incomplete or unexpected")
    for field in ("finding_id", "summary"):
        if not isinstance(payload[field], str) or not payload[field]:
            raise ValueError(f"Finding {field} is required")
    domain = payload["domain"]
    if not isinstance(domain, str) or re.fullmatch(r"[a-z][a-z0-9-]*", domain) is None:
        raise ValueError("Finding domain is invalid")
    if payload["severity"] not in {"blocking", "high", "medium", "low"}:
        raise ValueError("Finding severity is invalid")
    if not isinstance(payload["material"], bool) or not isinstance(payload["protected"], bool):
        raise ValueError("Finding material and protected fields must be boolean")
    protected = domain in {"security", "correctness", "validation", "accessibility", "data-loss-protection"}
    if payload["protected"] is not protected:
        raise ValueError("Finding protected flag conflicts with its domain")
    status = payload["status"]
    if status not in {"open", "resolved", "superseded", "accepted"}:
        raise ValueError("Finding status is invalid")
    boundary = payload["source_boundary"]
    if not isinstance(boundary, Mapping):
        raise ValueError("Finding source boundary is required")
    for field in (
        "review_issue_id",
        "reviewer_session_id",
        "reviewed_commit",
        "reviewed_diff_base",
        "reviewed_diff_digest",
    ):
        value = boundary.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Finding source_boundary.{field} is required")
    if status == "open" and any(payload[field] is not None for field in ("resolution", "verification", "waiver")):
        raise ValueError("Open findings cannot contain resolution evidence")
    if status in {"resolved", "accepted"} and any(payload[field] is None for field in ("resolution", "verification")):
        raise ValueError("Resolved findings require resolution and verification")
    if status != "accepted" and payload["waiver"] is not None:
        raise ValueError("Only accepted findings may contain a waiver")
    if status == "accepted":
        if payload["material"] or payload["protected"] or not isinstance(payload["waiver"], Mapping):
            raise ValueError("Accepted finding is not waiver-eligible")
        waiver = payload["waiver"]
        if set(waiver) != {"user", "rationale", "scope", "verification"}:
            raise ValueError("Accepted finding waiver is incomplete")
        for field in ("user", "rationale", "verification"):
            value = waiver.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"Accepted finding waiver.{field} is required")
        if waiver.get("scope") != [payload["finding_id"]]:
            raise ValueError("Accepted finding waiver scope is invalid")
    if status == "superseded" and not payload["supersedes_finding_id"]:
        raise ValueError("Superseded finding requires its prior finding ID")


def validate_record(kind: str, payload: Mapping[str, object], raw_json: str) -> None:
    if kind == "finding":
        validate_finding(payload)
        return
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("review-state.py")), "validate"],
        input=raw_json,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"Invalid review state: {result.stderr.strip()}")


def append_record(
    *,
    repository_root: Path,
    issue_id: str,
    kind: str,
    raw_json: str,
    runner: Runner = run,
) -> dict[str, object]:
    if kind not in SCHEMAS:
        raise ValueError(f"Unknown review record kind: {kind}")
    if re.fullmatch(r"[A-Za-z0-9._-]+", issue_id) is None:
        raise ValueError("Invalid review issue ID")
    if not raw_json or "\n" in raw_json or "\r" in raw_json:
        raise ValueError("Review JSON must be one non-empty line")
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Review record is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Review record must be a JSON object")
    prefix, schema = SCHEMAS[kind]
    if payload.get("schema") != schema:
        raise ValueError(f"Expected schema {schema}")
    validate_record(kind, payload, raw_json)

    root = repository_root.expanduser().resolve()
    runner(["bd", "update", issue_id, "--append-notes", f"{prefix} {raw_json}"], cwd=root)
    encoded = raw_json.encode()
    return {
        "issue_id": issue_id,
        "kind": kind,
        "schema": schema,
        "bytes": len(encoded),
        "record_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--issue-id", required=True)
    parser.add_argument("--kind", choices=sorted(SCHEMAS), required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    raw = sys.stdin.read()
    raw = raw.removesuffix("\n")
    evidence = append_record(
        repository_root=args.repository_root,
        issue_id=args.issue_id,
        kind=args.kind,
        raw_json=raw,
    )
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
