from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from dstack import formula as subject
from dstack.core import CommandResult, DstackError


def test_packaged_formula_has_one_native_five_step_graph() -> None:
    formula = subject.load_formula()
    assert formula["formula"] == "dstack-feature"
    assert formula["version"] == 2
    assert [step["id"] for step in formula["steps"]] == list(subject.EXPECTED_STEPS)
    assert formula["steps"][2]["gate"]["type"] == "human"
    assert formula["steps"][3]["type"] == "epic"
    assert "needs" not in formula["steps"][3]
    assert formula["steps"][4]["waits_for"] == "children-of(implementation)"


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


def test_failed_beads_parse_restores_previous_formula(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / subject.FORMULA_FILENAME
    source.write_bytes(subject.formula_path().read_bytes())
    destination = git_repo / ".beads/formulas" / subject.FORMULA_FILENAME
    destination.parent.mkdir(parents=True)
    destination.write_text("old formula\n", encoding="utf-8")

    class FakeClient:
        def __init__(self, root: Path):
            self.root = root

        def check_version(self) -> str:
            return "bd version 1.2.2 (test)"

    monkeypatch.setattr(subject, "formula_path", lambda: source)
    monkeypatch.setattr(subject, "ensure_beads_initialized", lambda root, initialize: (git_repo, False))
    monkeypatch.setattr(subject, "formula_destination", lambda root: destination)
    monkeypatch.setattr(subject, "BeadsClient", FakeClient)
    monkeypatch.setattr(
        subject,
        "run",
        lambda *args, **kwargs: CommandResult(1, "", "formula rejected"),
    )

    with pytest.raises(DstackError):
        subject.install_infrastructure(git_repo, update_formula=True)
    assert destination.read_text(encoding="utf-8") == "old formula\n"


def test_formula_display_path_handles_shared_workspace_outside_linked_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "repo.feature"
    destination = tmp_path / "repo" / ".beads" / "formulas" / subject.FORMULA_FILENAME
    assert subject.display_formula_path(destination, repository) == str(destination)


def test_formula_display_path_is_relative_inside_repository(tmp_path: Path) -> None:
    destination = tmp_path / ".beads" / "formulas" / subject.FORMULA_FILENAME
    assert subject.display_formula_path(destination, tmp_path) == f".beads/formulas/{subject.FORMULA_FILENAME}"
