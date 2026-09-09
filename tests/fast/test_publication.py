from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from dstack.core import run
from dstack.policy import canonical_docs_message, canonical_task_message

if TYPE_CHECKING:
    from conftest import FeatureRepository


def stage(feature: FeatureRepository, path: str, content: str) -> None:
    target = feature.worktree / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    run(["git", "add", "-f", "--", path], cwd=feature.worktree)


def publication(feature: FeatureRepository) -> None:
    feature.invoke("docs", "export-design", "--bead", "root", "--scaffold")
    stage(
        feature,
        "docs/src/features/example/index.md",
        "# Example\n\n## Overview\n\nDeliver the accepted behavior.\n\n"
        "## User Impact\n\nUsers receive the reviewed implementation.\n\n"
        "## Implemented Design\n\n{{#include design.md}}\n",
    )
    run(["git", "add", "docs"], cwd=feature.worktree)


def test_implementation_cannot_commit_feature_publication(public_feature: FeatureRepository) -> None:
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Publish the accepted design.")
    publication(public_feature)
    before = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout
    rejected = public_feature.invoke("commit", "--bead", "task", expected=2)
    assert "publication belongs to the close step" in rejected["error"]
    assert run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout == before
    assert run(["git", "diff", "--cached", "--name-only"], cwd=public_feature.worktree).stdout


def test_feature_check_and_task_check_reject_publication_under_a_task_footer(public_feature: FeatureRepository) -> None:
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Publish the accepted design.")
    publication(public_feature)
    run(["git", "commit", "-F", "-"], cwd=public_feature.worktree, input_text=canonical_task_message(task, "example"))
    checked = public_feature.invoke("check", "task", "--bead", "task", expected=4)
    assert any("publication belongs to the close step" in error for error in checked["errors"])
    reused = public_feature.invoke("commit", "--bead", "task", expected=2)
    assert "publication belongs to the close step" in reused["error"]
    task["status"] = "closed"
    audited = public_feature.invoke("check", "feature", "--bead", "root", "--require-docs", expected=4)
    assert any("requires one canonical documentation commit" in error for error in audited["checks"]["errors"])
    assert audited["git"]["close_commit"] is None


@pytest.mark.parametrize("already_committed", [False, True])
def test_docs_commit_rejects_application_changes_before_creation_or_reuse(
    public_feature: FeatureRepository,
    already_committed: bool,
) -> None:
    publication(public_feature)
    stage(public_feature, "application.py", 'print("not documentation")\n')
    if already_committed:
        run(
            ["git", "commit", "-F", "-"],
            cwd=public_feature.worktree,
            input_text=canonical_docs_message(public_feature.data["issues"]["root"], "example", "audit"),
        )
    before = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout
    rejected = public_feature.invoke("docs", "commit", "--bead", "root", expected=2)
    assert "non-feature paths: application.py" in rejected["error"]
    assert run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout == before
    if already_committed:
        audited = public_feature.invoke("check", "feature", "--bead", "root", "--require-docs", expected=4)
        assert any("non-feature paths: application.py" in error for error in audited["checks"]["errors"])


@pytest.mark.parametrize("filename", ["runtime.txt", "runtime\tdata"])
def test_removed_beads_runtime_is_still_rejected_in_history(
    public_feature: FeatureRepository,
    filename: str,
) -> None:
    issues = public_feature.data["issues"]
    first = issues["task"]
    first["notes"] = "Implementation: Add a record."
    second = {**first, "id": "task2", "title": "Remove record", "notes": "Implementation: Remove the record."}
    issues["task2"] = second
    path = f".beads/{filename}"
    stage(public_feature, path, "runtime material must not enter history\n")
    run(["git", "commit", "-F", "-"], cwd=public_feature.worktree, input_text=canonical_task_message(first, "example"))
    run(["git", "rm", "--", path], cwd=public_feature.worktree)
    run(["git", "commit", "-F", "-"], cwd=public_feature.worktree, input_text=canonical_task_message(second, "example"))
    result = public_feature.invoke("check", "feature", "--bead", "root", expected=4)
    assert result["git"]["changed_path_count"] == 0
    assert sum(path in error for error in result["checks"]["errors"]) == 2
    first["status"] = "in_progress"
    checked = public_feature.invoke("check", "task", "--bead", "task", expected=4)
    assert any(path in error for error in checked["errors"])


def test_inherited_publication_needs_no_empty_close_commit(public_feature: FeatureRepository) -> None:
    publication(public_feature)
    created = public_feature.invoke("docs", "commit", "--bead", "root")
    run(["git", "reset", "--hard", created["commit"]], cwd=public_feature.repo)
    # An unrelated navigation change still belongs to its implementation task.
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Add handbook navigation.")
    summary = public_feature.worktree / "docs/src/SUMMARY.md"
    stage(public_feature, "docs/src/SUMMARY.md", summary.read_text(encoding="utf-8") + "\n- [Handbook](handbook.md)\n")
    stage(public_feature, "docs/src/handbook.md", "# Handbook\n\nCurrent usage.\n")
    public_feature.invoke("commit", "--bead", "task")
    task["status"] = "closed"
    before = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout
    reused = public_feature.invoke("docs", "commit", "--bead", "root")
    assert reused["mode"] == "unchanged" and reused["commit"] is None
    assert run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout == before
    audited = public_feature.invoke("check", "feature", "--bead", "root", "--require-docs")
    assert audited["checks"]["status"] == "ok" and audited["git"]["close_commit"] is None


def test_new_navigation_needs_close_ownership_even_when_design_was_inherited(public_feature: FeatureRepository) -> None:
    publication(public_feature)
    stage(public_feature, "docs/src/SUMMARY.md", "# Summary\n")
    run(["git", "commit", "-m", "Existing publication files"], cwd=public_feature.worktree)
    inherited = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip()
    run(["git", "reset", "--hard", inherited], cwd=public_feature.repo)
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Add feature navigation.")
    stage(public_feature, "docs/src/SUMMARY.md", "# Summary\n\n- [Example](features/example/index.md)\n")
    public_feature.invoke("commit", "--bead", "task")
    task["status"] = "closed"
    rejected = public_feature.invoke("docs", "commit", "--bead", "root", expected=2)
    assert "without a close-owned commit" in rejected["error"]
    audited = public_feature.invoke("check", "feature", "--bead", "root", "--require-docs", expected=4)
    assert any("requires one canonical documentation commit" in error for error in audited["checks"]["errors"])


def test_docs_commit_requires_exported_design_in_the_staged_tree(public_feature: FeatureRepository) -> None:
    exclude = public_feature.repo / ".git/info/exclude"
    exclude.write_text(exclude.read_text(encoding="utf-8") + "docs/src/features/example/design.md\n", encoding="utf-8")
    publication(public_feature)
    before = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip()
    rejected = public_feature.invoke("docs", "commit", "--bead", "root", expected=2)
    assert "feature design is missing from Git revision" in rejected["error"]
    assert run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip() == before


def test_docs_commit_validates_the_resulting_commit_after_hooks(public_feature: FeatureRepository) -> None:
    publication(public_feature)
    common = run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=public_feature.worktree
    ).stdout.strip()
    hook = Path(common) / "hooks/pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\nprintf '\\nHook mutation.\\n' >> docs/src/features/example/design.md\n"
        "git add docs/src/features/example/design.md\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    before = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip()
    rejected = public_feature.invoke("docs", "commit", "--bead", "root", expected=2)
    after = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip()
    assert after != before
    assert "differs from the native plan" in rejected["error"]
    committed = run(["git", "show", f"{after}:docs/src/features/example/design.md"], cwd=public_feature.worktree).stdout
    assert "Hook mutation." in committed


def test_feature_check_validates_committed_publication_not_ignored_working_files(public_feature: FeatureRepository) -> None:
    exclude = public_feature.repo / ".git/info/exclude"
    exclude.write_text(exclude.read_text(encoding="utf-8") + "docs/src/features/example/design.md\n", encoding="utf-8")
    publication(public_feature)
    message = canonical_docs_message(public_feature.data["issues"]["root"], "example", "audit")
    run(["git", "commit", "-F", "-"], cwd=public_feature.worktree, input_text=message)
    audited = public_feature.invoke("check", "feature", "--bead", "root", "--require-docs", expected=4)
    assert audited["validation"]["feature_docs"]["status"] == "invalid"
    assert "feature documentation validation failed" in audited["checks"]["errors"]
