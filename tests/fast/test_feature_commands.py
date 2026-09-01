from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
from dstack import feature as dstack_feature
from dstack.commands import DstackError, create_child_reconciled, refuse_external_dependents, release_claim
from dstack.core import FeatureNotFound
from dstack.docs import RECORD_SUBJECTS

from scripted import ScriptedClient, call


@pytest.fixture(autouse=True)
def _stable_formula_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dstack_feature, "stamp_created_formula_version", lambda *args, **kwargs: 9)
    monkeypatch.setattr(dstack_feature, "stamp_formula_version", lambda *args, **kwargs: 9)
    monkeypatch.setattr(dstack_feature, "stamp_feature_formula_contract", lambda *args, **kwargs: 9)
    monkeypatch.setattr(
        dstack_feature,
        "feature_formula_contract_state",
        lambda *args, **kwargs: {
            "formula": "dstack-feature",
            "created_version": 9,
            "audited_version": 9,
            "current_version": 9,
        },
    )


def semantic_record(kind: str) -> str:
    lines = ["# Record", ""]
    for subject in RECORD_SUBJECTS[kind]:
        lines.extend([f"## {subject}", "", f"Evidence for {subject}.", ""])
    return "\n".join(lines)


def view(**overrides) -> dict:
    value = {
        "root": {
            "id": "feature-1",
            "status": "open",
            "title": "Feature: Feature",
            "description": "Preserve this planned outcome and its rationale.",
            "acceptance_criteria": "The planned behavior is externally observable.",
        },
        "slug": "feature",
        "current": True,
        "closed": False,
        "base_branch": "main",
        "design_path": "docs/src/features/feature/design.md",
        "approved_design_sha256": "digest",
        "current_design_sha256": "digest",
        "head_design_sha256": "digest",
        "design_state": "committed",
        "design_approved": True,
        "native_approved": True,
        "human_gate": {"id": "gate-1", "status": "open"},
        "steps": {
            "specification": {"id": "specification-1", "status": "open"},
            "approval": {"id": "approval-1", "status": "open"},
            "implementation": {"id": "implementation-1", "status": "open"},
            "closeout": {"id": "closeout-1", "status": "open"},
        },
        "work_items": [],
    }
    value.update(overrides)
    return value


def patch_command(monkeypatch, module, beads, current=None):
    current = current or view()
    monkeypatch.setattr(module, "client_for", lambda root: beads)
    monkeypatch.setattr(module, "feature_context", lambda client, selector: current)
    monkeypatch.setattr(
        module,
        "feature_design_state",
        lambda client, context: {
            "current_design_sha256": current.get("current_design_sha256"),
            "head_design_sha256": current.get("head_design_sha256"),
            "design_state": current.get("design_state"),
            "design_approved": current.get("design_approved", False),
        },
    )
    monkeypatch.setattr(
        module,
        "feature_branch_context",
        lambda *args: ("feat/feature", beads.root, "main"),
    )
    monkeypatch.setattr(
        module,
        "feature_authorization_state",
        lambda client, context: {
            "human_gate": current.get("human_gate"),
            "native_approved": current.get("native_approved", False),
        },
        raising=False,
    )
    if hasattr(module, "validate_feature_documentation"):
        monkeypatch.setattr(
            module,
            "validate_feature_documentation",
            lambda client, context: {"status": "ok"},
        )
    if hasattr(module, "create_child_reconciled"):
        monkeypatch.setattr(
            module,
            "create_child_reconciled",
            lambda client, title, **kwargs: client.create(
                title,
                parent=kwargs["parent_id"],
                labels=kwargs["labels"],
                dependencies=kwargs["dependencies"],
                description=kwargs["description"],
                acceptance=kwargs["acceptance"],
                priority=kwargs["priority"],
            ),
        )
    output = []
    monkeypatch.setattr(module, "emit", output.append)
    return output


def test_resolve_and_inspect_emit_observed_state(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    current = view()
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(
        dstack_feature,
        "resolve_feature",
        lambda client, selector: current["root"],
    )
    monkeypatch.setattr(dstack_feature, "feature_slug", lambda root: "feature")
    monkeypatch.setattr(dstack_feature, "is_current_feature", lambda client, root: True)
    monkeypatch.setattr(dstack_feature, "feature_view", lambda client, selector: current)
    output = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)

    assert dstack_feature.cmd_feature_resolve(argparse.Namespace(root=tmp_path, selector="feature")) == 0
    assert dstack_feature.cmd_feature_inspect(argparse.Namespace(root=tmp_path, selector="feature")) == 0
    assert output[0]["root"]["id"] == "feature-1"
    assert output[1]["steps"]["implementation"]["id"] == "implementation-1"


def test_initialize_rejects_option_like_base_before_beads_mutation(monkeypatch, git_repo: Path) -> None:
    beads = ScriptedClient(git_repo)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    with pytest.raises(DstackError, match="invalid base branch"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=git_repo,
                selector="Feature",
                title=None,
                slug=None,
                base_branch="--help",
                design_path=None,
            )
        )
    beads.assert_exhausted()


def test_initialize_rejects_design_path_outside_mdbook_features(monkeypatch, tmp_path: Path) -> None:
    planned = {
        "id": "planned-1",
        "issue_type": "epic",
        "status": "open",
        "title": "Feature",
        "labels": ["dstack:feature-idea", "feature:feature"],
    }
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda client, selector: planned)
    monkeypatch.setattr(
        dstack_feature,
        "feature_context",
        lambda client, selector: {"root": planned, "current": False, "closed": False},
    )
    args = argparse.Namespace(
        root=tmp_path,
        selector="Feature",
        title=None,
        slug=None,
        base_branch="main",
        design_path="docs/features/feature/design.md",
    )
    with pytest.raises(DstackError, match="docs/src/features/feature/design.md"):
        dstack_feature.cmd_feature_initialize(args)
    beads.assert_exhausted()


def test_initialize_requires_explicit_planned_feature(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(
        dstack_feature,
        "resolve_feature",
        lambda client, selector: (_ for _ in ()).throw(FeatureNotFound("no feature matches selector")),
    )

    with pytest.raises(DstackError, match="requires an open dstack:feature-idea"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=tmp_path,
                selector="Feature",
                title=None,
                slug=None,
                base_branch="main",
                design_path=None,
            )
        )
    beads.assert_exhausted()


def test_initialize_rejects_deferred_planned_feature(monkeypatch, tmp_path: Path) -> None:
    planned = {
        "id": "planned-1",
        "issue_type": "epic",
        "status": "deferred",
        "title": "Feature",
        "labels": ["dstack:feature-idea", "feature:feature"],
    }
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda client, selector: planned)
    monkeypatch.setattr(
        dstack_feature,
        "feature_context",
        lambda client, selector: {"root": planned, "current": False, "closed": False},
    )

    with pytest.raises(DstackError, match="requires an open dstack:feature-idea"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=tmp_path,
                selector="Feature",
                title=None,
                slug=None,
                base_branch="main",
                design_path=None,
            )
        )
    beads.assert_exhausted()


def test_initialize_rejects_legacy_planned_metadata_shape_without_mutation(monkeypatch, git_repo: Path) -> None:
    historical = {
        "id": "historical-planned-1",
        "issue_type": "epic",
        "status": "open",
        "labels": ["dstack:feature-idea", "feature:historical", "workflow:feature"],
        "metadata": {"feature_slug": "historical", "migration_classification": "planned"},
    }
    beads = ScriptedClient(git_repo)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda client, selector: historical)
    monkeypatch.setattr(
        dstack_feature,
        "feature_context",
        lambda client, selector: {"root": historical, "current": False, "closed": False},
    )

    with pytest.raises(DstackError, match="unsupported historical topology"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=git_repo,
                selector="historical-planned-1",
                title=None,
                slug=None,
                base_branch="main",
                design_path=None,
            )
        )
    beads.assert_exhausted()


def test_plan_rejects_molecule_planned_source_without_mutation(monkeypatch, tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Durable intent\n")
    planned = {
        "id": "planned-1",
        "issue_type": "molecule",
        "status": "open",
        "labels": ["dstack:feature-idea", "feature:feature"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "planned-1", result=planned),
        call("children", "planned-1", result=[]),
    )
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)

    with pytest.raises(DstackError, match="parentless planned feature"):
        dstack_feature.cmd_feature_plan(
            argparse.Namespace(
                root=tmp_path,
                selector="planned-1",
                title="Feature",
                slug="feature",
                body_file=body,
                acceptance="Observable outcome",
                priority=1,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_initialize_rejects_historical_topology_without_mutation(monkeypatch, git_repo: Path) -> None:
    historical = {
        "id": "historical-1",
        "issue_type": "epic",
        "status": "open",
        "labels": ["workflow:feature", "feature:historical"],
        "metadata": {
            "dstack.feature_slug": "historical",
            "migration_classification": "planned",
            "roadmap": "not-planned",
        },
    }
    beads = ScriptedClient(git_repo)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda client, selector: historical)
    monkeypatch.setattr(
        dstack_feature,
        "feature_context",
        lambda client, selector: {"root": historical, "current": False, "closed": False},
    )

    with pytest.raises(DstackError, match="unsupported historical topology"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=git_repo,
                selector="historical",
                title=None,
                slug=None,
                base_branch="main",
                design_path=None,
            )
        )

    beads.assert_exhausted()


def test_initialize_rejects_planned_feature_with_children_before_mutation(monkeypatch, tmp_path: Path) -> None:
    planned = {
        "id": "planned-1",
        "issue_type": "epic",
        "status": "open",
        "title": "Feature",
        "labels": ["dstack:feature-idea", "feature:feature"],
    }
    child = {"id": "child-1", "parent": "planned-1", "status": "open"}
    beads = ScriptedClient(tmp_path, call("children", "planned-1", result=[child]))
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda client, selector: planned)
    monkeypatch.setattr(
        dstack_feature,
        "feature_context",
        lambda client, selector: {"root": planned, "current": False, "closed": False},
    )
    monkeypatch.setattr(dstack_feature, "require_unique_open_feature_slug", lambda *args, **kwargs: None)
    monkeypatch.setattr(dstack_feature, "branch_exists", lambda *args: False)

    with pytest.raises(DstackError, match="children"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=tmp_path,
                selector="planned-1",
                title=None,
                slug=None,
                base_branch="main",
                design_path=None,
            )
        )
    beads.assert_exhausted()


def test_initialize_pours_formula_and_records_only_stable_identity(monkeypatch, tmp_path: Path) -> None:
    planned = {
        "id": "planned-1",
        "issue_type": "epic",
        "status": "open",
        "title": "Feature",
        "description": "planned details",
        "acceptance_criteria": "planned outcome",
        "priority": 2,
        "labels": ["dstack:feature-idea", "feature:feature"],
    }
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[planned]),
        call("children", "planned-1", result=[]),
        call("list", all_statuses=True, include_gates=True, result=[planned]),
        call(
            "pour",
            "dstack-feature",
            {
                "feature_title": "Feature",
                "feature_slug": "feature",
                "design_path": "docs/src/features/feature/design.md",
            },
            result={"root_id": "feature-1"},
        ),
        call(
            "update",
            "feature-1",
            "--title",
            "Feature: Feature",
            "--add-label",
            "workflow:feature",
            "--add-label",
            "feature:feature",
            "--set-metadata",
            "dstack.base_branch=main",
            "--set-metadata",
            "dstack.design_path=docs/src/features/feature/design.md",
            "--description",
            "planned details",
            "--acceptance",
            "planned outcome",
            "--priority",
            "2",
            result={"id": "feature-1"},
        ),
        call("supersede", "planned-1", "feature-1", result=None),
    )
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda client, selector: planned)

    def context(client, selector):
        if selector == "planned-1":
            return {"root": planned, "current": False, "closed": False}
        return view()

    monkeypatch.setattr(dstack_feature, "feature_context", context)
    monkeypatch.setattr(
        dstack_feature,
        "ensure_feature_worktree",
        lambda *args: ("feat/feature", tmp_path / "worktree", True, True),
    )
    monkeypatch.setattr(dstack_feature, "preserve_external_blockers", lambda *args: [])
    monkeypatch.setattr(dstack_feature, "refuse_external_dependents", lambda *args: None)
    output = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)

    args = argparse.Namespace(
        root=tmp_path,
        selector="planned-1",
        title=None,
        slug=None,
        base_branch="main",
        design_path=None,
    )
    assert dstack_feature.cmd_feature_initialize(args) == 0
    assert output[0]["created"] is True
    assert output[0]["planned_source"] == "planned-1"
    assert output[0]["branch"] == "feat/feature"
    beads.assert_exhausted()


def test_add_task_delegates_acceptance_and_dependencies(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result={"id": "feature-1", "metadata": {}}),
        call("show", "specification-1", result={"id": "specification-1", "status": "open"}),
        call("show", "approval-1", result={"id": "approval-1", "status": "open"}),
        call(
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "open"},
        ),
        call(
            "create",
            "Implement outcome",
            parent="implementation-1",
            labels=["dstack:work:implementation"],
            dependencies=["approval-1", "blocker-1"],
            description="details",
            acceptance="observable result",
            priority=1,
            result={"id": "task-1"},
        ),
        call("show", "feature-1", result={"id": "feature-1", "status": "open", "metadata": {}}),
        call("show", "specification-1", result={"id": "specification-1", "status": "open"}),
        call("show", "approval-1", result={"id": "approval-1", "status": "open"}),
        call("show", "implementation-1", result={"id": "implementation-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        title="Implement outcome",
        description="details",
        description_file=None,
        acceptance="observable result",
        acceptance_file=None,
        priority=1,
        depends_on=["blocker-1"],
    )
    assert dstack_feature.cmd_feature_add_task(args) == 0
    assert output == [{"status": "ok", "task": {"id": "task-1"}}]
    beads.assert_exhausted()


@pytest.mark.parametrize("title", ["Reconcile documentation", "Document the API"])
def test_add_task_rejects_documentation_or_reconciliation_work(monkeypatch, tmp_path: Path, title: str) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="sole final reconciliation"):
        dstack_feature.cmd_feature_add_task(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                title=title,
                description="details",
                description_file=None,
                acceptance="observable result",
                acceptance_file=None,
                priority=1,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_add_task_defers_created_child_when_authorization_closes_during_create(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "open",
        "labels": ["dstack:work:implementation"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result={"id": "feature-1", "metadata": {}}),
        call("show", "specification-1", result={"id": "specification-1", "status": "open"}),
        call("show", "approval-1", result={"id": "approval-1", "status": "open"}),
        call("show", "implementation-1", result={"id": "implementation-1", "status": "open"}),
        call(
            "create",
            "Raced outcome",
            parent="implementation-1",
            labels=["dstack:work:implementation"],
            dependencies=["approval-1"],
            description="details",
            acceptance="observable result",
            priority=1,
            result=task,
        ),
        call("show", "feature-1", result={"id": "feature-1", "metadata": {}}),
        call("show", "specification-1", result={"id": "specification-1", "status": "open"}),
        call("show", "approval-1", result={"id": "approval-1", "status": "closed"}),
        call("show", "implementation-1", result={"id": "implementation-1", "status": "open"}),
        call("update", "task-1", "--status", "deferred", result={"id": "task-1", "status": "deferred"}),
    )
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="authorization changed"):
        dstack_feature.cmd_feature_add_task(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                title="Raced outcome",
                description="details",
                description_file=None,
                acceptance="observable result",
                acceptance_file=None,
                priority=1,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_add_task_rejects_approved_graph_without_creation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "metadata": {"dstack.approved_design_sha256": "digest"},
            },
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        title="Late outcome",
        description=None,
        description_file=None,
        acceptance="observable result",
        acceptance_file=None,
        priority=1,
        depends_on=[],
    )
    with pytest.raises(DstackError, match="reauthorization"):
        dstack_feature.cmd_feature_add_task(args)
    beads.assert_exhausted()


@pytest.mark.parametrize(
    ("root_metadata", "specification_status"),
    [
        ({"dstack.pending_design_sha256": "digest"}, None),
        ({}, "closed"),
    ],
)
def test_add_task_rejects_interrupted_approval_without_creation(
    monkeypatch,
    tmp_path: Path,
    root_metadata: dict[str, str],
    specification_status: str | None,
) -> None:
    calls = [call("show", "feature-1", result={"id": "feature-1", "metadata": root_metadata})]
    if specification_status is not None:
        calls.append(
            call(
                "show",
                "specification-1",
                result={"id": "specification-1", "status": specification_status},
            )
        )
    beads = ScriptedClient(tmp_path, *calls)
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        title="Unreviewed late outcome",
        description=None,
        description_file=None,
        acceptance="observable result",
        acceptance_file=None,
        priority=1,
        depends_on=[],
    )
    with pytest.raises(DstackError, match="approval has begun"):
        dstack_feature.cmd_feature_add_task(args)
    beads.assert_exhausted()


def test_add_task_rejects_blank_acceptance_before_write(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        title="Invalid",
        description=None,
        description_file=None,
        acceptance="  ",
        acceptance_file=None,
        priority=2,
        depends_on=[],
    )
    with pytest.raises(DstackError, match="acceptance criteria is required"):
        dstack_feature.cmd_feature_add_task(args)
    beads.assert_exhausted()


def test_scaffold_design_creates_once_without_overwriting(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    output = patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    args = argparse.Namespace(root=tmp_path, selector="feature-1")
    assert dstack_feature.cmd_feature_scaffold_design(args) == 0
    design = worktree / "docs/src/features/feature/design.md"
    summary = worktree / "docs/src/SUMMARY.md"
    feature_index = worktree / "docs/src/features/index.md"
    authored = design.read_text()
    assert "Preserve this planned outcome" in authored
    assert "The planned behavior is externally observable" in authored
    assert "## Outcome" in authored
    assert "## Non-goals" in authored
    assert "## Design" in authored
    assert "## Failure, security, and compatibility" in authored
    assert "## Validation" in authored
    assert "## Documentation impact" in authored
    assert "[Feature Records](features/index.md)" in summary.read_text()
    assert "[Feature](features/feature/design.md)" in summary.read_text()
    assert "[Feature](feature/design.md)" in feature_index.read_text()
    navigation = (summary.read_text(), feature_index.read_text())
    assert dstack_feature.cmd_feature_scaffold_design(args) == 0
    assert design.read_text() == authored
    assert (summary.read_text(), feature_index.read_text()) == navigation
    assert [item["created"] for item in output] == [True, False]


def test_scaffold_reconciliation_creates_once_and_updates_navigation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    worktree = tmp_path / "worktree"
    design = worktree / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("accepted design\n")
    (worktree / "docs/src/features/index.md").write_text(
        "# Feature Records\n\n- [Authored catalog title](feature/design.md)\n"
    )
    (worktree / "docs/src/SUMMARY.md").write_text(
        "# Summary\n\n- [Feature Records](features/index.md)\n"
        "  - [Authored chapter title](features/feature/design.md)\n"
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    args = argparse.Namespace(root=tmp_path, selector="feature-1")

    assert dstack_feature.cmd_feature_scaffold_reconciliation(args) == 0
    reconciliation = design.with_name("index.md")
    authored = reconciliation.read_text()
    assert "## Delivered outcome" in authored
    assert "## Material deviations" in authored
    assert "## Documentation links" in authored
    assert "## Remaining limitations" in authored
    assert "[Authored catalog title](feature/index.md)" in (worktree / "docs/src/features/index.md").read_text()
    summary_path = worktree / "docs/src/SUMMARY.md"
    summary = summary_path.read_text()
    assert summary.count("[Feature Records](features/index.md)") == 1
    assert "  - [Authored chapter title](features/feature/index.md)" in summary
    assert "    - [Design](features/feature/design.md)" in summary

    reconciliation.write_text("authored reconciliation\n")
    summary_path.write_text(summary.replace("[Design]", "[Accepted intent]"))
    assert dstack_feature.cmd_feature_scaffold_design(args) == 0
    assert "[Authored catalog title](feature/index.md)" in (worktree / "docs/src/features/index.md").read_text()
    assert "[Accepted intent](features/feature/design.md)" in summary_path.read_text()
    assert dstack_feature.cmd_feature_scaffold_reconciliation(args) == 0
    assert reconciliation.read_text() == "authored reconciliation\n"
    assert [item["created"] for item in output] == [True, False, False]


def test_claim_spec_uses_native_ready_claim(monkeypatch, tmp_path: Path) -> None:
    claimed = {"id": "specification-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:specification",
            claim=True,
            result=[claimed],
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    assert dstack_feature.cmd_feature_claim_spec(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output[0]["specification"] == claimed
    beads.assert_exhausted()


def test_claim_spec_releases_unexpected_native_claim(monkeypatch, tmp_path: Path) -> None:
    unexpected = {"id": "other-1", "status": "in_progress", "assignee": "worker"}
    released = {"id": "other-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:specification",
            claim=True,
            result=[unexpected],
        ),
        call(
            "update",
            "other-1",
            "--status",
            "open",
            "--assignee",
            "",
            result=released,
        ),
        call("show", "other-1", result=released),
    )
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="unexpected specification"):
        dstack_feature.cmd_feature_claim_spec(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_approved_design_digest_requires_clean_committed_conventional_worktree(git_repo: Path, monkeypatch) -> None:
    relative = "docs/src/features/feature/design.md"
    design = git_repo / relative
    design.parent.mkdir(parents=True)
    accepted = semantic_record("feature-design")
    design.write_text(accepted)
    subprocess.run(["git", "add", relative], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "docs: add design"], cwd=git_repo, check=True)
    current = view(design_path=relative)
    beads = ScriptedClient(git_repo)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", git_repo, "main"),
    )
    monkeypatch.setattr(
        dstack_feature,
        "conventional_worktree",
        lambda *args: git_repo,
    )

    assert dstack_feature.approved_design_digest(beads, current) == hashlib.sha256(design.read_bytes()).hexdigest()

    design.write_text("changed design\n")
    with pytest.raises(DstackError, match="worktree changes"):
        dstack_feature.approved_design_digest(beads, current)

    design.write_text(accepted)
    monkeypatch.setattr(
        dstack_feature,
        "conventional_worktree",
        lambda *args: git_repo.parent / "unexpected",
    )
    with pytest.raises(DstackError, match="conventional path"):
        dstack_feature.approved_design_digest(beads, current)


def test_approve_spec_persists_pending_before_native_authorization(monkeypatch, tmp_path: Path) -> None:
    calls = []
    state = {
        "feature-1": {"id": "feature-1", "status": "open", "metadata": {}},
        "specification-1": {"id": "specification-1", "status": "open"},
        "approval-1": {"id": "approval-1", "status": "open"},
        "gate-1": {"id": "gate-1", "status": "open"},
    }
    beads = ScriptedClient(tmp_path)

    def show(issue_id):
        return dict(state[issue_id])

    def update(issue_id, *args):
        calls.append(("update", issue_id, *args))
        if "--set-metadata" in args:
            value = args[args.index("--set-metadata") + 1]
            key, data = value.split("=", 1)
            state[issue_id].setdefault("metadata", {})[key] = data
        elif "--unset-metadata" in args:
            state[issue_id]["metadata"].pop(args[-1], None)
        else:
            state[issue_id]["status"] = "in_progress"
        return dict(state[issue_id])

    def close(issue_id, reason):
        calls.append(("close", issue_id, reason))
        state[issue_id]["status"] = "closed"
        return dict(state[issue_id])

    def resolve_gate(issue_id, reason):
        calls.append(("resolve_gate", issue_id, reason))
        state[issue_id]["status"] = "closed"
        return dict(state[issue_id])

    beads.show = show
    beads.update = update
    beads.close = close
    beads.resolve_gate = resolve_gate
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(dstack_feature, "approved_design_digest", lambda *args: "accepted-digest")
    monkeypatch.setattr(
        dstack_feature,
        "human_gate_for_step",
        lambda *args, **kwargs: show("gate-1"),
    )

    assert (
        dstack_feature.cmd_feature_approve_spec(
            argparse.Namespace(root=tmp_path, selector="feature-1", summary_file=None)
        )
        == 0
    )
    pending = (
        "update",
        "feature-1",
        "--set-metadata",
        "dstack.pending_design_sha256=accepted-digest",
    )
    assert calls.index(pending) < calls.index(("close", "specification-1", "Specification approved"))
    assert calls[-1] == (
        "update",
        "feature-1",
        "--unset-metadata",
        "dstack.pending_design_sha256",
    )
    assert state["feature-1"]["metadata"] == {"dstack.approved_design_sha256": "accepted-digest"}
    assert all(state[item]["status"] == "closed" for item in ("specification-1", "gate-1", "approval-1"))


def test_approve_spec_resumes_closed_native_state_with_matching_pending_digest(monkeypatch, tmp_path: Path) -> None:
    digest = "accepted-digest"
    state = {
        "feature-1": {
            "id": "feature-1",
            "status": "open",
            "metadata": {"dstack.pending_design_sha256": digest},
        },
        "specification-1": {"id": "specification-1", "status": "closed"},
        "approval-1": {"id": "approval-1", "status": "closed"},
        "gate-1": {"id": "gate-1", "status": "closed"},
    }
    beads = ScriptedClient(tmp_path)
    beads.show = lambda issue_id: dict(state[issue_id])

    def update(issue_id, *args):
        if args[0] == "--set-metadata":
            key, value = args[1].split("=", 1)
            state[issue_id]["metadata"][key] = value
        else:
            state[issue_id]["metadata"].pop(args[1], None)
        return dict(state[issue_id])

    beads.update = update
    close_calls: list[str] = []

    def close(issue_id: str, reason: str) -> dict:
        del reason
        close_calls.append(issue_id)
        return dict(state[issue_id])

    beads.close = close
    beads.resolve_gate = lambda *args: pytest.fail("closed gate was resolved twice")
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(dstack_feature, "approved_design_digest", lambda *args: digest)
    monkeypatch.setattr(
        dstack_feature,
        "human_gate_for_step",
        lambda *args, **kwargs: dict(state["gate-1"]),
    )

    assert (
        dstack_feature.cmd_feature_approve_spec(
            argparse.Namespace(root=tmp_path, selector="feature-1", summary_file=None)
        )
        == 0
    )
    assert state["feature-1"]["metadata"] == {"dstack.approved_design_sha256": digest}
    assert close_calls == ["specification-1", "approval-1"]


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"dstack.pending_design_sha256": "design-a"}, "changed after approval began"),
        ({}, "lacks pending or approved content identity"),
    ],
)
def test_approve_spec_rejects_changed_or_unidentified_interrupted_approval(
    monkeypatch, tmp_path: Path, metadata: dict[str, str], message: str
) -> None:
    state = {
        "feature-1": {"id": "feature-1", "status": "open", "metadata": metadata},
        "specification-1": {"id": "specification-1", "status": "closed"},
        "approval-1": {"id": "approval-1", "status": "closed"},
        "gate-1": {"id": "gate-1", "status": "closed"},
    }
    beads = ScriptedClient(tmp_path)
    beads.show = lambda issue_id: dict(state[issue_id])
    beads.update = lambda *args: pytest.fail("unsafe approval mutated metadata")
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(dstack_feature, "approved_design_digest", lambda *args: "design-b")
    monkeypatch.setattr(
        dstack_feature,
        "human_gate_for_step",
        lambda *args, **kwargs: dict(state["gate-1"]),
    )

    with pytest.raises(DstackError, match=message):
        dstack_feature.cmd_feature_approve_spec(
            argparse.Namespace(root=tmp_path, selector="feature-1", summary_file=None)
        )


def test_reauthorize_invalidates_digest_before_reopening_native_boundary(monkeypatch, tmp_path: Path) -> None:
    state = {
        "feature-1": {
            "id": "feature-1",
            "status": "open",
            "metadata": {
                "dstack.approved_design_sha256": "digest",
                "dstack.pending_design_sha256": "digest",
            },
        },
        "specification-1": {"id": "specification-1", "status": "closed"},
        "approval-1": {"id": "approval-1", "status": "closed"},
        "gate-1": {
            "id": "gate-1",
            "status": "closed",
            "dependencies": [],
        },
        "implementation-1": {"id": "implementation-1", "status": "closed"},
        "closeout-1": {"id": "closeout-1", "status": "open"},
    }
    mutations = []
    beads = ScriptedClient(tmp_path)
    beads.show = lambda issue_id: dict(state[issue_id])

    def update(issue_id, *args):
        mutations.append(("update", issue_id, *args))
        if args[0] == "--unset-metadata":
            state[issue_id]["metadata"].pop(args[1], None)
        return dict(state[issue_id])

    def reopen(issue_id, reason):
        mutations.append(("reopen", issue_id, reason))
        state[issue_id]["status"] = "open"
        return dict(state[issue_id])

    beads.update = update
    beads.reopen = reopen
    beads.children = lambda parent: [{"id": "task-1", "status": "open"}]
    beads.ready_children = lambda *args, **kwargs: []
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "human_gate_for_step",
        lambda *args, **kwargs: dict(state["gate-1"]),
    )
    output = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)

    assert (
        dstack_feature.cmd_feature_reauthorize(
            argparse.Namespace(root=tmp_path, selector="feature-1", reason="Add scope")
        )
        == 0
    )
    assert mutations[:2] == [
        (
            "update",
            "feature-1",
            "--unset-metadata",
            "dstack.approved_design_sha256",
        ),
        (
            "update",
            "feature-1",
            "--unset-metadata",
            "dstack.pending_design_sha256",
        ),
    ]
    assert all(
        state[issue_id]["status"] == "open"
        for issue_id in (
            "specification-1",
            "approval-1",
            "gate-1",
            "implementation-1",
        )
    )
    assert state["feature-1"]["metadata"] == {}
    assert output[0]["status"] == "ok"


def test_approved_context_requires_closed_native_authorization(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(
        monkeypatch,
        dstack_feature,
        beads,
        view(native_approved=False),
    )

    with pytest.raises(DstackError, match="native approval state"):
        dstack_feature.approved_feature_context(beads, "feature-1")


def test_approved_context_does_not_gate_native_work_on_formula_version_drift(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    current = view()
    current["root"]["metadata"] = {
        "dstack.approved_design_sha256": "digest",
        "dstack.created_formula_version": 8,
        "dstack.formula_version": 8,
    }
    patch_command(monkeypatch, dstack_feature, beads, current)
    monkeypatch.setattr(
        dstack_feature,
        "feature_formula_contract_state",
        lambda context: {
            "formula": "dstack-feature",
            "created_version": 8,
            "audited_version": 8,
            "current_version": 9,
        },
    )

    observed = dstack_feature.approved_feature_context(beads, "feature-1")

    assert observed["root"]["id"] == "feature-1"
    beads.assert_exhausted()


def test_claim_next_uses_native_ready_result(monkeypatch, tmp_path: Path) -> None:
    ready = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "open",
        "labels": ["dstack:work:implementation"],
    }
    task = {**ready, "status": "claimed", "owner": "worker"}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=[task],
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", task=None)
    assert dstack_feature.cmd_feature_claim_next(args) == 0
    assert output == [{"status": "ok", "task": task, "feature": "feature-1"}]
    beads.assert_exhausted()


def test_claim_next_releases_every_unexpected_native_claim(monkeypatch, tmp_path: Path) -> None:
    unexpected = [
        {
            "id": f"task-{index}",
            "parent": "implementation-1",
            "status": "in_progress",
            "assignee": "worker",
            "labels": ["dstack:work:implementation"],
        }
        for index in (2, 3)
    ]
    calls = [
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=unexpected,
        ),
    ]
    for item in unexpected:
        released = {**item, "status": "open", "assignee": ""}
        calls.extend(
            [
                call(
                    "update",
                    item["id"],
                    "--status",
                    "open",
                    "--assignee",
                    "",
                    result=released,
                ),
                call("show", item["id"], result=released),
            ]
        )
    beads = ScriptedClient(tmp_path, *calls)
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="valid singleton"):
        dstack_feature.cmd_feature_claim_next(argparse.Namespace(root=tmp_path, selector="feature-1", task=None))
    beads.assert_exhausted()


def test_release_claim_reports_uncertain_ownership(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)

    def fail_release(*args):
        raise DstackError("storage unavailable")

    beads.update = fail_release
    with pytest.raises(DstackError, match="ownership is uncertain"):
        release_claim(beads, "task-1")


def test_claim_next_releases_claim_with_invalid_returned_scope(monkeypatch, tmp_path: Path) -> None:
    ready = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "open",
        "labels": ["dstack:work:implementation"],
    }
    claimed = {**ready, "status": "in_progress", "labels": ["other"]}
    released = {**claimed, "status": "open", "assignee": ""}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=[claimed],
        ),
        call(
            "update",
            "task-1",
            "--status",
            "open",
            "--assignee",
            "",
            result=released,
        ),
        call("show", "task-1", result=released),
    )
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="lacks required label"):
        dstack_feature.cmd_feature_claim_next(argparse.Namespace(root=tmp_path, selector="feature-1", task=None))
    beads.assert_exhausted()


def test_claim_next_releases_returned_foreign_parent(monkeypatch, tmp_path: Path) -> None:
    claimed = {
        "id": "task-1",
        "parent": "other-implementation",
        "status": "in_progress",
        "assignee": "worker",
        "labels": ["dstack:work:implementation"],
    }
    released = {**claimed, "status": "open", "assignee": ""}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=[claimed],
        ),
        call(
            "update",
            "task-1",
            "--status",
            "open",
            "--assignee",
            "",
            result=released,
        ),
        call("show", "task-1", result=released),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="not a direct child"):
        dstack_feature.cmd_feature_claim_next(argparse.Namespace(root=tmp_path, selector="feature-1", task=None))
    beads.assert_exhausted()


def test_claim_next_rejects_empty_native_claim(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=[],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="native ready claim returned no task"):
        dstack_feature.cmd_feature_claim_next(argparse.Namespace(root=tmp_path, selector="feature-1", task=None))
    beads.assert_exhausted()


def test_claim_next_releases_explicit_mismatched_native_claim(monkeypatch, tmp_path: Path) -> None:
    requested = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "open",
        "labels": ["dstack:work:implementation"],
    }
    claimed = {
        "id": "task-2",
        "parent": "implementation-1",
        "status": "in_progress",
        "assignee": "worker",
        "labels": ["dstack:work:implementation"],
    }
    released = {**claimed, "status": "open", "assignee": ""}
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=requested),
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            result=[requested],
        ),
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=[claimed],
        ),
        call(
            "update",
            "task-2",
            "--status",
            "open",
            "--assignee",
            "",
            result=released,
        ),
        call("show", "task-2", result=released),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="requested singleton task-1"):
        dstack_feature.cmd_feature_claim_next(argparse.Namespace(root=tmp_path, selector="feature-1", task="task-1"))
    beads.assert_exhausted()


def test_claim_next_rejects_explicit_task_not_ready(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "task-1",
            result={
                "id": "task-1",
                "parent": "implementation-1",
                "status": "open",
                "labels": ["dstack:work:implementation"],
            },
        ),
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            result=[],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", task="task-1")
    with pytest.raises(DstackError, match="not currently ready"):
        dstack_feature.cmd_feature_claim_next(args)
    beads.assert_exhausted()


def test_claim_next_rejects_wrong_work_label_without_mutation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "task-1",
            result={
                "id": "task-1",
                "parent": "implementation-1",
                "status": "open",
                "labels": ["other"],
            },
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="lacks required label"):
        dstack_feature.cmd_feature_claim_next(argparse.Namespace(root=tmp_path, selector="feature-1", task="task-1"))
    beads.assert_exhausted()


@pytest.mark.parametrize("no_repository_change", [False, True])
def test_finish_task_rejects_untracked_worktree(monkeypatch, tmp_path: Path, no_repository_change: bool) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "untracked.py").write_text("DIRTY = True\n")
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    with pytest.raises(DstackError, match="worktree changes"):
        dstack_feature.cmd_feature_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                task="task-1",
                reason="no code change" if no_repository_change else None,
                summary_file=None,
                no_repository_change=no_repository_change,
            )
        )
    beads.assert_exhausted()


def test_finish_task_accepts_explicit_clean_no_change(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "in_progress",
        "labels": ["dstack:work:implementation"],
    }
    closed = {**task, "status": "closed"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call("update", "task-1", "--claim", result=task),
        call("show", "task-1", result=task),
        call(
            "close",
            "task-1",
            "no-repository-change: already satisfied",
            result=closed,
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_feature, "evidence_for_bead", lambda *args: [])
    monkeypatch.setattr(dstack_feature, "finish_feature_workstream", lambda *args, **kwargs: {})
    assert (
        dstack_feature.cmd_feature_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                task="task-1",
                reason="already satisfied",
                summary_file=None,
                no_repository_change=True,
            )
        )
        == 0
    )
    assert output[0]["evidence"] == []
    beads.assert_exhausted()


@pytest.mark.parametrize(
    ("reason", "evidence", "message"),
    [
        (None, [], "requires a non-empty"),
        ("already satisfied", [{"commit": "abc"}], "conflicts with reachable"),
    ],
)
def test_finish_task_rejects_invalid_no_change_evidence(
    monkeypatch, tmp_path: Path, reason, evidence, message: str
) -> None:
    task = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "in_progress",
        "labels": ["dstack:work:implementation"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call("update", "task-1", "--claim", result=task),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_feature, "evidence_for_bead", lambda *args: evidence)
    with pytest.raises(DstackError, match=message):
        dstack_feature.cmd_feature_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                task="task-1",
                reason=reason,
                summary_file=None,
                no_repository_change=True,
            )
        )
    beads.assert_exhausted()


def test_finish_task_rechecks_approval_before_close(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "in_progress",
        "labels": ["dstack:work:implementation"],
    }
    initial = view()
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call("update", "task-1", "--claim", result=task),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_feature, "evidence_for_bead", lambda *args: [])
    contexts = iter([initial, DstackError("feature approval has been revoked")])

    def approved_context(*args):
        observed = next(contexts)
        if isinstance(observed, Exception):
            raise observed
        return observed

    monkeypatch.setattr(dstack_feature, "approved_feature_context", approved_context)

    with pytest.raises(DstackError, match="revoked"):
        dstack_feature.cmd_feature_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                task="task-1",
                reason="already done",
                summary_file=None,
                no_repository_change=True,
            )
        )
    beads.assert_exhausted()


def test_finish_task_leaves_workstream_and_closeout_open(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "open",
        "labels": ["dstack:work:implementation"],
    }
    closed_task = {**task, "status": "closed"}
    claimed_task = {**task, "status": "in_progress"}
    client_requests = []
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            result=[task],
        ),
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=[claimed_task],
        ),
        call("show", "task-1", result=claimed_task),
        call("close", "task-1", "Implementation completed", result=closed_task),
        call(
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "open"},
        ),
        call("children", "implementation-1", result=[closed_task]),
        call(
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "open"},
        ),
        call(
            "show",
            "closeout-1",
            result={"id": "closeout-1", "status": "open"},
        ),
    )
    current = view()
    monkeypatch.setattr(
        dstack_feature,
        "client_for",
        lambda root: client_requests.append(root) or beads,
    )
    monkeypatch.setattr(dstack_feature, "feature_context", lambda client, selector: current)
    monkeypatch.setattr(
        dstack_feature,
        "feature_design_state",
        lambda client, context: {"design_approved": True},
    )
    monkeypatch.setattr(
        dstack_feature,
        "feature_authorization_state",
        lambda client, context: {"native_approved": True},
    )
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(
        dstack_feature,
        "evidence_for_bead",
        lambda *args: [{"commit": "abc", "subject": "change", "paths": ["file.py"]}],
    )
    output = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        task="task-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    assert dstack_feature.cmd_feature_finish_task(args) == 0
    assert client_requests == [tmp_path]
    assert output[0]["workstream"]["closed_now"] is False
    assert output[0]["workstream"]["workstream"]["status"] == "open"
    assert output[0]["workstream"]["closeout"]["status"] == "open"
    beads.assert_exhausted()


def test_finish_task_rejects_documentation_changes_before_closeout(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "in_progress",
        "labels": ["dstack:work:implementation"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call("update", "task-1", "--claim", result=task),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(
        dstack_feature,
        "evidence_for_bead",
        lambda *args: [{"commit": "abc", "paths": ["docs/src/features/feature/index.md"]}],
    )
    with pytest.raises(DstackError, match="final reconciliation"):
        dstack_feature.cmd_feature_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                task="task-1",
                reason=None,
                summary_file=None,
                no_repository_change=False,
            )
        )
    beads.assert_exhausted()


def test_finish_task_requires_git_evidence(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "task-1",
        "parent": "implementation-1",
        "status": "in_progress",
        "labels": ["dstack:work:implementation"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call("update", "task-1", "--claim", result=task),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_feature, "evidence_for_bead", lambda *args: [])
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        task="task-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    with pytest.raises(DstackError, match="no reachable commit"):
        dstack_feature.cmd_feature_finish_task(args)
    beads.assert_exhausted()


def test_finish_workstream_rechecks_approval_before_close(monkeypatch, tmp_path: Path) -> None:
    implementation = {"id": "implementation-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "implementation-1", result=implementation),
        call("children", "implementation-1", result=[]),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    contexts = iter([view(), DstackError("feature approval has been revoked")])

    def approved_context(*args):
        observed = next(contexts)
        if isinstance(observed, Exception):
            raise observed
        return observed

    monkeypatch.setattr(dstack_feature, "approved_feature_context", approved_context)

    with pytest.raises(DstackError, match="revoked"):
        dstack_feature.cmd_feature_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="feature-1", quiet=False)
        )
    beads.assert_exhausted()


def test_finish_workstream_closes_only_after_all_children(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    implementation = {"id": "implementation-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "implementation-1", result=implementation),
        call("children", "implementation-1", result=[]),
        call("children", "implementation-1", result=[]),
        call(
            "close",
            "implementation-1",
            "All implementation work completed",
            result={"id": "implementation-1", "status": "closed"},
        ),
        call(
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "closed"},
        ),
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", quiet=False)
    assert dstack_feature.cmd_feature_finish_workstream(args) == 0
    assert output[0]["closed_now"] is True
    beads.assert_exhausted()


def test_finish_workstream_requires_authorization(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(
        monkeypatch,
        dstack_feature,
        beads,
        view(native_approved=False),
    )
    with pytest.raises(DstackError, match="native approval"):
        dstack_feature.cmd_feature_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="feature-1", quiet=False)
        )
    beads.assert_exhausted()


def test_claim_closeout_keeps_closed_closeout_idempotent(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "closed"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    assert dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output[0]["closeout"] == closeout
    assert output[0]["already_closed"] is True
    beads.assert_exhausted()


def test_claim_closeout_delegates_readiness_to_beads(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="not ready according to Beads"):
        dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_claim_closeout_refuses_open_native_child_before_ready_claim(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call(
            "children",
            "implementation-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="native-child"):
        dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_claim_closeout_releases_raced_claim_when_new_child_appears(monkeypatch, tmp_path: Path) -> None:
    claimed = {"id": "closeout-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[claimed],
        ),
        call(
            "children",
            "implementation-1",
            result=[{"id": "raced-child", "status": "open"}],
        ),
        call(
            "update",
            "closeout-1",
            "--status",
            "open",
            "--assignee",
            "",
            result={"id": "closeout-1", "status": "open"},
        ),
        call(
            "show",
            "closeout-1",
            result={"id": "closeout-1", "status": "open"},
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="raced-child"):
        dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_claim_closeout_uses_native_atomic_ready_claim(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "open"}
    claimed = {"id": "closeout-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[claimed],
        ),
        call("children", "implementation-1", result=[]),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    assert dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output[0]["closeout"] == claimed
    beads.assert_exhausted()


def test_closeout_validation_rejects_missing_documentation_impact_target(monkeypatch, tmp_path: Path) -> None:
    from dstack import docs as dstack_docs

    worktree = tmp_path / "worktree"
    dstack_docs.create_foundation(worktree)
    design = worktree / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("# Design\n\n## Documentation impact\n\n[Missing](../../guides/missing.md)\n")
    design.with_name("index.md").write_text(semantic_record("feature-reconciliation"))
    dstack_feature.ensure_feature_navigation(worktree, slug="feature", title="Feature", reconciled=True)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_docs.shutil, "which", lambda name: "/usr/bin/true")

    with pytest.raises(DstackError, match="guides/missing.md"):
        dstack_feature.validate_feature_documentation(ScriptedClient(tmp_path), view())


def test_finish_closeout_requires_reconciliation_before_beads_mutation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "validate_feature_documentation",
        lambda client, context: (_ for _ in ()).throw(DstackError("feature reconciliation does not exist")),
    )
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        reason="Closeout completed",
        summary_file=None,
    )

    with pytest.raises(DstackError, match="reconciliation"):
        dstack_feature.cmd_feature_finish_closeout(args)

    assert output == []
    beads.assert_exhausted()


def test_finish_closeout_keeps_closed_closeout_idempotent(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "closed"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "status": "closed",
                "close_reason": "Delivered by fast-forward merge",
            },
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        reason="Closeout completed",
        summary_file=None,
    )
    assert dstack_feature.cmd_feature_finish_closeout(args) == 0
    assert output[0]["closeout"] == closeout
    beads.assert_exhausted()


def test_finish_closeout_refuses_when_beads_does_not_mark_it_ready(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        reason="Closeout completed",
        summary_file=None,
    )
    with pytest.raises(DstackError, match="not ready according to Beads"):
        dstack_feature.cmd_feature_finish_closeout(args)
    beads.assert_exhausted()


def test_finish_closeout_rechecks_approval_before_close(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[{"id": "closeout-1", "status": "in_progress"}],
        ),
        call("children", "implementation-1", result=[]),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    contexts = iter([view(), DstackError("feature approval has been revoked")])

    def approved_context(*args):
        observed = next(contexts)
        if isinstance(observed, Exception):
            raise observed
        return observed

    monkeypatch.setattr(dstack_feature, "approved_feature_context", approved_context)

    with pytest.raises(DstackError, match="revoked"):
        dstack_feature.cmd_feature_finish_closeout(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                reason="Closeout completed",
                summary_file=None,
            )
        )
    beads.assert_exhausted()


def test_finish_closeout_closes_once(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[{"id": "closeout-1", "status": "in_progress"}],
        ),
        call("children", "implementation-1", result=[]),
        call("children", "implementation-1", result=[]),
        call(
            "show",
            "closeout-1",
            result={
                "id": "closeout-1",
                "status": "in_progress",
                "parent": "feature-1",
                "labels": ["dstack:step:closeout"],
            },
        ),
        call(
            "close",
            "closeout-1",
            "Closeout completed",
            result={"id": "closeout-1", "status": "closed"},
        ),
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "status": "closed",
                "close_reason": "all steps complete",
            },
        ),
        call(
            "reopen",
            "feature-1",
            "Await delivery",
            result={"id": "feature-1", "status": "open"},
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        reason="Closeout completed",
        summary_file=None,
    )
    assert dstack_feature.cmd_feature_finish_closeout(args) == 0
    assert output[0]["feature"] == "feature-1"
    assert output[0]["closeout"]["status"] == "closed"
    beads.assert_exhausted()


def test_safe_design_file_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(DstackError, match="repository-relative"):
        dstack_feature.safe_design_file(tmp_path, "../outside.md")


def test_safe_design_file_rejects_symlinked_root_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(DstackError, match="symlink"):
        dstack_feature.safe_design_file(link / "worktree", "docs/design.md")


def test_closeout_validation_rejects_untouched_reconciliation_scaffold(monkeypatch, tmp_path: Path) -> None:
    from dstack import docs as dstack_docs
    from dstack.docs import RECONCILIATION_SCAFFOLD

    worktree = tmp_path / "worktree"
    dstack_docs.create_foundation(worktree)
    design = worktree / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("# Design\n")
    design.with_name("index.md").write_text(RECONCILIATION_SCAFFOLD.format(title="Feature"))
    dstack_feature.ensure_feature_navigation(worktree, slug="feature", title="Feature", reconciled=True)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)

    with pytest.raises(DstackError, match="untouched scaffold"):
        dstack_feature.validate_feature_documentation(ScriptedClient(tmp_path), view())


def test_finish_workstream_counts_unlabeled_native_children(monkeypatch, tmp_path: Path) -> None:
    implementation = {"id": "implementation-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "implementation-1", result=implementation),
        call(
            "children",
            "implementation-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
        call("show", "implementation-1", result=implementation),
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", quiet=False)
    assert dstack_feature.cmd_feature_finish_workstream(args) == 0
    assert output[0]["open_items"] == ["native-child"]
    assert output[0]["closed_now"] is False
    beads.assert_exhausted()


def test_finish_closeout_refuses_untracked_worktree_before_beads_mutation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "validate_feature_documentation",
        lambda client, context: (_ for _ in ()).throw(DstackError("worktree changes prevent closeout")),
    )

    with pytest.raises(DstackError, match="worktree changes"):
        dstack_feature.cmd_feature_finish_closeout(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                reason="Closeout completed",
                summary_file=None,
            )
        )
    beads.assert_exhausted()


@pytest.mark.parametrize("relative", ["docs/src/features/index.md", "docs/src/SUMMARY.md"])
def test_feature_navigation_rejects_symlinked_destination(tmp_path: Path, relative: str) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n")
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside)

    with pytest.raises(DstackError, match="must not traverse a symlink"):
        dstack_feature.ensure_feature_navigation(tmp_path, slug="feature", title="Feature")

    assert outside.read_text() == "outside\n"


def test_feature_navigation_rejects_symlinked_worktree_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    worktree = tmp_path / "worktree"
    worktree.symlink_to(outside, target_is_directory=True)

    with pytest.raises(DstackError, match="worktree must not be a symlink"):
        dstack_feature.ensure_feature_navigation(worktree, slug="feature", title="Feature")

    assert not (outside / "docs").exists()


def test_feature_plan_rejects_noncanonical_slug_before_beads(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        dstack_feature,
        "client_for",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Beads must not be opened")),
    )
    args = argparse.Namespace(
        root=tmp_path,
        selector=None,
        title="Feature",
        slug="Feature Name",
        body_file=None,
        acceptance="Observable outcome",
        priority=1,
        depends_on=[],
    )

    with pytest.raises(DstackError, match="feature slug must be canonical"):
        dstack_feature.cmd_feature_plan(args)


def test_feature_initialize_preserves_planned_slug(monkeypatch, tmp_path: Path) -> None:
    planned = {
        "id": "planned-1",
        "status": "open",
        "issue_type": "epic",
        "title": "Feature: Planned",
        "labels": ["dstack:feature-idea", "feature:planned"],
    }
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda *args: planned)
    monkeypatch.setattr(dstack_feature, "feature_context", lambda *args: {"current": False})

    with pytest.raises(DstackError, match="planned feature slug is immutable: planned"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=tmp_path,
                selector="planned-1",
                title=None,
                slug="different",
                base_branch="main",
                design_path=None,
            )
        )
    beads.assert_exhausted()


def test_feature_plan_rejects_duplicate_open_slug(monkeypatch, tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Durable intent\n")
    existing = {
        "id": "existing-1",
        "status": "open",
        "issue_type": "epic",
        "labels": ["dstack:feature-idea", "feature:duplicate"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[existing]),
    )
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)

    with pytest.raises(DstackError, match="open feature root already uses slug duplicate"):
        dstack_feature.cmd_feature_plan(
            argparse.Namespace(
                root=tmp_path,
                selector=None,
                title="Duplicate",
                slug="duplicate",
                body_file=body,
                acceptance="Observable outcome",
                priority=1,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_feature_initialize_rejects_duplicate_open_current_slug(monkeypatch, tmp_path: Path) -> None:
    planned = {
        "id": "planned-1",
        "status": "open",
        "issue_type": "epic",
        "title": "Feature",
        "labels": ["dstack:feature-idea", "feature:feature"],
    }
    existing = {
        "id": "existing-1",
        "status": "open",
        "issue_type": "epic",
        "labels": ["workflow:feature", "feature:feature"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[planned, existing]),
    )
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_feature, "resolve_feature", lambda *args: planned)
    monkeypatch.setattr(
        dstack_feature,
        "feature_context",
        lambda *args: {"root": planned, "current": False, "closed": False},
    )

    with pytest.raises(DstackError, match="open feature root already uses slug feature"):
        dstack_feature.cmd_feature_initialize(
            argparse.Namespace(
                root=tmp_path,
                selector="planned-1",
                title=None,
                slug=None,
                base_branch="main",
                design_path=None,
            )
        )
    beads.assert_exhausted()


def test_reconciliation_symlink_is_rejected_for_scaffold_and_validation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    design = tmp_path / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("# Design\n")
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n")
    design.with_name("index.md").symlink_to(outside)

    beads = ScriptedClient(tmp_path)
    current = view()
    monkeypatch.setattr(dstack_feature, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_feature, "feature_context", lambda *args: current)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "ensure_clean_worktree", lambda *args: None)

    with pytest.raises(DstackError, match="must not traverse a symlink"):
        dstack_feature.cmd_feature_scaffold_reconciliation(argparse.Namespace(root=tmp_path, selector="feature-1"))
    with pytest.raises(DstackError, match="must not traverse a symlink"):
        dstack_feature.validate_feature_documentation(beads, current)
    assert outside.read_text() == "outside\n"


def test_navigation_reconciliation_rejects_stale_content(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "docs/src"
    features = source / "features"
    features.mkdir(parents=True)
    index = features / "index.md"
    summary = source / "SUMMARY.md"
    index.write_text("# Feature Records\n")
    summary.write_text("# Summary\n\n- [Feature Records](features/index.md)\n")
    real_replace = dstack_feature.replace_text_if_unchanged
    changed = False

    def race(path: Path, *, expected: str | None, content: str, purpose: str) -> bool:
        nonlocal changed
        if path == index and not changed:
            changed = True
            path.write_text("# Concurrent edit\n")
        return real_replace(path, expected=expected, content=content, purpose=purpose)

    monkeypatch.setattr(dstack_feature, "replace_text_if_unchanged", race)
    with pytest.raises(DstackError, match="changed while dStack was reconciling"):
        dstack_feature.ensure_feature_navigation(
            tmp_path,
            slug="feature",
            title="Feature",
        )
    assert index.read_text() == "# Concurrent edit\n"


def test_atomic_text_replacement_rechecks_content_before_commit(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "SUMMARY.md"
    target.write_text("original\n")
    real_read_text = Path.read_text
    reads = 0

    def concurrent_read(path: Path, *args: object, **kwargs: object) -> str:
        nonlocal reads
        if path == target:
            reads += 1
            if reads == 2:
                path.write_text("concurrent\n")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", concurrent_read)
    with pytest.raises(DstackError, match="changed while dStack was reconciling"):
        dstack_feature.replace_text_if_unchanged(
            target,
            expected="original\n",
            content="replacement\n",
            purpose="mdBook summary",
        )
    assert real_read_text(target) == "concurrent\n"


class _CreateReconciliationClient:
    def __init__(self, *, committed: int) -> None:
        self.root = Path(".")
        self.committed = committed
        self.items: dict[str, dict] = {}

    def children(self, parent_id: str, **kwargs) -> list[dict]:
        del kwargs
        return [dict(item) for item in self.items.values() if item["parent"] == parent_id]

    def show(self, issue_id: str) -> dict:
        return dict(self.items[issue_id])

    def create(self, title: str, **kwargs) -> dict:
        for index in range(self.committed):
            issue_id = f"task-{index + 1}"
            self.items[issue_id] = {
                "id": issue_id,
                "title": title,
                "type": kwargs["issue_type_name"],
                "parent": kwargs["parent"],
                "labels": list(kwargs["labels"]),
                "dependencies": [{"type": "blocks", "depends_on_id": item} for item in kwargs["dependencies"]],
                "description": kwargs["description"],
                "acceptance_criteria": kwargs["acceptance"],
                "priority": kwargs["priority"],
                "status": "open",
            }
        raise DstackError("bd create timed out and may have changed state")


def test_create_child_reconciles_one_committed_timeout() -> None:
    client = _CreateReconciliationClient(committed=1)

    observed = create_child_reconciled(
        client,  # type: ignore[arg-type]
        "Implement outcome",
        parent_id="implementation-1",
        labels=["dstack:work:implementation"],
        dependencies=["approval-1"],
        description="Details",
        acceptance="Observable",
        priority=1,
    )

    assert observed["id"] == "task-1"


def test_create_child_retains_and_reports_multiple_committed_timeout_results() -> None:
    client = _CreateReconciliationClient(committed=2)

    with pytest.raises(DstackError, match="retained matching children.*task-1, task-2"):
        create_child_reconciled(
            client,  # type: ignore[arg-type]
            "Implement outcome",
            parent_id="implementation-1",
            labels=["dstack:work:implementation"],
            dependencies=["approval-1"],
            description="Details",
            acceptance="Observable",
            priority=1,
        )


class _IncomingDependentClient:
    def children(self, parent_id: str, **kwargs) -> list[dict]:
        del parent_id, kwargs
        return []

    def list(self, **kwargs) -> list[dict]:
        assert kwargs == {"all_statuses": True, "include_gates": True}
        return [{"id": "idea-1"}, {"id": "dependent-1"}]

    def show(self, issue_id: str) -> dict:
        if issue_id == "dependent-1":
            return {
                "id": issue_id,
                "status": "open",
                "dependencies": [{"type": "blocks", "depends_on_id": "idea-1"}],
            }
        return {"id": issue_id, "status": "open"}


def test_planned_feature_supersession_refuses_active_external_dependents() -> None:
    with pytest.raises(DstackError, match="active external dependents: dependent-1"):
        refuse_external_dependents(_IncomingDependentClient(), "idea-1")  # type: ignore[arg-type]
