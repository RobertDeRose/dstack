#!/usr/bin/env python3
"""Install and validate dstack's Beads formulas in a target Git repository."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

FORMULA_NAMES = ("dstack-feature", "dstack-project-alignment")


class SetupError(RuntimeError):
    """Raised when setup cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    try:
        # File-backed capture avoids pipe hangs when a command starts a helper
        # process that briefly inherits its standard streams.
        with tempfile.TemporaryFile(mode="w+t") as stdout_file, tempfile.TemporaryFile(
            mode="w+t"
        ) as stderr_file:
            completed = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                text=True,
                stdout=stdout_file,
                stderr=stderr_file,
                env=dict(env) if env is not None else None,
            )
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read()
            stderr = stderr_file.read()
    except FileNotFoundError as exc:
        raise SetupError(f"required executable not found: {command[0]}") from exc

    if check and completed.returncode != 0:
        detail = stderr.strip() or stdout.strip()
        raise SetupError(f"command failed ({' '.join(command)}): {detail}")

    return CommandResult(stdout, stderr)


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


def step_map(formula: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    steps = formula.get("steps")
    if not isinstance(steps, list):
        raise SetupError("formula steps must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for raw in steps:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise SetupError("formula contains a step without a string id")
        result[raw["id"]] = raw
    return result


def require_step_type(
    steps: Mapping[str, Mapping[str, Any]],
    step_id: str,
    expected_type: str,
) -> Mapping[str, Any]:
    try:
        step = steps[step_id]
    except KeyError as exc:
        raise SetupError(f"missing required formula step: {step_id}") from exc
    actual = step.get("type", "task")
    if actual != expected_type:
        raise SetupError(
            f"formula step {step_id} must remain type={expected_type}, got {actual}"
        )
    return step


def validate_dstack_formula_contract(
    formula_name: str,
    formula: Mapping[str, Any],
) -> None:
    """Reject a cookable formula that violates dstack's workflow contract."""

    steps = step_map(formula)
    if formula_name == "dstack-feature":
        expected_ids = {"specification", "approval", "implementation", "closeout"}
        specification = require_step_type(steps, "specification", "task")
        approval = require_step_type(steps, "approval", "task")
        workstream = require_step_type(steps, "implementation", "epic")
        terminal = require_step_type(steps, "closeout", "task")
        expected_waits_for = "children-of(implementation)"
        expected_approval_label = "dstack:step:implementation-approval"
    elif formula_name == "dstack-project-alignment":
        expected_ids = {"analysis", "approval", "corrections", "landing"}
        specification = require_step_type(steps, "analysis", "task")
        approval = require_step_type(steps, "approval", "task")
        workstream = require_step_type(steps, "corrections", "epic")
        terminal = require_step_type(steps, "landing", "task")
        expected_waits_for = "children-of(corrections)"
        expected_approval_label = "dstack:step:alignment-approval"
    else:
        raise SetupError(f"unknown dstack formula contract: {formula_name}")

    if set(steps) != expected_ids:
        raise SetupError(
            f"{formula_name} must contain exactly {sorted(expected_ids)}, "
            f"got {sorted(steps)}"
        )
    if approval.get("needs") != [specification["id"]]:
        raise SetupError(
            f"{formula_name} approval must depend only on {specification['id']}"
        )
    gate = approval.get("gate")
    if not isinstance(gate, dict) or gate.get("type") != "human":
        raise SetupError(f"{formula_name} approval must carry a human gate")
    if workstream.get("gate"):
        raise SetupError(f"{formula_name} workstream epic must not carry a gate")
    if workstream.get("needs") or workstream.get("depends_on"):
        raise SetupError(
            f"{formula_name} workstream epic must not have ordinary task blockers"
        )
    if terminal.get("needs") != ["approval"]:
        raise SetupError(f"{formula_name} terminal step must depend on approval")
    if terminal.get("waits_for") != expected_waits_for:
        raise SetupError(
            f"{formula_name} terminal step must wait for {expected_waits_for}"
        )
    labels = approval.get("labels", [])
    if expected_approval_label not in labels:
        raise SetupError(
            f"{formula_name} approval step is missing {expected_approval_label}"
        )


def validate_formula_source(root: Path, formula_name: str) -> dict[str, Any]:
    result = run(["bd", "formula", "show", formula_name, "--json"], cwd=root)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SetupError(f"bd formula show returned invalid JSON for {formula_name}") from exc
    if not isinstance(parsed, dict):
        raise SetupError(f"bd formula show returned a non-object for {formula_name}")
    validate_dstack_formula_contract(formula_name, parsed)
    return parsed


def cook_formula(
    root: Path,
    formula_name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    run(
        ["bd", "cook", formula_name, "--persist", "--force"],
        cwd=root,
        env=env,
    )
    run(["bd", "mol", "seed", formula_name], cwd=root, env=env)


def validate_formula_bundle(source_dir: Path) -> None:
    """Cook every bundled formula in an isolated real Beads repository.

    ``bd formula show`` validates parsing, but only persisted cooking exercises
    dependency-kind constraints such as the task/epic rule applied to generated
    gates. This preflight runs before any target formula file is modified.
    """

    with tempfile.TemporaryDirectory(prefix="dstack-formula-preflight-") as raw:
        scratch = Path(raw)
        run(["git", "init", "-q"], cwd=scratch)

        env = dict(os.environ)
        # Keep the stateful test double isolated from the target test database.
        if "DSTACK_FAKE_BD_STATE" in env:
            env["DSTACK_FAKE_BD_STATE"] = str(scratch / "fake-bd-state.json")

        run(
            [
                "bd",
                "init",
                "--quiet",
                "--skip-agents",
                "--skip-hooks",
                "--non-interactive",
            ],
            cwd=scratch,
            env=env,
        )
        formula_dir = scratch / ".beads" / "formulas"
        formula_dir.mkdir(parents=True, exist_ok=True)
        for formula_name in FORMULA_NAMES:
            filename = f"{formula_name}.formula.toml"
            shutil.copyfile(source_dir / filename, formula_dir / filename)
        for formula_name in FORMULA_NAMES:
            result = run(
                ["bd", "formula", "show", formula_name, "--json"],
                cwd=scratch,
                env=env,
            )
            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise SetupError(
                    f"isolated bd formula show returned invalid JSON for {formula_name}"
                ) from exc
            if not isinstance(parsed, dict):
                raise SetupError(
                    f"isolated bd formula show returned a non-object for {formula_name}"
                )
            validate_dstack_formula_contract(formula_name, parsed)
            cook_formula(scratch, formula_name, env=env)


def restore_formula_files(snapshots: Mapping[Path, bytes | None]) -> None:
    for destination, previous in snapshots.items():
        if previous is None:
            destination.unlink(missing_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(previous)


def install(root_arg: Path, *, initialize: bool, force: bool) -> dict[str, Any]:
    root = resolve_git_root(root_arg)
    version = run(["bd", "--version"], cwd=root).stdout.strip()
    ensure_beads(root, initialize=initialize)

    formula_dir = root / ".beads" / "formulas"
    source_dir = package_root() / "formulas"
    installed: dict[str, str] = {}
    parsed: dict[str, Any] = {}

    validate_formula_bundle(source_dir)

    snapshots: dict[Path, bytes | None] = {}
    try:
        for formula_name in FORMULA_NAMES:
            filename = f"{formula_name}.formula.toml"
            destination = formula_dir / filename
            snapshots[destination] = destination.read_bytes() if destination.exists() else None
            installed[formula_name] = copy_formula(
                source_dir / filename,
                destination,
                force=force,
            )

        for formula_name in FORMULA_NAMES:
            parsed[formula_name] = validate_formula_source(root, formula_name)
            cook_formula(root, formula_name)
    except Exception:
        restore_formula_files(snapshots)
        raise

    return {
        "status": "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": installed,
        "protos": list(FORMULA_NAMES),
        "validated": sorted(parsed),
        "preflight": "isolated-persisted-cook",
    }


def doctor(root_arg: Path) -> dict[str, Any]:
    root = resolve_git_root(root_arg)
    version = run(["bd", "--version"], cwd=root).stdout.strip()
    if not (root / ".beads").is_dir():
        raise SetupError("Beads is not initialized")

    statuses: dict[str, str] = {}
    source_dir = package_root() / "formulas"
    for formula_name in FORMULA_NAMES:
        filename = f"{formula_name}.formula.toml"
        formula_path = root / ".beads" / "formulas" / filename
        source_path = source_dir / filename
        if not formula_path.is_file():
            raise SetupError(f"missing installed formula: {formula_path}")
        if formula_path.read_bytes() != source_path.read_bytes():
            raise SetupError(
                f"installed formula differs from dstack package: {formula_path}; "
                "rerun /setup-project --force"
            )
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
