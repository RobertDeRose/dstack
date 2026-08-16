#!/usr/bin/env python3
"""Move stale user-level dstack skills aside without deleting them."""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

LEGACY_NAMES = (
    "audit-project",
    "close-feature",
    "dstack-core",
    "implement-feature",
    "implement-task",
    "migrate-workflow",
    "plan-features",
    "project-alignment-execute",
    "project-alignment-land",
    "project-alignment-review",
    "review-feature-spec",
    "setup-project",
    "start-feature",
    "update-project",
)

MARKERS = ("dstack",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find or archive stale user-level dstack skills that shadow the installed package."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move matching skills to a timestamped backup directory. Default is dry-run.",
    )
    parser.add_argument(
        "--agent-dir",
        type=Path,
        default=None,
        help="Pi agent directory. Defaults to PI_CODING_AGENT_DIR or ~/.pi/agent.",
    )
    return parser.parse_args()


def agent_dir_from(args: argparse.Namespace) -> Path:
    if args.agent_dir is not None:
        return args.agent_dir.expanduser().resolve()
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    return Path(configured).expanduser().resolve() if configured else Path("~/.pi/agent").expanduser().resolve()


def looks_like_legacy_dstack(skill_file: Path) -> bool:
    try:
        text = skill_file.read_text(errors="replace").casefold()
    except OSError:
        return False
    return any(marker.casefold() in text for marker in MARKERS)


def main() -> int:
    args = parse_args()
    agent_dir = agent_dir_from(args)
    skills_dir = agent_dir / "skills"

    if not skills_dir.is_dir():
        print(f"No user skill directory exists at {skills_dir}")
        return 0

    candidates: list[Path] = []
    skipped: list[Path] = []
    for name in LEGACY_NAMES:
        directory = skills_dir / name
        skill_file = directory / "SKILL.md"
        if not skill_file.is_file():
            continue
        if looks_like_legacy_dstack(skill_file):
            candidates.append(directory)
        else:
            skipped.append(directory)

    if skipped:
        print("Skipped same-named skills that do not contain recognizable dstack markers:")
        for directory in skipped:
            print(f"  {directory}")

    if not candidates:
        print("No stale user-level dstack skills were found.")
        return 0

    print("Stale user-level dstack skills:")
    for directory in candidates:
        print(f"  {directory}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to archive these directories.")
        return 0

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = agent_dir / "skills-disabled" / f"dstack-legacy-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for source in candidates:
        destination = backup_dir / source.name
        shutil.move(str(source), str(destination))

    print(f"\nArchived {len(candidates)} skill directories under:")
    print(f"  {backup_dir}")
    print("Restart Pi or run /reload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
