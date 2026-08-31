from __future__ import annotations

import argparse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
from dstack import alignment as dstack_alignment
from dstack import delivery as dstack_delivery
from dstack.commands import DstackError
from dstack.docs import RECORD_SUBJECTS
from dstack.core import CommandResult

from scripted import ScriptedClient, call


@pytest.fixture(autouse=True)
def _ignore_formula_version_stamps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dstack_alignment, "stamp_created_formula_version", lambda *args, **kwargs: 8)
    monkeypatch.setattr(dstack_alignment, "stamp_formula_version", lambda *args, **kwargs: 8)


def semantic_record(kind: str) -> str:
    lines = ["# Record", ""]
    for subject in RECORD_SUBJECTS[kind]:
        lines.extend([f"## {subject}", "", f"Evidence for {subject}.", ""])
    return "\n".join(lines)


def alignment_view(**overrides) -> dict:
    value = {
        "root": {"id": "alignment-1", "status": "open"},
        "slug": "alignment",
        "target_branch": "main",
        "scope": "repository",
        "human_gate": {"id": "gate-1", "status": "open"},
        "steps": {
            "analysis": {"id": "analysis-1", "status": "open"},
            "approval": {"id": "approval-1", "status": "open"},
            "corrections": {"id": "corrections-1", "status": "open"},
            "landing": {"id": "landing-1", "status": "open"},
        },
    }
    value.update(overrides)
    return value


def approved_alignment_view() -> dict:
    value = alignment_view()
    value["steps"]["approval"] = {"id": "approval-1", "status": "closed"}
    return value


def patch_command(monkeypatch, beads, current=None, *, plan_metadata=None):
    current = current or alignment_view()
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda client, selector: current)
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_branch_context",
        lambda *args: ("audit/alignment", beads.root, "main"),
    )
    monkeypatch.setattr(
        dstack_alignment,
        "canonical_description",
        lambda *args: (
            {"schema": "dstack.alignment-review/v1", "summary": "review", "corrections": []},
            "review",
            "0" * 64,
        ),
    )
    if plan_metadata is None:
        plan_metadata = ("0" * 64, "0" * 64) if current["steps"]["approval"].get("status") == "closed" else (None, None)
    monkeypatch.setattr(dstack_alignment, "root_plan_metadata", lambda *args: plan_metadata)
    if current["steps"]["approval"].get("status") == "closed":
        monkeypatch.setattr(dstack_alignment, "require_alignment_authorized", lambda *args: {})
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    return output


def test_inspect_emits_observed_alignment(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    output = patch_command(monkeypatch, beads)
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_view",
        lambda client, selector: alignment_view(),
    )
    monkeypatch.setattr(dstack_alignment, "require_alignment_authorized", lambda *args: {})
    assert dstack_alignment.cmd_alignment_inspect(argparse.Namespace(root=tmp_path, selector="alignment")) == 0
    assert output[0]["steps"]["corrections"]["id"] == "corrections-1"


def test_initialize_rejects_option_like_target_before_beads_mutation(monkeypatch, git_repo: Path) -> None:
    beads = ScriptedClient(git_repo)
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root, **kwargs: beads)
    with pytest.raises(DstackError, match="invalid target branch"):
        dstack_alignment.cmd_alignment_initialize(
            argparse.Namespace(
                root=git_repo,
                title="Alignment",
                slug=None,
                target_branch="--help",
                scope="repository",
            )
        )
    beads.assert_exhausted()


def test_initialize_rejects_noncanonical_slug_before_pour(monkeypatch, git_repo: Path) -> None:
    monkeypatch.setattr(
        dstack_alignment,
        "client_for",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("invalid slug must not initialize Beads")),
    )

    with pytest.raises(DstackError, match="canonical lowercase kebab-case"):
        dstack_alignment.cmd_alignment_initialize(
            argparse.Namespace(
                root=git_repo,
                title="Repository Alignment",
                slug="Repository-Alignment",
                target_branch="main",
                scope="repository",
            )
        )



def test_initialize_pours_formula_and_records_stable_identity(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dstack_alignment, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_alignment, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(
        dstack_alignment,
        "ensure_branch_worktree",
        lambda *args: ("audit/repository-alignment", tmp_path / "worktree", False, False),
    )
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[]),
        call(
            "pour",
            "dstack-project-alignment",
            {
                "audit_title": "Repository Alignment",
                "audit_slug": "repository-alignment",
                "scope": "whole repository",
            },
            result={"root_id": "alignment-1"},
        ),
        call(
            "update",
            "alignment-1",
            "--title",
            "Project alignment: Repository Alignment",
            "--add-label",
            "workflow:project-alignment",
            "--add-label",
            "audit:repository-alignment",
            "--set-metadata",
            "dstack.target_branch=main",
            "--set-metadata",
            "dstack.scope=whole repository",
            result={"id": "alignment-1"},
        ),
    )
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root, **kwargs: beads)
    views = iter(
        [
            DstackError("alignment selector resolved to 0 roots"),
            alignment_view(slug="repository-alignment"),
        ]
    )

    def observed(client, selector):
        value = next(views)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(dstack_alignment, "alignment_context", observed)
    monkeypatch.setattr(dstack_alignment, "branch_exists", lambda *args: True)
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path / "worktree")
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    args = argparse.Namespace(
        root=tmp_path,
        title="Repository Alignment",
        slug=None,
        target_branch="main",
        scope="whole repository",
    )
    assert dstack_alignment.cmd_alignment_initialize(args) == 0
    assert output[0]["worktree"].endswith("worktree")
    beads.assert_exhausted()


def test_add_correction_delegates_native_dependencies(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "analysis-1", result={"id": "analysis-1", "status": "open"}),
        call("show", "approval-1", result={"id": "approval-1", "status": "open"}),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
        call(
            "create",
            "Fix drift",
            parent="corrections-1",
            labels=["dstack:work:correction"],
            dependencies=["approval-1", "external-1"],
            description="details",
            acceptance="observable",
            priority=2,
            result={"id": "correction-1"},
        ),
    )
    output = patch_command(monkeypatch, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        title="Fix drift",
        description="details",
        description_file=None,
        acceptance="observable",
        acceptance_file=None,
        priority=2,
        depends_on=["external-1"],
    )
    assert dstack_alignment.cmd_alignment_add_correction(args) == 0
    assert output == [{"status": "ok", "correction": {"id": "correction-1"}}]
    beads.assert_exhausted()


@pytest.mark.parametrize("title", ["Reconcile documentation", "Document the API"])
def test_add_correction_rejects_documentation_or_reconciliation_work(monkeypatch, tmp_path: Path, title: str) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="sole final reconciliation"):
        dstack_alignment.cmd_alignment_add_correction(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                title=title,
                description="details",
                description_file=None,
                acceptance="observable",
                acceptance_file=None,
                priority=2,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_add_correction_rejects_closed_authorization_without_creation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "analysis-1", result={"id": "analysis-1", "status": "open"}),
        call("show", "approval-1", result={"id": "approval-1", "status": "closed"}),
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
    )
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="reauthorization"):
        dstack_alignment.cmd_alignment_add_correction(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                title="Late correction",
                description=None,
                description_file=None,
                acceptance="observable",
                acceptance_file=None,
                priority=2,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


@pytest.mark.parametrize(
    ("analysis_status", "plan_metadata"),
    [
        ("closed", (None, None)),
        ("open", ("a" * 64, None)),
        ("open", (None, "a" * 64)),
    ],
)
def test_add_correction_rejects_finalized_review_scope(
    monkeypatch,
    tmp_path: Path,
    analysis_status: str,
    plan_metadata: tuple[str | None, str | None],
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "analysis-1", result={"id": "analysis-1", "status": analysis_status}),
    )
    patch_command(monkeypatch, beads, plan_metadata=plan_metadata)
    with pytest.raises(DstackError, match="review has been finalized"):
        dstack_alignment.cmd_alignment_add_correction(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                title="Unreviewed correction",
                description="details",
                description_file=None,
                acceptance="observable",
                acceptance_file=None,
                priority=2,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_alignment_scaffold_only_allows_reconciliation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dstack_alignment, "emit", lambda value: None)
    with pytest.raises(DstackError, match="only reconciliation records"):
        dstack_alignment.cmd_alignment_scaffold_record(argparse.Namespace(kind="plan", path=tmp_path / "plan.md"))


def test_finish_review_uses_markdown_summary_and_native_corrections(monkeypatch, tmp_path: Path) -> None:
    summary = tmp_path / "review.md"
    summary.write_text("One finding and its accepted correction.\n", encoding="utf-8")
    state = {
        "alignment-1": {"id": "alignment-1", "status": "open", "metadata": {}},
        "analysis-1": {"id": "analysis-1", "status": "open", "description": "Analyze repository"},
    }
    beads = ScriptedClient(tmp_path)
    beads.children = lambda parent, **kwargs: []
    beads.show = lambda issue: dict(state[issue])

    def update(issue, *args):
        if "--description" in args:
            state[issue]["description"] = args[args.index("--description") + 1]
        if "--set-metadata" in args:
            key, value = args[args.index("--set-metadata") + 1].split("=", 1)
            state[issue].setdefault("metadata", {})[key] = value
        return dict(state[issue])

    beads.update = update
    beads.ready_children = lambda *args, **kwargs: [{"id": "analysis-1", "status": "in_progress"}]
    beads.close = lambda issue, reason: state[issue].update(status="closed") or dict(state[issue])
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda *args: alignment_view())
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)

    assert (
        dstack_alignment.cmd_alignment_finish_plan(
            argparse.Namespace(root=tmp_path, selector="alignment-1", summary_file=summary)
        )
        == 0
    )
    assert state["analysis-1"]["description"] == "One finding and its accepted correction."
    assert state["analysis-1"]["status"] == "closed"
    assert output[0]["correction_count"] == 0


def test_claim_next_delegates_readiness_and_claim(monkeypatch, tmp_path: Path) -> None:
    ready = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "open",
        "labels": ["dstack:work:correction"],
    }
    correction = {**ready, "status": "claimed"}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "corrections-1",
            label="dstack:work:correction",
            claim=True,
            result=[correction],
        ),
    )
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    args = argparse.Namespace(root=tmp_path, selector="alignment-1", task=None)
    assert dstack_alignment.cmd_alignment_claim_next(args) == 0
    assert output == [{"status": "ok", "correction": correction, "audit": "alignment-1"}]
    beads.assert_exhausted()


def test_claim_next_requires_closed_approval(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="approval milestone"):
        dstack_alignment.cmd_alignment_claim_next(argparse.Namespace(root=tmp_path, selector="alignment-1", task=None))
    beads.assert_exhausted()


def test_finish_task_rejects_dirty_worktree(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)

    def dirty(*args):
        raise DstackError("worktree changes")

    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", dirty)
    with pytest.raises(DstackError, match="worktree changes"):
        dstack_alignment.cmd_alignment_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                task="correction-1",
                reason=None,
                summary_file=None,
                no_repository_change=False,
            )
        )
    beads.assert_exhausted()


def test_finish_task_reuses_client_for_workstream_fan_in(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "open",
        "labels": ["dstack:work:correction"],
    }
    closed_task = {**task, "status": "closed"}
    claimed_task = {**task, "status": "in_progress"}
    client_requests = []
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call(
            "ready_children",
            "corrections-1",
            label="dstack:work:correction",
            result=[task],
        ),
        call(
            "ready_children",
            "corrections-1",
            label="dstack:work:correction",
            claim=True,
            result=[claimed_task],
        ),
        call("close", "correction-1", "Correction completed", result=closed_task),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
        call("children", "corrections-1", result=[closed_task]),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
    )
    current = approved_alignment_view()
    monkeypatch.setattr(
        dstack_alignment,
        "client_for",
        lambda root: client_requests.append(root) or beads,
    )
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda client, selector: current)
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_branch_context",
        lambda *args: ("audit/alignment", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(
        dstack_alignment,
        "evidence_for_bead",
        lambda *args: [{"commit": "abc", "subject": "change", "paths": ["file.py"]}],
    )
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        task="correction-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    assert dstack_alignment.cmd_alignment_finish_task(args) == 0
    assert client_requests == [tmp_path]
    assert output[0]["workstream"]["open_items"] == []
    beads.assert_exhausted()


def test_finish_task_rejects_documentation_changes_before_landing(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "in_progress",
        "labels": ["dstack:work:correction"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call("update", "correction-1", "--claim", result=task),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(
        dstack_alignment,
        "evidence_for_bead",
        lambda *args: [{"commit": "abc", "subject": "docs", "paths": ["docs/src/index.md"]}],
    )
    with pytest.raises(DstackError, match="final reconciliation"):
        dstack_alignment.cmd_alignment_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                task="correction-1",
                reason=None,
                summary_file=None,
                no_repository_change=False,
            )
        )
    beads.assert_exhausted()


def test_finish_task_requires_reachable_git_evidence(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "in_progress",
        "labels": ["dstack:work:correction"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call("update", "correction-1", "--claim", result=task),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "evidence_for_bead", lambda *args: [])
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        task="correction-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    with pytest.raises(DstackError, match="no commit"):
        dstack_alignment.cmd_alignment_finish_task(args)
    beads.assert_exhausted()


def test_finish_workstream_closes_after_native_children_are_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    beads = ScriptedClient(
        tmp_path,
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "close",
            "corrections-1",
            "All corrections completed",
            result={"id": "corrections-1", "status": "closed"},
        ),
        call("show", "corrections-1", result={"id": "corrections-1", "status": "closed"}),
    )
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    assert (
        dstack_alignment.cmd_alignment_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="alignment-1", quiet=False)
        )
        == 0
    )
    assert output[0]["open_items"] == []
    beads.assert_exhausted()


def test_finish_workstream_requires_authorization(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
    )
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="approval milestone"):
        dstack_alignment.cmd_alignment_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="alignment-1", quiet=False)
        )
    beads.assert_exhausted()


def test_claim_landing_delegates_readiness_to_beads(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "ready_children",
            "alignment-1",
            label="dstack:step:alignment-landing",
            claim=True,
            result=[],
        ),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    args = argparse.Namespace(root=tmp_path, selector="alignment-1")
    with pytest.raises(DstackError, match="not ready according to Beads"):
        dstack_alignment.cmd_alignment_claim_landing(args)
    beads.assert_exhausted()


def test_claim_landing_refuses_open_native_child_before_ready_claim(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call(
            "children",
            "corrections-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())

    with pytest.raises(DstackError, match="native-child"):
        dstack_alignment.cmd_alignment_claim_landing(argparse.Namespace(root=tmp_path, selector="alignment-1"))
    beads.assert_exhausted()


def test_claim_landing_uses_native_atomic_ready_claim(monkeypatch, tmp_path: Path) -> None:
    claimed = {"id": "landing-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "ready_children",
            "alignment-1",
            label="dstack:step:alignment-landing",
            claim=True,
            result=[claimed],
        ),
        call("children", "corrections-1", result=[]),
    )
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    args = argparse.Namespace(root=tmp_path, selector="alignment-1")
    assert dstack_alignment.cmd_alignment_claim_landing(args) == 0
    assert output[0]["landing"] == claimed
    beads.assert_exhausted()


def test_finish_landing_closes_once(monkeypatch, tmp_path: Path) -> None:
    summary = tmp_path / "reconciliation.md"
    summary.write_text(semantic_record("alignment-reconciliation"))
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "ready_children",
            "alignment-1",
            label="dstack:step:alignment-landing",
            claim=True,
            result=[{"id": "landing-1", "status": "in_progress"}],
        ),
        call("children", "corrections-1", result=[]),
        call(
            "add_comment",
            "landing-1",
            semantic_record("alignment-reconciliation").strip(),
        ),
        call(
            "close",
            "landing-1",
            "Alignment landing completed",
            result={"id": "landing-1", "status": "closed"},
        ),
        call(
            "show",
            "alignment-1",
            result={
                "id": "alignment-1",
                "status": "closed",
                "close_reason": "all steps complete",
            },
        ),
        call(
            "reopen",
            "alignment-1",
            "Await delivery",
            result={"id": "alignment-1", "status": "open"},
        ),
    )
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "validate_docs", lambda *args: {"status": "ok"})
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_delivery_context",
        lambda client, selector: {**alignment_view(), "corrections": []},
    )
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_evidence_audit",
        lambda client, view: {
            "status": "ok",
            "missing": [],
            "unexpected_footer_ids": [],
        },
    )
    monkeypatch.setattr(
        dstack_delivery,
        "docs_check",
        lambda *args: {"status": "ok", "violations": []},
    )
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        reason="Alignment landing completed",
        summary_file=summary,
    )
    assert dstack_alignment.cmd_alignment_finish_landing(args) == 0
    assert output[0]["audit"] == "alignment-1"
    assert output[0]["landing"]["status"] == "closed"
    beads.assert_exhausted()


def test_finish_alignment_workstream_counts_unlabeled_native_children(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
        call(
            "children",
            "corrections-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, beads)
    assert (
        dstack_alignment.cmd_alignment_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="alignment-1", quiet=False)
        )
        == 0
    )
    assert output[0]["open_items"] == ["native-child"]
    beads.assert_exhausted()


def test_initialize_rolls_back_poured_state_when_worktree_registration_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dstack_alignment, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_alignment, "validate_git_revision", lambda *args, **kwargs: "main")
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[]),
        call(
            "pour",
            "dstack-project-alignment",
            {
                "audit_title": "Repository Alignment",
                "audit_slug": "repository-alignment",
                "scope": "whole repository",
            },
            result={"root_id": "alignment-1"},
        ),
        call(
            "update",
            "alignment-1",
            "--title",
            "Project alignment: Repository Alignment",
            "--add-label",
            "workflow:project-alignment",
            "--add-label",
            "audit:repository-alignment",
            "--set-metadata",
            "dstack.target_branch=main",
            "--set-metadata",
            "dstack.scope=whole repository",
            result={"id": "alignment-1"},
        ),
    )
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_context",
        lambda *args: (_ for _ in ()).throw(DstackError("alignment selector resolved to 0 roots")),
    )
    monkeypatch.setattr(
        dstack_alignment,
        "ensure_branch_worktree",
        lambda *args: (_ for _ in ()).throw(DstackError("failed to register worktree")),
    )
    commands = []
    monkeypatch.setattr(
        dstack_alignment,
        "run",
        lambda command, **kwargs: commands.append(tuple(command)) or CommandResult(0, "", ""),
    )

    with pytest.raises(DstackError, match="failed to register worktree"):
        dstack_alignment.cmd_alignment_initialize(
            argparse.Namespace(
                root=tmp_path,
                title="Repository Alignment",
                slug=None,
                target_branch="main",
                scope="whole repository",
            )
        )

    assert commands == [("bd", "delete", "alignment-1", "--cascade", "--force")]
    beads.assert_exhausted()


def test_finish_landing_refuses_failed_evidence_audit_before_claim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary = tmp_path / "reconciliation.md"
    summary.write_text(semantic_record("alignment-reconciliation"))
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "validate_docs", lambda *args: {"status": "ok"})
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_delivery_context",
        lambda client, selector: {**alignment_view(), "corrections": []},
    )
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_evidence_audit",
        lambda client, view: {
            "status": "issues",
            "missing": ["correction-1"],
            "unexpected_footer_ids": [],
        },
    )

    with pytest.raises(DstackError, match="evidence audit failed"):
        dstack_alignment.cmd_alignment_finish_landing(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                reason="Alignment landing completed",
                summary_file=summary,
            )
        )
    beads.assert_exhausted()
