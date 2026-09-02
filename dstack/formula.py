"""Installation and validation of the project-local Beads formula."""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Mapping

from .core import BeadsClient, DstackError, _assert_no_symlink_components, git_root, parse_json, run

FORMULA_NAME = "dstack-feature"
FORMULA_FILENAME = f"{FORMULA_NAME}.formula.toml"
EXPECTED_STEPS = ("plan", "review", "approval", "implementation", "audit")


def package_root() -> Path:
    return Path(__file__).resolve().parent


def formula_path() -> Path:
    path = package_root() / "assets" / "formulas" / FORMULA_FILENAME
    if not path.is_file():
        raise DstackError(f"packaged formula is missing: {path}")
    return path


def load_formula() -> dict[str, Any]:
    try:
        payload = tomllib.loads(formula_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise DstackError(f"cannot load packaged formula: {exc}") from exc
    validate_formula_contract(payload)
    return payload


def _step_map(formula: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = formula.get("steps")
    if not isinstance(raw, list):
        raise DstackError("dstack-feature formula must define steps")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise DstackError("dstack-feature formula contains an invalid step")
        step_id = str(item["id"])
        if step_id in result:
            raise DstackError(f"dstack-feature formula duplicates step {step_id}")
        result[step_id] = item
    return result


def validate_formula_contract(formula: Mapping[str, Any]) -> None:
    if formula.get("formula") != FORMULA_NAME:
        raise DstackError(f"formula must be named {FORMULA_NAME}")
    if formula.get("type") != "workflow" or formula.get("phase") != "liquid" or formula.get("pour") is not True:
        raise DstackError("dstack-feature must be a persistent poured workflow")
    steps = _step_map(formula)
    if tuple(steps) != EXPECTED_STEPS:
        raise DstackError(f"dstack-feature steps must be exactly: {', '.join(EXPECTED_STEPS)}")
    if list(steps["review"].get("needs") or []) != ["plan"]:
        raise DstackError("review must depend on plan")
    if list(steps["approval"].get("needs") or []) != ["review"]:
        raise DstackError("approval must depend on review")
    gate = steps["approval"].get("gate")
    if not isinstance(gate, dict) or gate.get("type") != "human":
        raise DstackError("approval must use a native human gate")
    if list(steps["implementation"].get("needs") or []) != ["approval"]:
        raise DstackError("implementation must depend on approval")
    if list(steps["audit"].get("needs") or []) != ["approval"]:
        raise DstackError("audit must depend on approval")
    if steps["audit"].get("waits_for") != "children-of(implementation)":
        raise DstackError("audit must use native implementation fan-in")


def beads_workspace_optional(root: Path) -> Path | None:
    """Resolve the authoritative workspace through native `bd where`."""

    repository = git_root(root)
    result = run(["bd", "where", "--json"], cwd=repository, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    payload = parse_json(result.stdout, context="bd where")
    if not isinstance(payload, dict) or not isinstance(payload.get("path"), str) or not payload["path"]:
        return None
    workspace = Path(payload["path"]).expanduser()
    if not workspace.is_absolute():
        workspace = repository / workspace
    _assert_no_symlink_components(workspace, purpose="Beads workspace")
    resolved = workspace.resolve()
    if resolved.name != ".beads" or not resolved.is_dir():
        raise DstackError(f"bd where returned an invalid Beads workspace: {resolved}")
    return resolved


def beads_workspace(root: Path) -> Path:
    workspace = beads_workspace_optional(root)
    if workspace is None:
        raise DstackError("Beads is not initialized for this repository; run `dstack ctl infra install`")
    return workspace


def formula_destination(root: Path) -> Path:
    return beads_workspace(root) / "formulas" / FORMULA_FILENAME


def display_formula_path(destination: Path, repository: Path) -> str:
    try:
        return str(destination.relative_to(repository))
    except ValueError:
        return str(destination)


def ensure_beads_initialized(root: Path, *, initialize: bool) -> tuple[Path, bool]:
    repository = git_root(root)
    initialized = False
    if beads_workspace_optional(repository) is None:
        if not initialize:
            raise DstackError("Beads is not initialized for this repository")
        run(
            [
                "bd",
                "init",
                "--quiet",
                "--stealth",
                "--skip-agents",
                "--skip-hooks",
                "--non-interactive",
            ],
            cwd=repository,
        )
        initialized = True
    beads_workspace(repository)
    return repository, initialized


def _atomic_write(path: Path, content: bytes) -> None:
    _assert_no_symlink_components(path, purpose="Beads formula destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise DstackError(f"cannot install Beads formula: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def install_infrastructure(root: Path, *, update_formula: bool = False) -> dict[str, Any]:
    repository, initialized = ensure_beads_initialized(root, initialize=True)
    client = BeadsClient(repository)
    beads_version = client.check_version()
    load_formula()

    source = formula_path().read_bytes()
    destination = formula_destination(repository)
    current = destination.read_bytes() if destination.is_file() else None
    if current is not None and current != source and not update_formula:
        raise DstackError(
            f"project formula differs from the installed dStack contract: {destination}; "
            "rerun with --update-formula after reviewing the change"
        )
    changed = current != source
    if changed:
        _atomic_write(destination, source)

    parsed = run(["bd", "formula", "show", FORMULA_NAME, "--json"], cwd=repository, check=False)
    if parsed.returncode != 0:
        failure = parsed.stderr.strip() or parsed.stdout.strip() or "Beads rejected the installed formula"
        if changed:
            try:
                if current is None:
                    destination.unlink(missing_ok=True)
                else:
                    _atomic_write(destination, current)
            except (OSError, DstackError) as exc:
                raise DstackError(f"{failure}; restoring the previous formula failed: {exc}") from exc
        raise DstackError(failure)

    return {
        "status": "ok",
        "root": str(repository),
        "beads_version": beads_version,
        "initialized": initialized,
        "formula": display_formula_path(destination, repository),
        "formula_changed": changed,
    }


def check_infrastructure(root: Path) -> dict[str, Any]:
    repository, _ = ensure_beads_initialized(root, initialize=False)
    client = BeadsClient(repository)
    beads_version = client.check_version()
    load_formula()

    destination = formula_destination(repository)
    if destination.is_symlink() or not destination.is_file():
        raise DstackError(f"project formula is not installed: {destination}")
    if destination.read_bytes() != formula_path().read_bytes():
        raise DstackError(f"project formula differs from the installed dStack contract: {destination}")

    parsed = run(["bd", "formula", "show", FORMULA_NAME, "--json"], cwd=repository, check=False)
    if parsed.returncode != 0:
        raise DstackError(parsed.stderr.strip() or parsed.stdout.strip() or "Beads rejected the installed formula")

    doctor = run(["bd", "doctor", "--json"], cwd=repository, check=False)
    return {
        "status": "ok",
        "root": str(repository),
        "beads_version": beads_version,
        "formula": display_formula_path(destination, repository),
        "doctor": {
            "status": "ok" if doctor.returncode == 0 else "issues",
            "returncode": doctor.returncode,
            "details": (doctor.stderr.strip() or doctor.stdout.strip())[-4000:],
        },
    }
