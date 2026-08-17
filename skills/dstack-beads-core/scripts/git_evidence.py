#!/usr/bin/env python3
"""Locate rewrite-safe Git evidence for a Beads work item.

Dstack links Git to Beads only through a `Beads: <id>` commit footer. Beads never
stores the commit SHA, so normal history rewriting does not require workflow
state repair.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


class EvidenceError(RuntimeError):
    pass


def run(args: Sequence[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise EvidenceError(f"{' '.join(args)}: {detail}")
    return proc


def git_root(path: Path) -> Path:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=path)
    return Path(proc.stdout.strip()).resolve()


def footer_pattern(bead_id: str) -> re.Pattern[str]:
    return re.compile(rf"(?m)^Beads:\s*{re.escape(bead_id)}\s*$")


def find_commit(root: Path, bead_id: str) -> str | None:
    proc = run(
        ["git", "log", "--format=%H%x00%B%x00"],
        cwd=root,
    )
    chunks = proc.stdout.split("\x00")
    pattern = footer_pattern(bead_id)
    for i in range(0, len(chunks) - 1, 2):
        commit = chunks[i].strip()
        message = chunks[i + 1]
        if commit and pattern.search(message):
            return commit
    return None


def path_unchanged(root: Path, commit: str, path: str) -> bool:
    proc = run(
        ["git", "diff", "--quiet", f"{commit}..HEAD", "--", path],
        cwd=root,
        check=False,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise EvidenceError(proc.stderr.strip() or "git diff failed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--bead", required=True)
    parser.add_argument("--path")
    args = parser.parse_args(argv)

    try:
        root = git_root(args.root)
        commit = find_commit(root, args.bead)
        if commit is None:
            payload = {
                "status": "missing",
                "bead": args.bead,
                "root": str(root),
            }
            json.dump(payload, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2

        unchanged = None
        if args.path:
            unchanged = path_unchanged(root, commit, args.path)

        payload = {
            "status": "ok" if unchanged is not False else "drifted",
            "bead": args.bead,
            "commit": commit,
            "path": args.path,
            "path_unchanged_since_evidence": unchanged,
            "root": str(root),
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if unchanged is not False else 3
    except EvidenceError as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
