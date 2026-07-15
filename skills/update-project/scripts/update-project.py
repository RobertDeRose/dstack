#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "copier>=9.16,<10",
#     "packaging>=24,<27",
#     "PyYAML>=6.0,<7",
# ]
# ///
# ruff: noqa: S603, S607
"""Update a Copier-managed dstack project and validate the resulting scaffold."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from copier import run_copy, run_update
from packaging.version import InvalidVersion, Version


DEFAULT_TEMPLATE_SOURCE = "gh:RobertDeRose/dstack"
CONFLICT_START = re.compile(r"^<<<<<<<(?: .*)?$", re.MULTILINE)
CONFLICT_MIDDLE = re.compile(r"^=======$", re.MULTILINE)
CONFLICT_END = re.compile(r"^>>>>>>>(?: .*)?$", re.MULTILINE)
IGNORED_SCAN_DIRS = {
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}
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
ADOPTION_CANDIDATES = Path("migration/copier-adoption-candidates")
TEMPLATE_CHANNELS = {"stable", "unstable"}

LEGACY_TASK_IGNORED_DIRS = IGNORED_SCAN_DIRS | {
    ".agents",
    ".beads",
    ".codex",
    ".cursor",
    ".github",
    "_template",
    "archive",
    "archived",
    "migration",
    "skills",
    "third_party",
    "vendor",
    "vendors",
}


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command and preserve useful output when it fails."""
    if not quiet:
        print("+", " ".join(command))
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=quiet,
        text=True,
    )
    if completed.returncode != 0:
        if quiet:
            if completed.stdout:
                print(completed.stdout, file=sys.stderr, end="")
            if completed.stderr:
                print(completed.stderr, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(
            completed.returncode,
            list(command),
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def run_capture(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output and fail with its diagnostics."""
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip())
        message = f"Command failed ({completed.returncode}): {' '.join(command)}"
        if details:
            message += f"\n{details}"
        raise SystemExit(message)
    return completed


def git_root(path: Path) -> Path:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        msg = "Copier updates require a Git repository"
        raise SystemExit(msg)
    return Path(completed.stdout.strip()).resolve()


def git_status(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def legacy_task_files(root: Path) -> list[str]:
    """Return active legacy task files without treating tools, templates, or archives as live state."""
    found: list[str] = []
    for current, directories, filenames in os.walk(root):
        directories[:] = [
            directory
            for directory in directories
            if directory not in LEGACY_TASK_IGNORED_DIRS and not directory.startswith(".")
        ]
        if not any(filename.casefold() == "tasks.md" for filename in filenames):
            continue
        current_path = Path(current)
        for filename in filenames:
            if filename.casefold() == "tasks.md":
                found.append((current_path / filename).relative_to(root).as_posix())
    return sorted(found)


def beads_state_present(root: Path) -> bool:
    """Detect initialized Beads state without counting a copied formula as a database."""
    beads = root / ".beads"
    markers = (
        beads / "metadata.json",
        beads / "config.yaml",
        beads / "beads.db",
        beads / "issues.jsonl",
        beads / "embeddeddolt",
        beads / "dolt",
    )
    return any(path.exists() for path in markers)


def detected_language_profiles(root: Path) -> list[str]:
    found = {profile for path, profile in PROFILE_MANIFESTS.items() if (root / path).is_file()}
    return [profile for profile in LANGUAGE_PROFILES if profile in found]


def canonical_language_profiles(values: Any) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        message = "language_profiles must be a list of supported profile names"
        raise SystemExit(message)
    unknown = sorted(set(values) - set(LANGUAGE_PROFILES))
    if unknown:
        raise SystemExit("Unknown language profile: " + ", ".join(unknown))
    if len(values) != len(set(values)):
        message = "language_profiles must not contain duplicates"
        raise SystemExit(message)
    if not values:
        message = "language_profiles must not be empty; use other for the universal baseline"
        raise SystemExit(message)
    if "other" in values and len(values) > 1:
        message = "The other language profile cannot be combined with recognized profiles"
        raise SystemExit(message)
    return [profile for profile in LANGUAGE_PROFILES if profile in values]


def updated_language_profiles(current: Any, additions: Sequence[str], removals: Sequence[str]) -> list[str]:
    existing = canonical_language_profiles(current)
    add = set(additions)
    remove = set(removals)
    overlap = sorted(add & remove)
    if overlap:
        raise SystemExit("Profiles cannot be added and removed together: " + ", ".join(overlap))

    result = set(existing) - remove
    recognized_additions = add - {"other"}
    if recognized_additions:
        result.discard("other")
        result.update(recognized_additions)
    if "other" in add:
        if result == {"other"}:
            return ["other"]
        if result:
            message = "The other profile can be added only when all recognized profiles are removed"
            raise SystemExit(message)
        result.add("other")
    return canonical_language_profiles(list(result))


def is_dstack_template_source(root: Path) -> bool:
    return (
        (root / "copier.yml").is_file()
        and (root / "skills/setup-project/copier.yml").is_file()
        and (root / "skills/setup-project/template").is_dir()
    )


def project_preflight(root: Path, answers_file: str) -> dict[str, Any]:
    tasks = legacy_task_files(root)
    beads_present = beads_state_present(root)
    answers = root / answers_file
    if tasks and not beads_present:
        route = "migrate-workflow"
        reason = "legacy feature tasks exist but Beads has not been initialized"
    elif answers.is_file():
        route = "update-project"
        reason = "Copier state exists"
    elif is_dstack_template_source(root):
        route = "update-project-adopt"
        reason = "dstack template source requires explicit self-adoption"
    else:
        route = "migrate-workflow"
        reason = "Copier state is missing from an existing repository"
    return {
        "destination": str(root),
        "answers_file": str(answers),
        "answers_exists": answers.is_file(),
        "legacy_task_files": tasks,
        "beads_state_present": beads_present,
        "template_source_repository": is_dstack_template_source(root),
        "recommended_workflow": route,
        "reason": reason,
        "suggested_language_profiles": detected_language_profiles(root),
    }


def nul_paths(command: Sequence[str], *, root: Path) -> set[str]:
    completed = subprocess.run(
        list(command),
        cwd=root,
        check=True,
        capture_output=True,
    )
    return {value.decode("utf-8", errors="surrogateescape") for value in completed.stdout.split(b"\0") if value}


def changed_project_paths(root: Path) -> set[str]:
    """Return Git-visible modified and untracked paths, excluding ignored files."""
    tracked = nul_paths(
        ["git", "diff", "--name-only", "-z", "HEAD", "--"],
        root=root,
    )
    untracked = nul_paths(
        ["git", "ls-files", "-z", "--others", "--exclude-standard"],
        root=root,
    )
    return {
        relative
        for relative in tracked | untracked
        if not any(part in IGNORED_SCAN_DIRS for part in Path(relative).parts)
    }


def unmerged_paths(root: Path) -> set[str]:
    return nul_paths(
        ["git", "diff", "--name-only", "-z", "--diff-filter=U", "--"],
        root=root,
    )


def reject_files(root: Path) -> set[str]:
    """Find reject files while pruning dependency and generated-cache trees."""
    found: set[str] = set()
    for current, directories, filenames in os.walk(root):
        directories[:] = [directory for directory in directories if directory not in IGNORED_SCAN_DIRS]
        current_path = Path(current)
        for filename in filenames:
            if filename.endswith(".rej"):
                found.add((current_path / filename).relative_to(root).as_posix())
    return found


def contains_inline_conflict(text: str) -> bool:
    """Require a coherent start/middle/end marker set to avoid separator false positives."""
    return bool(CONFLICT_START.search(text) and CONFLICT_MIDDLE.search(text) and CONFLICT_END.search(text))


def scan_conflicts(
    root: Path,
    *,
    baseline_rejects: set[str] | None = None,
) -> list[str]:
    """Inspect only Git-visible update output plus newly created reject files."""
    conflicts = set(unmerged_paths(root))
    candidates = changed_project_paths(root)

    for relative in sorted(candidates):
        path = root / relative
        if not path.is_file():
            continue
        if path.suffix == ".rej":
            conflicts.add(relative)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if contains_inline_conflict(text):
            conflicts.add(relative)

    prior = baseline_rejects or set()
    conflicts.update(reject_files(root) - prior)
    return sorted(conflicts)


def tagged_version(tag: str) -> Version | None:
    if not tag.startswith("v"):
        return None
    try:
        version = Version(tag.removeprefix("v"))
    except InvalidVersion:
        return None
    if len(version.release) != 3:
        return None
    return version


def default_vcs_ref(source: str, *, include_prereleases: bool = False) -> str:
    """Resolve the newest published PEP 440 release tag from the recorded Git source."""
    root = local_git_root(source)
    if root is not None:
        completed = subprocess.run(
            ["git", "-C", str(root), "tag", "--list", "v*"],
            check=True,
            capture_output=True,
            text=True,
        )
        tags = set(completed.stdout.splitlines())
    else:
        completed = subprocess.run(
            ["git", "ls-remote", "--tags", git_source(source), "refs/tags/v*"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            msg = f"Unable to discover dstack release tags from {source!r}; pass --vcs-ref explicitly."
            raise SystemExit(msg)
        tags = {
            line.split()[1].removeprefix("refs/tags/").removesuffix("^{}")
            for line in completed.stdout.splitlines()
            if len(line.split()) == 2
        }
    releases: list[tuple[Version, str]] = []
    for tag in tags:
        version = tagged_version(tag)
        if version is None:
            continue
        if not include_prereleases and (version.is_prerelease or version.is_devrelease):
            continue
        releases.append((version, tag))
    if not releases:
        qualifier = " including prereleases" if include_prereleases else " stable"
        msg = f"No{qualifier} dstack release tags found in {source!r}; pass --vcs-ref explicitly."
        raise SystemExit(msg)
    return max(releases)[1]


def load_answers(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        msg = f"Unable to read Copier answers from {path}: {exc}"
        raise SystemExit(msg) from exc
    if not isinstance(loaded, dict):
        msg = f"Copier answers must be a mapping: {path}"
        raise SystemExit(msg)
    return loaded


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


def git_source(source: str) -> str:
    if source.startswith("gh:"):
        return f"https://github.com/{source.removeprefix('gh:')}.git"
    if source.startswith("gl:"):
        return f"https://gitlab.com/{source.removeprefix('gl:')}.git"
    return source


def require_release_tag(source: str, vcs_ref: str) -> str | None:
    """Refuse an implicit HEAD fallback and return the resolved tag commit."""
    if tagged_version(vcs_ref) is None:
        return None
    root = local_git_root(source)
    if root is not None:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", f"refs/tags/{vcs_ref}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
        message = f"dstack release tag {vcs_ref!r} is not available from {source!r}"
        raise SystemExit(message)
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
            "The updater will not fall back to HEAD. Publish the matching tag or pass "
            "an explicit --vcs-ref after reviewing the source revision."
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


def local_git_root(source: str) -> Path | None:
    path = Path(source).expanduser()
    if not path.exists():
        return None
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    return Path(completed.stdout.strip()) if completed.returncode == 0 else None


def source_head(source: str) -> tuple[str, str]:
    root = local_git_root(source)
    if root is not None:
        branch = (
            subprocess.run(
                ["git", "-C", str(root), "symbolic-ref", "--short", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
            or "HEAD"
        )
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{commit}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return branch, sha

    completed = subprocess.run(
        ["git", "ls-remote", "--symref", git_source(source), "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = f"Unable to resolve the default branch HEAD from {source!r}"
        raise SystemExit(message)
    branch = "HEAD"
    sha = ""
    for line in completed.stdout.splitlines():
        if line.startswith("ref:") and line.endswith("\tHEAD"):
            branch = line.split()[1].removeprefix("refs/heads/")
        elif line.endswith("\tHEAD"):
            sha = line.split()[0]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        message = f"The default branch HEAD from {source!r} did not resolve to a commit"
        raise SystemExit(message)
    return branch, sha


def explicit_ref(source: str, requested: str) -> tuple[str, str]:
    root = local_git_root(source)
    if root is not None:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", f"{requested}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return requested, completed.stdout.strip()
        message = f"Template revision {requested!r} is not available from {source!r}"
        raise SystemExit(message)

    patterns = [requested, f"refs/heads/{requested}", f"refs/tags/{requested}", f"refs/tags/{requested}^{{}}"]
    completed = subprocess.run(
        ["git", "ls-remote", git_source(source), *patterns],
        check=False,
        capture_output=True,
        text=True,
    )
    refs = {ref: sha for sha, ref in (line.split() for line in completed.stdout.splitlines())}
    sha = refs.get(f"refs/tags/{requested}^{{}}") or refs.get(f"refs/tags/{requested}")
    sha = sha or refs.get(f"refs/heads/{requested}") or refs.get(requested)
    if not sha and re.fullmatch(r"[0-9a-f]{40}", requested):
        with tempfile.TemporaryDirectory(prefix="dstack-revision-") as temporary:
            subprocess.run(["git", "init", "--bare", temporary], check=True, capture_output=True)
            fetched = subprocess.run(
                ["git", "-C", temporary, "fetch", "--depth=1", git_source(source), requested],
                check=False,
                capture_output=True,
                text=True,
            )
            if fetched.returncode == 0:
                sha = requested
    if completed.returncode != 0 or not sha:
        message = f"Template revision {requested!r} is not available from {source!r}"
        raise SystemExit(message)
    return requested, sha


def selected_revision(
    source: str,
    channel: str,
    requested: str | None,
    *,
    include_prereleases: bool = False,
) -> tuple[str, str]:
    if requested:
        return explicit_ref(source, requested)
    if channel == "unstable":
        return source_head(source)
    tag = default_vcs_ref(source, include_prereleases=include_prereleases)
    commit = require_release_tag(source, tag)
    if commit is None:
        message = f"Stable release {tag} did not resolve to a commit"
        raise AssertionError(message)
    return tag, commit


def write_copier_state(path: Path, data: dict[str, Any], *, commit: str, channel: str) -> None:
    data = {**data, "_commit": commit, "dstack_template_channel": channel}
    path.write_text(
        "# This file is managed by Copier. Do not edit it manually.\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def adoption_data(args: argparse.Namespace) -> dict[str, Any]:
    required = {
        "--project-name": args.project_name,
        "--project-slug": args.project_slug,
        "--purpose": args.purpose,
        "--users": args.users,
        "--scope": args.scope,
        "--boundaries": args.boundaries,
        "--project-kind": args.project_kind,
    }
    missing = [flag for flag, value in required.items() if not value]
    if missing:
        message = "Template self-adoption requires " + ", ".join(missing)
        raise SystemExit(message)
    values = {flag: value.strip() for flag, value in required.items()}
    empty = [flag for flag, value in values.items() if not value]
    if empty:
        message = "Template self-adoption values must not be blank: " + ", ".join(empty)
        raise SystemExit(message)
    invalid = [
        flag for flag, value in required.items() if any(character in value for character in ("\x00", "\r", "\n"))
    ]
    if invalid:
        message = "Template self-adoption values must be nonempty single lines: " + ", ".join(invalid)
        raise SystemExit(message)
    profiles = canonical_language_profiles(args.language_profile)
    return {
        "project_name": values["--project-name"],
        "project_slug": values["--project-slug"],
        "project_purpose": values["--purpose"],
        "project_users": values["--users"],
        "project_scope": values["--scope"],
        "project_boundaries": values["--boundaries"],
        "project_kind": args.project_kind,
        "language_profiles": profiles,
        "repository_default_branch": args.default_branch,
        "include_readme": True,
        "dstack_template_channel": "unstable",
    }


def reject_adoption_symlinks(root: Path, target: Path) -> None:
    if target.is_symlink():
        message = f"Template adoption destination must not be a symlink: {target}"
        raise SystemExit(message)
    for parent in target.parents:
        if parent.is_symlink():
            message = f"Template adoption parent must not be a symlink: {parent}"
            raise SystemExit(message)
        if parent == root:
            break


def adopt_template_source(
    root: Path,
    args: argparse.Namespace,
    *,
    source: str,
    selected_ref: str,
    commit: str,
) -> dict[str, Any]:
    if not args.unstable or args.stable:
        message = "Template self-adoption requires explicit --unstable"
        raise SystemExit(message)
    if args.vcs_ref is not None:
        message = "Template self-adoption uses the reachable unstable default-branch HEAD; omit --vcs-ref"
        raise SystemExit(message)
    before = git_status(root)
    if before:
        preview = "\n".join(f"  {line}" for line in before[:25])
        message = "Commit or stash changes before adopting the template:\n" + preview
        raise SystemExit(message)

    data = adoption_data(args)
    candidates_root = root / ADOPTION_CANDIDATES
    if candidates_root.exists():
        message = f"Remove or reconcile the existing adoption candidates first: {candidates_root}"
        raise SystemExit(message)

    with tempfile.TemporaryDirectory(prefix="dstack-self-adopt-") as temporary:
        rendered = Path(temporary) / "rendered"
        run_copy(
            source,
            rendered,
            data=data,
            vcs_ref=commit,
            defaults=True,
            overwrite=False,
            quiet=args.quiet or args.json,
            unsafe=False,
        )
        rendered_answers = rendered / args.answers_file
        state = load_answers(rendered_answers)
        write_copier_state(rendered_answers, state, commit=commit, channel="unstable")

        created: list[str] = []
        preserved: list[str] = []
        customized: list[str] = []
        copies: list[tuple[Path, Path]] = []
        candidates: list[tuple[Path, Path]] = []
        answer_copy: tuple[Path, Path] | None = None
        for generated in sorted(path for path in rendered.rglob("*") if path.is_file()):
            relative = generated.relative_to(rendered)
            target = root / relative
            reject_adoption_symlinks(root, target)
            key = relative.as_posix()
            if key == args.answers_file:
                answer_copy = (generated, target)
                created.append(key)
            elif not target.exists():
                copies.append((generated, target))
                created.append(key)
            elif target.is_file() and filecmp.cmp(generated, target, shallow=False):
                preserved.append(key)
            else:
                candidates.append((generated, candidates_root / relative))
                customized.append(key)

        if answer_copy is None:
            message = "Rendered self-adoption template did not produce Copier answers"
            raise SystemExit(message)
        for _, target in [*copies, *candidates, answer_copy]:
            reject_adoption_symlinks(root, target)
            if target.exists() and not target.is_file():
                message = f"Template adoption file destination is not a file: {target}"
                raise SystemExit(message)
            for parent in target.parents:
                if parent.exists() and not parent.is_dir():
                    message = f"Template adoption parent is not a directory: {parent}"
                    raise SystemExit(message)
                if parent == root:
                    break

        written: list[Path] = []
        try:
            for generated, target in [*copies, *candidates]:
                written.append(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(generated, target)
            generated, target = answer_copy
            written.append(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generated, target)
        except OSError:
            for path in reversed(written):
                path.unlink(missing_ok=True)
            if candidates_root.exists():
                shutil.rmtree(candidates_root)
            raise

    return {
        "destination": str(root),
        "answers_file": str(root / args.answers_file),
        "template_source": source,
        "template_channel": "unstable",
        "selected_ref": selected_ref,
        "resolved_commit": commit,
        "created": created,
        "project_customized": customized,
        "preserved": preserved,
        "candidate_root": str(candidates_root),
        "changed_files": git_status(root),
        "ready_to_resume_feature_work": False,
        "next_step": "Reconcile every adoption candidate, remove the candidate directory, validate, and commit.",
    }


def parse_json_output(command: Sequence[str], *, cwd: Path) -> Any:
    completed = run_capture(command, cwd=cwd)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        msg = f"Expected JSON from {' '.join(command)}; output was not valid JSON"
        raise SystemExit(msg) from exc


def bd_available(root: Path) -> bool:
    if shutil.which("bd") is None:
        return False
    completed = subprocess.run(["bd", "--version"], cwd=root, check=False, capture_output=True, text=True)
    return completed.returncode == 0


def check_beads(root: Path) -> dict[str, Any]:
    """Run storage-mode-neutral Beads smoke checks."""
    info = parse_json_output(["bd", "info", "--json"], cwd=root)
    ready = parse_json_output(["bd", "ready", "--json", "--limit", "1"], cwd=root)

    formula_checked = False
    formula = root / ".beads/formulas/dstack-feature.formula.toml"
    if formula.is_file():
        parse_json_output(
            ["bd", "formula", "show", "dstack-feature", "--json"],
            cwd=root,
        )
        formula_checked = True

    database_path = info.get("database_path") if isinstance(info, dict) else None
    issue_count = info.get("issue_count") if isinstance(info, dict) else None
    return {
        "commands": [
            "bd info --json",
            "bd ready --json --limit 1",
            *(["bd formula show dstack-feature --json"] if formula_checked else []),
        ],
        "database_path": database_path,
        "issue_count": issue_count,
        "ready_sample_count": len(ready) if isinstance(ready, list) else None,
        "formula_checked": formula_checked,
    }


TOOLING_RERUN = "python3 scripts/setup-tooling.py --json"
TOOLING_PLATFORMS = ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"]


def skipped_tooling(*, recovery: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": "skipped",
        "mise": "skipped",
        "lock": {"status": "skipped", "path": "mise.lock", "error": None},
        "install": {"status": "skipped", "error": None},
        "hooks": {"status": "skipped", "error": None},
        "platforms": TOOLING_PLATFORMS,
        "recovery": recovery or [],
    }


def failed_tooling(error: str) -> dict[str, Any]:
    return {
        "status": "degraded",
        "mise": "skipped",
        "lock": {"status": "failed", "path": "mise.lock", "error": error},
        "install": {"status": "skipped", "error": None},
        "hooks": {"status": "skipped", "error": None},
        "platforms": TOOLING_PLATFORMS,
        "recovery": [TOOLING_RERUN],
    }


def tooling_result_error(result: dict[str, Any], destination: Path) -> str | None:
    if result.get("status") not in {"succeeded", "degraded", "skipped"}:
        return "tooling result has an invalid overall status"
    if result.get("mise") not in {"available", "unavailable", "skipped"}:
        return "tooling result has an invalid mise status"
    if result.get("platforms") != TOOLING_PLATFORMS:
        return "tooling result has an invalid platform contract"
    recovery = result.get("recovery")
    if not isinstance(recovery, list) or not all(isinstance(command, str) and command for command in recovery):
        return "tooling result has invalid recovery commands"

    allowed = {
        "lock": {"succeeded", "failed", "skipped"},
        "install": {"succeeded", "failed", "skipped"},
        "hooks": {"succeeded", "failed", "skipped", "skipped-no-git"},
    }
    for name, statuses in allowed.items():
        stage = result.get(name)
        if not isinstance(stage, dict) or stage.get("status") not in statuses:
            return f"tooling result has an invalid {name} stage"
        if "error" not in stage:
            return f"tooling result is missing the {name} error field"
        error = stage["error"]
        if error is not None and not isinstance(error, str):
            return f"tooling result has an invalid {name} error"
        if stage["status"] == "failed" and not error:
            return f"tooling result is missing the {name} failure error"
        if stage["status"] != "failed" and error is not None:
            return f"tooling result has an unexpected {name} error"
    if result["lock"].get("path") != "mise.lock":
        return "tooling result has an invalid lock path"

    lock = destination / "mise.lock"
    if result["lock"]["status"] == "succeeded" and (not lock.is_file() or lock.stat().st_size == 0):
        return "tooling reported a successful lock without a nonempty mise.lock"
    if result["status"] == "succeeded":
        if result["mise"] != "available" or any(result[name]["status"] != "succeeded" for name in allowed):
            return "tooling result has inconsistent successful stages"
        if recovery:
            return "successful tooling result unexpectedly contains recovery commands"
    return None


def provision_tooling(destination: Path) -> dict[str, Any]:
    script = destination / "scripts/setup-tooling.py"
    if not script.is_file():
        return failed_tooling("scripts/setup-tooling.py is not present after the template update")

    try:
        completed = subprocess.run(
            [sys.executable, str(script), "--json"],
            cwd=destination,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        completed = subprocess.CompletedProcess([sys.executable, str(script), "--json"], 127, "", str(exc))
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = None
    if completed.returncode == 0 and isinstance(result, dict):
        error = tooling_result_error(result, destination)
        if error is None:
            return result
    else:
        error = (completed.stderr or completed.stdout or "tooling provisioner returned invalid output").strip()[-2_000:]
    return failed_tooling(error)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", "-d", type=Path, default=Path.cwd())
    parser.add_argument("--answers-file", default=".copier-answers.yml")
    parser.add_argument("--template-source", help="Development source override for --adopt.")
    parser.add_argument("--adopt", action="store_true", help="Explicitly bootstrap the dstack template source.")
    parser.add_argument("--project-name")
    parser.add_argument("--project-slug")
    parser.add_argument("--purpose")
    parser.add_argument("--users")
    parser.add_argument("--scope")
    parser.add_argument("--boundaries")
    parser.add_argument(
        "--project-kind",
        choices=("library", "cli", "service", "application", "infrastructure", "documentation", "other"),
    )
    parser.add_argument("--language-profile", action="append", default=[], choices=LANGUAGE_PROFILES)
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Inspect Copier, legacy task, and Beads state without querying tags or modifying files.",
    )
    parser.add_argument(
        "--vcs-ref",
        help=(
            "Specific template tag, commit, branch, or HEAD. Defaults to the newest "
            "published stable tag from the Git source recorded by Copier."
        ),
    )
    parser.add_argument("--prereleases", action="store_true")
    channel = parser.add_mutually_exclusive_group()
    channel.add_argument("--stable", action="store_true", help="Use the newest stable release tag.")
    channel.add_argument("--unstable", action="store_true", help="Use the source default branch HEAD.")
    parser.add_argument("--conflict", choices=("inline", "rej"), default="inline")
    parser.add_argument("--add-profile", action="append", default=[], choices=LANGUAGE_PROFILES)
    parser.add_argument("--remove-profile", action="append", default=[], choices=LANGUAGE_PROFILES)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--pretend", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--skip-docs-check", action="store_true")
    parser.add_argument("--skip-beads-check", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    destination = git_root(args.destination.expanduser().resolve())
    preflight = project_preflight(destination, args.answers_file)
    if args.preflight:
        if args.json:
            print(json.dumps(preflight, indent=2, sort_keys=True))
        else:
            print(f"Recommended workflow: /{preflight['recommended_workflow']}")
            print(f"Reason: {preflight['reason']}")
            for path in preflight["legacy_task_files"]:
                print(f"  - {path}")
        return 0

    route = preflight["recommended_workflow"]
    if route == "update-project-adopt":
        if not args.adopt:
            message = (
                "The dstack template source is not Copier-managed. Run /update-project with explicit "
                "--adopt --unstable after reviewing the self-adoption contract."
            )
            raise SystemExit(message)
        if args.template_source is not None:
            message = "Template self-adoption does not accept --template-source; the official remote is authoritative"
            raise SystemExit(message)
        source = DEFAULT_TEMPLATE_SOURCE
        validate_template_source(source)
        selected_ref, commit = selected_revision(source, "unstable", None)
        result = adopt_template_source(
            destination,
            args,
            source=source,
            selected_ref=selected_ref,
            commit=commit,
        )
        result["preflight"] = preflight
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Adopted {source} {selected_ref} ({commit}) into {destination}")
            print(f"Reconcile candidates under {result['candidate_root']}")
        return 2 if result["project_customized"] else 0

    if args.adopt:
        message = "--adopt is valid only for the uninitialized dstack template source"
        raise SystemExit(message)

    if route == "migrate-workflow":
        tasks = preflight["legacy_task_files"]
        details = "\n".join(f"  - {path}" for path in tasks)
        message = (
            f"{preflight['reason']}. Do not run Copier update yet; offer /migrate-workflow "
            "and run it only after the user agrees."
        )
        if details:
            message += f"\nLegacy task files:\n{details}"
        raise SystemExit(message)

    answers = destination / args.answers_file
    answer_data = load_answers(answers)
    source = str(answer_data.get("_src_path") or "").strip()
    if not source:
        msg = f"Copier answers do not contain _src_path: {answers}"
        raise SystemExit(msg)

    validate_template_source(source)

    previous_profiles = canonical_language_profiles(answer_data.get("language_profiles", ["other"]))
    requested_profiles = updated_language_profiles(previous_profiles, args.add_profile, args.remove_profile)

    recorded_channel = answer_data.get("dstack_template_channel", "stable")
    if recorded_channel not in TEMPLATE_CHANNELS:
        message = "dstack_template_channel must be stable or unstable"
        raise SystemExit(message)
    channel = "unstable" if args.unstable else "stable" if args.stable else recorded_channel
    requested_vcs_ref = args.vcs_ref
    selected_ref, verified_source_commit = selected_revision(
        source,
        channel,
        requested_vcs_ref,
        include_prereleases=args.prereleases,
    )
    effective_vcs_ref = verified_source_commit

    before = git_status(destination)
    if before and not args.allow_dirty:
        preview = "\n".join(f"  {line}" for line in before[:25])
        msg = "Commit or stash changes before updating the template:\n" + preview
        raise SystemExit(msg)
    if unmerged_paths(destination):
        msg = "Resolve existing Git merge conflicts before updating the template"
        raise SystemExit(msg)

    baseline_rejects = reject_files(destination)
    try:
        run_update(
            destination,
            data={
                "language_profiles": requested_profiles,
                "dstack_template_channel": channel,
            },
            answers_file=args.answers_file,
            vcs_ref=effective_vcs_ref,
            use_prereleases=args.prereleases,
            defaults=not args.interactive,
            pretend=args.pretend,
            quiet=args.quiet or args.json,
            conflict=args.conflict,
            overwrite=True,
            unsafe=False,
        )
    except Exception as exc:  # Copier exposes multiple user-facing exception types.
        msg = f"Copier could not update {destination} to {effective_vcs_ref}: {exc}"
        raise SystemExit(msg) from exc

    conflicts: list[str] = []
    docs_validated = False
    beads_health: dict[str, Any] | None = None
    warnings: list[str] = []
    tooling = skipped_tooling()
    if not args.pretend:
        conflicts = scan_conflicts(destination, baseline_rejects=baseline_rejects)
        if conflicts:
            tooling = skipped_tooling(recovery=[TOOLING_RERUN])
            print("Copier produced unresolved conflicts:", file=sys.stderr)
            for path in conflicts:
                print(f"  - {path}", file=sys.stderr)
        else:
            tooling = provision_tooling(destination)
            if tooling["status"] != "succeeded":
                warnings.append("Tooling reconciliation is incomplete; run the reported recovery commands")

        if not conflicts and not args.skip_docs_check:
            checker = destination / "scripts/check-docs.py"
            if checker.exists():
                run(
                    ["uv", "run", str(checker)],
                    cwd=destination,
                    quiet=args.quiet or args.json,
                )
                docs_validated = True
            else:
                warnings.append("scripts/check-docs.py is not present; documentation validation skipped")

        if not conflicts and not args.skip_beads_check:
            if not bd_available(destination):
                warnings.append("bd is unavailable or its launcher cannot execute; Beads health checks skipped")
            else:
                beads_health = check_beads(destination)

    if not args.pretend and not conflicts:
        current_answers = load_answers(answers)
        write_copier_state(answers, current_answers, commit=verified_source_commit, channel=channel)

    changed = git_status(destination) if not args.pretend else []
    changed_paths = {line[3:] for line in changed if len(line) > 3}
    revision_changed = answer_data.get("_commit") != load_answers(answers).get("_commit")
    answers_only = bool(changed_paths) and changed_paths <= {args.answers_file}
    if not args.pretend and revision_changed and answers_only:
        warnings.append(
            "Template revision changed but only the Copier answers file changed; "
            "verify conditional template destinations and expected rendered output"
        )
    updated_answers = load_answers(answers) if answers.exists() else {}
    result = {
        "destination": str(destination),
        "answers_file": str(answers),
        "template_source": source,
        "previous_commit": answer_data.get("_commit"),
        "requested_vcs_ref": requested_vcs_ref,
        "template_channel": channel,
        "selected_ref": selected_ref,
        "vcs_ref": selected_ref,
        "resolved_commit": updated_answers.get("_commit"),
        "verified_source_commit": verified_source_commit,
        "previous_language_profiles": previous_profiles,
        "language_profiles": requested_profiles,
        "suggested_language_profiles": preflight["suggested_language_profiles"],
        "pretend": args.pretend,
        "conflicts": conflicts,
        "changed_files": changed,
        "docs_validated": docs_validated,
        "beads_checked": beads_health is not None,
        "beads_health": beads_health,
        "warnings": warnings,
        "tooling": tooling,
        "outstanding": [f"Tooling recovery: {command}" for command in tooling["recovery"]],
        "ready_to_resume_feature_work": bool(
            not args.pretend and not conflicts and tooling["status"] == "succeeded" and not changed
        ),
        "preflight": preflight,
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        action = "Previewed" if args.pretend else "Applied"
        print(f"{action} dstack template update {selected_ref} ({effective_vcs_ref}) in {destination}")
        if changed:
            print("Changed files:")
            for line in changed:
                print(f"  {line}")
        if beads_health is not None:
            print("Beads health checks passed:")
            for command in beads_health["commands"]:
                print(f"  - {command}")
        print(f"Tooling reconciliation: {tooling['status']}")
        for command in tooling["recovery"]:
            print(f"Tooling recovery: {command}")
        for warning in warnings:
            print(f"Warning: {warning}")
        print("Review the diff and commit the template update as a dedicated change.")
    return 2 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
