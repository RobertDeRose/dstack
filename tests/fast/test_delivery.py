from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_delivery
from dstack_commands import DstackError
from dstack_delivery import (
    docs_check,
    ensure_clean_candidate,
    immutable_candidate_revision,
    read_commit_message,
    require_candidate_head,
    validate_delivery,
    validate_pr_copy,
)
from dstacklib import CommandResult, current_head

from scripted import ScriptedClient, call


def payload(**overrides):
    value = {
        "tracked_runtime_beads": [],
        "paths": ["src/change.py"],
        "target_is_ancestor": True,
        "merge_commits": [],
        "docs": {"status": "ok"},
        "documentation": {"status": "ok"},
        "remote_target_head": "target",
        "remote_matches_local": True,
        "target_branch": "main",
    }
    value.update(overrides)
    return value


def test_delivery_refuses_new_open_child_after_terminal_closed(monkeypatch, tmp_path: Path) -> None:
    root = {"id": "feature-1", "labels": ["workflow:feature"]}
    view = {
        "root": root,
        "slug": "feature",
        "base_branch": "main",
        "steps": {
            "implementation": {"id": "implementation-1"},
            "closeout": {"id": "closeout-1", "status": "closed"},
        },
    }
    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "feature-1", result=root),
        call(
            "children",
            "implementation-1",
            result=[{"id": "late-child", "status": "open"}],
        ),
    )
    monkeypatch.setattr(dstack_delivery, "feature_delivery_context", lambda *args: view)

    with pytest.raises(DstackError, match="late-child"):
        dstack_delivery.delivery_view(beads, "feature-1")
    beads.assert_exhausted()


def test_commit_history_reuses_one_parsed_git_range(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[Path, str]] = []

    def records(root: Path, ref_range: str) -> list[dict]:
        calls.append((root, ref_range))
        return [{"commit": "head", "subject": "change", "paths": [], "footer_ids": ("task-1",)}]

    monkeypatch.setattr(dstack_delivery, "commit_records", records)
    history = dstack_delivery._CommitHistory()
    assert history.records(tmp_path, "main..feature") == history.records(tmp_path, "main..feature")
    assert history.mapping(tmp_path, "main..feature")["task-1"][0]["commit"] == "head"
    assert calls == [(tmp_path, "main..feature")]


def test_commit_message_adds_one_footer(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Details\n")
    assert read_commit_message("Implement behavior", body, "task-1") == (
        "Implement behavior\n\nDetails\n\nBeads: task-1\n"
    )


def test_commit_message_rejects_user_footer(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Beads: wrong\n")
    with pytest.raises(DstackError, match="must not contain"):
        read_commit_message("Subject", body, "task-1")


def test_commit_message_rejects_footer_in_subject_or_bead_id(tmp_path: Path) -> None:
    with pytest.raises(DstackError, match="footer"):
        read_commit_message("Beads: wrong", None, "task-1")
    with pytest.raises(DstackError, match="bead"):
        read_commit_message("Subject", None, "task-1\nBeads: task-2")


def test_commit_rejects_beads_type_changes_with_other_staged_changes(git_repo: Path, tmp_path: Path) -> None:
    config = git_repo / ".beads/config.yaml"
    config.parent.mkdir()
    config.write_text("stable: true\n")
    subprocess.run(["git", "add", str(config)], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "beads config"], cwd=git_repo, check=True)

    outside = tmp_path / "outside"
    outside.write_text("not repository state\n")
    config.unlink()
    config.symlink_to(outside)
    safe = git_repo / "safe.txt"
    safe.write_text("safe\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)

    with pytest.raises(DstackError, match="Beads repository/runtime"):
        commit_with_message(git_repo, "safe change\n\nBeads: task-1\n", amend=False)


@pytest.mark.parametrize(
    "bad",
    [
        {"tracked_runtime_beads": [".beads/dolt/foo"]},
        {"paths": [".beads/config.yaml"]},
        {"target_is_ancestor": False},
        {"merge_commits": ["merge"]},
        {"docs": {"status": "violations"}},
        {"documentation": {"status": "error"}},
    ],
)
def test_validate_delivery_rejects_safety_boundary(bad: dict) -> None:
    with pytest.raises(DstackError):
        validate_delivery(payload(**bad), require_remote=False)


def test_validate_delivery_rejects_post_closeout_candidate_head() -> None:
    with pytest.raises(DstackError, match="candidate HEAD"):
        validate_delivery(
            payload(candidate_head="later", candidate_revision="closeout"),
            require_remote=False,
        )


def test_validate_pr_copy_rejects_docs_title_for_code(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Summary")
    with pytest.raises(DstackError, match="docs-only"):
        validate_pr_copy(payload(), title="docs: update", body_file=body)


@pytest.mark.parametrize("status", ["blocked", "completed", "implemented"])
def test_docs_check_accepts_domain_status(git_repo: Path, status: str) -> None:
    docs = git_repo / "docs.md"
    docs.write_text(f"Status: {status}\n\nThis is durable product behavior.\n")
    subprocess.run(["git", "add", "docs.md"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "docs"], cwd=git_repo, check=True)
    result = docs_check(git_repo, "HEAD~1", "HEAD")
    assert result["status"] == "ok"


@pytest.mark.parametrize(
    "bookkeeping",
    [
        "dStack Status: blocked",
        "- dStack Workflow Status: review-active",
        "Beads task: task-1",
        "Gate ID: gate-1",
        "Candidate commit: abc123",
        "Reviewed commit: def456",
        "Delivery commit: fed789",
        "Feature branch: feat/example",
        "Worktree: /tmp/example",
        "Next command: /plan-feature example",
        "Next command: /implement-feature example",
    ],
)
def test_docs_check_rejects_structured_dstack_bookkeeping(git_repo: Path, bookkeeping: str) -> None:
    docs = git_repo / "docs.md"
    docs.write_text(f"{bookkeeping}\n")
    subprocess.run(["git", "add", "docs.md"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "docs"], cwd=git_repo, check=True)
    result = docs_check(git_repo, "HEAD~1", "HEAD")
    assert result["status"] == "violations"


def test_git_commit_amend_and_evidence_commands_use_real_git(git_repo: Path, monkeypatch) -> None:
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)
    change = git_repo / "change.py"
    change.write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "change.py"], cwd=git_repo, check=True)
    assert (
        dstack_delivery.cmd_git_commit(
            argparse.Namespace(
                root=git_repo,
                bead="task-1",
                subject="feat: add value",
                body_file=None,
            )
        )
        == 0
    )
    message = subprocess.check_output(["git", "log", "-1", "--format=%B"], cwd=git_repo, text=True)
    assert message.count("Beads: task-1") == 1

    assert (
        dstack_delivery.cmd_git_amend(
            argparse.Namespace(
                root=git_repo,
                bead="task-1",
                subject="feat: revise value",
                body_file=None,
            )
        )
        == 0
    )
    assert dstack_delivery.cmd_evidence_commits(argparse.Namespace(root=git_repo, bead="task-1", ref="HEAD")) == 0
    assert outputs[-1]["commits"][0]["subject"] == "feat: revise value"


def test_immutable_candidate_requires_unique_closeout_footer(git_repo: Path) -> None:
    change = git_repo / "feature.py"
    change.write_text("delivered = True\n")
    subprocess.run(["git", "add", "feature.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: deliver\n\nBeads: closeout-1"],
        cwd=git_repo,
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert immutable_candidate_revision(git_repo, "main", "closeout-1") == candidate
    assert require_candidate_head(git_repo, "main", "closeout-1", candidate) == candidate

    later = git_repo / "later.py"
    later.write_text("post_closeout = True\n")
    subprocess.run(["git", "add", "later.py"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "chore: later"], cwd=git_repo, check=True)
    with pytest.raises(DstackError, match="candidate HEAD"):
        require_candidate_head(git_repo, "main", "closeout-1", "HEAD")


def test_clean_candidate_recheck_rejects_post_inspection_commit(
    git_repo: Path,
) -> None:
    (git_repo / "closeout.py").write_text("closed = True\n")
    subprocess.run(["git", "add", "closeout.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "closeout\n\nBeads: closeout-1"],
        cwd=git_repo,
        check=True,
    )
    candidate = current_head(git_repo)
    (git_repo / "later.py").write_text("later = True\n")
    subprocess.run(["git", "add", "later.py"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "post-closeout"], cwd=git_repo, check=True)

    with pytest.raises(DstackError, match="candidate HEAD"):
        ensure_clean_candidate(
            git_repo,
            payload(
                candidate_worktree=str(git_repo),
                candidate_branch="main",
                candidate_head=candidate,
                candidate_revision=candidate,
                closeout_id="closeout-1",
            ),
        )


def test_clean_candidate_recheck_rejects_rewritten_closeout(
    git_repo: Path,
) -> None:
    path = git_repo / "closeout.py"
    path.write_text("version = 1\n")
    subprocess.run(["git", "add", "closeout.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "closeout\n\nBeads: closeout-1"],
        cwd=git_repo,
        check=True,
    )
    inspected = current_head(git_repo)
    path.write_text("version = 2\n")
    subprocess.run(["git", "add", "closeout.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "--amend", "-qm", "closeout\n\nBeads: closeout-1"],
        cwd=git_repo,
        check=True,
    )

    with pytest.raises(DstackError, match="candidate HEAD changed"):
        ensure_clean_candidate(
            git_repo,
            payload(
                candidate_worktree=str(git_repo),
                candidate_branch="main",
                candidate_head=inspected,
                candidate_revision=inspected,
                closeout_id="closeout-1",
            ),
        )


def test_immutable_candidate_reports_zero_and_duplicate_footers(git_repo: Path) -> None:
    with pytest.raises(DstackError, match="found 0"):
        immutable_candidate_revision(git_repo, "main", "missing-closeout")
    path = git_repo / "duplicate.py"
    path.write_text("x = 1\n")
    subprocess.run(["git", "add", "duplicate.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "one\n\nBeads: duplicate\nBeads: duplicate"],
        cwd=git_repo,
        check=True,
    )
    with pytest.raises(DstackError, match="found 2"):
        immutable_candidate_revision(git_repo, "main", "duplicate")


def test_delivery_context_keeps_unlabeled_tasks_for_compatibility(monkeypatch, tmp_path: Path) -> None:
    context = {
        "root": {"id": "feature-1"},
        "steps": {"implementation": {"id": "implementation-1"}},
    }
    task = {"id": "task-1", "issue_type": "task", "labels": []}
    beads = ScriptedClient(
        tmp_path,
        call(
            "children",
            "implementation-1",
            result=[task, {"id": "epic-1", "issue_type": "epic", "labels": []}],
        ),
    )
    monkeypatch.setattr(dstack_delivery, "feature_context", lambda client, selector: context.copy())
    monkeypatch.setattr(dstack_delivery, "feature_design_state", lambda client, view: {})
    monkeypatch.setattr(dstack_delivery, "feature_authorization_state", lambda client, view: {})
    observed = dstack_delivery.feature_delivery_context(beads, "feature-1")
    assert observed["work_items"] == [task]
    beads.assert_exhausted()


def test_alignment_delivery_context_excludes_structural_children(monkeypatch, tmp_path: Path) -> None:
    context = {
        "root": {"id": "alignment-1"},
        "steps": {"corrections": {"id": "corrections-1"}},
    }
    correction = {
        "id": "correction-1",
        "issue_type": "task",
        "labels": ["dstack:work:correction"],
    }
    beads = ScriptedClient(
        tmp_path,
        call(
            "children",
            "corrections-1",
            result=[
                correction,
                {"id": "structural-1", "issue_type": "epic", "status": "closed"},
            ],
        ),
    )
    monkeypatch.setattr(
        dstack_delivery, "alignment_context", lambda client, selector: context.copy()
    )
    observed = dstack_delivery.alignment_delivery_context(beads, "alignment-1")
    assert observed["corrections"] == [correction]
    beads.assert_exhausted()


def test_alignment_delivery_context_revalidates_authorization(monkeypatch, tmp_path: Path) -> None:
    context = {
        "root": {"id": "alignment-1", "status": "open"},
        "steps": {
            "analysis": {"id": "analysis-1"},
            "approval": {"id": "approval-1", "status": "closed"},
            "corrections": {"id": "corrections-1"},
            "landing": {"id": "landing-1", "status": "closed"},
        },
        "approved_alignment_plan_sha256": "approved",
        "pending_alignment_plan_sha256": None,
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "analysis-1", result={"id": "analysis-1"}),
        call("children", "corrections-1", result=[]),
    )
    authorized: list[dict] = []
    monkeypatch.setattr(dstack_delivery, "alignment_context", lambda client, selector: context.copy())
    monkeypatch.setattr(
        dstack_delivery,
        "canonical_description",
        lambda analysis: ({"schema": "dstack.alignment-plan/v2"}, "", ""),
    )
    monkeypatch.setattr(
        dstack_delivery,
        "require_alignment_authorized",
        lambda client, view: authorized.append(view) or {},
    )

    dstack_delivery.alignment_delivery_context(beads, "alignment-1")

    assert authorized[0]["root"] == context["root"]
    assert authorized[0]["corrections"] == []
    beads.assert_exhausted()


def test_evidence_audit_command_returns_controller_owned_result(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(
        dstack_delivery,
        "feature_delivery_context",
        lambda client, selector: {"root": {"id": "feature-1"}},
    )
    monkeypatch.setattr(
        dstack_delivery,
        "feature_evidence_audit",
        lambda client, view: {"status": "ok", "missing": []},
    )
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)
    assert dstack_delivery.cmd_evidence_audit_feature(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert outputs == [{"status": "ok", "missing": []}]


def test_delivery_inspect_and_preflight_validate_observed_candidate(
    monkeypatch, tmp_path: Path
) -> None:
    beads = ScriptedClient(tmp_path)
    candidate = payload(
        root={"id": "feature-1"},
        candidate_head="candidate",
        remote_candidate_head="candidate",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: candidate)
    commands = []
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda command, **kwargs: commands.append(tuple(command)) or CommandResult(0, "", ""),
    )
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)

    assert (
        dstack_delivery.cmd_delivery_inspect(argparse.Namespace(root=tmp_path, selector="feature-1", fetch=False)) == 0
    )
    assert (
        dstack_delivery.cmd_delivery_pr_preflight(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                title=None,
                body_file=None,
            )
        )
        == 0
    )
    assert commands == [("git", "fetch", "origin", "--prune")]
    assert outputs[-1]["candidate_head"] == "candidate"


def test_register_pr_creates_native_gate_only_for_pushed_candidate(monkeypatch, tmp_path: Path) -> None:
    gate = {"id": "gate-1", "await_type": "gh:pr"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result={"id": "feature-1", "dependencies": []}),
        call("gates", all_statuses=True, result=[]),
        call(
            "create_gate",
            gate_type="gh:pr",
            blocks="feature-1",
            await_id="42",
            reason="Await merged pull request",
            result=gate,
        ),
    )
    candidate = payload(
        root={"id": "feature-1"},
        candidate_head="candidate",
        remote_candidate_head="candidate",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: candidate)
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: CommandResult(0, "", ""),
    )
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)
    assert (
        dstack_delivery.cmd_delivery_register_pr(argparse.Namespace(root=tmp_path, selector="feature-1", pr_number=42))
        == 0
    )
    assert outputs[0]["gate"] == gate
    beads.assert_exhausted()


def test_register_pr_returns_the_same_unique_gate(monkeypatch, tmp_path: Path) -> None:
    gate = {
        "id": "gate-1",
        "status": "open",
        "await_type": "gh:pr",
        "await_id": "42",
        "dependencies": [],
    }
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "dependencies": [{"type": "blocks", "depends_on_id": "gate-1"}],
            },
        ),
        call("gates", all_statuses=True, result=[gate]),
        call("show", "gate-1", result=gate),
    )
    candidate = payload(
        root={"id": "feature-1"},
        candidate_head="candidate",
        remote_candidate_head="candidate",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: candidate)
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: CommandResult(0, "", ""),
    )
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)

    assert (
        dstack_delivery.cmd_delivery_register_pr(argparse.Namespace(root=tmp_path, selector="feature-1", pr_number=42))
        == 0
    )
    assert outputs[0]["gate"] == gate
    beads.assert_exhausted()


@pytest.mark.parametrize(
    "gates",
    [
        [
            {
                "id": "gate-1",
                "status": "open",
                "await_type": "gh:pr",
                "await_id": "41",
                "dependencies": [],
            }
        ],
        [
            {
                "id": "gate-1",
                "status": "open",
                "await_type": "gh:pr",
                "await_id": "42",
                "dependencies": [],
            },
            {
                "id": "gate-2",
                "status": "open",
                "await_type": "gh:pr",
                "await_id": "42",
                "dependencies": [],
            },
        ],
    ],
)
def test_register_pr_rejects_conflicting_or_duplicate_gates_without_mutation(
    monkeypatch, tmp_path: Path, gates: list[dict]
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "dependencies": [{"type": "blocks", "depends_on_id": gate["id"]} for gate in gates],
            },
        ),
        call("gates", all_statuses=True, result=gates),
        *(call("show", gate["id"], result=gate) for gate in gates),
    )
    candidate = payload(
        root={"id": "feature-1"},
        candidate_head="candidate",
        remote_candidate_head="candidate",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: candidate)
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: CommandResult(0, "", ""),
    )

    with pytest.raises(DstackError, match="PR gate"):
        dstack_delivery.cmd_delivery_register_pr(argparse.Namespace(root=tmp_path, selector="feature-1", pr_number=42))
    beads.assert_exhausted()


def test_replace_pr_gate_repairs_conflicting_closed_gate(monkeypatch, tmp_path: Path) -> None:
    old = {
        "id": "gate-old",
        "status": "closed",
        "await_type": "gh:pr",
        "await_id": "41",
        "dependencies": [],
    }
    target = {
        "id": "gate-target",
        "status": "open",
        "await_type": "gh:pr",
        "await_id": "42",
        "dependencies": [],
    }
    replaced = {
        **old,
        "dependencies": [{"type": "superseded-by", "depends_on_id": "gate-target"}],
    }
    root = {
        "id": "feature-1",
        "dependencies": [
            {"type": "blocks", "depends_on_id": "gate-old"},
            {"type": "blocks", "depends_on_id": "gate-target"},
        ],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result=root),
        call("gates", all_statuses=True, result=[old, target]),
        call("show", "gate-old", result=old),
        call("show", "gate-target", result=target),
        call(
            "reopen",
            "gate-old",
            "Replace PR gate: incorrect pull request",
            result={**old, "status": "open"},
        ),
        call("supersede", "gate-old", "gate-target", result=None),
        call("show", "feature-1", result=root),
        call("gates", all_statuses=True, result=[replaced, target]),
        call("show", "gate-old", result=replaced),
        call("show", "gate-target", result=target),
    )
    candidate = payload(
        root={"id": "feature-1"},
        candidate_head="candidate",
        remote_candidate_head="candidate",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: candidate)
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: CommandResult(0, "", ""),
    )
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)

    assert (
        dstack_delivery.cmd_delivery_replace_pr(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                pr_number=42,
                reason="incorrect pull request",
            )
        )
        == 0
    )
    assert outputs[0]["gate"] == target
    assert outputs[0]["replaced"] == ["gate-old"]
    beads.assert_exhausted()


def test_cancel_pr_gate_replaces_blocker_with_native_relation(monkeypatch, tmp_path: Path) -> None:
    gate = {
        "id": "gate-1",
        "status": "open",
        "await_type": "gh:pr",
        "await_id": "42",
        "waiter_id": "feature-1",
        "dependencies": [],
    }
    closed_gate = {**gate, "status": "closed", "close_reason": "direct delivery"}
    blocking_root = {
        "id": "feature-1",
        "dependencies": [{"type": "blocks", "depends_on_id": "gate-1"}],
    }
    related_root = {
        "id": "feature-1",
        "dependencies": [{"type": "relates-to", "depends_on_id": "gate-1"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result=blocking_root),
        call("gates", all_statuses=True, result=[gate]),
        call("show", "gate-1", result=gate),
        call("show", "feature-1", result=blocking_root),
        call("resolve_gate", "gate-1", "Cancel PR gate: direct delivery", result=closed_gate),
        call("remove_dependency", "feature-1", "gate-1", result=None),
        call("relate", "feature-1", "gate-1", result=None),
        call("show", "feature-1", result=related_root),
        call("gates", all_statuses=True, result=[closed_gate]),
        call("show", "gate-1", result=closed_gate),
        call("show", "feature-1", result=related_root),
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "_delivery_root", lambda *args: blocking_root)
    monkeypatch.setattr(
        dstack_delivery,
        "delivery_view",
        lambda *args: pytest.fail("cancellation must not inspect a delivery candidate"),
    )
    monkeypatch.setattr(
        dstack_delivery,
        "_git_snapshot",
        lambda *args: ("head", ""),
    )
    output = []
    monkeypatch.setattr(dstack_delivery, "emit", output.append)

    assert (
        dstack_delivery.cmd_delivery_cancel_pr_gate(
            argparse.Namespace(
                root=tmp_path,
                selector="feature-1",
                reason="direct delivery",
            )
        )
        == 0
    )
    assert output[0]["gate"] == closed_gate
    beads.assert_exhausted()


def test_cancel_pr_gate_rejects_unexpected_blocker_relation(monkeypatch, tmp_path: Path) -> None:
    gate = {
        "id": "gate-1",
        "status": "open",
        "await_type": "gh:pr",
        "await_id": "42",
        "waiter_id": "feature-1",
        "dependencies": [],
    }
    root = {
        "id": "feature-1",
        "dependencies": [{"type": "relates-to", "depends_on_id": "gate-1"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result=root),
        call("gates", all_statuses=True, result=[gate]),
        call("show", "gate-1", result=gate),
        call("show", "feature-1", result=root),
    )
    monkeypatch.setattr(dstack_delivery, "_git_snapshot", lambda *args: ("head", ""))
    with pytest.raises(DstackError, match="unexpected blocker/waiter"):
        dstack_delivery.cancel_pr_gate(beads, "feature-1", "abandon")
    beads.assert_exhausted()


def test_cancel_pr_gate_rejects_git_mutation_after_native_convergence(monkeypatch, tmp_path: Path) -> None:
    gate = {
        "id": "gate-1",
        "status": "open",
        "await_type": "gh:pr",
        "await_id": "42",
        "waiter_id": "feature-1",
        "dependencies": [],
    }
    closed_gate = {**gate, "status": "closed"}
    before_root = {
        "id": "feature-1",
        "dependencies": [{"type": "blocks", "depends_on_id": "gate-1"}],
    }
    empty_root = {"id": "feature-1", "dependencies": []}
    after_root = {
        "id": "feature-1",
        "dependencies": [{"type": "relates-to", "depends_on_id": "gate-1"}],
    }

    class Client:
        root = tmp_path

        def __init__(self) -> None:
            self.root_value = before_root
            self.calls = []

        def show(self, issue_id):
            self.calls.append(("show", issue_id))
            return self.root_value

        def resolve_gate(self, gate_id, reason):
            self.calls.append(("resolve_gate", gate_id, reason))
            return closed_gate

        def remove_dependency(self, root_id, gate_id):
            self.calls.append(("remove_dependency", root_id, gate_id))
            self.root_value = empty_root

        def relate(self, root_id, gate_id):
            self.calls.append(("relate", root_id, gate_id))
            self.root_value = after_root

    client = Client()
    states = iter(
        [
            {"all": [gate], "active": [gate]},
            {"all": [closed_gate], "active": []},
        ]
    )
    monkeypatch.setattr(dstack_delivery, "pr_gate_state", lambda *args: next(states))
    client.root_value = before_root
    snapshots = iter([("head", ""), ("other-head", "")])
    monkeypatch.setattr(dstack_delivery, "_git_snapshot", lambda *args: next(snapshots))
    with pytest.raises(DstackError, match="changed Git HEAD or status"):
        dstack_delivery.cancel_pr_gate(client, "feature-1", "abandon")
    assert ("resolve_gate", "gate-1", "Cancel PR gate: abandon") in client.calls
    assert ("remove_dependency", "feature-1", "gate-1") in client.calls
    assert ("relate", "feature-1", "gate-1") in client.calls


def test_cancel_pr_gate_relation_failure_is_retryable(monkeypatch, tmp_path: Path) -> None:
    gate = {
        "id": "gate-1",
        "status": "open",
        "await_type": "gh:pr",
        "waiter_id": "feature-1",
        "dependencies": [],
    }
    closed_gate = {**gate, "status": "closed"}
    blocking_root = {
        "id": "feature-1",
        "dependencies": [{"type": "blocks", "depends_on_id": "gate-1"}],
    }
    empty_root = {"id": "feature-1", "dependencies": []}
    related_root = {
        "id": "feature-1",
        "dependencies": [{"type": "relates-to", "depends_on_id": "gate-1"}],
    }

    class Client:
        root = tmp_path

        def __init__(self) -> None:
            self.root_value = blocking_root
            self.fail_relation = True

        def show(self, issue_id):
            return self.root_value

        def resolve_gate(self, gate_id, reason):
            return closed_gate

        def remove_dependency(self, root_id, gate_id):
            self.root_value = empty_root

        def relate(self, root_id, gate_id):
            if self.fail_relation:
                self.fail_relation = False
                raise DstackError("relation failed")
            self.root_value = related_root

    client = Client()
    states = iter(
        [
            {"all": [gate], "active": [gate]},
            {"all": [closed_gate], "active": []},
            {"all": [closed_gate], "active": []},
        ]
    )
    monkeypatch.setattr(dstack_delivery, "pr_gate_state", lambda *args: next(states))
    monkeypatch.setattr(dstack_delivery, "_git_snapshot", lambda *args: ("head", ""))
    with pytest.raises(DstackError, match="relation failed"):
        dstack_delivery.cancel_pr_gate(client, "feature-1", "abandon")
    assert client.root_value == empty_root

    assert dstack_delivery.cancel_pr_gate(client, "feature-1", "abandon") == closed_gate
    assert client.root_value == related_root


def test_delivery_merge_rejects_incomplete_gate_cancellation(monkeypatch, tmp_path: Path) -> None:
    gate = {
        "id": "gate-1",
        "status": "closed",
        "await_type": "gh:pr",
        "waiter_id": "feature-1",
    }
    root = {"id": "feature-1", "dependencies": []}
    beads = ScriptedClient(tmp_path, call("show", "feature-1", result=root))
    candidate = payload(root=root, candidate_worktree=str(tmp_path / "candidate"))
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: candidate)
    monkeypatch.setattr(
        dstack_delivery,
        "pr_gate_state",
        lambda *args: {"all": [gate], "active": []},
    )
    monkeypatch.setattr(
        dstack_delivery,
        "ensure_clean_worktree",
        lambda *args: pytest.fail("Git ran with incomplete cancellation"),
    )
    with pytest.raises(DstackError, match="incomplete PR gate cancellation"):
        dstack_delivery.cmd_delivery_merge(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


@pytest.mark.parametrize("status", ["open", "closed"])
def test_delivery_merge_refuses_active_pr_gate_before_git_mutation(monkeypatch, tmp_path: Path, status: str) -> None:
    gate = {"id": "gate-1", "status": status, "await_type": "gh:pr"}
    beads = ScriptedClient(tmp_path)
    candidate = payload(
        root={"id": "feature-1"},
        candidate_worktree=str(tmp_path / "candidate"),
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: candidate)
    monkeypatch.setattr(
        dstack_delivery,
        "pr_gate_state",
        lambda *args: {"all": [gate], "active": [gate]},
    )
    monkeypatch.setattr(
        dstack_delivery,
        "ensure_clean_worktree",
        lambda *args: pytest.fail("Git preflight ran with an active PR gate"),
    )

    with pytest.raises(DstackError, match="active PR gate"):
        dstack_delivery.cmd_delivery_merge(argparse.Namespace(root=tmp_path, selector="feature-1"))


def test_delivery_merge_rechecks_candidate_after_target_preparation(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "target"
    candidate = tmp_path / "candidate"
    target.mkdir()
    candidate.mkdir()
    beads = ScriptedClient(tmp_path)
    observed = payload(
        root={"id": "feature-1"},
        target_worktree=str(target),
        candidate_worktree=str(candidate),
        candidate_branch="feat/feature",
        candidate_head="closeout-head",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: observed)
    monkeypatch.setattr(
        dstack_delivery,
        "pr_gate_state",
        lambda *args: {"all": [], "active": []},
    )
    monkeypatch.setattr(dstack_delivery, "ensure_clean_worktree", lambda path: None)
    monkeypatch.setattr(
        dstack_delivery,
        "current_head",
        lambda root, *args: "post-closeout-head" if Path(root) == candidate else "target",
    )
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: pytest.fail("merge ran after candidate changed"),
    )
    with pytest.raises(DstackError, match="candidate HEAD changed"):
        dstack_delivery.cmd_delivery_merge(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_delivery_merge_checks_post_delivery_git_invariant(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "target"
    candidate = tmp_path / "candidate"
    target.mkdir()
    candidate.mkdir()
    beads = ScriptedClient(
        tmp_path,
        call(
            "close",
            "feature-1",
            "Delivered by fast-forward merge",
            result={"id": "feature-1", "status": "closed"},
        ),
    )
    observed = payload(
        root={"id": "feature-1"},
        target_worktree=str(target),
        candidate_worktree=str(candidate),
        candidate_branch="feat/feature",
        candidate_head="candidate-head",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: observed)
    monkeypatch.setattr(
        dstack_delivery,
        "pr_gate_state",
        lambda *args: {"all": [], "active": []},
    )
    monkeypatch.setattr(dstack_delivery, "ensure_clean_worktree", lambda path: None)
    heads = iter(["candidate-head", "target-head", "candidate-head", "candidate-head"])
    monkeypatch.setattr(dstack_delivery, "current_head", lambda *args: next(heads))
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: CommandResult(0, "", ""),
    )
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)
    assert dstack_delivery.cmd_delivery_merge(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert outputs[0]["delivered_head"] == "candidate-head"
    beads.assert_exhausted()


@pytest.mark.parametrize(
    ("after_head", "after_status"),
    [("mutated-head", ""), ("candidate-head", " M tracked.md")],
)
def test_delivery_merge_rejects_git_mutation_during_finalization(
    monkeypatch, tmp_path: Path, after_head: str, after_status: str
) -> None:
    target = tmp_path / "target"
    candidate = tmp_path / "candidate"
    target.mkdir()
    candidate.mkdir()
    beads = ScriptedClient(
        tmp_path,
        call(
            "close",
            "feature-1",
            "Delivered by fast-forward merge",
            result={"id": "feature-1", "status": "closed"},
        ),
        call(
            "reopen",
            "feature-1",
            "Post-delivery Git invariant violation",
            result={"id": "feature-1", "status": "open"},
        ),
    )
    observed = payload(
        root={"id": "feature-1"},
        target_worktree=str(target),
        candidate_worktree=str(candidate),
        candidate_branch="feat/feature",
        candidate_head="candidate-head",
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: observed)
    monkeypatch.setattr(
        dstack_delivery,
        "pr_gate_state",
        lambda *args: {"all": [], "active": []},
    )
    monkeypatch.setattr(dstack_delivery, "ensure_clean_worktree", lambda path: None)
    heads = iter(["candidate-head", "target-head", "candidate-head", after_head])
    monkeypatch.setattr(dstack_delivery, "current_head", lambda *args: next(heads))
    statuses = iter(["", after_status])

    def run(command, **kwargs):
        output = next(statuses) if command[1:3] == ["status", "--short"] else ""
        return CommandResult(0, output, "")

    monkeypatch.setattr(dstack_delivery, "run", run)
    with pytest.raises(DstackError, match="delivery completed but Beads finalization changed Git state"):
        dstack_delivery.cmd_delivery_merge(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


@pytest.mark.parametrize("root_status", ["open", "closed"])
def test_finalization_close_failure_reports_partial_delivery(monkeypatch, tmp_path: Path, root_status: str) -> None:
    beads = ScriptedClient(tmp_path)

    def fail_close(*args):
        raise DstackError("storage unavailable")

    beads.close = fail_close
    beads.show = lambda issue_id: {"id": issue_id, "status": root_status}
    monkeypatch.setattr(dstack_delivery, "current_head", lambda *args: "delivered")
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: CommandResult(0, "", ""),
    )

    with pytest.raises(DstackError) as failure:
        dstack_delivery.finalize_beads_without_git_mutation(
            beads,
            root_id="feature-1",
            worktree=tmp_path,
            reason="Delivered",
            expected_head="delivered",
            delivered_target_head="delivered",
            before_status="",
            previous_target_head="previous",
        )
    message = str(failure.value)
    for fact in (
        "delivery_completed=true",
        "previous_target_head=previous",
        "delivered_target_head=delivered",
        "observed_target_head=delivered",
        f"root_status={root_status}",
        "finalization_error=storage unavailable",
        "mutation_uncertain=true",
    ):
        assert fact in message


def test_finalize_pr_validates_candidate_before_gate_check(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(
        dstack_delivery,
        "delivery_view",
        lambda *args: payload(root={"id": "feature-1"}),
    )

    def reject_candidate(observed, *, require_remote):
        assert require_remote is False
        raise DstackError("invalid delivery candidate")

    monkeypatch.setattr(dstack_delivery, "validate_delivery", reject_candidate)
    with pytest.raises(DstackError, match="invalid delivery candidate"):
        dstack_delivery.cmd_delivery_finalize_pr(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_finalize_pr_rechecks_candidate_after_fetch_and_target_preparation(monkeypatch, tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    candidate.mkdir()
    target.mkdir()
    gate = {"id": "gate-1", "status": "closed", "await_type": "gh:pr"}
    root = {
        "id": "feature-1",
        "dependencies": [{"depends_on_id": "gate-1", "type": "blocks"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("gate_check", result=[gate]),
        call("show", "feature-1", result=root),
        call("gates", all_statuses=True, result=[gate]),
        call("show", "gate-1", result=gate),
    )
    observed = payload(
        root=root,
        target_branch="main",
        target_head="previous-target",
        candidate_head="closeout-head",
        candidate_worktree=str(candidate),
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: observed)
    monkeypatch.setattr(dstack_delivery, "worktree_for_branch", lambda *args: target)
    monkeypatch.setattr(dstack_delivery, "ensure_clean_worktree", lambda *args: None)
    heads = iter(["remote-delivered-head", "post-closeout-head"])
    monkeypatch.setattr(dstack_delivery, "current_head", lambda *args: next(heads))
    monkeypatch.setattr(
        dstack_delivery,
        "run",
        lambda *args, **kwargs: CommandResult(0, "", ""),
    )
    with pytest.raises(DstackError, match="candidate HEAD changed"):
        dstack_delivery.cmd_delivery_finalize_pr(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_finalize_pr_waits_without_closing_root(monkeypatch, tmp_path: Path) -> None:
    gate = {"id": "gate-1", "status": "open", "await_type": "gh:pr"}
    beads = ScriptedClient(
        tmp_path,
        call("gate_check", result=[gate]),
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "dependencies": [{"depends_on_id": "gate-1", "type": "blocks"}],
            },
        ),
        call("gates", all_statuses=True, result=[gate]),
        call("show", "gate-1", result=gate),
    )
    observed = payload(
        root={"id": "feature-1"},
        target_branch="main",
        candidate_head="candidate",
        remote_matches_local=False,
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: observed)
    outputs = []
    monkeypatch.setattr(dstack_delivery, "emit", outputs.append)
    assert dstack_delivery.cmd_delivery_finalize_pr(argparse.Namespace(root=tmp_path, selector="feature-1")) == 2
    assert outputs == [{"status": "waiting", "root": "feature-1", "gate": gate}]
    beads.assert_exhausted()


@pytest.mark.parametrize("dirty", ["candidate", "target"])
def test_finalize_pr_refuses_dirty_worktree_before_closing_root(monkeypatch, tmp_path: Path, dirty: str) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    candidate.mkdir()
    target.mkdir()
    gate = {"id": "gate-1", "status": "closed", "await_type": "gh:pr"}
    root = {
        "id": "feature-1",
        "dependencies": [{"depends_on_id": "gate-1", "type": "blocks"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("gate_check", result=[gate]),
        call("show", "feature-1", result=root),
        call("gates", all_statuses=True, result=[gate]),
        call("show", "gate-1", result=gate),
    )
    observed = payload(
        root=root,
        target_head="previous-target",
        candidate_head="candidate-head",
        candidate_worktree=str(candidate),
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: observed)
    monkeypatch.setattr(dstack_delivery, "ancestry", lambda *args: True)
    monkeypatch.setattr(
        dstack_delivery,
        "current_head",
        lambda root, *args: "candidate-head" if Path(root) == candidate else "remote-head",
    )
    monkeypatch.setattr(dstack_delivery, "worktree_for_branch", lambda *args: target)
    monkeypatch.setattr(dstack_delivery, "run", lambda *args, **kwargs: CommandResult(0, "", ""))

    def ensure_clean(path):
        if path == (candidate if dirty == "candidate" else target):
            raise DstackError(f"dirty {dirty}")

    monkeypatch.setattr(dstack_delivery, "ensure_clean_worktree", ensure_clean)

    with pytest.raises(DstackError, match=f"dirty {dirty}"):
        dstack_delivery.cmd_delivery_finalize_pr(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


@pytest.mark.parametrize(
    ("after_head", "after_status"),
    [("mutated-head", ""), ("target-head", " M tracked.md")],
)
def test_finalize_pr_rejects_git_mutation_during_finalization(
    monkeypatch, tmp_path: Path, after_head: str, after_status: str
) -> None:
    target = tmp_path / "target"
    candidate = tmp_path / "candidate"
    target.mkdir()
    candidate.mkdir()
    gate = {
        "id": "gate-1",
        "status": "closed",
        "await_type": "gh:pr",
    }
    root = {
        "id": "feature-1",
        "dependencies": [{"depends_on_id": "gate-1", "type": "blocks"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("gate_check", result=[gate]),
        call("show", "feature-1", result=root),
        call("gates", all_statuses=True, result=[gate]),
        call("show", "gate-1", result=gate),
        call(
            "close",
            "feature-1",
            "Delivered through merged pull request",
            result={"id": "feature-1", "status": "closed"},
        ),
        call(
            "reopen",
            "feature-1",
            "Post-delivery Git invariant violation",
            result={"id": "feature-1", "status": "open"},
        ),
    )
    observed = payload(
        root=root,
        target_branch="main",
        target_head="previous-target",
        candidate_head="candidate-head",
        candidate_worktree=str(candidate),
    )
    monkeypatch.setattr(dstack_delivery, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_delivery, "delivery_view", lambda *args: observed)
    monkeypatch.setattr(dstack_delivery, "ancestry", lambda *args: True)
    monkeypatch.setattr(dstack_delivery, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(
        dstack_delivery,
        "worktree_for_branch",
        lambda *args: target,
    )
    heads = iter(["remote-delivered-head", "candidate-head", "target-head", after_head])
    monkeypatch.setattr(dstack_delivery, "current_head", lambda *args: next(heads))
    statuses = iter(["", after_status])

    def run(command, **kwargs):
        output = next(statuses) if command[1:3] == ["status", "--short"] else ""
        return CommandResult(0, output, "")

    monkeypatch.setattr(dstack_delivery, "run", run)
    with pytest.raises(
        DstackError,
        match="delivery completed but Beads finalization changed Git state",
    ) as raised:
        dstack_delivery.cmd_delivery_finalize_pr(argparse.Namespace(root=tmp_path, selector="feature-1"))
    assert "previous_target_head=previous-target" in str(raised.value)
    assert "delivered_target_head=remote-delivered-head" in str(raised.value)
    beads.assert_exhausted()


def test_delivery_target_worktree_is_temporary_when_branch_is_not_checked_out(
    git_repo: Path,
) -> None:
    subprocess.run(["git", "branch", "release"], cwd=git_repo, check=True)
    assert dstack_delivery.worktree_for_branch(git_repo, "release") is None

    with dstack_delivery.delivery_target_worktree(
        git_repo, "release", None
    ) as target_worktree:
        assert target_worktree.is_dir()
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=target_worktree,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert branch == "release"
        assert dstack_delivery.worktree_for_branch(git_repo, "release") == target_worktree

    assert dstack_delivery.worktree_for_branch(git_repo, "release") is None


def test_temporary_delivery_worktree_preserves_primary_failure_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        if command[:3] == ["git", "worktree", "remove"]:
            return CommandResult(1, "", "cleanup failed")
        return CommandResult(0, "", "")

    monkeypatch.setattr(dstack_delivery, "run", fake_run)
    with pytest.raises(DstackError, match="primary delivery failure") as raised:
        with dstack_delivery.delivery_target_worktree(tmp_path, "main", None):
            raise DstackError("primary delivery failure")

    assert any(
        "failed to remove temporary delivery worktree" in note
        for note in getattr(raised.value, "__notes__", [])
    )
    assert calls[0][:3] == ("git", "worktree", "add")
    assert calls[-1][:3] == ("git", "worktree", "remove")
