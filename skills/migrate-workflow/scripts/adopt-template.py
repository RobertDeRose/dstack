#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "copier>=9.16,<10",
#     "PyYAML>=6.0,<7",
# ]
# ///
# ruff: noqa: S603, S607
"""Adopt an existing repository into the tagged dstack Copier template."""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import yaml
from copier import run_copy


DEFAULT_TEMPLATE_SOURCE = "gh:RobertDeRose/dstack"
RELEASE_TAG_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")
CURRENT_ANSWER_KEYS = (
    "project_name",
    "project_slug",
    "project_description",
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


def preserve_or_stage_candidate(source: Path, target: Path, root: Path) -> str:
    """Copy missing scaffold files, but stage conflicts for explicit manual reconciliation."""
    relative = target.relative_to(root)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return "created"
    if filecmp.cmp(source, target, shallow=False):
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
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--template-source",
        help="Template source override; defaults to existing Copier state or the official dstack repository.",
    )
    parser.add_argument("--vcs-ref")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


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
    recorded_description = str(existing_answers.get("project_description") or "").strip()
    recorded_branch = str(existing_answers.get("repository_default_branch") or "").strip()
    recorded_readme = existing_answers.get("include_readme")
    project_name = (args.project_name or recorded_name or root.name).strip()
    project_slug = args.project_slug or recorded_slug or slugify(project_name)
    project_description = recorded_description or "A documentation-first software project managed with Beads."
    default_branch = args.default_branch if args.default_branch != "main" else recorded_branch or args.default_branch
    include_readme = recorded_readme if isinstance(recorded_readme, bool) else True

    with tempfile.TemporaryDirectory(prefix="dstack-adopt-") as temporary:
        rendered = Path(temporary) / "rendered"
        run_copy(
            template_source,
            rendered,
            data={
                "project_name": project_name,
                "project_slug": project_slug,
                "project_description": project_description,
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
                status = preserve_or_stage_candidate(source, target, root)
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
