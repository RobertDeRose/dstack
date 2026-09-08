"""Install and validate the project-local dStack Beads contract."""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .beads import BeadsClient, beads_workspace, beads_workspace_optional, run_beads
from .core import DstackError, assert_no_symlink_components, run
from .git_state import git_root
from .workflow import FEATURE_STEP_LABELS, FEATURE_STEP_TYPES

FORMULA_NAME = "dstack-feature"
FORMULA_FILENAME = f"{FORMULA_NAME}.formula.toml"
PRIME_FILENAME = "PRIME.md"
EXPECTED_STEPS = tuple(FEATURE_STEP_TYPES)


def package_root() -> Path:
    return Path(__file__).resolve().parent


def formula_path() -> Path:
    path = package_root() / "assets" / "formulas" / FORMULA_FILENAME
    if not path.is_file():
        raise DstackError(f"packaged formula is missing: {path}")
    return path


def prime_path() -> Path:
    path = package_root() / "assets" / PRIME_FILENAME
    if not path.is_file():
        raise DstackError(f"packaged Beads prime is missing: {path}")
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
    """Validate the dStack-specific invariants Beads cannot infer from the name."""

    if formula.get("formula") != FORMULA_NAME:
        raise DstackError(f"formula must be named {FORMULA_NAME}")
    if formula.get("type") != "workflow" or formula.get("phase") != "liquid" or formula.get("pour") is not True:
        raise DstackError("dstack-feature must be a persistent poured workflow")

    steps = _step_map(formula)
    if set(steps) != set(EXPECTED_STEPS):
        raise DstackError(f"dstack-feature steps must be exactly: {', '.join(EXPECTED_STEPS)}")
    for step_id in EXPECTED_STEPS:
        if steps[step_id].get("type") != FEATURE_STEP_TYPES[step_id]:
            raise DstackError(f"{step_id} must be a {FEATURE_STEP_TYPES[step_id]}")
        if steps[step_id].get("labels") != [FEATURE_STEP_LABELS[step_id]]:
            raise DstackError(f"{step_id} label must be exactly {FEATURE_STEP_LABELS[step_id]}")
    # Native formula loading and acceptance tests own needs and gate semantics.
    # Only the role identities consumed by dStack belong in this validator.


@dataclass(frozen=True)
class FormulaContext:
    repository: Path
    workspace: Path
    beads_version: str


def _formula_context(root: Path) -> FormulaContext:
    repository = git_root(root)
    workspace = beads_workspace(repository)
    return FormulaContext(repository, workspace, BeadsClient(repository).check_version())


def display_formula_path(destination: Path, repository: Path) -> str:
    try:
        return str(destination.relative_to(repository))
    except ValueError:
        return str(destination)


def _atomic_write(path: Path, content: bytes, *, purpose: str = "Beads formula destination") -> None:
    assert_no_symlink_components(path, purpose=purpose)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        os.chmod(temporary, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise DstackError(f"cannot install Beads formula: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _verify_native_formula(repository: Path) -> None:
    parsed = run_beads(["bd", "formula", "show", FORMULA_NAME, "--json"], cwd=repository, check=False)
    if parsed.returncode != 0:
        raise DstackError(parsed.stderr.strip() or parsed.stdout.strip() or "Beads rejected the installed formula")


def init_workspace(root: Path, *, update: bool = False) -> dict[str, Any]:
    """Initialize Beads when absent, then install and verify the dStack contract."""

    repository = git_root(root)
    beads_version = BeadsClient(repository).check_version()
    workspace = beads_workspace_optional(repository)
    initialized = workspace is None
    if initialized:
        run_beads(
            [
                "bd",
                "init",
                "--quiet",
                "--non-interactive",
                "--init-if-missing",
                "--skip-agents",
                "--skip-hooks",
            ],
            cwd=repository,
        )

    if workspace is None:
        workspace = beads_workspace(repository)
    # Installation already verifies native loading and the exact installed bytes.
    installed = _install_formula(FormulaContext(repository, workspace, beads_version), update=update)
    return {**installed, "initialized": initialized, "validated": True}


def _install_formula(context: FormulaContext, *, update: bool) -> dict[str, Any]:
    repository = context.repository
    beads_version = context.beads_version
    load_formula()

    source = formula_path().read_bytes()
    destination = context.workspace / "formulas" / FORMULA_FILENAME
    assert_no_symlink_components(destination, purpose="Beads formula destination")
    current = destination.read_bytes() if destination.is_file() else None
    if current is not None and current != source and not update:
        raise DstackError(
            f"project formula differs from the packaged dStack contract: {destination}; "
            "rerun with `dstack init --update` after reviewing the change"
        )

    prime_source = prime_path().read_bytes()
    prime = context.workspace / PRIME_FILENAME
    assert_no_symlink_components(prime, purpose="Beads prime destination")
    current_prime = prime.read_bytes() if prime.is_file() else None
    if current_prime is not None and current_prime != prime_source and not update:
        raise DstackError(
            f"project Beads prime differs from the packaged dStack contract: {prime}; "
            "rerun with `dstack init --update` after reviewing the change"
        )

    formula_changed = current != source
    prime_changed = current_prime != prime_source
    try:
        if formula_changed:
            _atomic_write(destination, source)
        if prime_changed:
            _atomic_write(prime, prime_source, purpose="Beads prime destination")
        _verify_native_formula(repository)
    except DstackError as failure:
        try:
            if formula_changed:
                if current is None:
                    destination.unlink(missing_ok=True)
                else:
                    _atomic_write(destination, current)
            if prime_changed:
                if current_prime is None:
                    prime.unlink(missing_ok=True)
                else:
                    _atomic_write(prime, current_prime, purpose="Beads prime destination")
        except (OSError, DstackError) as exc:
            raise DstackError(f"{failure}; restoring the previous dStack contract failed: {exc}") from exc
        raise

    return {
        "status": "ok",
        "root": str(repository),
        "beads_version": beads_version,
        "formula": display_formula_path(destination, repository),
        "formula_changed": formula_changed,
        "prime": display_formula_path(prime, repository),
        "prime_changed": prime_changed,
    }


def check_formula(root: Path) -> dict[str, Any]:
    """Verify dStack's installed and committed project policy."""

    context = _formula_context(root)
    repository = context.repository
    beads_version = context.beads_version
    load_formula()

    destination = context.workspace / "formulas" / FORMULA_FILENAME
    assert_no_symlink_components(destination, purpose="Beads formula destination")
    if not destination.is_file():
        raise DstackError(f"project formula is not installed: {destination}")
    packaged_formula = formula_path().read_bytes()
    if destination.read_bytes() != packaged_formula:
        raise DstackError(f"project formula differs from the packaged dStack contract: {destination}")

    relative_formula = Path(".beads") / "formulas" / FORMULA_FILENAME
    observed = run(
        ["git", "show", f"HEAD:{relative_formula.as_posix()}"],
        cwd=repository,
        check=False,
    )
    if observed.returncode != 0 or observed.stdout.encode() != packaged_formula:
        raise DstackError(
            f"project formula must match the committed HEAD policy before feature work: {relative_formula}"
        )

    prime = context.workspace / PRIME_FILENAME
    assert_no_symlink_components(prime, purpose="Beads prime destination")
    if not prime.is_file():
        raise DstackError(f"project Beads prime is not installed: {prime}")
    if prime.read_bytes() != prime_path().read_bytes():
        raise DstackError(f"project Beads prime differs from the packaged dStack contract: {prime}")

    _verify_native_formula(repository)
    return {
        "status": "ok",
        "root": str(repository),
        "beads_version": beads_version,
        "formula": display_formula_path(destination, repository),
        "formula_committed": True,
        "prime": display_formula_path(prime, repository),
    }
