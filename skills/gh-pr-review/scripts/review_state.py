#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Persist resumable gh-pr-review state under the repository Git directory."""

# ruff: noqa: S607

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
PHASES = {
    "collecting",
    "awaiting_selection",
    "awaiting_clarification",
    "implementing",
    "validating",
    "awaiting_ci",
    "replying",
    "requesting_rereview",
    "awaiting_rereview",
    "complete",
    "blocked",
    "clarification-blocked",
    "cycle-limit-reached",
}
TERMINAL_PHASES = {"complete", "blocked", "clarification-blocked", "cycle-limit-reached"}


def git_dir() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).resolve()


def state_path() -> Path:
    return git_dir() / "dstack" / "gh-pr-review-state.json"


def load() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        message = "No active gh-pr-review state exists"
        raise SystemExit(message)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        message = f"Unsupported gh-pr-review state in {path}"
        raise SystemExit(message)
    return value


def save(value: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_numbers(raw: str) -> list[int]:
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        number = int(token)
        if number <= 0:
            message = "Ledger numbers must be positive"
            raise ValueError(message)
        values.append(number)
    return sorted(set(values))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--pr", type=int, required=True)
    init.add_argument("--head", required=True)
    init.add_argument("--cycle", type=int, default=1)

    phase = sub.add_parser("phase")
    phase.add_argument("value", choices=sorted(PHASES))

    selection = sub.add_parser("selection")
    selection.add_argument("numbers", help="Comma-separated ledger row numbers")

    ledger = sub.add_parser("ledger")
    ledger.add_argument("path", type=Path, help="JSON file containing the current ledger array")

    sub.add_parser("show")
    sub.add_parser("clear")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "init":
        if args.pr <= 0 or args.cycle <= 0 or not args.head.strip():
            message = "PR, head SHA, and cycle must be valid"
            raise SystemExit(message)
        value = {
            "schema_version": SCHEMA_VERSION,
            "pr_number": args.pr,
            "head_sha": args.head.strip(),
            "cycle": args.cycle,
            "phase": "collecting",
            "ledger": [],
            "selected": [],
            "clarifications": {},
        }
        save(value)
    elif args.command == "phase":
        value = load()
        value["phase"] = args.value
        save(value)
    elif args.command == "selection":
        value = load()
        value["selected"] = parse_numbers(args.numbers)
        value["phase"] = "implementing"
        save(value)
    elif args.command == "ledger":
        value = load()
        ledger = json.loads(args.path.read_text(encoding="utf-8"))
        if not isinstance(ledger, list):
            message = "Ledger JSON must contain an array"
            raise SystemExit(message)
        value["ledger"] = ledger
        save(value)
    elif args.command == "show":
        value = load()
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "clear":
        path = state_path()
        if path.exists():
            value = load()
            if value.get("phase") not in TERMINAL_PHASES:
                message = "Refusing to clear non-terminal gh-pr-review state"
                raise SystemExit(message)
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
