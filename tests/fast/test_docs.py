from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dstack.core import DstackError, run
from dstack.docs import export_design, markdown_links, validate_docs
from dstack.policy import PLAN_SECTIONS, markdown_sections


INDEX = """# Example feature

## Overview

This feature gives users a deterministic workflow.

## User Impact

Users invoke one explicit command and receive bounded output.

## Implemented Design

{{#include design.md}}
"""
DESIGN = """### Goals

Provide a safe feature workflow.

### User-facing behavior

Users explicitly invoke each lifecycle operation.
"""


def write_feature(root: Path, *, slug: str = "example", index: str = INDEX, design: str = DESIGN) -> Path:
    source = root / "docs/src"
    feature = source / "features" / slug
    feature.mkdir(parents=True)
    (feature / "index.md").write_text(index, encoding="utf-8")
    (feature / "design.md").write_text(design, encoding="utf-8")
    (source / "SUMMARY.md").write_text(
        f"# Summary\n\n- [Example](features/{slug}/index.md)\n",
        encoding="utf-8",
    )
    return feature


def test_validate_docs_accepts_minimal_feature_contract(tmp_path: Path) -> None:
    write_feature(tmp_path)

    result = validate_docs(tmp_path, feature="example")

    assert result == {
        "status": "ok",
        "feature": "example",
        "index": "docs/src/features/example/index.md",
        "design": "docs/src/features/example/design.md",
    }


def test_validate_docs_rejects_unsafe_slug_symlink_and_empty_sections(tmp_path: Path) -> None:
    with pytest.raises(DstackError, match="feature slug"):
        validate_docs(tmp_path, feature="../outside")

    feature = write_feature(tmp_path, index=INDEX.replace("This feature gives users a deterministic workflow.", ""))
    with pytest.raises(DstackError, match="Overview"):
        validate_docs(tmp_path, feature="example")

    (feature / "index.md").unlink()
    outside = tmp_path / "outside.md"
    outside.write_text(INDEX, encoding="utf-8")
    (feature / "index.md").symlink_to(outside)
    with pytest.raises(DstackError, match="symlink"):
        validate_docs(tmp_path, feature="example")


def test_validate_docs_requires_one_index_link_and_no_design_link(tmp_path: Path) -> None:
    write_feature(tmp_path)
    summary = tmp_path / "docs/src/SUMMARY.md"
    summary.write_text(
        summary.read_text(encoding="utf-8")
        + "- [Duplicate](features/example/index.md)\n"
        + "- [Raw design](features/example/design.md)\n",
        encoding="utf-8",
    )

    with pytest.raises(DstackError, match="exactly one SUMMARY link"):
        validate_docs(tmp_path, feature="example")

    summary.write_text("# Summary\n\n- [Raw design](features/example/design.md)\n", encoding="utf-8")
    with pytest.raises(DstackError, match="must not link directly"):
        validate_docs(tmp_path, feature="example")


def test_validate_docs_requires_exact_native_include_and_rejects_design_directives(tmp_path: Path) -> None:
    feature = write_feature(tmp_path, index=INDEX.replace("{{#include design.md}}", "{{#include ../design.md}}"))
    with pytest.raises(DstackError, match="exactly one native include"):
        validate_docs(tmp_path, feature="example")

    (feature / "index.md").write_text(INDEX, encoding="utf-8")
    for design in (
        "{{#include ../../../secret}}\n",
        "```markdown\n{{#include design.md}}\n```\n",
    ):
        (feature / "design.md").write_text(design, encoding="utf-8")
        with pytest.raises(DstackError, match="must not contain active mdBook file directives"):
            validate_docs(tmp_path, feature="example")


def test_validate_docs_matches_mdbook_file_helper_semantics(tmp_path: Path) -> None:
    feature = write_feature(tmp_path)
    fenced = INDEX + "\n```text\n{{#include ../../../../../secret.txt}}\n```\n"
    (feature / "index.md").write_text(fenced, encoding="utf-8")
    with pytest.raises(DstackError, match="exactly one native include"):
        validate_docs(tmp_path, feature="example")

    (feature / "index.md").write_text(INDEX, encoding="utf-8")
    (feature / "design.md").write_text("{{#rustdoc_include ../../../../../secret.rs}}\n", encoding="utf-8")
    with pytest.raises(DstackError, match="active mdBook file directives"):
        validate_docs(tmp_path, feature="example")

    (feature / "design.md").write_text(r"\{{#include ignored.md}}" + "\n", encoding="utf-8")
    assert validate_docs(tmp_path, feature="example")["status"] == "ok"


class ExportClient:
    def __init__(self, root: Path, design: str):
        self.root = root
        self.design = design
        self.feature = {
            "id": "root",
            "issue_type": "molecule",
            "labels": ["workflow:feature", "feature:example"],
            "metadata": {"dstack.base_branch": "main"},
        }
        self.steps = [
            {
                "id": name,
                "issue_type": "epic" if name == "implementation" else "task",
                "labels": [f"dstack:step:{name}"],
            }
            for name in ("plan", "review", "approval", "implementation", "audit")
        ]
        self.steps[0]["design"] = design

    def show(self, issue_id: str) -> dict[str, Any]:
        if issue_id == "root":
            return self.feature
        return next(step for step in self.steps if step["id"] == issue_id)

    def worktrees(self) -> list[dict[str, Any]]:
        return [{"path": str(self.root), "branch": "feat/example"}]

    def children(self, parent: str) -> list[dict[str, Any]]:
        assert parent == "root"
        return self.steps


def test_export_design_writes_unique_plan_verbatim_and_atomically(git_repo: Path) -> None:
    tmp_path = git_repo.with_name(git_repo.name + ".feat-example")
    run(["git", "worktree", "add", "-b", "feat/example", str(tmp_path)], cwd=git_repo)
    design = "### Goals\n\nKeep {{ braces }} and trailing text unchanged.\n"
    client = ExportClient(tmp_path, design)

    result = export_design(tmp_path, "root", client=client)  # type: ignore[arg-type]

    target = tmp_path / "docs/src/features/example/design.md"
    assert target.read_text(encoding="utf-8") == design
    assert result["path"] == "docs/src/features/example/design.md"
    assert not list(target.parent.glob(".design.md.*"))


def test_markdown_links_ignore_code_and_keep_balanced_parentheses() -> None:
    text = "[real](docs/a(b).md) ` [inline](ignored.md) `\n```\n[fenced](ignored.md)\n```\n"
    assert markdown_links(text) == ["docs/a(b).md"]


@pytest.mark.parametrize("design", ["", "   \n", DESIGN + "changed\n"])
def test_docs_validate_rejects_empty_or_stale_native_export(tmp_path: Path, design: str) -> None:
    write_feature(tmp_path, design=design)
    with pytest.raises(DstackError, match="empty|differs from the feature plan"):
        validate_docs(tmp_path, feature="example", expected_design=DESIGN)


def test_docs_export_refuses_primary_checkout_without_writing(git_repo: Path, tmp_path: Path) -> None:
    worktree = git_repo.with_name(git_repo.name + ".feat-example")
    run(["git", "worktree", "add", "-b", "feat/example", str(worktree)], cwd=git_repo)
    client = ExportClient(git_repo, DESIGN)
    client.worktrees = lambda: [{"path": str(worktree), "branch": "feat/example"}]  # type: ignore[method-assign]
    with pytest.raises(DstackError, match="registered feature worktree"):
        export_design(git_repo, "root", client=client)  # type: ignore[arg-type]
    assert not (git_repo / "docs").exists()
    assert not (worktree / "docs").exists()


def test_docs_scaffold_is_repeatable_without_overwriting_prose(git_repo: Path) -> None:
    worktree = git_repo.with_name(git_repo.name + ".feat-example")
    run(["git", "worktree", "add", "-b", "feat/example", str(worktree)], cwd=git_repo)
    git_repo = worktree
    client = ExportClient(git_repo, DESIGN)
    export_design(git_repo, "root", client=client, scaffold=True)  # type: ignore[arg-type]
    with pytest.raises(DstackError, match="Overview"):
        validate_docs(git_repo, feature="example")
    index = git_repo / "docs/src/features/example/index.md"
    index.write_text(INDEX, encoding="utf-8")
    before = (git_repo / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    export_design(git_repo, "root", client=client, scaffold=True)  # type: ignore[arg-type]
    assert index.read_text(encoding="utf-8") == INDEX
    assert (git_repo / "docs/src/SUMMARY.md").read_text(encoding="utf-8") == before
    assert validate_docs(git_repo, feature="example", expected_design=DESIGN)["status"] == "ok"


def test_markdown_reference_links_and_nested_fences() -> None:
    text = '[real][target]\n\n[target]: docs/a(b).md "Title"\n\n````md\n```\n[hidden](hidden.md)\n```\n````\n'
    assert markdown_links(text) == ["docs/a(b).md"]


def test_mdbook_landing_page_keeps_theme_aware_logo() -> None:
    root = Path(__file__).resolve().parents[2]
    index = (root / "docs/src/index.md").read_text(encoding="utf-8")
    book = (root / "docs/book.toml").read_text(encoding="utf-8")
    css = (root / "docs/src/assets/css/center_images.css").read_text(encoding="utf-8")

    assert "![dStack logo](assets/img/dstack_logo.png#center)" in index
    assert 'additional-css = ["src/assets/css/center_images.css"]' in book
    assert 'img[src*="#center"]' in css
    assert 'html.rust img[src*="dstack_logo.png"]' in css
    assert 'html.ayu img[src*="dstack_logo.png"]' in css
    assert 'html.coal img[src*="dstack_logo.png"]' in css
    assert 'html.navy img[src*="dstack_logo.png"]' in css

    for name in ("dstack_logo.png", "dstack_logo_neon_blue.png", "dstack_logo_neon_orange.png"):
        assert (root / "docs/src/assets/img" / name).is_file()


@pytest.mark.parametrize("feature", ["beads-native-control-plane", "lean-workflow-refinement"])
def test_implemented_feature_records_use_feature_publication_contract(feature: str) -> None:
    root = Path(__file__).resolve().parents[2]

    assert validate_docs(root, feature=feature)["status"] == "ok"

    design = (root / "docs/src/features" / feature / "design.md").read_text(encoding="utf-8")
    sections = [section.title for section in markdown_sections(design) if section.level == 3]
    assert sections == list(PLAN_SECTIONS)


def test_implemented_features_live_under_references_without_adr_navigation() -> None:
    root = Path(__file__).resolve().parents[2]
    summary = (root / "docs/src/SUMMARY.md").read_text(encoding="utf-8")

    assert "[Implemented Features](reference/implemented-features.md)" in summary
    assert "[Beads-native control plane](features/beads-native-control-plane/index.md)" in summary
    assert "[Lean workflow and documentation lifecycle](features/lean-workflow-refinement/index.md)" in summary
    assert "decisions/" not in summary
    assert "Architecture decisions" not in summary
