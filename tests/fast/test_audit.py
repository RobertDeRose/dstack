from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))

import dstack_audit
from dstack_commands import RECORD_SUBJECTS
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

    with pytest.raises(dstack_audit.DstackError, match="returned 0 issues"):
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


def test_delivered_audit_joins_docs_evidence_and_direct_delivery(monkeypatch, tmp_path: Path) -> None:
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
        "feature_evidence_audit",
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
    assert payload["documentation"]["reconciliation"]["status"] == "valid"
    assert payload["documentation"]["reconciliation"]["validation_and_limitations"]
    assert payload["documentation"]["current_product_links"] == ["../../architecture/index.md"]
    assert payload["delivery"]["direct_merge_observed"] is True
    rendered = dstack_audit.render_markdown(payload)
    embedded = rendered.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    assert json.loads(embedded) == payload
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
