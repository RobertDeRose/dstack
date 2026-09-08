from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dstack.core import run
from dstack.docs import markdown_links
from dstack.policy import markdown_sections

if TYPE_CHECKING:
    from conftest import FeatureRepository


def test_partial_publication_can_be_scaffolded_reviewed_committed_and_audited(
    public_feature: FeatureRepository,
) -> None:
    directory = public_feature.worktree / "docs/src/features/example"
    directory.mkdir(parents=True)
    index = directory / "index.md"
    original = "# Example\n\n## Overview\n\nPreserve this reviewed prose and `Result<T, E>`.\n"
    index.write_text(original, encoding="utf-8")
    public_feature.invoke("docs", "export-design", "--bead", "root", "--scaffold")
    text = index.read_text(encoding="utf-8")
    assert text.startswith(original)
    sections = markdown_sections(text)
    assert [section.title for section in sections if section.level == 2] == [
        "Overview",
        "User Impact",
        "Implemented Design",
    ]
    assert text.count("{{#include design.md}}") == 1
    checked = public_feature.invoke("check", "docs", "--slug", "example", expected=2)
    assert "User Impact" in checked["error"]
    # The agent supplies prose; scaffolding does not invent a product claim or word count.
    text = text.replace("## User Impact\n", "## User Impact\n\nUse it.\n")
    index.write_text(text, encoding="utf-8")
    public_feature.invoke("docs", "export-design", "--bead", "root", "--scaffold")
    assert index.read_text(encoding="utf-8") == text
    summary = public_feature.worktree / "docs/src/SUMMARY.md"
    assert markdown_links(summary.read_text(encoding="utf-8")) == ["features/example/index.md"]
    public_feature.invoke("check", "docs", "--slug", "example")
    run(["git", "add", "docs"], cwd=public_feature.worktree)
    created = public_feature.invoke("docs", "commit", "--bead", "root")
    assert created["mode"] == "created"
    audited = public_feature.invoke("audit", "--bead", "root", "--require-docs")
    assert audited["checks"]["status"] == "ok"
    assert audited["git"]["close_commit"]["commit"] == created["commit"]


def test_missing_include_is_inserted_inside_existing_design_section(public_feature: FeatureRepository) -> None:
    directory = public_feature.worktree / "docs/src/features/example"
    directory.mkdir(parents=True)
    index = directory / "index.md"
    before = "# Example\n\n## Implemented Design\n\nExisting design introduction.\n"
    after = "\n## References\n\nKeep these references unchanged.\n"
    index.write_text(before + after, encoding="utf-8")
    public_feature.invoke("docs", "export-design", "--bead", "root", "--scaffold")
    text = index.read_text(encoding="utf-8")
    assert "Existing design introduction." in text and text.endswith(after)
    design = next(section for section in markdown_sections(text) if section.title == "Implemented Design")
    assert "{{#include design.md}}" in design.content
    assert "Keep these references" not in design.content
    public_feature.invoke("docs", "export-design", "--bead", "root", "--scaffold")
    assert index.read_text(encoding="utf-8") == text


@pytest.mark.parametrize(
    "partial",
    [
        "## Overview\n\nOne.\n\n## Overview\n\nTwo.\n",
        "### User Impact\n\nWrong level.\n",
        "## Overview\n\n{{#include design.md}}\n",
        "## Implemented Design\n\n{{#include other.md}}\n",
        "## Implemented Design\n\n{{#include design.md}}\n\n{{#include design.md}}\n",
    ],
)
def test_ambiguous_scaffold_does_not_modify_any_publication_file(
    public_feature: FeatureRepository,
    partial: str,
) -> None:
    source = public_feature.worktree / "docs/src"
    directory = source / "features/example"
    directory.mkdir(parents=True)
    index, design, summary = directory / "index.md", directory / "design.md", source / "SUMMARY.md"
    for path, text in (
        (index, "# Example\n\n" + partial),
        (design, "Previously published design.\n"),
        (summary, "# Summary\n\n- [Home](index.md)\n"),
    ):
        path.write_text(text, encoding="utf-8")
    before = {path: path.read_bytes() for path in (index, design, summary)}
    rejected = public_feature.invoke("docs", "export-design", "--bead", "root", "--scaffold", expected=2)
    assert "before scaffolding" in rejected["error"]
    assert {path: path.read_bytes() for path in before} == before
