from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_docs
import setup
from dstack_commands import (
    ALIGNMENT_RECONCILIATION_SCAFFOLD,
    DESIGN_SCAFFOLD,
    RECORD_SUBJECTS,
    RECONCILIATION_SCAFFOLD,
    DstackError,
)


def test_markdown_values_is_public_and_ignores_code() -> None:
    text = "[real](docs/index.md) and `[fake](ignored.md)`"
    assert dstack_docs.markdown_values(text, dstack_docs.LINK_PATTERN) == ["docs/index.md"]


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
    assert "  - [Documentation](development/documentation.md)" in updated
    assert "[Feature Records](features/index.md)" in updated
    first = updated
    assert dstack_docs.create_foundation(root) == []
    assert summary.read_text() == first

    fake_mdbook(monkeypatch)
    assert dstack_docs.validate_docs(root)["status"] == "ok"


def complete_record(kind: str, *, omitted: str | None = None) -> str:
    lines = ["# Record", ""]
    for subject in RECORD_SUBJECTS[kind]:
        if subject == omitted:
            continue
        lines.extend([f"## {subject}", "", f"Evidence for {subject}.", ""])
    return "\n".join(lines)


@pytest.mark.parametrize(
    ("kind", "subject"),
    [(kind, subject) for kind, subjects in RECORD_SUBJECTS.items() for subject in subjects],
)
def test_every_record_subject_is_required(kind: str, subject: str) -> None:
    with pytest.raises(DstackError, match=f"missing required section: {subject}"):
        dstack_docs.validate_record(complete_record(kind, omitted=subject), kind)


@pytest.mark.parametrize("kind", RECORD_SUBJECTS)
def test_record_accepts_specific_applicability_reason(kind: str) -> None:
    subject = RECORD_SUBJECTS[kind][0]
    text = complete_record(kind).replace(
        f"Evidence for {subject}.",
        "Not applicable — this workflow does not expose a network interface.",
    )
    dstack_docs.validate_record(text, kind)
    with pytest.raises(DstackError, match="specific reason"):
        dstack_docs.validate_record(
            text.replace(
                "Not applicable — this workflow does not expose a network interface.",
                "Not applicable",
            ),
            kind,
        )


@pytest.mark.parametrize("placeholder", ["TODO", "TBD", "<fill this>", "{{placeholder}}"])
def test_record_rejects_placeholders_duplicates_and_reference_links(
    placeholder: str,
) -> None:
    kind = "alignment-reconciliation"
    text = complete_record(kind)
    with pytest.raises(DstackError, match="placeholder"):
        dstack_docs.validate_record(text + placeholder, kind)
    heading = RECORD_SUBJECTS[kind][0]
    with pytest.raises(DstackError, match="duplicate heading"):
        dstack_docs.validate_record(text + f"\n## {heading}\nDuplicate.\n", kind)
    with pytest.raises(DstackError, match="reference-style"):
        dstack_docs.validate_record(text + "\n[Current docs][docs]\n", kind)


def test_record_local_links_and_scaffolds_share_the_contract(tmp_path: Path) -> None:
    current = tmp_path / "current.md"
    current.write_text("# Current\n")
    record = tmp_path / "record.md"
    text = complete_record("feature-reconciliation").replace(
        "Evidence for Delivered capability.",
        "Evidence for delivery. [Current behavior](current.md)",
    )
    record.write_text(text)
    dstack_docs.validate_record(
        text,
        "feature-reconciliation",
        source=record,
        source_root=tmp_path,
    )
    with pytest.raises(DstackError, match="local link is missing"):
        dstack_docs.validate_record(
            text.replace("current.md", "missing.md"),
            "feature-reconciliation",
            source=record,
            source_root=tmp_path,
        )

    scaffolds = {
        "feature-design": DESIGN_SCAFFOLD.format(planned_intent="Intent.", planned_acceptance="Acceptance."),
        "feature-reconciliation": RECONCILIATION_SCAFFOLD.format(title="Feature"),
        "alignment-reconciliation": ALIGNMENT_RECONCILIATION_SCAFFOLD,
    }
    for kind, scaffold in scaffolds.items():
        headings = {match.group(2).strip() for match in dstack_docs.HEADING_PATTERN.finditer(scaffold)}
        assert set(RECORD_SUBJECTS[kind]) <= headings
        with pytest.raises(DstackError, match="substantive content"):
            dstack_docs.validate_record(scaffold, kind)


def test_operator_security_reference_and_decision_pages_are_reachable() -> None:
    source = ROOT / "docs/src"
    summary = (source / "SUMMARY.md").read_text()
    pages = [
        "operations/index.md",
        "operations/delivery.md",
        "operations/recovery.md",
        "security/index.md",
        "reference/cli.md",
        "reference/environment.md",
        "reference/metadata-labels.md",
        "decisions/index.md",
        "decisions/0001-authority-ownership.md",
        "decisions/0002-one-way-git-evidence.md",
        "decisions/0003-committed-content-approval.md",
        "decisions/0004-root-open-until-delivery.md",
        "decisions/0005-interactions-and-documentation.md",
    ]
    for relative in pages:
        content = (source / relative).read_text()
        assert len(content.split()) >= 60, relative
        assert f"]({relative})" in summary, relative


def test_decision_record_status_and_supersession_contract(tmp_path: Path) -> None:
    decisions = tmp_path / "decisions"
    decisions.mkdir()
    record = decisions / "0001-choice.md"
    record.write_text("# Choice\n\n- **Status:** Accepted\n- **Supersedes:** None\n- **Superseded by:** None\n")
    assert dstack_docs.validate_decision_records(tmp_path) == []

    record.write_text("# Choice\n\n- **Status:** Done\n- **Supersedes:** another record\n- **Superseded by:** None\n")
    errors = dstack_docs.validate_decision_records(tmp_path)
    assert any("invalid status" in error for error in errors)
    assert any("must be None or a local link" in error for error in errors)


def test_initialize_requires_mdbook_before_documentation_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dstack_docs.shutil, "which", lambda name: None)

    with pytest.raises(DstackError, match="locked mdbook is unavailable"):
        dstack_docs.initialize_docs(tmp_path)

    assert not (tmp_path / "docs").exists()


def test_validation_accepts_project_sections_external_links_and_includes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dstack_docs.create_foundation(tmp_path)
    guide = tmp_path / "docs/src/guides/install.md"
    guide.parent.mkdir()
    guide.write_text("# Install\n\n[Website](https://example.com)\n[Project](../index.md?view=full#overview)\n")
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


@pytest.mark.parametrize("outside", [False, True])
def test_validation_rejects_required_file_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outside: bool
) -> None:
    dstack_docs.create_foundation(tmp_path)
    required = tmp_path / "docs/src/index.md"
    target = tmp_path / "outside.md" if outside else tmp_path / "docs/src/target.md"
    target.write_text("target\n")
    required.unlink()
    required.symlink_to(target)
    fake_mdbook(monkeypatch)

    with pytest.raises(DstackError, match="not a regular file"):
        dstack_docs.validate_docs(tmp_path)


def test_validation_reports_all_deterministic_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dstack_docs.create_foundation(tmp_path)
    index = tmp_path / "docs/src/index.md"
    index.write_text("[One](one.md)\n[Two](two.md)\n")
    (tmp_path / "docs/src/hidden.md").write_text("hidden\n")
    fake_mdbook(monkeypatch)

    with pytest.raises(DstackError) as raised:
        dstack_docs.validate_docs(tmp_path)

    message = str(raised.value)
    assert "one.md" in message
    assert "two.md" in message
    assert "hidden.md" in message


def test_validation_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_configured_source_plan_reports_external_manual_action(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    legacy = docs / "book"
    legacy.mkdir(parents=True)
    (docs / "book.toml").write_text('[book]\nsrc = "book"\n')
    (legacy / "SUMMARY.md").write_text("# Summary\n")
    (legacy / "README.md").write_text("# Existing home\n")
    note = docs / "notes/placement.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Choose a chapter\n")

    plan = dstack_docs.legacy_documentation_plan(tmp_path)

    assert plan["configured_source_moves"]
    assert plan["unresolved_outside_markdown"] == ["docs/notes/placement.md"]
    assert plan["manual_actions"][0]["path"] == "docs/notes/placement.md"


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
    assert plan["manual_actions"] == [
        {
            "path": "docs/notes/internal.md",
            "action": "choose a docs/src chapter, move the file, update SUMMARY.md, and rerun setup",
        }
    ]
    assert migrated["referenced_content_moves"] == []
    assert migrated["unresolved_outside_markdown"] == ["docs/notes/internal.md"]
    assert migrated["manual_actions"] == plan["manual_actions"]
    assert note.is_file()


REPRESENTATIVE_MIGRATIONS = {
    "distributed": {
        "summary": (
            "- [Runtime](../legacy/distributed/architecture/runtime.md)\n"
            "- [Runbook](../legacy/distributed/operations/runbook.md)\n"
        ),
        "canonical": {
            "docs/src/architecture/index.md": (
                "# Service architecture\n\n[Runtime](../../legacy/distributed/architecture/runtime.md)\n"
            )
        },
        "external": {
            "docs/legacy/distributed/architecture/runtime.md": (
                "# Runtime topology\n\n[Runbook](../operations/runbook.md)\n"
            ),
            "docs/legacy/distributed/operations/runbook.md": ("# Service runbook\n\nRestart the worker pool.\n"),
        },
        "ambiguous": "docs/legacy/distributed/decisions/placement.md",
        "manual_destination": "docs/src/operations/placement.md",
    },
    "embedded": {
        "summary": "- [Hardware](hardware/index.md)\n",
        "canonical": {
            "docs/src/hardware/index.md": ("# Board hardware\n\n{{#include ../../legacy/embedded/pinout.md}}\n")
        },
        "external": {
            "docs/legacy/embedded/pinout.md": ("# Pinout\n\n{{#include provisioning/boot.md}}\n"),
            "docs/legacy/embedded/provisioning/boot.md": ("# Boot provisioning\n\nUse the recovery jumper.\n"),
        },
        "ambiguous": "docs/legacy/embedded/notes/board.md",
        "manual_destination": "docs/src/hardware/board-notes.md",
    },
    "modular": {
        "summary": ("- [Modules](modules/index.md)\n- [Core API](../legacy/modular/core/api.md#stable)\n"),
        "canonical": {
            "docs/src/modules/index.md": ("# Modules\n\n[Core API](../../legacy/modular/core/api.md#stable)\n")
        },
        "external": {
            "docs/legacy/modular/core/api.md": ("# Core API\n\nThe stable module contract.\n"),
        },
        "ambiguous": "docs/legacy/modular/proposals/plugin.md",
        "manual_destination": "docs/src/modules/plugin-proposal.md",
    },
}


def _write_representative_fixture(root: Path, case: dict[str, object]) -> tuple[Path, Path]:
    dstack_docs.create_foundation(root)
    summary = root / "docs/src/SUMMARY.md"
    summary.write_text(summary.read_text() + str(case["summary"]))
    for relative, content in case["canonical"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    for relative, content in case["external"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    ambiguous = root / str(case["ambiguous"])
    ambiguous.parent.mkdir(parents=True, exist_ok=True)
    ambiguous.write_text("# Placement needs a human decision\n")
    return summary, ambiguous


@pytest.mark.parametrize("shape", REPRESENTATIVE_MIGRATIONS)
def test_representative_project_shapes_migrate_without_semantic_guessing(tmp_path: Path, shape: str) -> None:
    case = REPRESENTATIVE_MIGRATIONS[shape]
    summary, ambiguous = _write_representative_fixture(tmp_path, case)

    plan = dstack_docs.legacy_documentation_plan(tmp_path)
    expected_moves = [
        {
            "source": relative,
            "destination": relative.replace("docs/", "docs/src/", 1),
        }
        for relative in sorted(case["external"])
    ]
    assert plan["referenced_content_moves"] == expected_moves
    assert plan["unresolved_outside_markdown"] == [str(case["ambiguous"])]
    assert plan["manual_actions"] == [
        {
            "path": case["ambiguous"],
            "action": "choose a docs/src chapter, move the file, update SUMMARY.md, and rerun setup",
        }
    ]

    original = {relative: (tmp_path / relative).read_bytes() for relative in case["external"]}
    migrated = dstack_docs.migrate_legacy_documentation(tmp_path)
    assert migrated["referenced_content_moves"] == expected_moves
    assert migrated["unresolved_outside_markdown"] == [str(case["ambiguous"])]
    for relative, content in original.items():
        destination = tmp_path / relative.replace("docs/", "docs/src/", 1)
        assert destination.read_bytes() == content
        assert not (tmp_path / relative).exists()
    assert "../legacy/" not in summary.read_text()
    assert ambiguous.is_file()

    manual_destination = tmp_path / str(case["manual_destination"])
    manual_destination.parent.mkdir(parents=True, exist_ok=True)
    ambiguous.replace(manual_destination)
    summary.write_text(
        summary.read_text() + f"- [Manual notes]({manual_destination.relative_to(tmp_path / 'docs/src')})\n"
    )
    converged = dstack_docs.legacy_documentation_plan(tmp_path)
    assert converged["referenced_content_moves"] == []
    assert converged["unresolved_outside_markdown"] == []
    assert converged["manual_actions"] == []


@pytest.mark.parametrize("shape", REPRESENTATIVE_MIGRATIONS)
def test_representative_migration_conflict_is_fail_closed(tmp_path: Path, shape: str) -> None:
    case = REPRESENTATIVE_MIGRATIONS[shape]
    _write_representative_fixture(tmp_path, case)
    source_relative, source_content = next(iter(case["external"].items()))
    source = tmp_path / source_relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(source_content)
    destination = tmp_path / source_relative.replace("docs/", "docs/src/", 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("authored canonical content\n")

    with pytest.raises(DstackError, match="conflict"):
        dstack_docs.migrate_legacy_documentation(tmp_path)
    assert source.read_text() == source_content
    assert destination.read_text() == "authored canonical content\n"


@pytest.mark.parametrize("shape", REPRESENTATIVE_MIGRATIONS)
def test_setup_repair_reports_and_converges_manual_migration(
    tmp_path: Path, shape: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = REPRESENTATIVE_MIGRATIONS[shape]
    summary, ambiguous = _write_representative_fixture(tmp_path, case)

    class Client:
        def check_version(self) -> str:
            return "bd version 1.2.2 (6c124203e)"

    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(setup, "legacy_template_artifacts", lambda client: [])
    monkeypatch.setattr(setup, "_normalize_current_workflows", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "missing_feature_reconciliations", lambda client: [])
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    monkeypatch.setattr(setup, "ensure_interaction_log_policy", lambda root: {})
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})

    first = setup.repair_legacy(tmp_path, force=True)
    assert first["status"] == "manual-action-required"
    assert first["documentation_migration"]["unresolved_outside_markdown"] == [str(case["ambiguous"])]
    assert first["documentation_migration"]["manual_actions"] == [
        {
            "path": str(case["ambiguous"]),
            "action": dstack_docs.MANUAL_MIGRATION_ACTION,
        }
    ]

    manual_destination = tmp_path / str(case["manual_destination"])
    manual_destination.parent.mkdir(parents=True, exist_ok=True)
    ambiguous.replace(manual_destination)
    summary.write_text(
        summary.read_text() + f"- [Manual notes]({manual_destination.relative_to(tmp_path / 'docs/src')})\n"
    )

    second = setup.repair_legacy(tmp_path, force=True)
    assert second["status"] == "ok"
    assert second["documentation_migration"]["unresolved_outside_markdown"] == []
    assert second["documentation_migration"]["manual_actions"] == []


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


def test_migration_refuses_dot_source_without_mutation(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    source = docs / "src"
    source.mkdir(parents=True)
    book = docs / "book.toml"
    book.write_text('[book]\nsrc = "."\n')
    existing = source / "existing.md"
    existing.write_text("existing\n")

    with pytest.raises(DstackError, match='src = "."'):
        dstack_docs.migrate_legacy_documentation(tmp_path)

    assert book.is_file()
    assert existing.read_text() == "existing\n"
    assert not (source / "book.toml").exists()
    assert not (source / "src").exists()


def test_configured_source_migration_preflights_all_documentation_symlinks(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    legacy = docs / "book"
    canonical = docs / "src"
    legacy.mkdir(parents=True)
    canonical.mkdir()
    book = docs / "book.toml"
    book.write_text('[book]\nsrc = "book"\n')
    chapter = legacy / "SUMMARY.md"
    chapter.write_text("# Summary\n")
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n")
    (canonical / "link.md").symlink_to(outside)

    with pytest.raises(DstackError, match="symlink"):
        dstack_docs.migrate_legacy_documentation(tmp_path)

    assert book.read_text() == '[book]\nsrc = "book"\n'
    assert chapter.read_text() == "# Summary\n"
    assert outside.read_text() == "outside\n"


def test_generic_migration_refuses_canonical_markdown_symlink_without_mutation(
    tmp_path: Path,
) -> None:
    dstack_docs.create_foundation(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n")
    (tmp_path / "docs/src/link.md").symlink_to(outside)

    with pytest.raises(DstackError, match="symlink"):
        dstack_docs.migrate_legacy_documentation(tmp_path)

    assert outside.read_text() == "outside\n"
    assert (tmp_path / "docs/src/link.md").is_symlink()


def test_known_file_migration_refuses_symlink_without_mutation(tmp_path: Path) -> None:
    source = tmp_path / "docs/src/real.md"
    source.parent.mkdir(parents=True)
    source.write_text("real\n")
    link = source.with_name("link.md")
    link.symlink_to(source.name)

    with pytest.raises(DstackError, match="symlink"):
        dstack_docs.migrate_known_documentation_file(tmp_path, "docs/src/link.md", "docs/src/moved.md")

    assert source.read_text() == "real\n"
    assert link.is_symlink()
    assert not source.with_name("moved.md").exists()


def test_validation_ignores_link_and_include_syntax_inside_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dstack_docs.create_foundation(tmp_path)
    index = tmp_path / "docs/src/index.md"
    index.write_text(
        "# Project\n\n"
        "Inline examples: `[missing](missing.md)` and `{{#include missing.md}}`.\n\n"
        "Multiline code: `first line\n[missing](multiline.md)`.\n\n"
        "Exact delimiter: ``code with ` and {{#include exact.md}}``.\n\n"
        "```markdown\n"
        "[also missing](also-missing.md)\n"
        "{{#include also-missing.md}}\n"
        "```\n\n"
        r"Escaped examples: \[missing](escaped.md) and \{{#include escaped.md}}."
        "\n"
    )
    fake_mdbook(monkeypatch)

    assert dstack_docs.validate_docs(tmp_path)["status"] == "ok"


def test_even_backslashes_do_not_hide_real_markdown_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dstack_docs.create_foundation(tmp_path)
    index = tmp_path / "docs/src/index.md"
    index.write_text("# Project\n\n" + r"\\[Missing](missing.md)" + "\n")
    fake_mdbook(monkeypatch)

    with pytest.raises(DstackError, match="missing.md"):
        dstack_docs.validate_docs(tmp_path)


def test_validation_still_checks_real_include_outside_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dstack_docs.create_foundation(tmp_path)
    index = tmp_path / "docs/src/index.md"
    index.write_text("# Project\n\n{{#include missing.md}}\n")
    fake_mdbook(monkeypatch)

    with pytest.raises(DstackError, match="missing.md"):
        dstack_docs.validate_docs(tmp_path)


def test_repository_book_passes_dstack_validation() -> None:
    assert dstack_docs.validate_docs(ROOT, mdbook="/usr/bin/true")["status"] == "ok"
