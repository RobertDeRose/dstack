#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "copier>=9.16,<10",
#     "PyYAML>=6.0,<7",
# ]
# ///
# ruff: noqa: EM101, S603, S607
"""Adopt an existing repository into the tagged dstack Copier template."""

from __future__ import annotations

import argparse
import filecmp
import html
import json
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import yaml
from copier import run_copy


DEFAULT_TEMPLATE_SOURCE = "gh:RobertDeRose/dstack"
RELEASE_TAG_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")
PROJECT_KINDS = ("library", "cli", "service", "application", "infrastructure", "documentation", "other")
LANGUAGE_PROFILES = ("python", "typescript", "rust", "go", "elixir", "nix", "other")
PROFILE_MANIFESTS = {
    "pyproject.toml": "python",
    "tsconfig.json": "typescript",
    "package.json": "typescript",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "mix.exs": "elixir",
    "flake.nix": "nix",
}
PROFILE_CI_PATTERNS = {
    "python": re.compile(r"^(?:pytest|python(?:3)?\s+-m|uv\s+run\s+python)\b"),
    "typescript": re.compile(
        r"^(?:npm\s+(?:ci|install|test|run|exec)|pnpm\s+(?:install|test|run|exec)|"
        r"yarn\s+(?:install|test|run)|bun\s+(?:install|test|run)|vitest|tsc)\b"
    ),
    "rust": re.compile(r"^(?:cargo\s+(?:test|build|check|fmt|clippy)|rustfmt|clippy)\b"),
    "go": re.compile(r"^(?:go\s+(?:test|build|vet)|golangci)\b"),
    "elixir": re.compile(r"^(?:mix\s+(?:test|compile|format)|elixir)\b"),
    "nix": re.compile(r"^(?:nix\s+flake|nixfmt)\b"),
}
DISCOVERY_IGNORED_PARTS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "fixtures",
    "migration",
    "node_modules",
    "target",
    "third_party",
    "vendor",
}
DISCOVERY_IGNORED_PATHS = (
    Path("docs/book"),
    Path("docs/src/features"),
    Path("docs/src/planned-features.md"),
)
BRIEF_HEADING_ALIASES = {
    "project_purpose": {"purpose", "project purpose"},
    "project_users": {"audience", "intended users", "project users", "users"},
    "project_scope": {"current scope", "project scope", "scope", "supported scope"},
    "project_boundaries": {"boundaries", "key boundaries", "ownership boundaries", "project boundaries"},
}
BRIEF_LABELS = {
    "project_purpose": ("purpose",),
    "project_users": ("intended users", "users"),
    "project_scope": ("current supported scope", "current scope", "supported scope", "scope"),
    "project_boundaries": ("boundaries",),
}
BRIEF_ARGUMENTS = {
    "project_purpose": "purpose",
    "project_users": "users",
    "project_scope": "scope",
    "project_boundaries": "boundaries",
}
CURRENT_ANSWER_KEYS = (
    "project_name",
    "project_slug",
    "project_description",
    *BRIEF_ARGUMENTS,
    "project_kind",
    "language_profiles",
    "repository_default_branch",
    "include_readme",
)


def load_answers(path: Path) -> dict[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        message = f"Unable to read Copier answers from {path}: {exc}"
        raise SystemExit(message) from exc
    if not isinstance(value, dict):
        message = f"Copier answers must be a mapping: {path}"
        raise SystemExit(message)
    return {str(key): item for key, item in value.items()}


def _discovery_files(root: Path) -> list[Path]:
    """Return bounded, project-owned files used for migration recommendations."""
    candidates = [*root.glob("README*"), root / "AGENTS.md"]
    docs_root = root / "docs"
    if docs_root.is_dir():
        candidates.extend(docs_root.rglob("*.md"))
    return sorted(
        {
            path
            for path in candidates
            if path.is_file()
            and not any(part in DISCOVERY_IGNORED_PARTS for part in path.relative_to(root).parts)
            and path.name != "tasks.md"
            and not any(
                path.relative_to(root) == ignored or ignored in path.relative_to(root).parents
                for ignored in DISCOVERY_IGNORED_PATHS
            )
        }
    )


def _normalized_heading(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _section_candidates(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    for line in text.splitlines():
        match = heading_pattern.match(line)
        if match:
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            current_heading = _normalized_heading(match.group(2))
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)
    if current_heading is not None:
        sections.append((current_heading, current_lines))

    result: list[tuple[str, str]] = []
    for heading, lines in sections:
        content = _decoded_value(
            " ".join(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("<!--"))
        )
        if content:
            result.append((heading, content))
    return result


def _label_pattern(labels: Sequence[str]) -> re.Pattern[str]:
    alternatives = "|".join(sorted((re.escape(label) for label in labels), key=len, reverse=True))
    return re.compile(
        rf"^\s*(?:[-*]\s*)?(?:\*\*|__)?(?:{alternatives})(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.+?)\s*$",
        re.IGNORECASE,
    )


def _decoded_value(value: str) -> str:
    return html.unescape(" ".join(value.split())).strip()


def infer_project_kind(root: Path) -> tuple[str | None, list[str], list[str]]:
    """Reuse only an explicit documented project kind; operational clues remain recommendations for the agent."""
    pattern = _label_pattern(("project kind",))

    candidates: dict[str, list[str]] = {}
    for path in _discovery_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        relative = path.relative_to(root).as_posix()
        for line in text.splitlines():
            match = pattern.match(line)
            if match:
                kind = _decoded_value(match.group(1)).strip("`").strip()
                if kind in PROJECT_KINDS:
                    candidates.setdefault(kind, []).append(relative)
    if len(candidates) == 1:
        kind, sources = next(iter(candidates.items()))
        return kind, sorted(set(sources)), []
    if len(candidates) > 1:
        return None, [], sorted({source for sources in candidates.values() for source in sources})
    return None, [], []


def infer_project_brief(root: Path) -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    """Extract only explicit, current brief sections; ambiguous prose is not inferred."""
    candidates: dict[str, list[tuple[str, str]]] = {field: [] for field in BRIEF_ARGUMENTS}
    label_patterns = {field: _label_pattern(labels) for field, labels in BRIEF_LABELS.items()}
    for path in _discovery_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        relative = path.relative_to(root).as_posix()
        for heading, content in _section_candidates(text):
            for field, aliases in BRIEF_HEADING_ALIASES.items():
                if heading in aliases:
                    candidates[field].append((content, relative))
        for line in text.splitlines():
            for field, pattern in label_patterns.items():
                match = pattern.match(line)
                if match:
                    candidates[field].append((_decoded_value(match.group(1)), relative))

    inferred: dict[str, str] = {}
    evidence: dict[str, list[str]] = {}
    conflicts: dict[str, list[str]] = {}
    for field, values in candidates.items():
        by_value: dict[str, list[str]] = {}
        for value, source in values:
            by_value.setdefault(_decoded_value(value), []).append(source)
        if len(by_value) == 1:
            value, sources = next(iter(by_value.items()))
            inferred[field] = value
            evidence[field] = sorted(set(sources))
        elif len(by_value) > 1:
            conflicts[field] = sorted({source for sources in by_value.values() for source in sources})
    return inferred, evidence, conflicts


def _tracked_files(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if completed.returncode == 0:
        paths = [root / item for item in completed.stdout.decode().split("\0") if item]
    else:
        paths = [path for path in root.rglob("*") if path.is_file()]
    return [path for path in paths if not any(part in DISCOVERY_IGNORED_PARTS for part in path.relative_to(root).parts)]


def _manifest_is_project_evidence(path: Path, profile: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if profile == "python":
        return path.name == "pyproject.toml" and ("[project]" in text or "[tool." in text)
    if profile == "typescript":
        if path.name == "tsconfig.json":
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                return False
            return isinstance(value, dict) and "compilerOptions" in value
        if path.name == "package.json":
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                return False
            return isinstance(value, dict) and any(
                key in value for key in ("name", "scripts", "dependencies", "devDependencies")
            )
    if profile == "rust":
        return path.name == "Cargo.toml" and ("[package]" in text or "[workspace" in text)
    if profile == "go":
        return path.name == "go.mod" and text.lstrip().startswith("module ")
    if profile == "elixir":
        return path.name == "mix.exs" and "Mix.Project" in text
    if profile == "nix":
        return path.name == "flake.nix" and ("inputs" in text or "outputs" in text)
    return False


def _shell_command_segments(command: str) -> list[str]:
    segments: list[str] = []
    for line in command.splitlines() or [command]:
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|")
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            continue
        segment: list[str] = []
        for token in [*tokens, ";"]:
            if token in {";", "&&", "||", "|", "&"}:
                if segment:
                    while segment and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", segment[0]):
                        segment.pop(0)
                    if segment:
                        segments.append(" ".join(segment))
                segment = []
            else:
                segment.append(token)
    return segments


def _workflow_run_commands(text: str) -> list[str]:
    try:
        workflow = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
        return []

    commands: list[str] = []
    for job in workflow["jobs"].values():
        if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
            continue
        for step in job["steps"]:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                commands.extend(_shell_command_segments(step["run"]))
    return commands


def infer_language_profiles(root: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Infer language profiles from project manifests and repository CI evidence."""
    evidence: dict[str, list[str]] = {profile: [] for profile in LANGUAGE_PROFILES}
    files = _tracked_files(root)
    for path in files:
        profile = PROFILE_MANIFESTS.get(path.name)
        if profile is not None and _manifest_is_project_evidence(path, profile):
            evidence[profile].append(path.relative_to(root).as_posix())

    for path in files:
        relative = path.relative_to(root).as_posix()
        if not relative.startswith(".github/workflows/") or path.suffix not in {".yml", ".yaml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for command in _workflow_run_commands(text):
            for profile, pattern in PROFILE_CI_PATTERNS.items():
                if pattern.search(command):
                    evidence[profile].append(relative)

    profiles = [profile for profile in LANGUAGE_PROFILES if profile != "other" and evidence[profile]]
    if not profiles:
        profiles = ["other"]
        evidence["other"] = ["no recognized project manifest or CI profile"]
    return profiles, {profile: sorted(set(paths)) for profile, paths in evidence.items() if paths}


def canonical_language_profiles(values: object) -> list[str]:
    if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values):
        raise SystemExit("language_profiles must be a nonempty list of supported profile names")
    profiles = [value for value in values if isinstance(value, str)]
    unknown = sorted(set(profiles) - set(LANGUAGE_PROFILES))
    if unknown:
        raise SystemExit("Unknown language profile: " + ", ".join(unknown))
    if len(profiles) != len(set(profiles)):
        raise SystemExit("language_profiles must not contain duplicates")
    if "other" in profiles and len(profiles) > 1:
        raise SystemExit("The other language profile cannot be combined with recognized profiles")
    return [profile for profile in LANGUAGE_PROFILES if profile in profiles]


def preserve_current_answer_values(path: Path, existing: dict[str, object]) -> None:
    """Keep current question values Copier omitted from its rendered answers file."""
    rendered = load_answers(path)
    changed = False
    for key in CURRENT_ANSWER_KEYS:
        if key not in rendered and key in existing:
            rendered[key] = existing[key]
            changed = True
    if not changed:
        return
    path.write_text(
        "# This file is managed by Copier. Do not edit it manually.\n"
        + yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def validate_template_source(source: str) -> None:
    if any(character in source for character in ("\n", "\r", "\x00")):
        msg = "Template source contains prohibited control characters"
        raise SystemExit(msg)
    if source == DEFAULT_TEMPLATE_SOURCE:
        return
    if Path(source).expanduser().exists():
        return
    if source.startswith(("gh:", "gl:", "https://", "ssh://", "git@")):
        return
    msg = (
        "Unsupported template source. Use the packaged gh: source, an existing local path, "
        "or an explicit gh:, gl:, https://, ssh://, or git@ source."
    )
    raise SystemExit(msg)


def is_remote_template_source(source: str) -> bool:
    return source.startswith(("gh:", "gl:", "https://", "ssh://", "git@"))


def latest_release_tag(source: str) -> str:
    completed = subprocess.run(
        ["git", "ls-remote", "--tags", git_source(source), "refs/tags/v*"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        msg = "Unable to discover dstack release tags; pass --vcs-ref explicitly."
        raise SystemExit(msg)
    tags = {line.split()[1].removeprefix("refs/tags/").removesuffix("^{}") for line in completed.stdout.splitlines()}
    releases = [tag for tag in tags if re.fullmatch(r"v\d+\.\d+\.\d+", tag)]
    if not releases:
        msg = "No dstack release tags found; pass --vcs-ref explicitly."
        raise SystemExit(msg)

    def release_key(tag: str) -> tuple[int, int, int]:
        match = re.match(r"^v(\d+)\.(\d+)\.(\d+)", tag)
        if match is None:
            return (0, 0, 0)
        major, minor, patch = match.groups()
        return (int(major), int(minor), int(patch))

    return max(releases, key=release_key)


def default_vcs_ref(template_source: str, requested: str | None) -> str | None:
    if requested:
        return requested
    if template_source == DEFAULT_TEMPLATE_SOURCE:
        return latest_release_tag(template_source)
    if is_remote_template_source(template_source):
        msg = "A non-default remote template source requires an explicit --vcs-ref."
        raise SystemExit(msg)
    return None


def git_source(source: str) -> str:
    if source.startswith("gh:"):
        return f"https://github.com/{source.removeprefix('gh:')}.git"
    if source.startswith("gl:"):
        return f"https://gitlab.com/{source.removeprefix('gl:')}.git"
    return source


def require_release_tag(source: str, vcs_ref: str | None) -> str | None:
    if vcs_ref is None or not RELEASE_TAG_PATTERN.fullmatch(vcs_ref):
        return None
    completed = subprocess.run(
        [
            "git",
            "ls-remote",
            "--exit-code",
            "--tags",
            git_source(source),
            f"refs/tags/{vcs_ref}",
            f"refs/tags/{vcs_ref}^{{}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        message = (
            f"dstack release tag {vcs_ref!r} is not available from {source!r}. "
            "The installed skill is stale or the matching release tag has not been published. "
            "Update the installed skills and retry, or pass an explicit --vcs-ref after reviewing "
            "the intended release. dstack will not fall back to an untagged HEAD."
        )
        if detail:
            message += f"\nGit reported: {detail}"
        raise SystemExit(message)

    refs: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2:
            refs[fields[1]] = fields[0]
    return refs.get(f"refs/tags/{vcs_ref}^{{}}") or refs.get(f"refs/tags/{vcs_ref}")


BACKUP_ROOT = Path("migration/template-adoption-backup")
CANDIDATE_ROOT = Path("migration/template-adoption-candidates")
DSTACK_MANAGED_PREFIXES = (
    ".beads/formulas/",
    "docs/src/features/_template/",
)
DSTACK_MANAGED_FILES = {
    ".copier-answers.yml",
    "scripts/check-docs.py",
}
AGENTS_BEGIN = "<!-- BEGIN DSTACK WORKFLOW -->"
AGENTS_END = "<!-- END DSTACK WORKFLOW -->"
GITIGNORE_BEGIN = "# BEGIN DSTACK WORKFLOW"
GITIGNORE_END = "# END DSTACK WORKFLOW"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        msg = "Project name must contain at least one letter or number"
        raise ValueError(msg)
    return slug


def git_root(path: Path) -> Path:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        msg = "Template adoption must run inside an existing Git repository"
        raise SystemExit(msg)
    return Path(completed.stdout.strip()).resolve()


def git_value(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def canonical_repository_name(root: Path) -> str:
    common_dir = git_value(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common_dir:
        common_path = Path(common_dir).resolve()
        if common_path.name == ".git":
            return common_path.parent.name
    return root.name


def repository_default_branch(root: Path) -> str:
    remote_head = git_value(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if remote_head.startswith("origin/"):
        return remote_head.removeprefix("origin/")
    git_dir = git_value(root, "rev-parse", "--path-format=absolute", "--git-dir")
    common_dir = git_value(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if git_dir and common_dir and Path(git_dir).resolve() == Path(common_dir).resolve():
        return git_value(root, "symbolic-ref", "--short", "HEAD")
    return ""


def git_status(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def extract_block(text: str, begin: str, end: str) -> str:
    start = text.find(begin)
    finish = text.find(end)
    if start < 0 or finish < start:
        msg = f"Generated template is missing managed markers: {begin} / {end}"
        raise SystemExit(msg)
    return text[start : finish + len(end)].strip()


def merge_block(target: Path, generated: Path, begin: str, end: str) -> bool:
    generated_text = generated.read_text(encoding="utf-8")
    block = extract_block(generated_text, begin, end)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated, target)
        return True

    current = target.read_text(encoding="utf-8")
    start = current.find(begin)
    finish = current.find(end)
    if start >= 0 and finish >= start:
        finish += len(end)
        prefix = current[:start].rstrip()
        suffix = current[finish:].strip("\n")
        parts = [part for part in (prefix, block, suffix) if part]
        updated = "\n\n".join(parts) + "\n"
    else:
        updated = current.rstrip() + "\n\n" + block + "\n"
    if updated == current:
        return False
    target.write_text(updated, encoding="utf-8", newline="\n")
    return True


def backup_and_copy(source: Path, target: Path, root: Path) -> str:
    relative = target.relative_to(root)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return "created"
    if filecmp.cmp(source, target, shallow=False):
        return "preserved"

    backup = root / BACKUP_ROOT / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(target, backup)
    shutil.copy2(source, target)
    return "replaced"


def is_dstack_managed(relative: Path) -> bool:
    key = relative.as_posix()
    return key in DSTACK_MANAGED_FILES or any(key.startswith(prefix) for prefix in DSTACK_MANAGED_PREFIXES)


def has_live_legacy_tasks(root: Path) -> bool:
    return any(
        path.is_file() and not any(part in DISCOVERY_IGNORED_PARTS for part in path.relative_to(root).parts)
        for path in root.rglob("tasks.md")
    )


def preserve_or_stage_candidate(
    source: Path,
    target: Path,
    root: Path,
    *,
    defer_missing: bool = False,
) -> str:
    """Copy missing scaffold files, but stage conflicts for explicit manual reconciliation."""
    relative = target.relative_to(root)
    if not target.exists() and not defer_missing:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return "created"
    if target.exists() and filecmp.cmp(source, target, shallow=False):
        return "preserved"

    candidate = root / CANDIDATE_ROOT / relative
    candidate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, candidate)
    return "manual-merge"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_name", nargs="?", help="Defaults to basename($PWD).")
    parser.add_argument("--destination", "-d", type=Path, default=Path.cwd())
    parser.add_argument("--project-slug")
    parser.add_argument("--purpose")
    parser.add_argument("--users")
    parser.add_argument("--scope")
    parser.add_argument("--boundaries")
    parser.add_argument("--project-kind", choices=PROJECT_KINDS)
    parser.add_argument("--language-profile", action="append", choices=LANGUAGE_PROFILES)
    parser.add_argument("--default-branch")
    parser.add_argument(
        "--template-source",
        help="Template source override; defaults to existing Copier state or the official dstack repository.",
    )
    parser.add_argument("--vcs-ref")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def project_brief(
    args: argparse.Namespace,
    existing: dict[str, object],
    root: Path,
) -> tuple[
    dict[str, str],
    list[str],
    dict[str, str],
    dict[str, list[str]],
    dict[str, list[str]],
    str,
]:
    brief: dict[str, str] = {}
    inferred_sources: dict[str, str] = {}
    brief_evidence: dict[str, list[str]] = {}
    missing: list[str] = []
    inferred, evidence, conflicts = infer_project_brief(root)
    for answer, argument in BRIEF_ARGUMENTS.items():
        raw = getattr(args, argument)
        if raw is None:
            recorded = existing.get(answer)
            if isinstance(recorded, str) and recorded.strip():
                raw = recorded
            elif answer in conflicts:
                missing.append(f"--{argument} (conflicting current documentation: {', '.join(conflicts[answer])})")
                continue
            else:
                raw = inferred.get(answer)
                if raw is not None:
                    inferred_sources[answer] = evidence[answer][0]
                    brief_evidence[answer] = evidence[answer]
        if raw is None:
            missing.append(f"--{argument}")
            continue
        if any(character in raw for character in ("\x00", "\r", "\n")):
            message = f"--{argument} must be a single line without NUL, CR, or LF characters"
            raise SystemExit(message)
        value = raw.strip()
        if not value:
            message = f"--{argument} must not be blank"
            raise SystemExit(message)
        brief[answer] = value

    kind: str | None = args.project_kind
    if kind is None:
        recorded_kind = existing.get("project_kind")
        if isinstance(recorded_kind, str) and recorded_kind:
            kind = recorded_kind
    if kind is None:
        inferred_kind, kind_sources, kind_conflicts = infer_project_kind(root)
        if inferred_kind is not None:
            kind = inferred_kind
            inferred_sources["project_kind"] = kind_sources[0]
            brief_evidence["project_kind"] = kind_sources
        elif kind_conflicts:
            missing.append(f"--project-kind (conflicting current documentation: {', '.join(kind_conflicts)})")
    if (not isinstance(kind, str) or kind not in PROJECT_KINDS) and not any(
        item.startswith("--project-kind") for item in missing
    ):
        missing.append("--project-kind")

    language_profile_evidence: dict[str, list[str]] = {}
    requested_profiles = args.language_profile
    if requested_profiles:
        profiles = canonical_language_profiles(requested_profiles)
        language_source = "argument"
    else:
        recorded_profiles = existing.get("language_profiles")
        if recorded_profiles is not None:
            profiles = canonical_language_profiles(recorded_profiles)
            language_source = "copier"
        else:
            profiles, language_profile_evidence = infer_language_profiles(root)
            if profiles == ["other"] and language_profile_evidence.get("other") == [
                "no recognized project manifest or CI profile"
            ]:
                missing.append("--language-profile")
                language_source = "missing"
            else:
                language_source = "current repository evidence"
    if missing:
        message = "Template adoption requires " + ", ".join(missing)
        if "--project-kind" in missing:
            message += "; accepted kinds: " + ", ".join(PROJECT_KINDS)
        raise SystemExit(message)
    if not isinstance(kind, str):
        raise SystemExit("Template adoption requires --project-kind")
    brief["project_kind"] = kind
    return brief, profiles, inferred_sources, brief_evidence, language_profile_evidence, language_source


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = git_root(args.destination.expanduser().resolve())
    answers = root / ".copier-answers.yml"
    answers_existed = answers.is_file()
    existing_answers = load_answers(answers) if answers_existed else {}
    recorded_source = str(existing_answers.get("_src_path") or "").strip()
    template_source = args.template_source or recorded_source or DEFAULT_TEMPLATE_SOURCE
    validate_template_source(template_source)
    vcs_ref = default_vcs_ref(template_source, args.vcs_ref)
    resolved_template_commit = require_release_tag(template_source, vcs_ref)
    dirty = git_status(root)
    if dirty and not args.allow_dirty:
        preview = "\n".join(f"  {line}" for line in dirty[:25])
        raise SystemExit("Commit or stash changes before adopting the template:\n" + preview)

    recorded_name = str(existing_answers.get("project_name") or "").strip()
    recorded_slug = str(existing_answers.get("project_slug") or "").strip()
    recorded_branch = str(existing_answers.get("repository_default_branch") or "").strip()
    recorded_readme = existing_answers.get("include_readme")
    inferred_name = canonical_repository_name(root)
    inferred_branch = repository_default_branch(root)
    project_name = (args.project_name or recorded_name or inferred_name).strip()
    project_slug = args.project_slug or recorded_slug or slugify(project_name)
    (
        brief,
        language_profiles,
        inferred_brief_sources,
        brief_evidence,
        language_profile_evidence,
        language_profile_source,
    ) = project_brief(args, existing_answers, root)
    default_branch = args.default_branch or recorded_branch or inferred_branch
    if not default_branch:
        message = "Template adoption requires --default-branch because repository policy could not be discovered"
        raise SystemExit(message)
    include_readme = recorded_readme if isinstance(recorded_readme, bool) else True
    defer_generated_hook = has_live_legacy_tasks(root)

    with tempfile.TemporaryDirectory(prefix="dstack-adopt-") as temporary:
        rendered = Path(temporary) / "rendered"
        run_copy(
            template_source,
            rendered,
            data={
                "project_name": project_name,
                "project_slug": project_slug,
                **brief,
                "language_profiles": language_profiles,
                "repository_default_branch": default_branch,
                "include_readme": include_readme,
            },
            vcs_ref=vcs_ref,
            defaults=True,
            overwrite=False,
            quiet=args.quiet or args.json,
            unsafe=False,
        )
        preserve_current_answer_values(rendered / ".copier-answers.yml", existing_answers)

        created: list[str] = []
        replaced: list[str] = []
        preserved: list[str] = []
        manual_merge: list[str] = []
        for source in sorted(path for path in rendered.rglob("*") if path.is_file()):
            relative = source.relative_to(rendered)
            target = root / relative
            key = relative.as_posix()

            if key == "AGENTS.md":
                changed = merge_block(target, source, AGENTS_BEGIN, AGENTS_END)
                (created if changed else preserved).append(key)
                continue
            if key == ".gitignore":
                changed = merge_block(target, source, GITIGNORE_BEGIN, GITIGNORE_END)
                (created if changed else preserved).append(key)
                continue

            if is_dstack_managed(relative):
                status = backup_and_copy(source, target, root)
            else:
                status = preserve_or_stage_candidate(
                    source,
                    target,
                    root,
                    defer_missing=key == "hk.pkl" and defer_generated_hook,
                )
            {
                "created": created,
                "replaced": replaced,
                "preserved": preserved,
                "manual-merge": manual_merge,
            }[status].append(key)

    if not answers.exists():
        msg = "Template adoption did not create .copier-answers.yml"
        raise SystemExit(msg)
    adopted_answers = load_answers(answers)

    result = {
        "project_name": project_name,
        "project_slug": project_slug,
        "destination": str(root),
        "inferred_brief_sources": inferred_brief_sources,
        "brief_evidence": brief_evidence,
        "language_profiles": language_profiles,
        "language_profile_evidence": language_profile_evidence,
        "language_profile_source": language_profile_source,
        "template_source": template_source,
        "copier_state": "rebased-existing" if answers_existed else "created",
        "previous_copier_source": existing_answers.get("_src_path"),
        "previous_copier_commit": existing_answers.get("_commit"),
        "recorded_copier_source": adopted_answers.get("_src_path"),
        "recorded_copier_commit": adopted_answers.get("_commit"),
        "vcs_ref": vcs_ref,
        "resolved_template_commit": resolved_template_commit,
        "created": created,
        "replaced": replaced,
        "preserved": preserved,
        "manual_merge": manual_merge,
        "backup_root": str(root / BACKUP_ROOT),
        "candidate_root": str(root / CANDIDATE_ROOT),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Adopted dstack Copier state in {root}")
        print(
            f"Created: {len(created)}; replaced with backup: {len(replaced)}; "
            f"preserved: {len(preserved)}; manual merge: {len(manual_merge)}"
        )
        if manual_merge:
            print(f"Reconcile generated candidates under {root / CANDIDATE_ROOT}, then remove that directory.")
        print("Next: validate the reconciled scaffold, initialize Beads, then scan the legacy workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
