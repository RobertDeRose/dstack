#!/usr/bin/env python3
"""Compare an executing installed skill with locally available dstack evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


SCHEMA = "dstack.skill-version.v1"
REFRESH_COMMAND = "npx skills update"
VERSION_LINE = re.compile(r"(?m)^[ \t]+version:[ \t]*[\"']?([^\"'\s#]+)")
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class VersionRead:
    version: str | None
    error: str | None = None


def read_skill_version(skill_dir: Path) -> VersionRead:
    path = skill_dir / "SKILL.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return VersionRead(None, f"cannot read {path}: {exc}")

    if not text.startswith("---\n"):
        return VersionRead(None, f"missing frontmatter in {path}")
    end = text.find("\n---", 4)
    if end < 0:
        return VersionRead(None, f"unterminated frontmatter in {path}")
    frontmatter = text[4:end]
    metadata_start = re.search(r"(?m)^metadata:\s*$", frontmatter)
    if metadata_start is None:
        return VersionRead(None, f"missing metadata in {path}")
    version = VERSION_LINE.search(frontmatter[metadata_start.end() :])
    if version is None:
        return VersionRead(None, f"missing metadata.version in {path}")
    return VersionRead(version.group(1))


def read_project_version(root: Path) -> VersionRead:
    path = root / "pyproject.toml"
    if not path.is_file():
        return VersionRead(None)
    try:
        with path.open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return VersionRead(None, f"cannot read {path}: {exc}")
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or not version:
        return VersionRead(None)
    return VersionRead(version)


def read_project_name(root: Path) -> str | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        with path.open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = project.get("name") if isinstance(project, dict) else None
    return name if isinstance(name, str) else None


def is_dstack_root(root: Path, skill_name: str, *, require_project: bool) -> bool:
    if not (root / "skills" / skill_name / "SKILL.md").is_file():
        return False
    if not require_project:
        return True
    if not (root / "skills/dstack-core/SKILL.md").is_file():
        return False
    name = read_project_name(root)
    return name is not None and name.casefold() in {"dstack-workflow", "dstack"}


def ancestors(path: Path) -> list[Path]:
    resolved = path.expanduser().resolve()
    return [resolved, *resolved.parents]


def infer_installed_skill_dir(skill_name: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    core_dir = Path(__file__).resolve().parents[1]
    return (core_dir.parent / skill_name).resolve()


def find_canonical_root(
    skill_name: str,
    installed_dir: Path,
    configured_root: Path | None,
    *,
    cwd: Path,
    installed_was_explicit: bool,
) -> tuple[Path | None, str | None]:
    if configured_root is not None:
        root = configured_root.expanduser().resolve()
        if is_dstack_root(root, skill_name, require_project=False):
            return root, "configured"
        return None, f"configured canonical root does not contain skills/{skill_name}/SKILL.md: {root}"

    candidates: list[Path] = []
    if not installed_was_explicit:
        candidates.extend(ancestors(installed_dir))
    candidates.extend(ancestors(cwd))
    seen: set[Path] = set()
    for root in candidates:
        if root in seen:
            continue
        seen.add(root)
        if is_dstack_root(root, skill_name, require_project=True):
            return root, "local"
    return None, "no local canonical dstack checkout was found"


def git_head(root: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed git subcommand and validated path argument
            [git, "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def canonical_version(root: Path, skill_name: str) -> tuple[str | None, str | None, str | None]:
    skill = read_skill_version(root / "skills" / skill_name)
    if skill.version is None:
        return None, None, skill.error
    project = read_project_version(root)
    if project.error:
        return None, None, project.error
    if project.version is not None and project.version != skill.version:
        return (
            None,
            None,
            (
                f"canonical project.version {project.version!r} differs from "
                f"skills/{skill_name}/SKILL.md metadata.version {skill.version!r}"
            ),
        )
    return project.version or skill.version, git_head(root), None


def evidence(
    skill_name: str,
    installed_dir: Path,
    configured_root: Path | None,
    *,
    cwd: Path,
    installed_was_explicit: bool,
) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    installed = read_skill_version(installed_dir)
    canonical_root, canonical_source = find_canonical_root(
        skill_name,
        installed_dir,
        configured_root,
        cwd=cwd,
        installed_was_explicit=installed_was_explicit,
    )

    canonical: str | None = None
    commit: str | None = None
    canonical_error: str | None = None
    if canonical_root is not None:
        canonical, commit, canonical_error = canonical_version(canonical_root, skill_name)

    if installed.version is None:
        status = "invalid-installed"
        message = installed.error or "installed skill version is unavailable"
        refresh_command: str | None = None
    elif canonical is None:
        status = "unavailable"
        detail = canonical_error or "canonical version evidence is unavailable"
        message = f"Canonical dstack version evidence is unavailable ({detail}); continuing without a freshness claim."
        refresh_command = None
    elif installed.version == canonical:
        status = "current"
        message = (
            f"Installed {skill_name} skill version {installed.version} matches canonical dstack version {canonical}."
        )
        refresh_command = None
    else:
        status = "stale"
        message = (
            f"Installed {skill_name} skill version {installed.version} is stale relative to canonical dstack "
            f"version {canonical}; refresh with {REFRESH_COMMAND}."
        )
        refresh_command = REFRESH_COMMAND

    line_parts = [
        f"Skill version evidence: schema={SCHEMA}",
        f"skill={skill_name}",
        f"installed={installed.version or 'unavailable'}",
        f"canonical={canonical or 'unavailable'}",
        f"status={status}",
        f"installed_source={installed_dir / 'SKILL.md'}",
        f"checked_at={checked_at}",
    ]
    if canonical_root is not None:
        line_parts.append(f"canonical_source={canonical_root}")
    if commit is not None:
        line_parts.append(f"canonical_commit={commit}")
    if refresh_command is not None:
        line_parts.append(f"action={refresh_command}")

    return {
        "schema": SCHEMA,
        "skill_name": skill_name,
        "installed_version": installed.version,
        "installed_source": str(installed_dir / "SKILL.md"),
        "canonical_version": canonical,
        "canonical_source": str(canonical_root) if canonical_root is not None else None,
        "canonical_source_kind": canonical_source,
        "canonical_commit": commit,
        "status": status,
        "message": message,
        "refresh_command": refresh_command,
        "checked_at": checked_at,
        "evidence_line": " ".join(line_parts),
    }


def skill_name_argument(value: str) -> str:
    if not SKILL_NAME.fullmatch(value):
        message = "skill name must contain only lowercase letters, digits, and hyphens"
        raise argparse.ArgumentTypeError(message)
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-name", required=True, type=skill_name_argument, help="installed dstack skill directory name"
    )
    parser.add_argument("--installed-skill-dir", type=Path, help="directory containing the executing SKILL.md")
    parser.add_argument(
        "--canonical-root",
        type=Path,
        help="local canonical dstack checkout; defaults to DSTACK_CANONICAL_ROOT or safe local discovery",
    )
    parser.add_argument("--format", choices=("json", "line"), default="line")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    installed_was_explicit = args.installed_skill_dir is not None
    configured_root = args.canonical_root
    if configured_root is None:
        environment_root = os.environ.get("DSTACK_CANONICAL_ROOT")
        configured_root = Path(environment_root) if environment_root else None
    result = evidence(
        args.skill_name,
        infer_installed_skill_dir(args.skill_name, args.installed_skill_dir),
        configured_root,
        cwd=Path.cwd(),
        installed_was_explicit=installed_was_explicit,
    )
    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
    else:
        print(result["evidence_line"])
        print(result["message"], file=sys.stderr)
    return 2 if result["status"] == "invalid-installed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
