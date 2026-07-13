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
"""Create and initialize a new Copier-managed dstack project."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from copier import run_copy


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MANIFEST = SKILL_DIR / "SKILL.md"
BUNDLED_TEMPLATE_SOURCE = SKILL_DIR
DEFAULT_UPDATE_SOURCE = "gh:RobertDeRose/dstack"
FRONTMATTER_PATTERN = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---(?:\n|\Z)", re.DOTALL)
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
RELEASE_TAG_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")
REQUIRED_GENERATED_PATHS = (
    Path(".copier-answers.yml"),
    Path("AGENTS.md"),
    Path(".beads/formulas/feature-lifecycle.formula.toml"),
    Path("docs/book.toml"),
    Path("docs/src/SUMMARY.md"),
    Path("docs/src/planned-features.md"),
    Path("docs/src/features/_template/design.md"),
    Path("docs/src/features/_template/index.md"),
    Path("scripts/check-docs.py"),
)

# A project-local skills installation can exist before the project scaffold does.
ALLOWED_EXISTING_ENTRIES = {".git", "skills-lock.json"}


def load_yaml_mapping(path: Path, *, label: str) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        message = f"Unable to read {label} from {path}: {exc}"
        raise SystemExit(message) from exc
    if not isinstance(loaded, dict):
        message = f"{label.capitalize()} must be a mapping: {path}"
        raise SystemExit(message)
    return loaded


def load_skill_version(path: Path = SKILL_MANIFEST) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"Unable to read installed skill metadata from {path}: {exc}"
        raise SystemExit(message) from exc
    match = FRONTMATTER_PATTERN.match(text)
    if match is None:
        message = f"Installed skill has invalid frontmatter: {path}"
        raise SystemExit(message)
    try:
        manifest = yaml.safe_load(match.group("frontmatter"))
    except yaml.YAMLError as exc:
        message = f"Unable to parse installed skill metadata from {path}: {exc}"
        raise SystemExit(message) from exc
    if not isinstance(manifest, dict):
        message = f"Installed skill frontmatter must be a mapping: {path}"
        raise SystemExit(message)
    metadata = manifest.get("metadata")
    version = metadata.get("version") if isinstance(metadata, dict) else None
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        message = f"Installed skill metadata.version must be a stable X.Y.Z value: {path}"
        raise SystemExit(message)
    return version


def record_update_state(path: Path, *, source: str, commit: str) -> None:
    """Replace local-render state with the published source used for future updates."""
    data = load_yaml_mapping(path, label="Copier answers")
    recorded: dict[str, Any] = {"_commit": commit, "_src_path": source}
    recorded.update({key: value for key, value in data.items() if key not in recorded})
    rendered = yaml.safe_dump(recorded, allow_unicode=True, sort_keys=False)
    path.write_text(
        "# This file is managed by Copier. Do not edit it manually.\n" + rendered,
        encoding="utf-8",
    )


def validate_bundled_template() -> None:
    required = (BUNDLED_TEMPLATE_SOURCE / "copier.yml", BUNDLED_TEMPLATE_SOURCE / "template")
    missing = [path for path in required if not path.exists()]
    if missing:
        shown = ", ".join(str(path) for path in missing)
        message = f"The installed setup-project skill is incomplete; missing: {shown}"
        raise SystemExit(message)


def validate_template_source(source: str) -> None:
    if any(character in source for character in ("\n", "\r", "\x00")):
        message = "Template source contains prohibited control characters"
        raise SystemExit(message)
    if Path(source).expanduser().exists():
        return
    if source.startswith(("gh:", "gl:", "https://", "ssh://", "git@")):
        return
    message = (
        "Unsupported template source. Use an existing local path or an explicit "
        "gh:, gl:, https://, ssh://, or git@ source."
    )
    raise SystemExit(message)


def is_remote_template_source(source: str) -> bool:
    return source.startswith(("gh:", "gl:", "https://", "ssh://", "git@"))


def selected_vcs_ref(template_source: str, requested: str | None) -> str | None:
    if requested:
        return requested
    if is_remote_template_source(template_source):
        message = "A remote template override requires an explicit --vcs-ref."
        raise SystemExit(message)
    return None


def git_source(source: str) -> str:
    if source.startswith("gh:"):
        return f"https://github.com/{source.removeprefix('gh:')}.git"
    if source.startswith("gl:"):
        return f"https://gitlab.com/{source.removeprefix('gl:')}.git"
    return source


def require_release_tag(source: str, vcs_ref: str | None) -> str | None:
    if vcs_ref is None or RELEASE_TAG_PATTERN.fullmatch(vcs_ref) is None:
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
            "The setup helper will not fall back to an untagged HEAD."
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


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        message = "Project name must contain at least one letter or number"
        raise ValueError(message)
    return slug


def run_checked(command: Sequence[str], *, cwd: Path, quiet: bool) -> subprocess.CompletedProcess[str]:
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


def bd_available(cwd: Path) -> bool:
    if shutil.which("bd") is None:
        return False
    completed = subprocess.run(["bd", "--version"], cwd=cwd, check=False, capture_output=True, text=True)
    return completed.returncode == 0


def ensure_trailing_newline(path: Path) -> None:
    if not path.is_file():
        return
    content = path.read_bytes()
    if content and not content.endswith(b"\n"):
        path.write_bytes(content + b"\n")


def initialize_beads(destination: Path, args: argparse.Namespace, *, quiet: bool) -> None:
    command = ["bd", "init", "--skip-agents"]
    if args.beads_mode == "stealth":
        command.append("--stealth")
    elif args.beads_mode == "contributor":
        command.append("--contributor")
    elif args.beads_mode == "server":
        command.append("--server")
    if quiet:
        command.append("--quiet")
    run_checked(command, cwd=destination, quiet=quiet)
    for integration in args.setup:
        run_checked(["bd", "setup", integration], cwd=destination, quiet=quiet)
    run_checked(
        ["bd", "formula", "show", "feature-lifecycle", "--json"],
        cwd=destination,
        quiet=True,
    )
    ensure_trailing_newline(destination / ".beads/metadata.json")
    ensure_trailing_newline(destination / ".beads/config.yaml")


def verify_scaffold(destination: Path) -> None:
    missing = [path for path in REQUIRED_GENERATED_PATHS if not (destination / path).is_file()]
    if missing:
        details = "\n".join(f"  - {path}" for path in missing)
        message = f"Workflow scaffold is incomplete:\n{details}"
        raise SystemExit(message)
    forbidden = [Path("scripts/bootstrap.py"), Path("scripts/migrate-legacy-workflow.py"), Path("MIGRATION.md")]
    unexpected = [path for path in forbidden if (destination / path).exists()]
    if unexpected:
        details = "\n".join(f"  - {path}" for path in unexpected)
        message = f"New-project scaffold contains migration-only files:\n{details}"
        raise SystemExit(message)


def validate_docs(destination: Path, *, quiet: bool) -> None:
    command = ["uv", "run", "scripts/check-docs.py"]
    if quiet:
        command.append("--json")
    run_checked(command, cwd=destination, quiet=quiet)


def initialize_git(destination: Path, branch: str, *, quiet: bool) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return False
    if shutil.which("git") is None:
        message = "Git is required for Copier-managed template updates"
        raise SystemExit(message)

    result = subprocess.run(
        ["git", "-C", str(destination), "init", "-b", branch],
        check=False,
        capture_output=quiet,
        text=True,
    )
    if result.returncode != 0:
        run_checked(["git", "init"], cwd=destination, quiet=quiet)
        run_checked(["git", "branch", "-M", branch], cwd=destination, quiet=quiet)
    return True


def is_skills_cli_entry(entry: Path) -> bool:
    """Accept an installed skills tree, but not unrelated files beside it."""
    if not entry.is_dir():
        return False
    skill_root = entry if entry.name == "skills" else entry / "skills"
    if not skill_root.is_dir() or not any(skill_root.glob("*/SKILL.md")):
        return False
    return all(path.is_relative_to(skill_root) for path in entry.rglob("*"))


def unexpected_entries(destination: Path) -> list[Path]:
    if not destination.exists():
        return []
    return sorted(
        (
            entry
            for entry in destination.iterdir()
            if entry.name not in ALLOWED_EXISTING_ENTRIES and not is_skills_cli_entry(entry)
        ),
        key=lambda entry: entry.name,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_name", nargs="?", help="Human-readable project name; defaults to basename($PWD).")
    parser.add_argument(
        "--destination",
        "-d",
        type=Path,
        default=Path.cwd(),
        help="Destination directory; defaults to the current directory.",
    )
    parser.add_argument("--project-slug")
    parser.add_argument(
        "--description",
        default="A documentation-first software project managed with Beads.",
        help="One-line project description used by the generated README.",
    )
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--template-source",
        help="Development override for the template bundled with the installed setup-project skill.",
    )
    parser.add_argument(
        "--vcs-ref",
        help="Tag, branch, or commit for --template-source. The bundled template does not accept this option.",
    )
    parser.add_argument("--delete-readme", action="store_true")
    parser.add_argument("--no-git-init", action="store_true")
    parser.add_argument("--skip-post-setup", action="store_true")
    parser.add_argument("--skip-beads", action="store_true")
    parser.add_argument(
        "--beads-mode",
        choices=("default", "stealth", "contributor", "server"),
        default="stealth",
    )
    parser.add_argument(
        "--setup",
        action="append",
        default=[],
        metavar="INTEGRATION",
        help="Run bd setup for an integration after bd init; repeatable.",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    destination = args.destination.expanduser().resolve()
    skill_version = load_skill_version()
    using_bundled_template = args.template_source is None

    if using_bundled_template:
        if args.vcs_ref is not None:
            message = "--vcs-ref is only valid with an explicit --template-source override"
            raise SystemExit(message)
        validate_bundled_template()
        template_source = str(BUNDLED_TEMPLATE_SOURCE)
        render_vcs_ref = None
        update_source = DEFAULT_UPDATE_SOURCE
        recorded_vcs_ref: str | None = f"v{skill_version}"
        resolved_template_commit = None
    else:
        template_source = args.template_source
        validate_template_source(template_source)
        render_vcs_ref = selected_vcs_ref(template_source, args.vcs_ref)
        update_source = template_source
        recorded_vcs_ref = render_vcs_ref
        resolved_template_commit = require_release_tag(template_source, render_vcs_ref)

    project_name = (args.project_name or Path.cwd().name).strip()
    if not project_name:
        message = "Project name cannot be empty"
        raise SystemExit(message)
    project_slug = args.project_slug or slugify(project_name)

    answers = destination / ".copier-answers.yml"
    if answers.exists():
        message = (
            f"{destination} is already Copier-managed. /setup-project will not modify it; "
            "offer /update-project and run it only after the user agrees."
        )
        raise SystemExit(message)

    existing = unexpected_entries(destination)
    if existing:
        shown = "\n".join(f"  - {entry.name}" for entry in existing[:25])
        raise SystemExit(
            "Destination contains project files. New-project setup will not adopt or migrate them. "
            "Use /migrate-workflow for an existing project:\n" + shown
        )

    destination.mkdir(parents=True, exist_ok=True)
    run_copy(
        template_source,
        destination,
        data={
            "project_name": project_name,
            "project_slug": project_slug,
            "project_description": args.description,
            "repository_default_branch": args.default_branch,
            "include_readme": not args.delete_readme,
        },
        vcs_ref=render_vcs_ref,
        defaults=True,
        overwrite=False,
        quiet=args.quiet or args.json,
        unsafe=False,
    )

    if not answers.exists():
        message = "Copier completed without creating .copier-answers.yml"
        raise SystemExit(message)
    if using_bundled_template:
        if recorded_vcs_ref is None:
            message = "Bundled template setup did not determine a published update tag"
            raise AssertionError(message)
        record_update_state(answers, source=update_source, commit=recorded_vcs_ref)
    else:
        answer_data = load_yaml_mapping(answers, label="Copier answers")
        recorded_vcs_ref = str(answer_data.get("_commit") or render_vcs_ref or "") or None

    git_initialized = False
    if not args.no_git_init:
        git_initialized = initialize_git(destination, args.default_branch, quiet=args.quiet or args.json)

    beads_is_available = bd_available(destination)
    beads_initialized = False
    docs_validated = False
    post_setup_ran = False
    outstanding: list[str] = []
    if not args.skip_post_setup:
        verify_scaffold(destination)
        if args.skip_beads:
            outstanding.append("Beads initialization and verification")
        elif beads_is_available:
            initialize_beads(destination, args, quiet=args.quiet or args.json)
            beads_initialized = True
        else:
            outstanding.append("Beads initialization and verification")
        validate_docs(destination, quiet=args.quiet or args.json)
        docs_validated = True
        verify_scaffold(destination)
        post_setup_ran = True
    else:
        outstanding.append("Post-setup scaffold and documentation validation")
        if not args.skip_beads:
            outstanding.append("Beads initialization and verification")

    result = {
        "project_name": project_name,
        "project_slug": project_slug,
        "destination": str(destination),
        "template_source": template_source,
        "template_source_kind": "bundled" if using_bundled_template else "override",
        "update_source": update_source,
        "skill_version": skill_version,
        "vcs_ref": recorded_vcs_ref,
        "render_vcs_ref": render_vcs_ref,
        "resolved_template_commit": resolved_template_commit,
        "copier_answers": str(answers),
        "git_initialized": git_initialized,
        "post_setup_ran": post_setup_ran,
        "docs_validated": docs_validated,
        "beads_available": beads_is_available,
        "beads_initialized": beads_initialized,
        "readme_created": (destination / "README.md").exists(),
        "outstanding": outstanding,
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Created dstack project: {project_name}")
        print(f"Destination: {destination}")
        print(f"Template: {template_source} ({recorded_vcs_ref or 'unversioned override'})")
        print(f"Future update source: {update_source}")
        print(f"Copier state: {answers}")
        if beads_initialized:
            print("Beads initialized. Next: run 'bd prime', then use /plan-features.")
        elif args.skip_beads:
            print("Beads initialization and verification remain outstanding because --skip-beads was supplied.")
        elif not beads_is_available:
            print("warning: bd is unavailable; Beads initialization and verification remain outstanding")
            print("Install Beads, run 'bd init --stealth --skip-agents', then verify the feature-lifecycle formula.")
        if docs_validated:
            print("Documentation scaffold validation passed.")
        print("Commit the initial scaffold before applying Copier updates.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130) from None
