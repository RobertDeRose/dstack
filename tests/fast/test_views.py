from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstacklib
from dstacklib import ALIGNMENT_STEPS, FEATURE_STEPS

from scripted import ScriptedClient, call


def test_feature_context_reads_only_root_and_stable_steps(tmp_path: Path) -> None:
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
    observed = dstacklib.feature_context(beads, "feature-1")
    assert observed["steps"]["implementation"]["id"] == "implementation-1"
    assert observed["base_branch"] == "main"
    assert "ready_work" not in observed
    assert "progress" not in observed
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


def test_feature_view_projects_real_steps_gate_design_and_ready_work(
    tmp_path: Path, monkeypatch
) -> None:
    design = tmp_path / "docs/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("accepted design\n")
    digest = hashlib.sha256(design.read_bytes()).hexdigest()
    root = {
        "id": "feature-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": "docs/features/feature/design.md",
            "dstack.approved_design_sha256": digest,
        },
    }
    steps = [
        {"id": "specification-1", "issue_type": "task", "labels": [FEATURE_STEPS["specification"]]},
        {
            "id": "approval-1",
            "issue_type": "task",
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
    gate = {"id": "gate-1", "issue_type": "gate", "await_type": "human"}
    task = {
        "id": "task-1",
        "issue_type": "task",
        "labels": ["dstack:work:implementation"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "feature-1", result=root),
        call("children", "feature-1", result=steps),
        call("children", "implementation-1", result=[task]),
        call("show", "approval-1", result=approval),
        call("show_optional", "gate-1", result=gate),
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            result=[task],
        ),
        call("progress", "feature-1", result={"completed": 1, "total": 5}),
    )
    monkeypatch.setattr(dstacklib, "worktree_for_branch", lambda *args: tmp_path)

    observed = dstacklib.feature_view(beads, "feature-1")
    assert observed["steps"]["approval"]["id"] == "approval-1"
    assert observed["human_gate"] == gate
    assert observed["design_approved"] is True
    assert observed["ready_work"] == [task]
    beads.assert_exhausted()


def test_alignment_view_projects_real_steps_gate_metadata_and_ready_work(
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
        call(
            "ready_children",
            "corrections-1",
            label="dstack:work:correction",
            result=[correction],
        ),
        call("progress", "alignment-1", result={"completed": 1, "total": 5}),
    )

    observed = dstacklib.alignment_view(beads, "alignment-1")
    assert observed["steps"]["corrections"]["id"] == "corrections-1"
    assert observed["human_gate"] == gate
    assert observed["target_branch"] == "main"
    assert observed["scope"] == "whole repository"
    assert observed["ready_work"] == [correction]
    beads.assert_exhausted()
