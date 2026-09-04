from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

from .core import DstackError
from .output import emit

MANAGED_KEY = "dstack-managed"
CURRENT_SKILLS = (
    "dstack-audit-feature",
    "dstack-implement",
    "dstack-plan-feature",
    "dstack-review-plan",
)
CURRENT_PROMPTS = (
    "audit-feature.md",
    "implement.md",
    "plan-feature.md",
    "review-plan.md",
)


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


def _owned_prompt(path: Path, expected_name: str) -> bool:
    metadata = _frontmatter(path)
    return metadata.get(MANAGED_KEY) == "true" and metadata.get("name") == expected_name


def _remove_stale_owned_resources(skills_target: Path, prompts_target: Path) -> list[str]:
    """Remove only dStack-owned resources outside the current manifest."""

    removed: list[str] = []
    for directory in sorted(skills_target.iterdir()):
        if not directory.is_dir() or directory.name in CURRENT_SKILLS:
            continue
        _assert_no_symlink(directory)
        skill = directory / "SKILL.md"
        if skill.is_file() and _owned_skill(skill, directory.name):
            shutil.rmtree(directory)
            removed.append(f"skills/{directory.name}")

    for prompt in sorted(prompts_target.glob("*.md")):
        if prompt.name in CURRENT_PROMPTS:
            continue
        _assert_no_symlink(prompt)
        if _owned_prompt(prompt, prompt.stem):
            prompt.unlink()
            removed.append(f"prompts/{prompt.name}")
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


def _verify_packaged_manifest(skill_source: Path, prompt_source: Path) -> None:
    packaged_skills = {path.name for path in skill_source.iterdir() if path.is_dir()}
    packaged_prompts = {path.name for path in prompt_source.glob("*.md")}
    expected_skills = set(CURRENT_SKILLS)
    expected_prompts = set(CURRENT_PROMPTS)
    if packaged_skills != expected_skills:
        raise DstackError(
            "packaged skill manifest differs from the supported set: "
            f"expected={sorted(expected_skills)}, observed={sorted(packaged_skills)}"
        )
    if packaged_prompts != expected_prompts:
        raise DstackError(
            "packaged prompt manifest differs from the supported set: "
            f"expected={sorted(expected_prompts)}, observed={sorted(packaged_prompts)}"
        )


def install_skills(agent_dir: Path) -> dict[str, object]:
    source = asset_root()
    skill_source = source / "skills"
    prompt_source = source / "prompts"
    _verify_packaged_manifest(skill_source, prompt_source)

    original_target = agent_dir.expanduser()
    _assert_no_symlink(original_target)
    target = original_target.resolve()
    skills_target = target / "skills"
    prompts_target = target / "prompts"
    try:
        for path in (skills_target, prompts_target):
            _assert_no_symlink(path)
        skills_target.mkdir(parents=True, exist_ok=True)
        prompts_target.mkdir(parents=True, exist_ok=True)
        removed = _remove_stale_owned_resources(skills_target, prompts_target)

        for name in CURRENT_SKILLS:
            _replace_skill(skill_source / name, skills_target / name)
        for name in CURRENT_PROMPTS:
            _replace_prompt(prompt_source / name, prompts_target / name)
    except DstackError:
        raise
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot install dStack agent resources under {target}: {exc}") from exc

    return {
        "status": "ok",
        "agent_dir": str(target),
        "skills": list(CURRENT_SKILLS),
        "prompts": list(CURRENT_PROMPTS),
        "removed_stale": removed,
    }


def cmd_install_skills(args: argparse.Namespace) -> int:
    emit(install_skills(args.agent_dir))
    return 0
