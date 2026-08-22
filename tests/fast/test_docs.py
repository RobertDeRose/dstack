from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_docs
from dstack_commands import DstackError


REQUIRED = {
    "docs/book.toml",
    "docs/src/SUMMARY.md",
    "docs/src/index.md",
    "docs/src/architecture/index.md",
    "docs/src/development/index.md",
    "docs/src/development/documentation.md",
    "docs/src/features/index.md",
}


def fake_mdbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dstack_docs.shutil, "which", lambda name: "/usr/bin/true")


def test_foundation_creates_only_missing_required_files_and_is_idempotent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    existing = root / "docs/src/index.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("authored\n")

    created = dstack_docs.create_foundation(root)

    assert set(created) == REQUIRED - {"docs/src/index.md"}
    assert existing.read_text() == "authored\n"
    assert {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()} == REQUIRED
    assert dstack_docs.create_foundation(root) == []


def test_foundation_extends_existing_summary_without_rewriting_project_navigation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    summary = root / "docs/src/SUMMARY.md"
    custom = root / "docs/src/guides/index.md"
    architecture = root / "docs/src/architecture/index.md"
    custom.parent.mkdir(parents=True)
    architecture.parent.mkdir(parents=True)
    custom.write_text("# Guide\n")
    architecture.write_text("# Existing architecture\n")
    original = "# Summary\n\n- [Getting Started](guides/index.md)\n- [System Design](architecture/index.md)\n"
    summary.write_text(original)

    dstack_docs.create_foundation(root)

    updated = summary.read_text()
    assert updated.startswith(original)
    assert updated.count("architecture/index.md") == 1
    assert "[System Design](architecture/index.md)" in updated
    assert "[Project](index.md)" in updated
    assert "[Development](development/index.md)" in updated
    assert "[Documentation](development/documentation.md)" in updated
    assert "[Feature Records](features/index.md)" in updated
    first = updated
    assert dstack_docs.create_foundation(root) == []
    assert summary.read_text() == first

    fake_mdbook(monkeypatch)
    assert dstack_docs.validate_docs(root)["status"] == "ok"


def test_initialize_requires_mdbook_before_documentation_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dstack_docs.shutil, "which", lambda name: None)

    with pytest.raises(DstackError, match="mdbook executable"):
        dstack_docs.initialize_docs(tmp_path)

    assert not (tmp_path / "docs").exists()


def test_validation_accepts_project_sections_external_links_and_includes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dstack_docs.create_foundation(tmp_path)
    guide = tmp_path / "docs/src/guides/install.md"
    guide.parent.mkdir()
    guide.write_text("# Install\n\n[Website](https://example.com)\n")
    snippet = tmp_path / "docs/src/snippets/note.md"
    snippet.parent.mkdir()
    snippet.write_text("included\n")
    index = tmp_path / "docs/src/index.md"
    index.write_text(index.read_text() + "\n{{#include snippets/note.md}}\n")
    summary = tmp_path / "docs/src/SUMMARY.md"
    summary.write_text(summary.read_text() + "\n- [Install](guides/install.md)\n")
    fake_mdbook(monkeypatch)

    result = dstack_docs.validate_docs(tmp_path)

    assert result["status"] == "ok"
    assert "guides/install.md" in result["chapters"]
    assert "snippets/note.md" in result["includes"]


@pytest.mark.parametrize(
    ("path", "content", "message"),
    [
        ("docs/src/hidden.md", "# Hidden\n", "orphan"),
        ("docs/src/index.md", "[Missing](missing.md)\n", "missing local documentation target"),
        ("docs/src/index.md", "[Escape](../../outside.md)\n", "escapes docs/src"),
    ],
)
def test_validation_rejects_orphans_broken_links_and_escapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    content: str,
    message: str,
) -> None:
    dstack_docs.create_foundation(tmp_path)
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    fake_mdbook(monkeypatch)

    with pytest.raises(DstackError, match=message):
        dstack_docs.validate_docs(tmp_path)


def test_validation_rejects_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dstack_docs.create_foundation(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n")
    (tmp_path / "docs/src/escape.md").symlink_to(outside)
    index = tmp_path / "docs/src/index.md"
    index.write_text("[Escape](escape.md)\n")
    fake_mdbook(monkeypatch)

    with pytest.raises(DstackError, match="escapes docs/src"):
        dstack_docs.validate_docs(tmp_path)


def test_validation_propagates_mdbook_build_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dstack_docs.create_foundation(tmp_path)
    monkeypatch.setattr(dstack_docs.shutil, "which", lambda name: "/usr/bin/false")

    with pytest.raises(DstackError):
        dstack_docs.validate_docs(tmp_path)


def test_validation_rejects_noncanonical_book_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dstack_docs.create_foundation(tmp_path)
    book = tmp_path / "docs/book.toml"
    book.write_text('[book]\ntitle = "Legacy"\nsrc = "book"\n')
    legacy = tmp_path / "docs/book"
    legacy.mkdir()
    (legacy / "SUMMARY.md").write_text("# Summary\n")
    fake_mdbook(monkeypatch)

    with pytest.raises(DstackError, match=r"\[book\]\.src must resolve to docs/src"):
        dstack_docs.validate_docs(tmp_path)


def test_migration_moves_configured_book_source_before_foundation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs = tmp_path / "docs"
    legacy = docs / "book"
    legacy.mkdir(parents=True)
    (docs / "book.toml").write_text('[book]\ntitle = "Legacy"\nlanguage = "en"\nsrc = "book"\n')
    (legacy / "SUMMARY.md").write_text("# Summary\n\n- [Home](README.md)\n- [Guide](guides/install.md)\n")
    (legacy / "README.md").write_text("# Existing home\n")
    guide = legacy / "guides/install.md"
    guide.parent.mkdir()
    guide.write_text("# Install\n")
    fake_mdbook(monkeypatch)

    migrated = dstack_docs.migrate_legacy_documentation(tmp_path)
    created = dstack_docs.create_foundation(tmp_path)
    result = dstack_docs.validate_docs(tmp_path)

    assert migrated["configured_source_moves"]
    assert not legacy.exists()
    assert (docs / "src/README.md").read_text() == "# Existing home\n"
    assert (docs / "src/guides/install.md").read_text() == "# Install\n"
    assert 'src = "src"' in (docs / "book.toml").read_text()
    assert "docs/src/index.md" in created
    assert result["status"] == "ok"
    summary = (docs / "src/SUMMARY.md").read_text()
    assert "[Home](README.md)" in summary
    assert "[Guide](guides/install.md)" in summary
    assert "[Architecture](architecture/index.md)" in summary


def test_migration_moves_book_referenced_content_from_outside_src(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dstack_docs.create_foundation(tmp_path)
    legacy = tmp_path / "docs/features/widget/design.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# Widget\n\n{{#include ../shared/details.md}}\n")
    shared = tmp_path / "docs/features/shared/details.md"
    shared.parent.mkdir(parents=True)
    shared.write_text("# Details\n")
    summary = tmp_path / "docs/src/SUMMARY.md"
    summary.write_text(summary.read_text() + "\n- [Widget](../features/widget/design.md?mode=review#top)\n")
    fake_mdbook(monkeypatch)

    plan = dstack_docs.legacy_documentation_plan(tmp_path)
    assert plan["referenced_content_moves"] == [
        {
            "source": "docs/features/shared/details.md",
            "destination": "docs/src/features/shared/details.md",
        },
        {
            "source": "docs/features/widget/design.md",
            "destination": "docs/src/features/widget/design.md",
        },
    ]

    migrated = dstack_docs.migrate_legacy_documentation(tmp_path)
    dstack_docs.ensure_core_navigation(tmp_path)
    result = dstack_docs.validate_docs(tmp_path)

    assert result["status"] == "ok"
    assert not legacy.exists()
    assert not shared.exists()
    moved_design = tmp_path / "docs/src/features/widget/design.md"
    moved_shared = tmp_path / "docs/src/features/shared/details.md"
    assert moved_design.is_file()
    assert moved_shared.is_file()
    assert "features/widget/design.md?mode=review#top" in summary.read_text()
    assert "{{#include ../shared/details.md}}" in moved_design.read_text()
    assert {
        "source": "docs/features/shared/details.md",
        "destination": "docs/src/features/shared/details.md",
    } in migrated["referenced_content_moves"]


def test_migration_leaves_unreferenced_outside_markdown_for_semantic_judgment(
    tmp_path: Path,
) -> None:
    dstack_docs.create_foundation(tmp_path)
    note = tmp_path / "docs/notes/internal.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Maybe book content\n")

    plan = dstack_docs.legacy_documentation_plan(tmp_path)
    migrated = dstack_docs.migrate_legacy_documentation(tmp_path)

    assert plan["referenced_content_moves"] == []
    assert plan["unresolved_outside_markdown"] == ["docs/notes/internal.md"]
    assert migrated["referenced_content_moves"] == []
    assert migrated["unresolved_outside_markdown"] == ["docs/notes/internal.md"]
    assert note.is_file()



def test_migration_rejects_symlinked_configured_source(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    real = docs / "real-book"
    real.mkdir(parents=True)
    (real / "SUMMARY.md").write_text("# Summary\n")
    (docs / "legacy-book").symlink_to(real, target_is_directory=True)
    (docs / "book.toml").write_text('[book]\nsrc = "legacy-book"\n')

    with pytest.raises(DstackError, match="symlink"):
        dstack_docs.migrate_legacy_documentation(tmp_path)

    assert (real / "SUMMARY.md").read_text() == "# Summary\n"


def test_migration_refuses_conflicting_configured_source(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    legacy = docs / "book"
    canonical = docs / "src"
    legacy.mkdir(parents=True)
    canonical.mkdir(parents=True)
    (docs / "book.toml").write_text('[book]\nsrc = "book"\n')
    (legacy / "SUMMARY.md").write_text("legacy\n")
    (canonical / "SUMMARY.md").write_text("canonical\n")

    with pytest.raises(DstackError, match="conflicts with docs/src"):
        dstack_docs.migrate_legacy_documentation(tmp_path)

    assert (legacy / "SUMMARY.md").read_text() == "legacy\n"
    assert (canonical / "SUMMARY.md").read_text() == "canonical\n"
