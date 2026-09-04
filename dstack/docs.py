"""Feature-scoped documentation export and structural validation."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .core import (
    BeadsClient,
    DstackError,
    _assert_no_symlink_components,
    feature_identity,
    feature_steps,
    read_utf8_text,
)
from .output import emit
from .policy import markdown_sections

LINK_PATTERN = re.compile(r"!?\[[^]]*\]\((.+)\)")
INCLUDE_PATTERN = re.compile(r"\{\{#include\s+([^}\s]+)[^}]*\}\}")
FENCE_PATTERN = re.compile(r"^( {0,3})(`{3,}|~{3,})")
FEATURE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _is_escaped(text: str, index: int) -> bool:
    count = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        count += 1
        index -= 1
    return count % 2 == 1


def _mask_markdown_code(text: str) -> str:
    """Mask fenced and inline code while preserving offsets and line breaks."""

    masked = list(text)
    offset = 0
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        match = FENCE_PATTERN.match(plain)
        opened = False
        if fence is None and match:
            marker = match.group(2)
            fence = (marker[0], len(marker))
            opened = True
        if fence is not None:
            for index in range(offset, offset + len(line)):
                if masked[index] not in "\r\n":
                    masked[index] = " "
            if (
                not opened
                and match
                and match.group(2)[0] == fence[0]
                and len(match.group(2)) >= fence[1]
                and plain[match.end() :].strip() == ""
            ):
                fence = None
        offset += len(line)

    masked_text = "".join(masked)
    index = 0
    while index < len(masked_text):
        if masked_text[index] != "`" or _is_escaped(masked_text, index):
            index += 1
            continue
        width = 1
        while index + width < len(masked_text) and masked_text[index + width] == "`":
            width += 1
        cursor = index + width
        closed = False
        while cursor < len(masked_text):
            cursor = masked_text.find("`", cursor)
            if cursor < 0:
                break
            closing = 1
            while cursor + closing < len(masked_text) and masked_text[cursor + closing] == "`":
                closing += 1
            if closing == width:
                for position in range(index, cursor + width):
                    if masked[position] not in "\r\n":
                        masked[position] = " "
                index = cursor + width
                closed = True
                break
            cursor += closing
        if not closed:
            index += width
    return "".join(masked)


def _link_target_spans(text: str) -> list[tuple[int, int]]:
    masked = _mask_markdown_code(text)
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(masked):
        syntax = index
        if masked[index] == "!":
            if _is_escaped(masked, index) or index + 1 >= len(masked) or masked[index + 1] != "[":
                index += 1
                continue
            index += 1
        if masked[index] != "[" or _is_escaped(masked, index):
            index = syntax + 1
            continue

        label_end = index + 1
        while label_end < len(masked):
            if masked[label_end] == "]" and not _is_escaped(masked, label_end):
                break
            label_end += 1
        if label_end >= len(masked) or label_end + 1 >= len(masked) or masked[label_end + 1] != "(":
            index = syntax + 1
            continue

        target_start = label_end + 2
        cursor = target_start
        depth = 1
        while cursor < len(masked):
            if _is_escaped(masked, cursor):
                cursor += 1
                continue
            if masked[cursor] == "(":
                depth += 1
            elif masked[cursor] == ")":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        if depth == 0 and cursor > target_start:
            spans.append((target_start, cursor))
            index = cursor + 1
        else:
            index = syntax + 1
    return spans


def markdown_values(text: str, pattern: re.Pattern[str]) -> list[str]:
    if pattern is LINK_PATTERN:
        return [text[start:end] for start, end in _link_target_spans(text)]
    masked = _mask_markdown_code(text)
    return [match.group(1) for match in pattern.finditer(masked) if not _is_escaped(masked, match.start())]


def _raw_target(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


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
    return len(matches) == 1 and matches[0].level == 2 and len(matches[0].content.strip()) >= 12


def validate_docs(root: Path, *, feature: str) -> dict[str, object]:
    summary_path, index_path, design_path, repository = _feature_paths(root, feature)
    summary = _regular_file(summary_path, "documentation summary")
    index = _regular_file(index_path, "feature index")
    design = _regular_file(design_path, "feature design")

    errors: list[str] = []
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
    includes = markdown_values(index, INCLUDE_PATTERN)
    if len(implemented) != 1 or includes != ["design.md"] or "{{#include design.md}}" not in implemented[0].content:
        errors.append("Implemented Design must contain exactly one native include of design.md")
    if INCLUDE_PATTERN.search(design):
        errors.append("feature design must not contain active mdBook directives")

    targets = [_raw_target(value) for value in markdown_values(summary, LINK_PATTERN)]
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
) -> dict[str, str]:
    repository = root.expanduser().resolve()
    if client is None:
        from .commands import client_for

        client = client_for(repository)
        repository = client.root
    feature_root, slug, _ = feature_identity(client, selector)
    plan = client.show(str(feature_steps(client, str(feature_root["id"]))["plan"]["id"]))
    design = plan.get("design")
    if not isinstance(design, str) or not design:
        raise DstackError(f"plan Bead {plan.get('id')} has no design to export")
    _, _, target, repository = _feature_paths(repository, slug)
    _atomic_write(target, design)
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


def cmd_docs_export(args: object) -> int:
    emit(export_design(Path(getattr(args, "root")), str(getattr(args, "feature"))))
    return 0
