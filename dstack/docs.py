"""Feature-scoped documentation export and structural validation."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

from .core import (
    BeadsClient,
    DstackError,
    _assert_no_symlink_components,
    feature_identity,
    feature_steps,
    read_utf8_text,
    require_feature_worktree,
    serialized_repository_mutation,
)
from .output import emit
from .policy import markdown_sections

INCLUDE_PATTERN = re.compile(r"\{\{#include\s+([^}\s]+)[^}]*\}\}")
FEATURE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def markdown_links(text: str) -> list[str]:
    """Return rendered link destinations, including reference-style links."""
    return [
        str(child.attrGet("href"))
        for token in MarkdownIt("commonmark").parse(text)
        for child in token.children or ()
        if child.type == "link_open"
    ]


def markdown_includes(text: str) -> list[str]:
    return [
        match.group(1)
        for token in MarkdownIt("commonmark").parse(text)
        for child in token.children or ()
        if child.type == "text"
        for match in INCLUDE_PATTERN.finditer(child.content)
    ]


def _feature_paths(root: Path, feature: str) -> tuple[Path, Path, Path, Path]:
    if not FEATURE_SLUG.fullmatch(feature):
        raise DstackError(f"invalid feature slug: {feature!r}")
    repository = root.expanduser().resolve()
    source = repository / "docs" / "src"
    directory = source / "features" / feature
    for path, purpose in (
        (repository, "repository root"),
        (repository / "docs", "documentation directory"),
        (source, "documentation source"),
        (source / "features", "feature documentation root"),
        (directory, "feature documentation directory"),
    ):
        _assert_no_symlink_components(path, purpose=purpose)
    return source / "SUMMARY.md", directory / "index.md", directory / "design.md", repository


def _regular_file(path: Path, purpose: str) -> str:
    _assert_no_symlink_components(path, purpose=purpose)
    if path.is_symlink() or not path.is_file():
        raise DstackError(f"{purpose} must be a regular file: {path}")
    return read_utf8_text(path, purpose=purpose)


def _meaningful_section(index: str, title: str) -> bool:
    matches = [section for section in markdown_sections(index) if section.title.casefold() == title.casefold()]
    return (
        len(matches) == 1
        and matches[0].level == 2
        and len(matches[0].content.strip()) >= 12
    )


def validate_docs(root: Path, *, feature: str, expected_design: str | None = None) -> dict[str, object]:
    summary_path, index_path, design_path, repository = _feature_paths(root, feature)
    summary = _regular_file(summary_path, "documentation summary")
    index = _regular_file(index_path, "feature index")
    design = _regular_file(design_path, "feature design")

    errors: list[str] = []
    if not design.strip():
        errors.append("feature design must not be empty")
    if expected_design is not None and design != expected_design:
        errors.append("feature design differs from the native plan; export the accepted design again")
    first_content = next((line.strip() for line in index.splitlines() if line.strip()), "")
    if not re.fullmatch(r"#\s+\S.+", first_content):
        errors.append("feature index must begin with one level-one title")
    for title in ("Overview", "User Impact"):
        if not _meaningful_section(index, title):
            errors.append(f"feature index requires one meaningful level-two {title} section")

    implemented = [
        section
        for section in markdown_sections(index)
        if section.title.casefold() == "implemented design" and section.level == 2
    ]
    includes = markdown_includes(index)
    if len(implemented) != 1 or includes != ["design.md"] or "{{#include design.md}}" not in implemented[0].content:
        errors.append("Implemented Design must contain exactly one native include of design.md")
    if INCLUDE_PATTERN.search(design):
        errors.append("feature design must not contain active mdBook directives")

    targets = markdown_links(summary)
    index_target = f"features/{feature}/index.md"
    design_target = f"features/{feature}/design.md"
    if targets.count(index_target) != 1:
        errors.append(f"feature requires exactly one SUMMARY link to {index_target}")
    if design_target in targets:
        errors.append(f"SUMMARY must not link directly to {design_target}")
    if errors:
        raise DstackError("documentation validation failed: " + "; ".join(errors))

    return {
        "status": "ok",
        "feature": feature,
        "index": index_path.relative_to(repository).as_posix(),
        "design": design_path.relative_to(repository).as_posix(),
    }


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_components(path.parent, purpose="feature documentation directory")
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise DstackError(f"cannot export feature design: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def export_design(
    root: Path,
    selector: str,
    *,
    client: BeadsClient | None = None,
    scaffold: bool = False,
) -> dict[str, str]:
    repository = root.expanduser().resolve()
    if client is None:
        from .commands import client_for

        client = client_for(repository)
        repository = client.root
    feature_root, slug, _ = feature_identity(client, selector)
    repository = require_feature_worktree(client, f"feat/{slug}")
    plan = client.show(str(feature_steps(client, str(feature_root["id"]))["plan"]["id"]))
    design = plan.get("design")
    if not isinstance(design, str) or not design.strip():
        raise DstackError(f"plan Bead {plan.get('id')} has no design to export")
    if INCLUDE_PATTERN.search(design):
        raise DstackError("feature design must not contain active mdBook directives")
    summary, index, target, repository = _feature_paths(repository, slug)
    # Preflight all optional scaffolding before exporting. Existing prose is never replaced.
    if scaffold:
        for path, purpose in ((index, "feature index"), (summary, "documentation summary")):
            _assert_no_symlink_components(path, purpose=purpose)
            if path.exists():
                _regular_file(path, purpose)
        summary_text = _regular_file(summary, "documentation summary") if summary.exists() else "# Summary\n"
        index_target = f"features/{slug}/index.md"
        targets = markdown_links(summary_text)
        if targets.count(index_target) > 1 or f"features/{slug}/design.md" in targets:
            raise DstackError("repair duplicate or direct-design SUMMARY links before scaffolding")
    _assert_no_symlink_components(target, purpose="feature design")
    _atomic_write(target, design)
    if scaffold:
        if not index.exists():
            _atomic_write(
                index,
                f"# {slug}\n\n## Overview\n\n## User Impact\n\n"
                "## Implemented Design\n\n{{#include design.md}}\n",
            )
        if index_target not in targets:
            _atomic_write(summary, summary_text.rstrip() + f"\n\n- [{slug}]({index_target})\n")
    return {
        "status": "ok",
        "feature": str(feature_root["id"]),
        "slug": slug,
        "plan": str(plan["id"]),
        "path": target.relative_to(repository).as_posix(),
    }


def cmd_docs_validate(args: object) -> int:
    emit(validate_docs(Path(getattr(args, "root")), feature=str(getattr(args, "slug"))))
    return 0


@serialized_repository_mutation
def cmd_docs_export(args: object) -> int:
    emit(
        export_design(
            Path(getattr(args, "root")),
            str(getattr(args, "bead")),
            scaffold=bool(getattr(args, "scaffold", False)),
        )
    )
    return 0
