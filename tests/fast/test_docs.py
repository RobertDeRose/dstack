from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dstack.core import DstackError
from dstack.docs import LINK_PATTERN, export_design, markdown_values, validate_docs


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


def test_validate_docs_rejects_unsafe_slug_symlink_and_weak_sections(tmp_path: Path) -> None:
    with pytest.raises(DstackError, match="feature slug"):
        validate_docs(tmp_path, feature="../outside")

    feature = write_feature(
        tmp_path, index=INDEX.replace("This feature gives users a deterministic workflow.", "Short")
    )
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
        with pytest.raises(DstackError, match="must not contain active mdBook directives"):
            validate_docs(tmp_path, feature="example")


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

    def children(self, parent: str) -> list[dict[str, Any]]:
        assert parent == "root"
        return self.steps


def test_export_design_writes_unique_plan_verbatim_and_atomically(tmp_path: Path) -> None:
    design = "### Goals\n\nKeep {{ braces }} and trailing text unchanged.\n"
    client = ExportClient(tmp_path, design)

    result = export_design(tmp_path, "root", client=client)  # type: ignore[arg-type]

    target = tmp_path / "docs/src/features/example/design.md"
    assert target.read_text(encoding="utf-8") == design
    assert result["path"] == "docs/src/features/example/design.md"
    assert not list(target.parent.glob(".design.md.*"))


def test_markdown_links_ignore_code_and_keep_balanced_parentheses() -> None:
    text = "[real](docs/a(b).md) ` [inline](ignored.md) `\n```\n[fenced](ignored.md)\n```\n"
    assert markdown_values(text, LINK_PATTERN) == ["docs/a(b).md"]
