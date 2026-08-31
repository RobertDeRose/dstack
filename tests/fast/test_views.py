from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
from dstack import core as dstacklib
from dstack.core import ALIGNMENT_STEPS, FEATURE_STEPS

from scripted import ScriptedClient, call


def test_feature_context_reads_only_root_and_stable_steps(tmp_path: Path) -> None:
    root = {
        "id": "feature-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": "docs/src/features/feature/design.md",
        },
    }
    steps = [
        {"id": f"{name}-1", "issue_type": kind, "labels": [label]}
        for name, label, kind in (
            ("specification", FEATURE_STEPS["specification"], "task"),
            ("approval", FEATURE_STEPS["approval"], "task"),
            ("implementation", FEATURE_STEPS["implementation"], "epic"),
            ("closeout", FEATURE_STEPS["closeout"], "task"),
        )
    ]
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "feature-1", result=root),
        call("children", "feature-1", result=steps),
    )
    observed = dstacklib.feature_context(beads, "feature-1")
    assert observed["steps"]["implementation"]["id"] == "implementation-1"
    assert observed["base_branch"] == "main"
    assert "ready_work" not in observed
    assert "progress" not in observed
    beads.assert_exhausted()


def test_current_feature_context_rejects_noncanonical_design_path(
    tmp_path: Path,
) -> None:
    root = {
        "id": "feature-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": "docs/features/feature/design.md",
        },
    }
    steps = [
        {"id": f"{name}-1", "issue_type": kind, "labels": [label]}
        for name, label, kind in (
            ("specification", FEATURE_STEPS["specification"], "task"),
            ("approval", FEATURE_STEPS["approval"], "task"),
            ("implementation", FEATURE_STEPS["implementation"], "epic"),
            ("closeout", FEATURE_STEPS["closeout"], "task"),
        )
    ]
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "feature-1", result=root),
        call("children", "feature-1", result=steps),
    )
    with pytest.raises(dstacklib.DstackError, match="docs/src/features/feature/design.md"):
        dstacklib.feature_context(beads, "feature-1")
    beads.assert_exhausted()


def test_noncurrent_feature_context_does_not_expose_child_inventory(
    tmp_path: Path,
) -> None:
    root = {
        "id": "legacy-1",
        "issue_type": "epic",
        "status": "open",
        "labels": ["workflow:feature", "feature:legacy"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "legacy-1", result=root),
        call("children", "legacy-1", result=[{"id": "legacy-child"}]),
    )
    observed = dstacklib.feature_context(beads, "legacy-1")
    assert observed["current"] is False
    assert "children" not in observed
    beads.assert_exhausted()


def test_alignment_context_reads_only_root_and_stable_steps(tmp_path: Path) -> None:
    root = {
        "id": "alignment-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:project-alignment", "audit:repository"],
        "metadata": {"dstack.target_branch": "main", "dstack.scope": "repository"},
    }
    steps = [
        {"id": f"{name}-1", "issue_type": kind, "labels": [label]}
        for name, label, kind in (
            ("analysis", ALIGNMENT_STEPS["analysis"], "task"),
            ("approval", ALIGNMENT_STEPS["approval"], "task"),
            ("corrections", ALIGNMENT_STEPS["corrections"], "epic"),
            ("landing", ALIGNMENT_STEPS["landing"], "task"),
        )
    ]
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "alignment-1", result=root),
        call("children", "alignment-1", result=steps),
    )
    observed = dstacklib.alignment_context(beads, "alignment-1")
    assert observed["steps"]["corrections"]["id"] == "corrections-1"
    assert observed["target_branch"] == "main"
    assert "ready_work" not in observed
    assert "progress" not in observed
    beads.assert_exhausted()


def test_human_gate_requires_the_steps_native_blocking_relation(tmp_path: Path) -> None:
    approval = {"id": "approval-1", "issue_type": "task", "dependencies": []}
    beads = ScriptedClient(
        tmp_path,
        call("show", "approval-1", result=approval),
    )

    assert (
        dstacklib.human_gate_for_step(
            beads,
            root_id="feature-1",
            step=approval,
        )
        is None
    )
    beads.assert_exhausted()


def test_feature_design_state_uses_registered_committed_content(git_repo: Path, monkeypatch) -> None:
    relative = "docs/src/features/feature/design.md"
    design = git_repo / relative
    design.parent.mkdir(parents=True)
    design.write_text("accepted design\n")
    subprocess.run(["git", "add", relative], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "docs: add design"], cwd=git_repo, check=True)
    digest = hashlib.sha256(design.read_bytes()).hexdigest()
    context = {
        "slug": "feature",
        "design_path": relative,
        "approved_design_sha256": digest,
    }
    monkeypatch.setattr(dstacklib, "worktree_for_branch", lambda *args: git_repo)

    state = dstacklib.feature_design_state(ScriptedClient(git_repo), context)
    assert state["design_state"] == "committed"
    assert state["head_design_sha256"] == digest
    assert state["design_approved"] is True

    context["pending_design_sha256"] = digest
    assert dstacklib.feature_design_state(ScriptedClient(git_repo), context)["design_approved"] is False
    context.pop("pending_design_sha256")

    design.write_text("changed design\n")
    state = dstacklib.feature_design_state(ScriptedClient(git_repo), context)
    assert state["design_state"] == "worktree_mismatch"
    assert state["design_approved"] is False

    monkeypatch.setattr(dstacklib, "worktree_for_branch", lambda *args: None)
    state = dstacklib.feature_design_state(ScriptedClient(git_repo), context)
    assert state["design_state"] == "worktree_missing"
    assert state["current_design_sha256"] is None


def test_feature_view_default_stops_at_specification_without_hydrating_work(
    tmp_path: Path, monkeypatch
) -> None:
    root = {
        "id": "feature-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": "docs/src/features/feature/design.md",
        },
    }
    steps = [
        {
            "id": "specification-1",
            "issue_type": "task",
            "status": "open",
            "labels": [FEATURE_STEPS["specification"]],
        },
        {
            "id": "approval-1",
            "issue_type": "task",
            "status": "open",
            "labels": [FEATURE_STEPS["approval"]],
        },
        {
            "id": "implementation-1",
            "issue_type": "epic",
            "status": "open",
            "labels": [FEATURE_STEPS["implementation"]],
        },
        {
            "id": "closeout-1",
            "issue_type": "task",
            "status": "open",
            "labels": [FEATURE_STEPS["closeout"]],
        },
    ]
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "feature-1", result=root),
        call("children", "feature-1", result=steps),
    )
    monkeypatch.setattr(dstacklib, "worktree_for_branch", lambda *args: tmp_path)

    observed = dstacklib.feature_view(beads, "feature-1")

    assert observed == {
        "selected_bead_id": "feature-1",
        "next_bead_id": "specification-1",
        "worktree": str(tmp_path),
        "required_evidence": ["committed feature design", "explicit human authorization"],
        "blocking_reason": None,
    }
    beads.assert_exhausted()


def test_feature_view_verbose_projects_real_steps_gate_and_design(git_repo: Path, monkeypatch) -> None:
    relative = "docs/src/features/feature/design.md"
    design = git_repo / relative
    design.parent.mkdir(parents=True)
    design.write_text("accepted design\n")
    subprocess.run(["git", "add", relative], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "docs: add design"], cwd=git_repo, check=True)
    digest = hashlib.sha256(design.read_bytes()).hexdigest()
    root = {
        "id": "feature-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": relative,
            "dstack.approved_design_sha256": digest,
        },
    }
    steps = [
        {
            "id": "specification-1",
            "issue_type": "task",
            "status": "closed",
            "labels": [FEATURE_STEPS["specification"]],
        },
        {
            "id": "approval-1",
            "issue_type": "task",
            "status": "closed",
            "labels": [FEATURE_STEPS["approval"]],
        },
        {
            "id": "implementation-1",
            "issue_type": "epic",
            "labels": [FEATURE_STEPS["implementation"]],
        },
        {
            "id": "closeout-1",
            "issue_type": "task",
            "status": "open",
            "labels": [FEATURE_STEPS["closeout"]],
        },
    ]
    approval = {
        **steps[1],
        "dependencies": [{"depends_on_id": "gate-1", "type": "blocks"}],
    }
    gate = {
        "id": "gate-1",
        "issue_type": "gate",
        "status": "closed",
        "await_type": "human",
    }
    task = {
        "id": "task-1",
        "issue_type": "task",
        "labels": ["dstack:work:implementation"],
    }
    beads = ScriptedClient(
        git_repo,
        call("show_optional", "feature-1", result=root),
        call("children", "feature-1", result=steps),
        call("children", "implementation-1", result=[task]),
        call("show", "specification-1", result=steps[0]),
        call("show", "approval-1", result=approval),
        call("show_optional", "gate-1", result=gate),
    )
    monkeypatch.setattr(dstacklib, "worktree_for_branch", lambda *args: git_repo)

    observed = dstacklib.feature_view(beads, "feature-1", verbose=True)
    assert observed["steps"]["approval"]["id"] == "approval-1"
    assert observed["human_gate"] == gate
    assert observed["native_approved"] is True
    assert observed["design_approved"] is True
    assert "ready_work_ids" not in observed
    assert "progress" not in observed
    assert "delivery_ready" not in observed
    beads.assert_exhausted()


def test_alignment_view_default_stops_at_analysis_without_hydrating_corrections(
    tmp_path: Path, monkeypatch
) -> None:
    root = {
        "id": "alignment-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:project-alignment", "audit:repository"],
        "metadata": {"dstack.target_branch": "main", "dstack.scope": "repository"},
    }
    steps = [
        {
            "id": "analysis-1",
            "issue_type": "task",
            "status": "open",
            "labels": [ALIGNMENT_STEPS["analysis"]],
        },
        {
            "id": "approval-1",
            "issue_type": "task",
            "status": "open",
            "labels": [ALIGNMENT_STEPS["approval"]],
        },
        {
            "id": "corrections-1",
            "issue_type": "epic",
            "status": "open",
            "labels": [ALIGNMENT_STEPS["corrections"]],
        },
        {
            "id": "landing-1",
            "issue_type": "task",
            "status": "open",
            "labels": [ALIGNMENT_STEPS["landing"]],
        },
    ]
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "alignment-1", result=root),
        call("children", "alignment-1", result=steps),
    )
    monkeypatch.setattr(dstacklib, "worktree_for_branch", lambda *args: tmp_path)

    observed = dstacklib.alignment_view(beads, "alignment-1")

    assert observed == {
        "selected_bead_id": "alignment-1",
        "next_bead_id": "analysis-1",
        "worktree": str(tmp_path),
        "required_evidence": ["review summary", "native correction graph"],
        "blocking_reason": None,
    }
    beads.assert_exhausted()


def test_alignment_view_verbose_projects_real_steps_gate_and_metadata(
    tmp_path: Path,
) -> None:
    root = {
        "id": "alignment-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:project-alignment", "audit:repository"],
        "metadata": {
            "dstack.target_branch": "main",
            "dstack.scope": "whole repository",
        },
    }
    steps = [
        {"id": "analysis-1", "issue_type": "task", "labels": [ALIGNMENT_STEPS["analysis"]]},
        {"id": "approval-1", "issue_type": "task", "labels": [ALIGNMENT_STEPS["approval"]]},
        {"id": "corrections-1", "issue_type": "epic", "labels": [ALIGNMENT_STEPS["corrections"]]},
        {
            "id": "landing-1",
            "issue_type": "task",
            "status": "open",
            "labels": [ALIGNMENT_STEPS["landing"]],
        },
    ]
    approval = {
        **steps[1],
        "dependencies": [{"depends_on_id": "gate-1", "type": "blocks"}],
    }
    gate = {"id": "gate-1", "issue_type": "gate", "await_type": "human"}
    correction = {"id": "correction-1", "issue_type": "task"}
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "alignment-1", result=root),
        call("children", "alignment-1", result=steps),
        call("show", "approval-1", result=approval),
        call("show_optional", "gate-1", result=gate),
        call("children", "corrections-1", result=[correction]),
    )

    observed = dstacklib.alignment_view(beads, "alignment-1", verbose=True)
    assert observed["steps"]["corrections"]["id"] == "corrections-1"
    assert observed["human_gate"] == gate
    assert observed["target_branch"] == "main"
    assert observed["scope"] == "whole repository"
    assert "ready_work_ids" not in observed
    assert "progress" not in observed
    assert "delivery_ready" not in observed
    beads.assert_exhausted()
