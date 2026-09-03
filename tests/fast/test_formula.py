from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from dstack import formula as subject
from dstack.core import CommandResult, DstackError


def test_packaged_formula_has_one_native_five_step_graph() -> None:
    formula = subject.load_formula()
    steps = {step["id"]: step for step in formula["steps"]}
    assert formula["formula"] == "dstack-feature"
    assert formula["version"] == 2
    assert set(steps) == set(subject.EXPECTED_STEPS)
    assert steps["approval"]["gate"]["type"] == "human"
    assert steps["implementation"]["type"] == "epic"
    assert "needs" not in steps["implementation"]
    assert steps["audit"]["waits_for"] == "children-of(implementation)"


def test_formula_contract_rejects_controller_owned_phase() -> None:
    formula = deepcopy(subject.load_formula())
    formula["steps"].append({"id": "delivery", "title": "Implicit controller phase"})
    with pytest.raises(DstackError):
        subject.validate_formula_contract(formula)


def test_formula_contract_rejects_cross_type_implementation_blocker() -> None:
    formula = deepcopy(subject.load_formula())
    formula["steps"][3]["needs"] = ["approval"]
    with pytest.raises(DstackError):
        subject.validate_formula_contract(formula)


def test_formula_install_requires_native_beads_initialization(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "beads_workspace_optional", lambda root: None)
    with pytest.raises(DstackError):
        subject.install_formula(git_repo)


def test_failed_native_parse_restores_previous_formula(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / subject.FORMULA_FILENAME
    source.write_bytes(subject.formula_path().read_bytes())
    workspace = git_repo / ".beads"
    destination = workspace / "formulas" / subject.FORMULA_FILENAME
    destination.parent.mkdir(parents=True)
    destination.write_text("old formula\n", encoding="utf-8")

    class FakeClient:
        def __init__(self, root: Path):
            self.root = root

        def check_version(self) -> str:
            return "bd version 1.2.2 (test)"

    monkeypatch.setattr(subject, "formula_path", lambda: source)
    monkeypatch.setattr(subject, "beads_workspace", lambda root: workspace)
    monkeypatch.setattr(subject, "formula_destination", lambda root: destination)
    monkeypatch.setattr(subject, "BeadsClient", FakeClient)
    monkeypatch.setattr(subject, "run", lambda *args, **kwargs: CommandResult(1, "", "formula rejected"))

    with pytest.raises(DstackError):
        subject.install_formula(git_repo, update=True)
    assert destination.read_text(encoding="utf-8") == "old formula\n"


def test_formula_install_invokes_no_beads_setup_or_diagnostics(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = git_repo / ".beads"
    workspace.mkdir()
    source = tmp_path / subject.FORMULA_FILENAME
    source.write_bytes(subject.formula_path().read_bytes())
    observed: list[list[str]] = []

    class FakeClient:
        def __init__(self, root: Path):
            self.root = root

        def check_version(self) -> str:
            return "bd version 1.2.2 (test)"

    def fake_run(command: list[str], **kwargs: object) -> CommandResult:
        observed.append(command)
        return CommandResult(0, "{}", "")

    monkeypatch.setattr(subject, "formula_path", lambda: source)
    monkeypatch.setattr(subject, "beads_workspace", lambda root: workspace)
    monkeypatch.setattr(subject, "BeadsClient", FakeClient)
    monkeypatch.setattr(subject, "run", fake_run)

    result = subject.install_formula(git_repo)

    assert result["status"] == "ok"
    assert observed == [["bd", "formula", "show", "dstack-feature", "--json"]]


def test_formula_display_path_handles_shared_workspace_outside_linked_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "repo.feature"
    destination = tmp_path / "repo" / ".beads" / "formulas" / subject.FORMULA_FILENAME
    assert subject.display_formula_path(destination, repository) == str(destination)


def test_formula_display_path_is_relative_inside_repository(tmp_path: Path) -> None:
    destination = tmp_path / ".beads" / "formulas" / subject.FORMULA_FILENAME
    assert subject.display_formula_path(destination, tmp_path) == f".beads/formulas/{subject.FORMULA_FILENAME}"
