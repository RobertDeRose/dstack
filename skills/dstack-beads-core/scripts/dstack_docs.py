"""Canonical mdBook foundation, migration, and stateless validation."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from dstack_commands import emit
from dstacklib import DstackError, run

LINK_PATTERN = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
INCLUDE_PATTERN = re.compile(r"\{\{#include\s+([^}\s]+)[^}]*\}\}")
FENCE_PATTERN = re.compile(r"^( {0,3})(`{3,}|~{3,})")

CORE_NAVIGATION = (
    ("Project", "index.md"),
    ("Architecture", "architecture/index.md"),
    ("Development", "development/index.md"),
    ("Documentation", "development/documentation.md"),
    ("Feature Records", "features/index.md"),
)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _mask_markdown_code(text: str) -> str:
    """Replace Markdown code with spaces while preserving offsets and newlines."""

    masked = list(text)
    lines = text.splitlines(keepends=True)
    offset = 0
    fence: tuple[str, int] | None = None
    for line in lines:
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
        run = 1
        while index + run < len(masked_text) and masked_text[index + run] == "`":
            run += 1
        end = index + run
        while end < len(masked_text):
            end = masked_text.find("`", end)
            if end < 0:
                break
            closing = 1
            while end + closing < len(masked_text) and masked_text[end + closing] == "`":
                closing += 1
            if closing == run:
                for position in range(index, end + run):
                    if masked[position] not in "\r\n":
                        masked[position] = " "
                index = end + run
                break
            end += closing
        else:
            index += run
            continue
        if end < 0:
            index += run
    return "".join(masked)


def _markdown_matches(text: str, pattern: re.Pattern[str]) -> tuple[str, list[re.Match[str]]]:
    masked = _mask_markdown_code(text)
    matches = []
    for match in pattern.finditer(masked):
        syntax = match.start()
        if pattern is LINK_PATTERN and masked[syntax] == "!":
            if _is_escaped(masked, syntax) or _is_escaped(masked, syntax + 1):
                continue
        elif _is_escaped(masked, syntax):
            continue
        matches.append(match)
    return masked, matches


def _markdown_values(text: str, pattern: re.Pattern[str]) -> list[str]:
    _, matches = _markdown_matches(text, pattern)
    return [match.group(1) for match in matches]


def _rewrite_markdown_values(
    text: str,
    pattern: re.Pattern[str],
    transform: Any,
) -> str:
    _, matches = _markdown_matches(text, pattern)
    for match in reversed(matches):
        replacement = transform(text[match.start(1) : match.end(1)])
        text = text[: match.start(1)] + replacement + text[match.end(1) :]
    return text


def foundation_files(project: str) -> dict[str, str]:
    title = project.replace("-", " ").replace("_", " ").strip().title() or "Project"
    return {
        "docs/book.toml": (f'[book]\ntitle = {json.dumps(title)}\nlanguage = "en"\nsrc = "src"\n'),
        "docs/src/SUMMARY.md": (
            "# Summary\n\n"
            "- [Project](index.md)\n"
            "- [Architecture](architecture/index.md)\n"
            "- [Development](development/index.md)\n"
            "  - [Documentation](development/documentation.md)\n"
            "- [Feature Records](features/index.md)\n"
        ),
        "docs/src/index.md": (
            f"# {title}\n\n"
            f"This book documents {title} for users, operators, developers, "
            "reviewers, and future maintainers.\n"
        ),
        "docs/src/architecture/index.md": (
            "# Architecture\n\n"
            "Describe the current system, its components, relationships, "
            "boundaries, and durable invariants here.\n"
        ),
        "docs/src/development/index.md": (
            "# Development\n\nDescribe how to build, test, change, validate, and release this project here.\n"
        ),
        "docs/src/development/documentation.md": (
            "# Documentation\n\n"
            "Put documentation where a reader would look based on the question "
            "they are trying to answer. Keep current product behavior in current "
            "architecture, user, operator, development, and reference pages; "
            "keep accepted change intent and delivery reconciliation in feature "
            "records. Humans and agents use the same durable documentation.\n"
        ),
        "docs/src/features/index.md": (
            "# Feature Records\n\n"
            "Feature records preserve accepted change intent and reconcile it "
            "with delivered behavior. Current product guidance belongs in the "
            "sections where readers look for that behavior.\n"
        ),
    }


def _inside(path: Path, parent: Path, message: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise DstackError(message) from exc
    return resolved


def _book_source_value(book: Path) -> str:
    try:
        payload = tomllib.loads(book.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DstackError(f"invalid mdBook configuration: {book}") from exc
    table = payload.get("book", {})
    if not isinstance(table, dict):
        raise DstackError("mdBook [book] configuration must be a table")
    raw = table.get("src", "src")
    if not isinstance(raw, str) or not raw.strip():
        raise DstackError("mdBook [book].src must be a non-empty relative path")
    return raw.strip()


def configured_source(root: Path) -> tuple[str, Path]:
    root = root.resolve()
    docs = _inside(root / "docs", root, "documentation directory escapes repository")
    book = docs / "book.toml"
    if not book.is_file() or book.is_symlink():
        raise DstackError("docs/book.toml must be a regular file")
    raw = _book_source_value(book)
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise DstackError("mdBook [book].src must stay within docs")
    lexical_source = docs / relative
    current = docs
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DstackError("mdBook [book].src must not traverse symlinks")
    source = lexical_source.resolve()
    try:
        source.relative_to(docs.resolve())
    except ValueError as exc:
        raise DstackError("mdBook [book].src must stay within docs") from exc
    return raw, source


def _rewrite_book_src(book: Path) -> None:
    text = book.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    in_book = False
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_book = stripped == "[book]"
            continue
        if in_book and re.match(r"^\s*src\s*=", line):
            ending = "\n" if line.endswith("\n") else ""
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f'{indent}src = "src"{ending}'
            replaced = True
            break
    if not replaced:
        # Missing src already means mdBook's default "src"; no rewrite needed.
        return
    book.write_text("".join(lines), encoding="utf-8")


def _summary_link_target(raw: str) -> str | None:
    target = urlsplit(_raw_target(raw))
    if target.scheme or target.netloc or not target.path:
        return None
    normalized = Path(unquote(target.path)).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def ensure_core_navigation(root: Path) -> list[str]:
    """Add missing canonical pages without rewriting project-owned navigation."""

    root = root.resolve()
    summary = root / "docs/src/SUMMARY.md"
    if summary.is_symlink() or not summary.is_file():
        raise DstackError("documentation foundation path is not a regular file: docs/src/SUMMARY.md")

    original = summary.read_text(encoding="utf-8")
    targets = {
        target for raw in _markdown_values(original, LINK_PATTERN) if (target := _summary_link_target(raw)) is not None
    }
    missing = [(label, target) for label, target in CORE_NAVIGATION if target not in targets]
    if not missing:
        return []

    lines = original.rstrip("\n").splitlines()
    for label, target in missing:
        if target == "development/documentation.md":
            continue
        lines.append(f"- [{label}]({target})")

    if "development/documentation.md" not in targets:
        parent = next(
            (
                index
                for index, line in enumerate(lines)
                if "development/index.md" in _markdown_values(line, LINK_PATTERN)
            ),
            None,
        )
        entry = "  - [Documentation](development/documentation.md)"
        if parent is None:
            lines.append(entry.lstrip())
        else:
            indentation = lines[parent][: len(lines[parent]) - len(lines[parent].lstrip())]
            lines.insert(parent + 1, indentation + entry)
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [target for _, target in missing]


def create_foundation(root: Path) -> list[str]:
    root = root.resolve()
    created: list[str] = []
    for relative, content in foundation_files(root.name).items():
        path = root / relative
        _inside(path.parent, root, "documentation foundation path escapes repository")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(content)
            created.append(relative)
        except FileExistsError:
            if path.is_symlink() or not path.is_file():
                raise DstackError(f"documentation foundation path is not a regular file: {relative}")
    ensure_core_navigation(root)
    return created


def require_mdbook() -> str:
    executable = shutil.which("mdbook")
    if not executable:
        raise DstackError("mdbook executable is required on PATH")
    return executable


def _raw_target(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _target_parts(value: str) -> tuple[str, str, bool]:
    stripped = value.strip()
    if stripped.startswith("<") and ">" in stripped:
        end = stripped.index(">")
        return stripped[1:end], stripped[end + 1 :], True
    parts = stripped.split(maxsplit=1)
    return parts[0], (" " + parts[1] if len(parts) == 2 else ""), False


def _rewritten_target(value: str, new_path: str) -> str:
    old_target, tail, angle = _target_parts(value)
    split = urlsplit(old_target)
    rebuilt = new_path
    if split.query:
        rebuilt += f"?{split.query}"
    if split.fragment:
        rebuilt += f"#{split.fragment}"
    return (f"<{rebuilt}>" if angle else rebuilt) + tail


def _local_candidate(source: Path, raw: str) -> Path | None:
    target = urlsplit(_raw_target(raw))
    if target.scheme or target.netloc:
        return None
    path_text = unquote(target.path)
    if not path_text:
        return source.resolve()
    relative = Path(path_text)
    if relative.is_absolute():
        return None
    return (source.parent / relative).resolve()


def _move_file(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise DstackError(f"legacy documentation target is not a safe regular file: {source}")
    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            raise DstackError(f"canonical documentation target is not a regular file: {destination}")
        if source.read_bytes() != destination.read_bytes():
            raise DstackError(f"legacy and canonical documentation targets conflict: {source} -> {destination}")
        source.unlink()
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination)


def _safe_docs_path(root: Path, relative: str, message: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise DstackError(message)
    lexical = root.joinpath(candidate)
    docs = root / "docs"
    try:
        lexical.relative_to(docs)
    except ValueError as exc:
        raise DstackError(message) from exc
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise DstackError(f"documentation migration path traverses a symlink: {relative}")
    return lexical.resolve()


def migrate_known_documentation_file(root: Path, source_relative: str, destination_relative: str) -> None:
    """Move one explicitly identified documentation file through the shared engine."""

    root = root.resolve()
    docs = (root / "docs").resolve()
    source = _safe_docs_path(root, source_relative, "legacy documentation path escapes docs")
    destination = _safe_docs_path(root, destination_relative, "canonical documentation path escapes docs")
    if source == destination:
        if not destination.is_file() or destination.is_symlink():
            raise DstackError("canonical documentation target is missing or unsafe")
        return
    if source.exists():
        source_root = root / "docs/src"
        if source_root.is_dir():
            markdown_files = list(source_root.rglob("*.md"))
            symlinks = [path for path in markdown_files if path.is_symlink()]
            if symlinks:
                raise DstackError("documentation migration source contains a symlink: " + str(symlinks[0]))
            for markdown in markdown_files:
                original = markdown.read_text(encoding="utf-8")

                def rewrite(raw: str) -> str:
                    candidate = _local_candidate(markdown, raw)
                    if candidate != source:
                        return raw
                    target = os.path.relpath(destination, markdown.parent).replace(os.sep, "/")
                    return _rewritten_target(raw, target)

                updated = _rewrite_markdown_values(original, LINK_PATTERN, rewrite)
                updated = _rewrite_markdown_values(
                    updated,
                    INCLUDE_PATTERN,
                    lambda raw: rewrite(_include_path(raw)[0]) + _include_path(raw)[1],
                )
                if updated != original:
                    markdown.write_text(updated, encoding="utf-8")
        _move_file(source, destination)
        _prune_empty_directories(source.parent, docs)
    elif not destination.is_file() or destination.is_symlink():
        raise DstackError("legacy documentation source and canonical target are missing")


def _prune_empty_directories(start: Path, stop: Path) -> None:
    stop = stop.resolve()
    if not start.exists():
        return
    root = start if start.is_dir() else start.parent
    directories = [path for path in root.rglob("*") if path.is_dir()]
    directories.append(root)
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        if directory.resolve() == stop:
            continue
        try:
            directory.rmdir()
        except OSError:
            pass


def _migrate_configured_source(root: Path, *, apply: bool) -> list[dict[str, str]]:
    docs = root / "docs"
    book = docs / "book.toml"
    if not book.is_file() or book.is_symlink():
        return []
    raw, configured = configured_source(root)
    canonical = (docs / "src").resolve()
    if configured == canonical:
        return []
    if configured == docs.resolve():
        raise DstackError(
            'mdBook src = "." cannot be migrated automatically; '
            "move book content under docs/src and rerun /setup-project --force"
        )
    if configured.is_symlink() or not configured.is_dir():
        raise DstackError(f"configured mdBook source does not exist safely: docs/{raw}")

    moves: list[dict[str, str]] = []
    entries = sorted(configured.rglob("*"))
    symlinks = [path for path in entries if path.is_symlink()]
    if symlinks:
        raise DstackError("configured mdBook source contains a symlink: " + str(symlinks[0]))
    files = [path for path in entries if path.is_file()]
    for source in files:
        relative = source.relative_to(configured)
        destination = canonical / relative
        if destination.exists() and (
            destination.is_symlink() or not destination.is_file() or source.read_bytes() != destination.read_bytes()
        ):
            raise DstackError("configured mdBook source conflicts with docs/src at " + relative.as_posix())
        moves.append(
            {
                "source": source.relative_to(root).as_posix(),
                "destination": destination.relative_to(root).as_posix(),
            }
        )

    if apply:
        for move in moves:
            source = root / move["source"]
            destination = root / move["destination"]
            _move_file(source, destination)
        _prune_empty_directories(configured, docs)
        _rewrite_book_src(book)
    return moves


def _include_path(raw: str) -> tuple[str, str]:
    path, separator, suffix = raw.partition(":")
    return path, separator + suffix if separator else ""


def _referenced_content_state(
    root: Path,
) -> tuple[dict[Path, Path], dict[Path, str], list[str]]:
    docs = (root / "docs").resolve()
    source_root = (docs / "src").resolve()
    if not source_root.is_dir():
        return {}, {}, []

    summary = source_root / "SUMMARY.md"
    moves: dict[Path, Path] = {}
    unresolved: set[str] = set()

    def canonical_destination(candidate: Path) -> Path | None:
        try:
            candidate.relative_to(source_root)
            return candidate
        except ValueError:
            pass
        try:
            return source_root / candidate.relative_to(docs)
        except ValueError:
            return None

    # A SUMMARY entry gives deterministic chapter placement, so any local file
    # it names under docs/ can be moved while preserving that navigation.
    if summary.is_file():
        for raw in _markdown_values(summary.read_text(encoding="utf-8"), LINK_PATTERN):
            candidate = _local_candidate(summary, raw)
            if candidate is None:
                continue
            destination = canonical_destination(candidate)
            if destination is None or destination == candidate:
                continue
            if candidate.exists() or destination.exists():
                moves[candidate] = destination

    queue = list(sorted(source_root.rglob("*.md")))
    queue.extend(source for source in moves if source.suffix.casefold() == ".md" and source.exists())
    scanned: set[Path] = set()
    while queue:
        queued = queue.pop(0)
        if queued.is_symlink():
            raise DstackError("documentation migration source contains a symlink: " + str(queued))
        path = queued.resolve()
        if path in scanned or not path.is_file():
            continue
        scanned.add(path)
        text = path.read_text(encoding="utf-8")

        for raw in _markdown_values(text, INCLUDE_PATTERN):
            target_raw, _ = _include_path(raw)
            candidate = _local_candidate(path, target_raw)
            if candidate is None:
                continue
            destination = canonical_destination(candidate)
            if destination is None or destination == candidate:
                continue
            if candidate.exists() or destination.exists():
                moves[candidate] = destination
                if candidate.suffix.casefold() == ".md" and candidate.exists():
                    queue.append(candidate)

        for raw in _markdown_values(text, LINK_PATTERN):
            candidate = _local_candidate(path, raw)
            if candidate is None:
                continue
            destination = canonical_destination(candidate)
            if destination is None or destination == candidate:
                continue
            if candidate.suffix.casefold() == ".md" and candidate not in moves:
                if candidate.exists():
                    unresolved.add(candidate.relative_to(root).as_posix())
                continue
            if candidate.exists() or destination.exists():
                moves[candidate] = destination

    rewrites: dict[Path, str] = {}
    for path in scanned:
        original = path.read_text(encoding="utf-8")
        eventual_source = moves.get(path, path)

        def replacement(raw: str, *, include: bool = False) -> str:
            target_raw, include_suffix = _include_path(raw) if include else (raw, "")
            candidate = _local_candidate(path, target_raw)
            if candidate is None:
                return raw
            eventual_target = moves.get(candidate)
            if eventual_target is None:
                try:
                    candidate.relative_to(source_root)
                    eventual_target = candidate
                except ValueError:
                    return raw
            new_path = os.path.relpath(eventual_target, eventual_source.parent).replace(os.sep, "/")
            return _rewritten_target(target_raw, new_path) + include_suffix

        text = _rewrite_markdown_values(
            original,
            LINK_PATTERN,
            replacement,
        )
        text = _rewrite_markdown_values(
            text,
            INCLUDE_PATTERN,
            lambda raw: replacement(raw, include=True),
        )
        if text != original:
            rewrites[path] = text

    # Markdown under docs/ but outside the canonical source is still visible
    # legacy documentation even when nothing currently links to it. Its
    # destination in the book hierarchy is not mechanically knowable, so
    # report it rather than silently ignoring or guessing placement.
    for candidate in docs.rglob("*.md"):
        resolved = candidate.resolve()
        try:
            resolved.relative_to(source_root)
            continue
        except ValueError:
            pass
        if resolved in moves:
            continue
        unresolved.add(candidate.relative_to(root).as_posix())

    return moves, rewrites, sorted(unresolved)


def _rewrite_external_references(root: Path, *, apply: bool) -> list[dict[str, str]]:
    moves, rewrites, _ = _referenced_content_state(root)
    existing_moves = {source: destination for source, destination in moves.items() if source.exists()}
    for source, destination in existing_moves.items():
        if source.is_symlink() or not source.is_file():
            raise DstackError(f"legacy documentation target is not a safe regular file: {source}")
        if destination.exists() and (
            destination.is_symlink() or not destination.is_file() or source.read_bytes() != destination.read_bytes()
        ):
            raise DstackError(f"legacy and canonical documentation targets conflict: {source} -> {destination}")

    result = [
        {
            "source": source.relative_to(root).as_posix(),
            "destination": destination.relative_to(root).as_posix(),
        }
        for source, destination in sorted(existing_moves.items(), key=lambda item: item[0].as_posix())
    ]
    if not apply:
        return result

    for path, text in rewrites.items():
        path.write_text(text, encoding="utf-8")
    for source, destination in sorted(existing_moves.items(), key=lambda item: len(item[0].parts), reverse=True):
        parent = source.parent
        _move_file(source, destination)
        _prune_empty_directories(parent, root / "docs")
    return result


def _unresolved_outside_markdown(root: Path) -> list[str]:
    _, _, unresolved = _referenced_content_state(root)
    return unresolved


def _reject_documentation_symlinks(root: Path) -> None:
    docs = root / "docs"
    if not docs.is_dir():
        return
    symlinks = [path for path in docs.rglob("*") if path.is_symlink()]
    if symlinks:
        raise DstackError("documentation migration source contains a symlink: " + str(symlinks[0]))


def legacy_documentation_plan(root: Path) -> dict[str, object]:
    root = root.resolve()
    _reject_documentation_symlinks(root)
    configured = _migrate_configured_source(root, apply=False)
    references: list[dict[str, str]] = []
    # Reference migration can only be inspected against the canonical source.
    if not configured:
        references = _rewrite_external_references(root, apply=False)
    return {
        "configured_source_moves": configured,
        "referenced_content_moves": references,
        "unresolved_outside_markdown": (
            [] if configured else _unresolved_outside_markdown(root)
        ),
    }


def migrate_legacy_documentation(root: Path) -> dict[str, object]:
    """Move only mechanically identifiable book content into ``docs/src``.

    A non-canonical configured mdBook source is moved wholesale because mdBook
    itself identifies every file under that source as book content. With the
    canonical source already in use, only local files explicitly referenced by
    book Markdown are moved. Unreferenced files outside ``docs/src`` are left
    for semantic judgment rather than guessed into navigation.
    """

    root = root.resolve()
    _reject_documentation_symlinks(root)
    configured = _migrate_configured_source(root, apply=True)
    references = _rewrite_external_references(root, apply=True)
    return {
        "configured_source_moves": configured,
        "referenced_content_moves": references,
        "unresolved_outside_markdown": _unresolved_outside_markdown(root),
    }


def _local_target(source: Path, raw: str, source_root: Path) -> Path | None:
    target = urlsplit(_raw_target(raw))
    if target.scheme or target.netloc:
        return None
    path_text = unquote(target.path)
    if not path_text:
        return source
    relative = Path(path_text)
    if relative.is_absolute():
        raise DstackError(f"local documentation target escapes docs/src: {raw}")
    candidate = (source.parent / relative).resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError as exc:
        raise DstackError(f"local documentation target escapes docs/src: {raw}") from exc
    if not candidate.is_file():
        raise DstackError(f"missing local documentation target: {raw}")
    return candidate


def _links(path: Path) -> list[str]:
    return _markdown_values(path.read_text(encoding="utf-8"), LINK_PATTERN)


def validate_decision_records(source: Path) -> list[str]:
    decisions = source / "decisions"
    if not decisions.is_dir():
        return []
    errors: list[str] = []
    allowed = {"Proposed", "Accepted", "Deprecated", "Superseded"}
    for path in sorted(decisions.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8")
        fields: dict[str, str] = {}
        for name in ("Status", "Supersedes", "Superseded by"):
            match = re.search(rf"^- \*\*{re.escape(name)}:\*\*\s*(.+)$", text, re.MULTILINE)
            if not match:
                errors.append(f"{path.name} lacks {name}")
                continue
            fields[name] = match.group(1).strip()
        status = fields.get("Status")
        if status and status not in allowed:
            errors.append(f"{path.name} has invalid status {status!r}")
        for name in ("Supersedes", "Superseded by"):
            value = fields.get(name)
            if value and value != "None" and not _markdown_values(value, LINK_PATTERN):
                errors.append(f"{path.name} {name} must be None or a local link")
    return errors


def validate_docs(root: Path, *, mdbook: str | None = None) -> dict[str, object]:
    root = root.resolve()
    docs = _inside(root / "docs", root, "documentation directory escapes repository")
    source = _inside(docs / "src", root, "documentation source escapes repository")
    required = foundation_files(root.name)
    missing: list[str] = []
    invalid: list[str] = []
    for relative in required:
        path = root / relative
        if path.is_symlink() or (path.exists() and not path.is_file()):
            invalid.append(relative)
        elif not path.is_file():
            missing.append(relative)
    foundation_errors = []
    if missing:
        foundation_errors.append("missing required documentation: " + ", ".join(missing))
    if invalid:
        foundation_errors.append("required documentation is not a regular file: " + ", ".join(invalid))
    if foundation_errors:
        raise DstackError("; ".join(foundation_errors))

    raw_source, configured = configured_source(root)
    if configured != source:
        raise DstackError(
            "mdBook [book].src must resolve to docs/src; "
            f"configured source is {raw_source!r}; run /setup-project --force to migrate it"
        )

    errors: list[str] = validate_decision_records(source)
    summary = source / "SUMMARY.md"
    chapters: set[Path] = set()
    for raw in _links(summary):
        try:
            target = _local_target(summary, raw, source)
        except DstackError as exc:
            errors.append(str(exc))
            continue
        if target is not None and target.suffix.casefold() == ".md":
            chapters.add(target)

    markdown = set(source.rglob("*.md"))
    for path in markdown:
        for raw in _links(path):
            try:
                _local_target(path, raw, source)
            except DstackError as exc:
                errors.append(str(exc))

    includes: set[Path] = set()
    pending = list(chapters)
    while pending:
        path = pending.pop()
        for raw in _markdown_values(path.read_text(encoding="utf-8"), INCLUDE_PATTERN):
            try:
                included = _local_target(path, raw.split(":", 1)[0], source)
            except DstackError as exc:
                errors.append(str(exc))
                continue
            if included is not None and included not in includes:
                includes.add(included)
                if included.suffix.casefold() == ".md":
                    pending.append(included)

    orphans = sorted(path.relative_to(source).as_posix() for path in markdown - chapters - includes - {summary})
    if orphans:
        errors.append("orphan documentation is not in SUMMARY.md: " + ", ".join(orphans))
    if errors:
        raise DstackError("documentation validation failed: " + "; ".join(sorted(set(errors))))

    executable = mdbook or require_mdbook()
    with tempfile.TemporaryDirectory(prefix="dstack-mdbook-") as output:
        run(
            [executable, "build", str(docs), "--dest-dir", output],
            cwd=root,
        )

    return {
        "status": "ok",
        "chapters": sorted(path.relative_to(source).as_posix() for path in chapters),
        "includes": sorted(path.relative_to(source).as_posix() for path in includes),
    }


def initialize_docs(root: Path) -> dict[str, object]:
    executable = require_mdbook()
    created = create_foundation(root)
    return {
        "created_documentation": created,
        "documentation": validate_docs(root, mdbook=executable),
    }


def cmd_docs_validate(args: object) -> int:
    emit(validate_docs(Path(getattr(args, "root"))))
    return 0
