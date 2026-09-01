from __future__ import annotations

from contextlib import contextmanager
import subprocess
import threading
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from dstack import formula as dstack_formula  # noqa: E402
from dstack.formula import (  # noqa: E402
    FEATURE_FORMULA,
    formula_contract_version,
    pour_current_formula,
    validate_formula_contract,
)
from dstack.core import DstackError  # noqa: E402


def load(name: str) -> dict:
    return tomllib.loads((ROOT / "dstack/assets/formulas" / f"{name}.formula.toml").read_text())


def test_feature_formula_is_minimal_and_uses_native_fan_in() -> None:
    formula = load("dstack-feature")
    assert formula["version"] == 9
    assert formula_contract_version(FEATURE_FORMULA) == 9
    assert set(formula["vars"]) == {"feature_title", "feature_slug", "design_path"}
    assert [step["id"] for step in formula["steps"]] == [
        "specification",
        "approval",
        "implementation",
        "closeout",
    ]
    steps = {step["id"]: step for step in formula["steps"]}
    assert steps["approval"]["gate"]["type"] == "human"
    assert steps["implementation"]["type"] == "epic"
    assert steps["closeout"]["waits_for"] == "children-of(implementation)"
    assert sum(step["id"] == "closeout" for step in formula["steps"]) == 1
    assert "single final reconciliation" in formula["description"]
    assert all("metadata" not in step for step in formula["steps"])
    assert all("{{" not in repr(step.get("labels", [])) for step in formula["steps"])
    validate_formula_contract("dstack-feature", formula)


def test_formula_contract_rejects_extra_stable_step() -> None:
    formula = load("dstack-feature")
    formula["steps"].append({"id": "review", "type": "task", "labels": []})
    with pytest.raises(DstackError, match="exactly"):
        validate_formula_contract("dstack-feature", formula)


def test_formula_contract_rejects_duplicate_step_ids() -> None:
    formula = load("dstack-feature")
    formula["steps"].append(dict(formula["steps"][0]))
    with pytest.raises(DstackError, match="duplicate step ID"):
        validate_formula_contract("dstack-feature", formula)


def test_infrastructure_checks_beads_before_initializing(monkeypatch, tmp_path: Path) -> None:
    events: list[str] = []

    class Client:
        def __init__(self, root: Path) -> None:
            assert root == tmp_path

        def check_version(self) -> str:
            events.append("version")
            return "bd version 1.2.2 (6c124203e)"

    monkeypatch.setattr(dstack_formula, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(dstack_formula, "BeadsClient", Client)
    monkeypatch.setattr(
        dstack_formula,
        "ensure_beads_initialized",
        lambda root: (events.append("init") or root, True),
    )
    monkeypatch.setattr(
        dstack_formula,
        "formula_contract_version",
        lambda name: events.append(name) or 1,
    )

    infrastructure = dstack_formula.ensure_infrastructure(tmp_path)

    assert events == ["version", "dstack-feature", "init"]
    assert infrastructure["beads_version"] == "bd version 1.2.2 (6c124203e)"


def test_beads_initialization_uses_repository_mutation_lock(monkeypatch, tmp_path: Path) -> None:
    events: list[str] = []

    @contextmanager
    def locked(root: Path):
        assert root == tmp_path
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    def run(command, *, cwd, **kwargs):
        del kwargs
        assert cwd == tmp_path
        assert events == ["enter"]
        assert command[:2] == ["bd", "init"]
        (tmp_path / ".beads").mkdir()
        return None

    monkeypatch.setattr(dstack_formula, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(dstack_formula, "repository_mutation_lock", locked)
    monkeypatch.setattr(dstack_formula, "run", run)

    assert dstack_formula.ensure_beads_initialized(tmp_path) == (tmp_path, True)
    assert events == ["enter", "exit"]


def test_concurrent_formula_pours_are_serialized(git_repo: Path) -> None:
    destination = git_repo / ".beads/formulas/dstack-feature.formula.toml"
    first = dstack_formula.current_formula_for_pour(type("Client", (), {"root": git_repo})(), "dstack-feature")
    first.__enter__()
    acquired = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []

    def pour() -> None:
        try:
            with dstack_formula.current_formula_for_pour(type("Client", (), {"root": git_repo})(), "dstack-feature"):
                acquired.set()
        except BaseException as exc:  # pragma: no cover - only reports thread failures
            errors.append(exc)
        finally:
            finished.set()

    worker = threading.Thread(target=pour)
    worker.start()
    try:
        assert not acquired.wait(0.05)
    finally:
        first.__exit__(None, None, None)
    assert acquired.wait(1)
    assert finished.wait(1)
    worker.join()
    assert errors == []
    assert not destination.exists()


def test_formula_pour_uses_package_bytes_without_persistent_cache(git_repo: Path) -> None:
    destination = git_repo / ".beads/formulas/dstack-feature.formula.toml"

    class Client:
        root = git_repo

        def pour(self, name, variables):
            assert name == "dstack-feature"
            assert (
                destination.read_bytes() == (ROOT / "dstack/assets/formulas/dstack-feature.formula.toml").read_bytes()
            )
            return {"root_id": "feature-1"}

    assert pour_current_formula(Client(), "dstack-feature", {"feature_title": "Demo"}) == {"root_id": "feature-1"}
    assert not destination.exists()


def test_untracked_identical_formula_residue_is_cleaned(git_repo: Path) -> None:
    destination = git_repo / ".beads/formulas/dstack-feature.formula.toml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((ROOT / "dstack/assets/formulas/dstack-feature.formula.toml").read_bytes())

    with dstack_formula.current_formula_for_pour(type("Client", (), {"root": git_repo})(), "dstack-feature"):
        assert destination.is_file()

    assert not destination.exists()


def test_tracked_identical_formula_is_preserved(git_repo: Path) -> None:
    destination = git_repo / ".beads/formulas/dstack-feature.formula.toml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "dstack/assets/formulas/dstack-feature.formula.toml").read_bytes()
    destination.write_bytes(source)
    subprocess.run(["git", "add", str(destination.relative_to(git_repo))], cwd=git_repo, check=True)

    with dstack_formula.current_formula_for_pour(type("Client", (), {"root": git_repo})(), "dstack-feature"):
        assert destination.read_bytes() == source

    assert destination.read_bytes() == source


def test_interrupted_owned_formula_residue_is_recovered(git_repo: Path) -> None:
    destination = git_repo / ".beads/formulas/dstack-feature.formula.toml"
    owner = dstack_formula._formula_owner_path(git_repo, "dstack-feature")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((ROOT / "dstack/assets/formulas/dstack-feature.formula.toml").read_bytes())
    owner.write_text("remove\n")

    with dstack_formula.current_formula_for_pour(type("Client", (), {"root": git_repo})(), "dstack-feature"):
        assert destination.is_file()
        assert owner.is_file()

    assert not destination.exists()
    assert not owner.exists()


@pytest.mark.parametrize("replacement_written", [False, True])
def test_interrupted_tracked_formula_replacement_restores_original(git_repo: Path, replacement_written: bool) -> None:
    destination = git_repo / ".beads/formulas/dstack-feature.formula.toml"
    owner = dstack_formula._formula_owner_path(git_repo, "dstack-feature")
    backup = dstack_formula._formula_backup_path(git_repo, "dstack-feature")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("legacy tracked formula\n")
    subprocess.run(["git", "add", ".beads/formulas/dstack-feature.formula.toml"], cwd=git_repo, check=True)

    original = destination.read_bytes()
    source = (ROOT / "dstack/assets/formulas/dstack-feature.formula.toml").read_bytes()
    backup.write_bytes(original)
    owner.write_text("restore\n")
    if replacement_written:
        destination.write_bytes(source)

    with dstack_formula.current_formula_for_pour(type("Client", (), {"root": git_repo})(), "dstack-feature"):
        assert destination.read_bytes() == source
        assert owner.read_text() == "restore\n"
        assert backup.read_bytes() == original

    assert destination.read_bytes() == original
    assert not owner.exists()
    assert not backup.exists()


def test_tracked_legacy_formula_is_not_migrated_and_pour_uses_package_bytes(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    destination = tmp_path / ".beads/formulas/dstack-feature.formula.toml"
    destination.parent.mkdir(parents=True)
    destination.write_text("legacy tracked formula\n")
    subprocess.run(["git", "add", ".beads/formulas/dstack-feature.formula.toml"], cwd=tmp_path, check=True)

    class Client:
        root = tmp_path

        def pour(self, name, variables):
            assert name == "dstack-feature"
            assert (
                destination.read_bytes() == (ROOT / "dstack/assets/formulas/dstack-feature.formula.toml").read_bytes()
            )
            return {"root_id": "feature-1"}

    assert destination.read_text() == "legacy tracked formula\n"
    assert pour_current_formula(Client(), "dstack-feature", {"feature_title": "Demo"}) == {"root_id": "feature-1"}
    assert destination.read_text() == "legacy tracked formula\n"


def test_formula_pour_rejects_beads_symlink(git_repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-beads"
    outside.mkdir()
    (git_repo / ".beads").symlink_to(outside, target_is_directory=True)

    with pytest.raises(DstackError, match="symlink"):
        with dstack_formula.current_formula_for_pour(type("Client", (), {"root": git_repo})(), "dstack-feature"):
            raise AssertionError("formula pour should not run")
    assert not (outside / "formulas").exists()


def test_ensure_beads_initialized_rejects_dangling_symlink(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dstack_formula, "git_root", lambda root: tmp_path)
    (tmp_path / ".beads").symlink_to(tmp_path / "missing-beads", target_is_directory=True)

    with pytest.raises(DstackError, match="symlink"):
        dstack_formula.ensure_beads_initialized(tmp_path)
