#!/usr/bin/env python3
"""Small dStack-owned infrastructure and formula-contract helpers.

Formula files are controller-managed inputs for creating new work. Their version
is a semantic planning/review contract version, not a schema version for
historical Beads graphs.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import tomllib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core import (
    ALIGNMENT_STEPS,
    FEATURE_STEPS,
    BeadsClient,
    DstackError,
    git_common_dir,
    git_root,
    issue_metadata,
    run,
)

FORMULA_NAMES = ("dstack-feature", "dstack-project-alignment")
FEATURE_FORMULA = "dstack-feature"
ALIGNMENT_FORMULA = "dstack-project-alignment"
FORMULA_VERSION_KEY = "dstack.formula_version"
CREATED_FORMULA_VERSION_KEY = "dstack.created_formula_version"


class FormulaAuditRequired(DstackError):
    """Signal that semantic compatibility review is required before execution."""

    def __init__(self, payload: Mapping[str, Any]):
        self.payload = dict(payload)
        super().__init__(str(self.payload.get("message") or "formula compatibility audit required"))


def package_root() -> Path:
    return Path(__file__).resolve().parent


def formula_path(name: str) -> Path:
    if name not in FORMULA_NAMES:
        raise DstackError(f"unknown dStack formula: {name}")
    return package_root() / "assets" / "formulas" / f"{name}.formula.toml"


def load_formula(name: str) -> dict[str, Any]:
    path = formula_path(name)
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DstackError(f"invalid packaged formula {name}: {path}") from exc
    if payload.get("formula") != name:
        raise DstackError(f"packaged formula identity mismatch: {name}")
    version = payload.get("version")
    if not isinstance(version, int) or version < 1:
        raise DstackError(f"packaged formula {name} has invalid contract version")
    validate_formula_contract(name, payload)
    return payload


def formula_contract_version(name: str) -> int:
    return int(load_formula(name)["version"])


def _step_map(formula: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = formula.get("steps")
    if not isinstance(raw, list):
        raise DstackError("formula steps must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise DstackError("formula contains an invalid step")
        step_id = str(item["id"])
        if step_id in result:
            raise DstackError(f"formula contains duplicate step ID: {step_id}")
        result[step_id] = item
    return result


def validate_formula_contract(name: str, formula: Mapping[str, Any]) -> None:
    """Validate the deliberately small stable lifecycle skeleton."""

    steps = _step_map(formula)
    if name == FEATURE_FORMULA:
        expected = {
            "specification": ("task", FEATURE_STEPS["specification"]),
            "approval": ("task", FEATURE_STEPS["approval"]),
            "implementation": ("epic", FEATURE_STEPS["implementation"]),
            "closeout": ("task", FEATURE_STEPS["closeout"]),
        }
        planning, approval, workstream, terminal = "specification", "approval", "implementation", "closeout"
    elif name == ALIGNMENT_FORMULA:
        expected = {
            "analysis": ("task", ALIGNMENT_STEPS["analysis"]),
            "approval": ("task", ALIGNMENT_STEPS["approval"]),
            "corrections": ("epic", ALIGNMENT_STEPS["corrections"]),
            "landing": ("task", ALIGNMENT_STEPS["landing"]),
        }
        planning, approval, workstream, terminal = "analysis", "approval", "corrections", "landing"
    else:  # guarded by load_formula callers, kept explicit for direct tests
        raise DstackError(f"unknown dStack formula: {name}")

    if set(steps) != set(expected):
        raise DstackError(f"{name} must contain exactly {sorted(expected)}")
    for step_id, (expected_type, expected_label) in expected.items():
        step = steps[step_id]
        actual_type = str(step.get("type") or "task")
        if actual_type != expected_type:
            raise DstackError(f"{name} step {step_id} must be {expected_type}, got {actual_type}")
        if step.get("labels") != [expected_label]:
            raise DstackError(f"{name} step {step_id} must have only label {expected_label}")
        if step.get("metadata"):
            raise DstackError(f"{name} step {step_id} must not duplicate identity in metadata")

    if steps[approval].get("needs") != [planning]:
        raise DstackError(f"{name} approval must depend only on {planning}")
    gate = steps[approval].get("gate")
    if not isinstance(gate, dict) or gate.get("type") != "human":
        raise DstackError(f"{name} approval must carry a human gate")
    if steps[workstream].get("needs") or steps[workstream].get("gate"):
        raise DstackError(f"{name} workstream must remain an ungated epic container")
    if steps[terminal].get("needs") != [approval]:
        raise DstackError(f"{name} terminal must depend on approval")
    if steps[terminal].get("waits_for") != f"children-of({workstream})":
        raise DstackError(f"{name} terminal must use native dynamic child fan-in")


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or (path.exists() and path.is_symlink()):
        raise DstackError(f"formula path must not be a symlink: {path}")
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(raw, path)
    finally:
        Path(raw).unlink(missing_ok=True)


def _formula_destination(root: Path, name: str) -> Path:
    return root / ".beads/formulas" / formula_path(name).name


def _formula_lock_path(root: Path) -> Path:
    try:
        return git_common_dir(root) / ".dstack-formula.lock"
    except DstackError:
        lock_dir = Path(tempfile.gettempdir()) / "dstack-formula-locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
        return lock_dir / f"{digest}.lock"


@contextmanager
def _formula_lock(root: Path):
    lock_path = _formula_lock_path(root)
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            lock.write(b"\0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def current_formula_for_pour(client: BeadsClient, name: str):
    """Expose the packaged formula only for one native pour.

    Historical tracked formula copies are restored byte-for-byte. When no
    project copy exists, the temporary formula file is removed after the pour,
    so a dStack upgrade creates no formula-cache migration or Git boundary.
    """

    with _formula_lock(client.root):
        destination = _formula_destination(client.root, name)
        source = formula_path(name).read_bytes()
        existed = destination.exists()
        if existed and (not destination.is_file() or destination.is_symlink()):
            raise DstackError(f"formula path must be a regular file: {destination}")
        original = destination.read_bytes() if existed else None
        if original == source:
            yield
            return

        _atomic_replace(destination, source)
        try:
            yield
        finally:
            if original is None:
                destination.unlink(missing_ok=True)
            else:
                _atomic_replace(destination, original)


def pour_current_formula(client: BeadsClient, name: str, variables: Mapping[str, str]) -> dict[str, Any]:
    with current_formula_for_pour(client, name):
        return client.pour(name, variables)


def ensure_beads_initialized(root_arg: Path) -> tuple[Path, bool]:
    root = git_root(root_arg)
    beads = root / ".beads"
    if beads.is_symlink():
        raise DstackError(".beads must be a repository directory, not a symlink")
    if beads.exists():
        if not beads.is_dir():
            raise DstackError(".beads must be a repository directory")
        return root, False
    run(
        ["bd", "init", "--quiet", "--stealth", "--skip-agents", "--skip-hooks", "--non-interactive"],
        cwd=root,
    )
    if not beads.is_dir():
        raise DstackError("bd init completed without creating .beads")
    return root, True


def ensure_infrastructure(root_arg: Path) -> dict[str, Any]:
    """Validate prerequisites, initialize Beads, and expose formula contracts."""

    root = git_root(root_arg)
    beads_version = BeadsClient(root).check_version()
    versions = {name: formula_contract_version(name) for name in FORMULA_NAMES}
    root, initialized = ensure_beads_initialized(root)
    return {
        "root": root,
        "initialized": initialized,
        "formula_versions": versions,
        "beads_version": beads_version,
    }


def metadata_formula_version(issue: Mapping[str, Any], key: str = FORMULA_VERSION_KEY) -> int | None:
    value = issue_metadata(issue).get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def stamp_formula_version(
    client: BeadsClient,
    issue_ids: Sequence[str],
    *,
    formula_name: str,
) -> int:
    version = formula_contract_version(formula_name)
    ids = list(dict.fromkeys(str(item) for item in issue_ids if item))
    if ids:
        client.update_many(ids, "--set-metadata", f"{FORMULA_VERSION_KEY}={version}")
    return version


def stamp_created_formula_version(client: BeadsClient, root_id: str, *, formula_name: str) -> int:
    version = formula_contract_version(formula_name)
    client.update(root_id, "--set-metadata", f"{CREATED_FORMULA_VERSION_KEY}={version}")
    return version
