from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from .core import DstackError

SYSTEM_BEGIN = "<!-- dstack:managed-system-prompt:begin -->"
SYSTEM_END = "<!-- dstack:managed-system-prompt:end -->"
MANAGED_KEY = "dstack-managed"
LEGACY_SKILL_NAMES = (
    "adopt-feature",
    "audit-project",
    "close-feature",
    "dstack-core",
    "dstack-beads-core",
    "dstack-beads-adopt-feature",
    "dstack-beads-setup-project",
    "dstack-beads-start-feature",
    "implement-feature",
    "implement-task",
    "migrate-workflow",
    "plan-feature",
    "plan-features",
    "project-alignment-execute",
    "project-alignment-land",
    "project-alignment-review",
    "review-feature-spec",
    "setup-project",
    "start-feature",
    "update-project",
)
LEGACY_PROMPT_NAMES = ("adopt-feature.md", "setup-project.md", "start-feature.md")


def asset_root() -> Path:
    return Path(__file__).resolve().parent / "assets"


def default_agent_dir() -> Path:
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".pi" / "agent"


def _assert_no_symlink(path: Path) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise DstackError(f"managed destination must not be a symlink: {path}")
        if current.parent == current:
            return
        current = current.parent


def _atomic_write_text(path: Path, content: str) -> None:
    _assert_no_symlink(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, raw_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(raw_path, mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(raw_path, path)
    finally:
        Path(raw_path).unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    _assert_no_symlink(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink(destination)
    fd, raw_path = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(fd)
    try:
        shutil.copy2(source, raw_path)
        os.replace(raw_path, destination)
    finally:
        Path(raw_path).unlink(missing_ok=True)


def _frontmatter(path: Path) -> dict[str, str]:
    _assert_no_symlink(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DstackError(f"cannot read installed agent resource: {path}") from exc
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() and key.strip() not in result:
            result[key.strip()] = value.strip().strip('"')
    return result


def _owned_skill(path: Path, expected_name: str) -> bool:
    metadata = _frontmatter(path)
    return metadata.get(MANAGED_KEY) == "true" and metadata.get("name") == expected_name


def _owned_prompt(path: Path, expected_name: str | None = None) -> bool:
    metadata = _frontmatter(path)
    if metadata.get(MANAGED_KEY) != "true":
        return False
    return expected_name is None or metadata.get("name") == expected_name


def _managed_block_bounds(current: str) -> tuple[int, int] | None:
    begins = current.count(SYSTEM_BEGIN)
    ends = current.count(SYSTEM_END)
    if begins == 0 and ends == 0:
        return None
    if begins != 1 or ends != 1:
        raise DstackError("managed system prompt must contain exactly one complete block")
    begin = current.find(SYSTEM_BEGIN)
    end = current.find(SYSTEM_END)
    if end < begin:
        raise DstackError("managed system prompt markers are out of order")
    return begin, end + len(SYSTEM_END)


def _validate_managed_destination(path: Path) -> None:
    _assert_no_symlink(path)
    if not path.exists():
        return
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot read managed destination: {path}") from exc
    _managed_block_bounds(current)


def _replace_managed_block(path: Path, content: str) -> None:
    _validate_managed_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    block = f"{SYSTEM_BEGIN}\n{content.rstrip()}\n{SYSTEM_END}"
    if not path.exists():
        updated = block + "\n"
    else:
        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DstackError(f"cannot read managed destination: {path}") from exc
        bounds = _managed_block_bounds(current)
        if bounds is None:
            updated = current.rstrip() + "\n\n" + block + "\n"
        else:
            begin, end = bounds
            updated = current[:begin].rstrip() + "\n\n" + block + current[end:]
    _atomic_write_text(path, updated.lstrip("\n"))


def _remove_stale_resources(skills_target: Path, prompts_target: Path) -> list[str]:
    removed: list[str] = []
    for name in LEGACY_SKILL_NAMES:
        directory = skills_target / name
        _assert_no_symlink(directory)
        skill = directory / "SKILL.md"
        if skill.is_file() and _owned_skill(skill, name):
            shutil.rmtree(directory)
            removed.append(f"skills/{name}")
    for filename in LEGACY_PROMPT_NAMES:
        prompt = prompts_target / filename
        _assert_no_symlink(prompt)
        if prompt.is_file() and _owned_prompt(prompt, Path(filename).stem):
            prompt.unlink()
            removed.append(f"prompts/{filename}")
    return removed


def _replace_skill(source: Path, destination: Path) -> None:
    source_skill = source / "SKILL.md"
    if not _owned_skill(source_skill, source.name):
        raise DstackError(f"packaged skill lacks dStack ownership marker: {source.name}")
    _assert_no_symlink(destination)
    if destination.exists():
        installed = destination / "SKILL.md"
        if not installed.is_file() or not _owned_skill(installed, source.name):
            raise DstackError(f"refusing to replace user-owned skill: {destination}")
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _replace_prompt(source: Path, destination: Path) -> None:
    expected_name = source.stem
    if not _owned_prompt(source, expected_name):
        raise DstackError(f"packaged prompt lacks dStack ownership marker: {source.name}")
    _assert_no_symlink(destination)
    if destination.exists() and (not destination.is_file() or not _owned_prompt(destination, expected_name)):
        raise DstackError(f"refusing to replace user-owned prompt: {destination}")
    _atomic_copy(source, destination)


def install_skills(agent_dir: Path) -> dict[str, object]:
    source = asset_root()
    skill_source = source / "skills"
    prompt_source = source / "prompts"
    original_target = agent_dir.expanduser()
    _assert_no_symlink(original_target)
    target = original_target.resolve()
    skills_target = target / "skills"
    prompts_target = target / "prompts"
    system_path = target / "APPEND_SYSTEM.md"
    try:
        for path in (skills_target, prompts_target, system_path):
            _assert_no_symlink(path)
        _validate_managed_destination(system_path)
        skills_target.mkdir(parents=True, exist_ok=True)
        prompts_target.mkdir(parents=True, exist_ok=True)
        removed = _remove_stale_resources(skills_target, prompts_target)

        installed_skills: list[str] = []
        for path in sorted(skill_source.iterdir()):
            if not path.is_dir():
                continue
            _replace_skill(path, skills_target / path.name)
            installed_skills.append(path.name)

        installed_prompts: list[str] = []
        for path in sorted(prompt_source.glob("*.md")):
            _replace_prompt(path, prompts_target / path.name)
            installed_prompts.append(path.name)

        try:
            system_content = (source / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DstackError(f"cannot read packaged system guidance: {source / 'APPEND_SYSTEM.md'}") from exc
        _replace_managed_block(system_path, system_content)
    except DstackError:
        raise
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot install dStack agent resources under {target}: {exc}") from exc

    return {
        "status": "ok",
        "agent_dir": str(target),
        "skills": installed_skills,
        "prompts": installed_prompts,
        "system_prompt": str(system_path),
        "removed_stale": removed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install dStack Pi skills, prompts, and system guidance.")
    parser.add_argument(
        "--agent-dir",
        type=Path,
        default=default_agent_dir(),
        help="Pi agent directory; defaults to PI_CODING_AGENT_DIR or ~/.pi/agent.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = install_skills(args.agent_dir)
    except DstackError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
