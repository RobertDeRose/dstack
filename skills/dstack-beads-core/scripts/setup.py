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
PREFLIGHT_VARS: dict[str, dict[str, str]] = {
    "dstack-feature": {
        "feature_title": "Dstack Formula Preflight",
        "feature_slug": "dstack-formula-preflight",
        "base_branch": "main",
        "design_path": "docs/src/features/dstack-formula-preflight/design.md",
    },
    "dstack-project-alignment": {
        "audit_title": "Dstack Alignment Preflight",
        "audit_slug": "dstack-alignment-preflight",
        "target_branch": "main",
        "scope": "formula validation",
    },
}


class SetupError(RuntimeError):
    """Raised when setup cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
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

    result = CommandResult(completed.returncode, stdout, stderr)
    if check and completed.returncode != 0:
        detail = stderr.strip() or stdout.strip()
        raise SetupError(f"command failed ({' '.join(command)}): {detail}")

    return result


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
    run(
        [
            "bd",
            "init",
            "--quiet",
            "--skip-agents",
            "--skip-hooks",
            "--non-interactive",
        ],
        cwd=root,
    )
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

    # Beads 1.2.2 interpolates formula variables reliably in titles,
    # descriptions, and gate IDs, but can preserve template expressions
    # literally in issue labels/metadata. dstack therefore requires stable
    # formula children to use only static identity in those fields.
    for step_id, step in steps.items():
        metadata = step.get("metadata", {})
        step_labels = step.get("labels", [])
        encoded = json.dumps({"metadata": metadata, "labels": step_labels}, sort_keys=True)
        if "{{" in encoded:
            raise SetupError(
                f"{formula_name} step {step_id} must not template labels or metadata"
            )


def parse_json_output(result: CommandResult, *, context: str) -> Any:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SetupError(f"{context} returned invalid JSON") from exc


def issue_items(payload: Any) -> list[dict[str, Any]]:
    """Normalize Beads 1.x arrays and the opt-in v2 JSON envelope."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("issues", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if isinstance(payload.get("id"), str):
            return [payload]
    return []


def formula_var_args(formula_name: str) -> list[str]:
    try:
        variables = PREFLIGHT_VARS[formula_name]
    except KeyError as exc:
        raise SetupError(f"missing preflight variables for {formula_name}") from exc
    args: list[str] = []
    for key, value in variables.items():
        args.extend(["--var", f"{key}={value}"])
    return args


def validate_formula_source(
    root: Path,
    formula_name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    result = run(
        ["bd", "formula", "show", formula_name, "--json"],
        cwd=root,
        env=env,
    )
    parsed = parse_json_output(result, context=f"bd formula show for {formula_name}")
    if not isinstance(parsed, dict):
        raise SetupError(f"bd formula show returned a non-object for {formula_name}")
    validate_dstack_formula_contract(formula_name, parsed)
    return parsed


def seed_formula(
    root: Path,
    formula_name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    run(
        ["bd", "mol", "seed", formula_name, *formula_var_args(formula_name)],
        cwd=root,
        env=env,
    )


def pour_formula_preflight(
    root: Path,
    formula_name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    result = run(
        [
            "bd",
            "mol",
            "pour",
            formula_name,
            *formula_var_args(formula_name),
            "--json",
        ],
        cwd=root,
        env=env,
    )
    payload = parse_json_output(result, context=f"bd mol pour for {formula_name}")
    if not isinstance(payload, dict):
        raise SetupError(f"bd mol pour returned a non-object for {formula_name}")
    if not any(
        isinstance(payload.get(key), str) and payload.get(key)
        for key in ("new_epic_id", "root_id")
    ):
        raise SetupError(f"bd mol pour did not return a root ID for {formula_name}")


def validate_formula_bundle(source_dir: Path) -> None:
    """Pour every bundled formula in an isolated real Beads repository.

    ``bd mol seed`` verifies formula discovery and in-memory cooking. The
    isolated pour additionally exercises real issue and dependency insertion,
    including generated gates and task/epic type constraints, without creating
    template issues or gates in the target repository.
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
            validate_formula_source(scratch, formula_name, env=env)
            seed_formula(scratch, formula_name, env=env)
            pour_formula_preflight(scratch, formula_name, env=env)


def show_issue_optional(root: Path, issue_id: str) -> dict[str, Any] | None:
    result = run(["bd", "show", issue_id, "--json"], cwd=root, check=False)
    if result.returncode != 0:
        detail = f"{result.stdout}\n{result.stderr}".casefold()
        if "not found" in detail or "no issues found" in detail:
            return None
        raise SetupError(
            f"command failed (bd show {issue_id} --json): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    payload = parse_json_output(result, context=f"bd show for {issue_id}")
    matches = [item for item in issue_items(payload) if item.get("id") == issue_id]
    if len(matches) != 1:
        raise SetupError(f"bd show returned an unexpected result for {issue_id}")
    return matches[0]


def all_issue_inventory(root: Path) -> list[dict[str, Any]]:
    """Return every issue, including hidden templates and gate issues.

    ``bd list`` excludes templates and gates by default. Older dstack setup
    persisted formula protos, and an early cleanup could delete only their
    roots while leaving template steps and gates orphaned. A root-based walk
    therefore cannot prove that the repository is clean.
    """

    result = run(
        [
            "bd",
            "list",
            "--all",
            "--include-templates",
            "--include-gates",
            "--limit",
            "0",
            "--json",
        ],
        cwd=root,
    )
    return issue_items(parse_json_output(result, context="bd list inventory"))


def persisted_proto_artifacts(
    root: Path,
    formula_name: str,
    *,
    inventory: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return verified legacy template artifacts for one reserved formula ID.

    The exact formula name and its dotted namespace are reserved for the
    accidental graphs created by older ``bd cook --persist`` setup releases.
    Detection intentionally does not require the root to exist: a prior partial
    cleanup may have left only orphaned child steps or gates.
    """

    source = (
        list(inventory)
        if inventory is not None
        else all_issue_inventory(root)
    )
    matching_summaries: list[Mapping[str, Any]] = []
    prefix = f"{formula_name}."
    for item in source:
        item_id = item.get("id")
        if isinstance(item_id, str) and (
            item_id == formula_name or item_id.startswith(prefix)
        ):
            matching_summaries.append(item)

    if not matching_summaries:
        return []

    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for summary in matching_summaries:
        artifact_id = summary.get("id")
        if not isinstance(artifact_id, str) or artifact_id in seen:
            continue
        seen.add(artifact_id)

        artifact = show_issue_optional(root, artifact_id)
        if artifact is None:
            raise SetupError(
                f"legacy dstack template artifact disappeared during inspection: {artifact_id}"
            )
        if artifact.get("is_template") is not True:
            raise SetupError(
                f"issue {artifact_id} uses dstack's reserved template namespace "
                "but is not a dstack template; refusing to delete it"
            )
        artifacts.append(artifact)

    artifacts.sort(
        key=lambda item: (
            item.get("id") != formula_name,
            str(item.get("id", "")).count("."),
            str(item.get("id", "")),
        )
    )
    return artifacts


def find_legacy_persisted_protos(root: Path) -> dict[str, list[dict[str, Any]]]:
    inventory = all_issue_inventory(root)
    found: dict[str, list[dict[str, Any]]] = {}
    for formula_name in FORMULA_NAMES:
        artifacts = persisted_proto_artifacts(
            root,
            formula_name,
            inventory=inventory,
        )
        if artifacts:
            found[formula_name] = artifacts
    return found


def remove_legacy_persisted_protos(
    root: Path,
    found: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    artifact_ids: list[str] = []
    for formula_name, artifacts in found.items():
        prefix = f"{formula_name}."
        for artifact in artifacts:
            artifact_id = artifact.get("id")
            if not isinstance(artifact_id, str) or not (
                artifact_id == formula_name or artifact_id.startswith(prefix)
            ):
                raise SetupError(
                    f"legacy persisted template inventory is invalid for {formula_name}"
                )
            artifact_ids.append(artifact_id)

    artifact_ids = sorted(set(artifact_ids))
    if not artifact_ids:
        return []

    # Refuse cleanup if any issue outside the verified set depends on one of
    # these artifacts. The dry run validates the complete batch before --force
    # performs the irreversible deletion.
    run(
        ["bd", "delete", *artifact_ids, "--dry-run", "--json"],
        cwd=root,
    )
    run(
        ["bd", "delete", *artifact_ids, "--force", "--json"],
        cwd=root,
    )

    remaining = find_legacy_persisted_protos(root)
    if remaining:
        remaining_ids = sorted(
            str(item.get("id"))
            for artifacts in remaining.values()
            for item in artifacts
        )
        raise SetupError(
            "failed to remove legacy persisted dstack template artifacts: "
            + ", ".join(remaining_ids)
        )

    return sorted(found)


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

    legacy_protos = find_legacy_persisted_protos(root)
    if legacy_protos and not force:
        names = ", ".join(sorted(legacy_protos))
        raise SetupError(
            "legacy persisted dstack template artifacts pollute Beads ready "
            "work and gates: "
            f"{names}; rerun with --force to remove only those verified template graphs"
        )

    snapshots: dict[Path, bytes | None] = {}
    removed: list[str] = []
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
            seed_formula(root, formula_name)

        if legacy_protos:
            removed = remove_legacy_persisted_protos(root, legacy_protos)
    except Exception:
        restore_formula_files(snapshots)
        raise

    return {
        "status": "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": installed,
        "validated": sorted(parsed),
        "preflight": "isolated-formula-pour",
        "legacy_persisted_protos_removed": removed,
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
        seed_formula(root, formula_name)
        statuses[formula_name] = "available"

    legacy_protos = find_legacy_persisted_protos(root)
    if legacy_protos:
        names = ", ".join(sorted(legacy_protos))
        raise SetupError(
            "legacy persisted dstack template artifacts remain in Beads: "
            f"{names}; rerun /setup-project --force"
        )

    return {
        "status": "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": statuses,
        "persisted_protos": "absent",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="install and validate formulas")
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
