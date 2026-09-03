from __future__ import annotations

from pathlib import Path

import pytest

from dstack.core import DstackError
from dstack.docs import LINK_PATTERN, create_foundation, markdown_values, validate_docs


def fake_mdbook(tmp_path: Path) -> Path:
    executable = tmp_path / "mdbook"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def test_foundation_covers_user_developer_and_decision_surfaces(tmp_path: Path) -> None:
    created = create_foundation(tmp_path)
    assert "docs/src/getting-started/index.md" in created
    assert "docs/src/operations/index.md" in created
    assert "docs/src/development/index.md" in created
    assert "docs/src/decisions/index.md" in created
    assert create_foundation(tmp_path) == []


def test_validate_docs_accepts_complete_book(tmp_path: Path) -> None:
    create_foundation(tmp_path)
    result = validate_docs(tmp_path, mdbook=str(fake_mdbook(tmp_path)))
    assert result["status"] == "ok"
    assert "getting-started/index.md" in result["chapters"]


def test_validate_docs_rejects_symlinked_summary(tmp_path: Path) -> None:
    create_foundation(tmp_path)
    summary = tmp_path / "docs/src/SUMMARY.md"
    outside = tmp_path / "outside-summary.md"
    outside.write_text(summary.read_text(encoding="utf-8"), encoding="utf-8")
    summary.unlink()
    summary.symlink_to(outside)

    with pytest.raises(DstackError, match="symlink"):
        validate_docs(tmp_path, mdbook=str(fake_mdbook(tmp_path)))


def test_validate_docs_accepts_a_current_decision_record(tmp_path: Path) -> None:
    create_foundation(tmp_path)
    source = tmp_path / "docs/src"
    decision = source / "decisions/0001-current.md"
    decision.write_text("# Current decision\n\n- **Status:** Accepted\n", encoding="utf-8")
    summary = source / "SUMMARY.md"
    summary.write_text(
        summary.read_text(encoding="utf-8") + "- [Current decision](decisions/0001-current.md)\n",
        encoding="utf-8",
    )

    assert validate_docs(tmp_path, mdbook=str(fake_mdbook(tmp_path)))["status"] == "ok"


def test_validate_docs_tracks_navigation_and_local_targets_by_behavior(tmp_path: Path) -> None:
    create_foundation(tmp_path)
    mdbook = str(fake_mdbook(tmp_path))
    source = tmp_path / "docs/src"
    summary = source / "SUMMARY.md"

    orphan = source / "orphan.md"
    orphan.write_text("# Orphan\n", encoding="utf-8")
    with pytest.raises(DstackError):
        validate_docs(tmp_path, mdbook=mdbook)

    summary.write_text(
        summary.read_text(encoding="utf-8") + "- [Additional](orphan.md)\n",
        encoding="utf-8",
    )
    assert "orphan.md" in validate_docs(tmp_path, mdbook=mdbook)["chapters"]

    summary.write_text(
        summary.read_text(encoding="utf-8") + "- [Pending](pending.md)\n",
        encoding="utf-8",
    )
    with pytest.raises(DstackError):
        validate_docs(tmp_path, mdbook=mdbook)

    (source / "pending.md").write_text("# Pending\n", encoding="utf-8")
    result = validate_docs(tmp_path, mdbook=mdbook)
    assert set(result["chapters"]) >= {"orphan.md", "pending.md"}


def test_markdown_links_ignore_code_and_keep_balanced_parentheses() -> None:
    text = "[real](docs/a(b).md) ` [inline](ignored.md) `\n```\n[fenced](ignored.md)\n```\n"
    assert markdown_values(text, LINK_PATTERN) == ["docs/a(b).md"]
