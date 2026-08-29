from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from dstack import audit as dstack_audit
from dstack.commands import RECORD_SUBJECTS
from dstack.delivery import delivered_candidate_revision, immutable_candidate_revision
from dstack.core import DstackError, ancestry, current_head
from scripted import ScriptedClient, call


def record(kind: str) -> str:
    lines = ["# Record", ""]
    for subject in RECORD_SUBJECTS[kind]:
        lines.extend([f"## {subject}", "", f"Evidence for {subject}.", ""])
    return "\n".join(lines)


def root(status: str = "open") -> dict:
    return {
        "id": "feature-1",
        "title": "Feature: Audit",
        "description": "Durable intent",
        "acceptance_criteria": "Observable acceptance",
        "issue_type": "molecule",
        "status": status,
        "labels": ["workflow:feature", "feature:audit"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": "docs/src/features/audit/design.md",
            "dstack.approved_design_sha256": "approved",
        },
    }


def test_immutable_candidate_supports_pr_merge_ancestry(git_repo: Path) -> None:
    subprocess.run(["git", "checkout", "-qb", "feat/audit"], cwd=git_repo, check=True)
    change = git_repo / "feature.py"
    change.write_text("delivered = True\n")
    subprocess.run(["git", "add", "feature.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: deliver\n\nBeads: closeout-1"],
        cwd=git_repo,
        check=True,
    )
    candidate = current_head(git_repo)
    subprocess.run(["git", "checkout", "main"], cwd=git_repo, check=True)
    (git_repo / "target.txt").write_text("target changed\n")
    subprocess.run(["git", "add", "target.txt"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "chore: target change"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "merge", "--no-ff", "feat/audit", "-m", "Merge feature"],
        cwd=git_repo,
        check=True,
    )

    assert immutable_candidate_revision(git_repo, "main", "closeout-1") == candidate
    assert ancestry(git_repo, candidate, "main")


def test_delivered_candidate_uses_remote_target_when_local_is_stale(
    git_repo: Path,
) -> None:
    subprocess.run(["git", "checkout", "-qb", "feat/audit"], cwd=git_repo, check=True)
    (git_repo / "feature.py").write_text("delivered = True\n")
    subprocess.run(["git", "add", "feature.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: deliver\n\nBeads: closeout-1"],
        cwd=git_repo,
        check=True,
    )
    candidate = current_head(git_repo)
    subprocess.run(["git", "checkout", "main"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", candidate],
        cwd=git_repo,
        check=True,
    )

    assert delivered_candidate_revision(git_repo, "main", "closeout-1") == (
        "origin/main",
        candidate,
    )


def current_context(status: str = "open") -> dict:
    return {
        "root": root(status),
        "slug": "audit",
        "current": True,
        "closed": status == "closed",
        "base_branch": "main",
        "design_path": "docs/src/features/audit/design.md",
        "approved_design_sha256": "approved",
        "steps": {
            name: {
                "id": f"{name}-1",
                "title": name,
                "issue_type": "epic" if name == "implementation" else "task",
                "status": "closed",
                "labels": [f"dstack:step:{name}"],
            }
            for name in ("specification", "approval", "implementation", "closeout")
        },
    }


def patch_current(monkeypatch, context: dict, *, worktree: Path | None) -> None:
    monkeypatch.setattr(dstack_audit, "feature_context", lambda *args: context)
    monkeypatch.setattr(
        dstack_audit,
        "feature_design_state",
        lambda *args: {
            "current_design_sha256": "current",
            "head_design_sha256": "current",
            "design_state": "committed",
            "design_approved": False,
        },
    )
    monkeypatch.setattr(
        dstack_audit,
        "feature_authorization_state",
        lambda *args: {
            "authorization_states": {
                "specification": "closed",
                "human_gate": "closed",
                "approval": "closed",
            },
            "human_gate": {
                "id": "gate-1",
                "issue_type": "gate",
                "await_type": "human",
                "await_id": "approval",
                "status": "closed",
            },
            "native_approved": True,
        },
    )
    monkeypatch.setattr(dstack_audit, "worktree_for_branch", lambda *args: worktree)


def test_audit_command_does_not_initialize_beads(monkeypatch, git_repo: Path, tmp_path: Path) -> None:
    bd = tmp_path / "bd"
    bd.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = --version ]; then echo 'bd version 1.2.2 (6c124203e)'; exit 0; fi\n"
        'if [ "$1" = init ]; then mkdir -p .beads; exit 0; fi\n'
        "echo '[]'\n"
    )
    bd.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    with pytest.raises(dstack_audit.DstackError, match="Beads is not initialized"):
        dstack_audit.cmd_audit_feature(argparse.Namespace(root=git_repo, selector="feature-1", format="json"))

    assert not (git_repo / ".beads").exists()


def test_audit_command_uses_a_non_initializing_client(monkeypatch, tmp_path: Path) -> None:
    client = object()
    seen: dict[str, object] = {}

    def client_for(root: Path, *, initialize: bool = True) -> object:
        seen.update(root=root, initialize=initialize)
        return client

    monkeypatch.setattr(dstack_audit, "client_for", client_for)
    monkeypatch.setattr(dstack_audit, "feature_audit", lambda observed, selector: {"selector": selector})

    assert dstack_audit.cmd_audit_feature(argparse.Namespace(root=tmp_path, selector="feature-1", format="json")) == 0
    assert seen == {"root": tmp_path, "initialize": False}


def test_planned_audit_is_deterministic_and_read_only(monkeypatch, git_repo: Path) -> None:
    planned = {**root(), "labels": ["dstack:feature-idea", "feature:audit"]}
    monkeypatch.setattr(
        dstack_audit,
        "feature_context",
        lambda *args: {
            "root": planned,
            "slug": "audit",
            "current": False,
            "closed": False,
        },
    )
    client = ScriptedClient(git_repo)
    before = (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True).stdout,
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
        sorted(path.relative_to(git_repo).as_posix() for path in git_repo.rglob("*") if path.is_file()),
    )
    first = dstack_audit.feature_audit(client, "audit")
    second = dstack_audit.feature_audit(client, "audit")
    after = (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True).stdout,
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
        sorted(path.relative_to(git_repo).as_posix() for path in git_repo.rglob("*") if path.is_file()),
    )
    assert first == second
    assert first["classification"] == "planned"
    assert first["git_evidence"]["status"] == "unavailable"
    assert before == after
    client.assert_exhausted()


def test_current_audit_reports_missing_and_pr_observations(monkeypatch, tmp_path: Path) -> None:
    context = current_context()
    task = {
        "id": "task-1",
        "title": "Remaining",
        "issue_type": "task",
        "status": "open",
        "parent": "implementation-1",
        "labels": ["dstack:work:implementation"],
        "dependencies": [{"depends_on_id": "approval-1", "type": "blocks"}],
    }
    client = ScriptedClient(
        tmp_path,
        call("children", "implementation-1", result=[task]),
    )
    patch_current(monkeypatch, context, worktree=None)
    monkeypatch.setattr(dstack_audit, "ref_exists", lambda *args: False)
    monkeypatch.setattr(
        dstack_audit,
        "pr_gate_state",
        lambda *args: {
            "all": [
                {
                    "id": "pr-gate",
                    "issue_type": "gate",
                    "await_type": "gh:pr",
                    "await_id": "41",
                    "status": "open",
                }
            ],
            "active": [],
        },
    )

    payload = dstack_audit.feature_audit(client, "audit")
    assert payload["classification"] == "current"
    assert payload["design"]["approved"] is False
    assert payload["missing_observations"] == ["worktree"]
    assert payload["work"]["remaining_or_deferred"][0]["id"] == "task-1"
    assert payload["delivery"]["pr_gates"][0]["await"] == "41"
    assert "ready" not in json.dumps(payload).casefold()
    client.assert_exhausted()


def test_closed_audit_never_falls_back_to_live_worktree_docs(monkeypatch, tmp_path: Path) -> None:
    context = current_context("closed")
    design = tmp_path / context["design_path"]
    design.parent.mkdir(parents=True)
    design.write_text(record("feature-design"))
    reconciliation = design.with_name("index.md")
    reconciliation.write_text(
        record("feature-reconciliation").replace(
            "Evidence for Delivered capability.",
            "Delivered. [Architecture](../../architecture/index.md)",
        )
    )
    architecture = tmp_path / "docs/src/architecture/index.md"
    architecture.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text("# Architecture\n")
    client = ScriptedClient(tmp_path, call("children", "implementation-1", result=[]))
    patch_current(monkeypatch, context, worktree=tmp_path)
    monkeypatch.setattr(
        dstack_audit,
        "delivered_feature_evidence_audit",
        lambda *args: {
            "feature": "feature-1",
            "status": "issues",
            "range": "main..feat/audit",
            "missing": ["task-1"],
            "mapping": {},
        },
    )
    monkeypatch.setattr(dstack_audit, "ref_exists", lambda *args: True)
    monkeypatch.setattr(dstack_audit, "ancestry", lambda *args: True)
    monkeypatch.setattr(
        dstack_audit,
        "pr_gate_state",
        lambda *args: {"all": [], "active": []},
    )

    payload = dstack_audit.feature_audit(client, "audit")
    assert payload["classification"] == "delivered"
    assert payload["git_evidence"]["status"] == "issues"
    assert payload["documentation"]["design"] is None
    assert payload["documentation"]["reconciliation"] is None
    assert "documentation:immutable-source-unavailable" in payload["missing_observations"]
    assert payload["delivery"]["direct_merge_observed"] is True
    rendered = dstack_audit.render_markdown(payload)
    embedded = rendered.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    assert json.loads(embedded) == payload
    client.assert_exhausted()


def test_delivered_audit_recovers_footer_evidence_after_branch_cleanup(
    monkeypatch, git_repo: Path, tmp_path: Path
) -> None:
    unrelated = git_repo / "unrelated.py"
    unrelated.write_text("UNRELATED = True\n")
    subprocess.run(["git", "add", "unrelated.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: unrelated\n\nBeads: other-task"],
        cwd=git_repo,
        check=True,
    )
    worktree = tmp_path / "feature"
    subprocess.run(
        ["git", "worktree", "add", "-qb", "feat/audit", str(worktree)],
        cwd=git_repo,
        check=True,
    )
    design = worktree / "docs/src/features/audit/design.md"
    design.parent.mkdir(parents=True)
    design.write_text(record("feature-design"))
    architecture = worktree / "docs/src/architecture/index.md"
    architecture.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text("# Candidate architecture\n")
    subprocess.run(["git", "add", "docs"], cwd=worktree, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            "docs: specify audit\n\nBeads: specification-1",
        ],
        cwd=worktree,
        check=True,
    )
    implementation = worktree / "feature.py"
    implementation.write_text("DELIVERED = True\n")
    subprocess.run(["git", "add", "feature.py"], cwd=worktree, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: deliver audit\n\nBeads: task-1"],
        cwd=worktree,
        check=True,
    )
    design.with_name("index.md").write_text(
        record("feature-reconciliation").replace(
            "Evidence for Delivered capability.",
            "Delivered. [Architecture](../../architecture/index.md)",
        )
    )
    subprocess.run(["git", "add", "docs"], cwd=worktree, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "docs: reconcile audit\n\nBeads: closeout-1"],
        cwd=worktree,
        check=True,
    )
    subprocess.run(["git", "merge", "--ff-only", "feat/audit"], cwd=git_repo, check=True)
    subprocess.run(["git", "worktree", "remove", str(worktree)], cwd=git_repo, check=True)
    subprocess.run(["git", "branch", "-d", "feat/audit"], cwd=git_repo, check=True)
    # Advance the configured target, then put conflicting documentation on an
    # unrelated checkout. The audit must continue reading the closeout revision.
    (git_repo / "after-delivery.txt").write_text("target advanced\n")
    subprocess.run(["git", "add", "after-delivery.txt"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "chore: advance target\n\nBeads: later-task"],
        cwd=git_repo,
        check=True,
    )
    subprocess.run(["git", "checkout", "-qb", "unrelated-docs"], cwd=git_repo, check=True)
    (git_repo / "docs/src/features/audit/index.md").write_text("# conflicting current checkout\n")
    subprocess.run(["git", "add", "docs"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "docs: unrelated conflict"], cwd=git_repo, check=True)

    context = current_context("closed")
    task = {
        "id": "task-1",
        "title": "Delivered",
        "issue_type": "task",
        "status": "closed",
        "parent": "implementation-1",
        "labels": ["dstack:work:implementation"],
    }
    no_change = {
        **task,
        "id": "task-no-change",
        "close_reason": "no-repository-change: documentation only",
    }
    client = ScriptedClient(
        git_repo,
        call("children", "implementation-1", result=[task, no_change]),
    )
    patch_current(monkeypatch, context, worktree=None)
    monkeypatch.setattr(
        dstack_audit,
        "pr_gate_state",
        lambda *args: {"all": [], "active": []},
    )

    payload = dstack_audit.feature_audit(client, "audit")
    evidence = payload["git_evidence"]
    assert evidence["status"] == "ok"
    assert evidence["source"] == "delivered-target"
    assert evidence["search_ref"] == "main"
    assert evidence["candidate_revision"] == evidence["mapping"]["closeout-1"][0]["commit"]
    assert evidence["derivation"] == "latest reachable closeout Beads footer"
    assert evidence["target_ref"] == "main"
    assert evidence["feature_branch_present"] is False
    assert set(evidence["mapping"]) == {
        "specification-1",
        "task-1",
        "closeout-1",
    }
    assert evidence["no_repository_change"] == ["task-no-change"]
    assert "other-task" not in evidence["mapping"]
    assert "later-task" not in evidence["mapping"]
    assert payload["documentation"]["source"] == evidence["candidate_revision"]
    assert payload["documentation"]["reconciliation"]["status"] == "valid"
    assert payload["documentation"]["linked_records"]["docs/src/architecture/index.md"]["status"] == "valid"
    assert "worktree" not in payload["missing_observations"]
    client.assert_exhausted()


def test_audit_reports_malformed_record(monkeypatch, tmp_path: Path) -> None:
    context = current_context()
    design = tmp_path / context["design_path"]
    design.parent.mkdir(parents=True)
    design.write_text("# Minimal\n")
    client = ScriptedClient(tmp_path, call("children", "implementation-1", result=[]))
    patch_current(monkeypatch, context, worktree=tmp_path)
    monkeypatch.setattr(
        dstack_audit,
        "feature_evidence_audit",
        lambda *args: {"feature": "feature-1", "status": "ok"},
    )
    monkeypatch.setattr(dstack_audit, "ref_exists", lambda *args: False)
    monkeypatch.setattr(
        dstack_audit,
        "pr_gate_state",
        lambda *args: {"all": [], "active": []},
    )
    payload = dstack_audit.feature_audit(client, "audit")
    assert payload["documentation"]["design"]["status"] == "malformed"
    assert "design:malformed" in payload["missing_observations"]
    assert payload["documentation"]["reconciliation"]["status"] == "missing"


def test_live_audit_rejects_symlinked_feature_document(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")
    design = tmp_path / "docs/src/features/audit/design.md"
    design.parent.mkdir(parents=True)
    design.symlink_to(outside)

    with pytest.raises(DstackError, match="must not traverse a symlink"):
        dstack_audit.record_fact(design, "feature-design", tmp_path)
