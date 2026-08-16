#!/usr/bin/env python3
"""Install and validate dstack's Beads formulas in a target Git repository."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

FORMULA_NAMES = ("dstack-feature", "dstack-project-alignment")


class SetupError(RuntimeError):
    """Raised when setup cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str


def run(command: Sequence[str], *, cwd: Path, check: bool = True) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SetupError(f"required executable not found: {command[0]}") from exc

    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SetupError(f"command failed ({' '.join(command)}): {detail}")

    return CommandResult(completed.stdout, completed.stderr)


def package_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_git_root(requested: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=requested.resolve())
    return Path(result.stdout.strip()).resolve()


def ensure_beads(root: Path, *, initialize: bool) -> None:
    beads_dir = root / ".beads"
    if beads_dir.exists():
        return
    if not initialize:
        raise SetupError("Beads is not initialized; rerun with --init after authorization")
    run(["bd", "init", "--quiet"], cwd=root)
    if not beads_dir.exists():
        raise SetupError("bd init completed without creating .beads")


def copy_formula(source: Path, destination: Path, *, force: bool) -> str:
    if destination.exists():
        if destination.read_bytes() == source.read_bytes():
            return "unchanged"
        if not force:
            raise SetupError(
                f"formula differs: {destination}; rerun with --force to replace it"
            )
        state = "updated"
    else:
        state = "installed"

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return state


def validate_formula_source(root: Path, formula_name: str) -> dict[str, Any]:
    result = run(["bd", "formula", "show", formula_name, "--json"], cwd=root)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SetupError(f"bd formula show returned invalid JSON for {formula_name}") from exc
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def cook_formula(root: Path, formula_name: str) -> None:
    run(["bd", "cook", formula_name, "--persist", "--force"], cwd=root)
    run(["bd", "mol", "seed", formula_name], cwd=root)


def install(root_arg: Path, *, initialize: bool, force: bool) -> dict[str, Any]:
    root = resolve_git_root(root_arg)
    version = run(["bd", "--version"], cwd=root).stdout.strip()
    ensure_beads(root, initialize=initialize)

    formula_dir = root / ".beads" / "formulas"
    source_dir = package_root() / "formulas"
    installed: dict[str, str] = {}
    parsed: dict[str, Any] = {}

    for formula_name in FORMULA_NAMES:
        filename = f"{formula_name}.formula.toml"
        installed[formula_name] = copy_formula(
            source_dir / filename,
            formula_dir / filename,
            force=force,
        )

    for formula_name in FORMULA_NAMES:
        parsed[formula_name] = validate_formula_source(root, formula_name)
        cook_formula(root, formula_name)

    return {
        "status": "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": installed,
        "protos": list(FORMULA_NAMES),
        "validated": sorted(parsed),
    }


def doctor(root_arg: Path) -> dict[str, Any]:
    root = resolve_git_root(root_arg)
    version = run(["bd", "--version"], cwd=root).stdout.strip()
    if not (root / ".beads").is_dir():
        raise SetupError("Beads is not initialized")

    statuses: dict[str, str] = {}
    for formula_name in FORMULA_NAMES:
        formula_path = root / ".beads" / "formulas" / f"{formula_name}.formula.toml"
        if not formula_path.is_file():
            raise SetupError(f"missing installed formula: {formula_path}")
        validate_formula_source(root, formula_name)
        run(["bd", "mol", "seed", formula_name], cwd=root)
        statuses[formula_name] = "available"

    return {
        "status": "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": statuses,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="install and cook formulas")
    install_parser.add_argument("--root", type=Path, default=Path.cwd())
    install_parser.add_argument("--init", action="store_true")
    install_parser.add_argument("--force", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="validate installed formulas")
    doctor_parser.add_argument("--root", type=Path, default=Path.cwd())

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install":
            payload = install(args.root, initialize=args.init, force=args.force)
        else:
            payload = doctor(args.root)
    except SetupError as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1

    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
