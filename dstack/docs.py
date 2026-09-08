"""Feature-scoped documentation export and structural validation."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

from .beads import BeadsClient, client_for
from .core import DstackError, _assert_no_symlink_components, read_utf8_text, run
from .git_state import require_feature_worktree, serialized_repository_mutation
from .workflow import feature_identity, feature_steps
from .output import emit
from .policy import markdown_sections

MDBOOK_HELPER_PATTERN = re.compile(
    r"(?<!\\)\{\{\s*#\s*(include|rustdoc_include|playground|playpen)\s+([^}\s]+)[^}]*\}\}",
    re.IGNORECASE,
)
INCLUDE_PATTERN = re.compile(r"(?<!\\)\{\{\s*#\s*include\s+([^}\s]+)[^}]*\}\}", re.IGNORECASE)
FEATURE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def markdown_links(text: str) -> list[str]:
    """Return rendered link destinations, including reference-style links."""
    return [
        str(child.attrGet("href"))
        for token in MarkdownIt("commonmark").parse(text)
        for child in token.children or ()
        if child.type == "link_open"
    ]


def publication_changed(root: Path, base: str, head: str, slug: str) -> bool:
    """Report whether this feature publication differs from the inherited base state."""

    changed = run(
        ["git", "diff", "--name-only", "-z", f"{base}...{head}", "--", f"docs/src/features/{slug}"], cwd=root
    ).stdout
    if changed:
        return True
    ancestor = run(["git", "merge-base", base, head], cwd=root).stdout.strip()
    summary = run(["git", "show", f"{ancestor}:docs/src/SUMMARY.md"], cwd=root, check=False)
    # Current publication is validated separately. Unrelated SUMMARY changes do
    # not require a close commit when this feature's navigation already existed.
    return summary.returncode != 0 or markdown_links(summary.stdout).count(f"features/{slug}/index.md") != 1


def markdown_includes(text: str) -> list[str]:
    """Return active mdBook include targets from raw chapter input.

    mdBook expands helpers before Markdown rendering, including helpers inside
    fenced code blocks. A leading backslash escapes a helper.
    """
    return [match.group(1) for match in INCLUDE_PATTERN.finditer(text)]


def markdown_file_helpers(text: str) -> list[tuple[str, str]]:
    """Return active mdBook helpers that can read another file."""
    return [(match.group(1).casefold(), match.group(2)) for match in MDBOOK_HELPER_PATTERN.finditer(text)]


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


def _nonempty_section(index: str, title: str) -> bool:
    matches = [section for section in markdown_sections(index) if section.title.casefold() == title.casefold()]
    return len(matches) == 1 and matches[0].level == 2 and bool(matches[0].content.strip())


def _validate_docs_content(
    *,
    feature: str,
    summary: str,
    index: str,
    design: str,
    expected_design: str | None,
    index_name: str,
    design_name: str,
) -> dict[str, object]:
    errors: list[str] = []
    if not design.strip():
        errors.append("feature design must not be empty")
    if expected_design is not None and design != expected_design:
        errors.append("feature design differs from the native plan; export the accepted design again")
    first_content = next((line.strip() for line in index.splitlines() if line.strip()), "")
    if not re.fullmatch(r"#\s+\S.+", first_content):
        errors.append("feature index must begin with one level-one title")
    for title in ("Overview", "User Impact"):
        if not _nonempty_section(index, title):
            errors.append(f"feature index requires one nonempty level-two {title} section")

    implemented = [
        section
        for section in markdown_sections(index)
        if section.title.casefold() == "implemented design" and section.level == 2
    ]
    helpers = markdown_file_helpers(index)
    if (
        len(implemented) != 1
        or helpers != [("include", "design.md")]
        or "{{#include design.md}}" not in implemented[0].content
    ):
        errors.append("Implemented Design must contain exactly one native include of design.md")
    if markdown_file_helpers(design):
        errors.append("feature design must not contain active mdBook file directives")

    targets = markdown_links(summary)
    index_target = f"features/{feature}/index.md"
    design_target = f"features/{feature}/design.md"
    if targets.count(index_target) != 1:
        errors.append(f"feature requires exactly one SUMMARY link to {index_target}")
    if design_target in targets:
        errors.append(f"SUMMARY must not link directly to {design_target}")
    if errors:
        raise DstackError("documentation validation failed: " + "; ".join(errors))

    return {"status": "ok", "feature": feature, "index": index_name, "design": design_name}


def validate_docs(root: Path, *, feature: str, expected_design: str | None = None) -> dict[str, object]:
    summary_path, index_path, design_path, repository = _feature_paths(root, feature)
    return _validate_docs_content(
        feature=feature,
        summary=_regular_file(summary_path, "documentation summary"),
        index=_regular_file(index_path, "feature index"),
        design=_regular_file(design_path, "feature design"),
        expected_design=expected_design,
        index_name=index_path.relative_to(repository).as_posix(),
        design_name=design_path.relative_to(repository).as_posix(),
    )


def _git_text(root: Path, revision: str, path: str, *, purpose: str) -> str:
    entry = run(["git", "ls-tree", "-z", revision, "--", path], cwd=root, check=False)
    if entry.returncode or not entry.stdout:
        raise DstackError(f"{purpose} is missing from Git revision {revision}: {path}")
    record = entry.stdout.rstrip("\0")
    metadata, separator, recorded_path = record.partition("\t")
    fields = metadata.split()
    if not separator or recorded_path != path or len(fields) != 3 or fields[1] != "blob":
        raise DstackError(f"{purpose} is not a regular Git file at revision {revision}: {path}")
    if fields[0] == "120000":
        raise DstackError(f"{purpose} must not be a symlink in Git revision {revision}: {path}")
    content = run(["git", "show", f"{revision}:{path}"], cwd=root, check=False)
    if content.returncode:
        raise DstackError(f"cannot read {purpose} from Git revision {revision}: {path}")
    try:
        return content.stdout.encode("utf-8", errors="surrogateescape").decode("utf-8")
    except UnicodeError as exc:
        raise DstackError(f"cannot decode {purpose} from Git revision {revision}: {path}") from exc


def validate_docs_revision(
    root: Path, *, feature: str, revision: str, expected_design: str | None = None
) -> dict[str, object]:
    """Validate the exact documentation tree stored by Git at revision."""
    if not FEATURE_SLUG.fullmatch(feature):
        raise DstackError(f"invalid feature slug: {feature!r}")
    repository = root.expanduser().resolve()
    summary = "docs/src/SUMMARY.md"
    index = f"docs/src/features/{feature}/index.md"
    design = f"docs/src/features/{feature}/design.md"
    return _validate_docs_content(
        feature=feature,
        summary=_git_text(repository, revision, summary, purpose="documentation summary"),
        index=_git_text(repository, revision, index, purpose="feature index"),
        design=_git_text(repository, revision, design, purpose="feature design"),
        expected_design=expected_design,
        index_name=index,
        design_name=design,
    )


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


def _scaffold_index(text: str, slug: str) -> str:
    """Insert unambiguous missing structure; never rewrite or rearrange prose."""
    if not text.strip():
        text = f"# {slug}\n"
    lines = text.splitlines(keepends=True)
    tokens = MarkdownIt("commonmark").parse(text)
    headings = [
        (token.map[0], int(token.tag[1:]), tokens[position + 1].content.strip().casefold())
        for position, token in enumerate(tokens)
        if token.type == "heading_open" and token.level == 0 and token.map is not None
    ]
    titles = ("Overview", "User Impact", "Implemented Design")
    positions: dict[str, int] = {}
    for title in titles:
        matches = [(start, level) for start, level, name in headings if name == title.casefold()]
        if len(matches) > 1 or (matches and matches[0][1] != 2):
            raise DstackError(f"repair duplicate or non-level-two {title} headings before scaffolding")
        if matches:
            positions[title] = matches[0][0]

    includes = markdown_includes(text)
    implemented = next(
        (section for section in markdown_sections(text) if section.title.casefold() == "implemented design"),
        None,
    )
    if includes and (
        includes != ["design.md"] or implemented is None or "{{#include design.md}}" not in implemented.content
    ):
        raise DstackError("repair duplicate, noncanonical, or misplaced design includes before scaffolding")

    additions: dict[int, list[str]] = {}
    for order, title in enumerate(titles):
        if title not in positions:
            insert_at = min(
                (positions[later] for later in titles[order + 1 :] if later in positions), default=len(lines)
            )
            content = f"## {title}\n"
            if title == "Implemented Design":
                content += "\n{{#include design.md}}\n"
            additions.setdefault(insert_at, []).append(content)
    if "Implemented Design" in positions and not includes:
        start = positions["Implemented Design"]
        end = next((line for line, level, _ in headings if line > start and level <= 2), len(lines))
        additions.setdefault(end, []).append("{{#include design.md}}\n")

    # Reverse insertion keeps source offsets valid and every existing line intact.
    for position in sorted(additions, reverse=True):
        suffix = "\n" if position < len(lines) else ""
        lines[position:position] = ["\n\n" + "\n".join(additions[position]) + suffix]
    return "".join(lines)


def export_design(
    root: Path,
    selector: str,
    *,
    client: BeadsClient | None = None,
    scaffold: bool = False,
) -> dict[str, str]:
    repository = root.expanduser().resolve()
    if client is None:
        client = client_for(repository)
        repository = client.root
    feature_root, slug, _ = feature_identity(client, selector)
    repository = require_feature_worktree(client, f"feat/{slug}")
    plan = client.show(str(feature_steps(client, str(feature_root["id"]))["plan"]["id"]))
    design = plan.get("design")
    if not isinstance(design, str) or not design.strip():
        raise DstackError(f"plan Bead {plan.get('id')} has no design to export")
    if markdown_file_helpers(design):
        raise DstackError("feature design must not contain active mdBook file directives")
    summary, index, target, repository = _feature_paths(repository, slug)
    # Preflight all optional scaffolding before exporting. Existing prose is never replaced.
    if scaffold:
        for path, purpose in ((index, "feature index"), (summary, "documentation summary")):
            _assert_no_symlink_components(path, purpose=purpose)
        index_text = _regular_file(index, "feature index") if index.exists() else ""
        scaffolded_index = _scaffold_index(index_text, slug)
        summary_text = _regular_file(summary, "documentation summary") if summary.exists() else "# Summary\n"
        index_target = f"features/{slug}/index.md"
        targets = markdown_links(summary_text)
        if targets.count(index_target) > 1 or f"features/{slug}/design.md" in targets:
            raise DstackError("repair duplicate or direct-design SUMMARY links before scaffolding")
    _assert_no_symlink_components(target, purpose="feature design")
    _atomic_write(target, design)
    if scaffold:
        if scaffolded_index != index_text:
            _atomic_write(index, scaffolded_index)
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
