from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

from .core import DstackError, assert_no_symlink_components
from .output import emit

MANAGED_KEY = "dstack-managed"
CURRENT_SKILLS = (
    "dstack-audit-project",
    "dstack-close-feature",
    "dstack-implement",
    "dstack-plan-feature",
    "dstack-review-plan",
)
CURRENT_PROMPTS = (
    "audit-project.md",
    "close-feature.md",
    "implement.md",
    "plan-feature.md",
    "review-plan.md",
)


def asset_root() -> Path:
    return Path(__file__).resolve().parent / "assets"


def default_agent_dir() -> Path:
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".pi" / "agent"


def _frontmatter(path: Path) -> dict[str, str]:
    assert_no_symlink_components(path, purpose="managed destination")
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


def _stale_owned_resources(skills_target: Path, prompts_target: Path) -> list[tuple[Path, str]]:
    """Find removable dStack resources without mutating the installation."""

    stale: list[tuple[Path, str]] = []
    for target, kind in ((skills_target, "skills"), (prompts_target, "prompts")):
        assert_no_symlink_components(target, purpose="managed destination")
        if target.exists() and not target.is_dir():
            raise DstackError(f"agent {kind} destination is not a directory: {target}")

    if skills_target.exists():
        for directory in sorted(skills_target.iterdir()):
            if not directory.is_dir() or directory.name in CURRENT_SKILLS:
                continue
            assert_no_symlink_components(directory, purpose="managed destination")
            skill = directory / "SKILL.md"
            if skill.is_file() and _owned_skill(skill, directory.name):
                stale.append((directory, f"skills/{directory.name}"))

    if prompts_target.exists():
        for prompt in sorted(prompts_target.glob("*.md")):
            if prompt.name in CURRENT_PROMPTS:
                continue
            assert_no_symlink_components(prompt, purpose="managed destination")
            if _owned_prompt(prompt, prompt.stem):
                stale.append((prompt, f"prompts/{prompt.name}"))
    return stale


def _preflight_resources(
    skill_source: Path,
    prompt_source: Path,
    skills_target: Path,
    prompts_target: Path,
) -> list[tuple[Path, str]]:
    """Validate every source and destination before changing any resource."""

    stale = _stale_owned_resources(skills_target, prompts_target)
    for name in CURRENT_SKILLS:
        source_skill = skill_source / name / "SKILL.md"
        if not _owned_skill(source_skill, name):
            raise DstackError(f"packaged skill lacks dStack ownership marker: {name}")
        if _frontmatter(source_skill).get("disable-model-invocation") != "true":
            raise DstackError(f"packaged skill must disable model invocation: {name}")

        destination = skills_target / name
        assert_no_symlink_components(destination, purpose="managed destination")
        if destination.exists():
            installed = destination / "SKILL.md"
            if not destination.is_dir() or not installed.is_file() or not _owned_skill(installed, name):
                raise DstackError(f"refusing to replace user-owned skill: {destination}")

    for name in CURRENT_PROMPTS:
        source = prompt_source / name
        expected_name = source.stem
        if not _owned_prompt(source, expected_name):
            raise DstackError(f"packaged prompt lacks dStack ownership marker: {name}")

        destination = prompts_target / name
        assert_no_symlink_components(destination, purpose="managed destination")
        if destination.exists() and (not destination.is_file() or not _owned_prompt(destination, expected_name)):
            raise DstackError(f"refusing to replace user-owned prompt: {destination}")
    return stale


def _stage_resources(
    skill_source: Path,
    prompt_source: Path,
    skills_target: Path,
    prompts_target: Path,
    staging: Path,
) -> list[tuple[Path, Path]]:
    staged_skills = staging / "new/skills"
    staged_prompts = staging / "new/prompts"
    staged_skills.mkdir(parents=True)
    staged_prompts.mkdir(parents=True)

    resources: list[tuple[Path, Path]] = []
    for name in CURRENT_SKILLS:
        staged = staged_skills / name
        shutil.copytree(skill_source / name, staged, copy_function=shutil.copy2)
        resources.append((staged, skills_target / name))
    for name in CURRENT_PROMPTS:
        staged = staged_prompts / name
        shutil.copy2(prompt_source / name, staged)
        resources.append((staged, prompts_target / name))
    return resources


def _remove_resource(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


class IncompleteRollback(DstackError):
    """The installer must retain its recovery copies for manual restoration."""


def _apply_resources(
    resources: list[tuple[Path, Path]],
    stale: list[tuple[Path, str]],
    backup_root: Path,
) -> None:
    """Install staged resources and restore the prior installation on failure."""

    backup_root.mkdir(parents=True)
    installed: list[Path] = []
    backups: list[tuple[Path, Path]] = []
    try:
        for staged, destination in resources:
            if destination.exists():
                backup = backup_root / f"{len(backups):03d}"
                os.replace(destination, backup)
                backups.append((destination, backup))
            os.replace(staged, destination)
            installed.append(destination)
        for path, _label in stale:
            backup = backup_root / f"{len(backups):03d}"
            os.replace(path, backup)
            backups.append((path, backup))
    except OSError as exc:
        rollback_errors: list[str] = []
        for path in reversed(installed):
            try:
                _remove_resource(path)
            except OSError as rollback_exc:
                rollback_errors.append(f"remove {path}: {rollback_exc}")
        for destination, backup in reversed(backups):
            try:
                os.replace(backup, destination)
            except OSError as rollback_exc:
                rollback_errors.append(f"restore {backup} -> {destination}: {rollback_exc}")
        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise IncompleteRollback(
                f"agent resource installation failed and rollback was incomplete; "
                f"recovery copies retained at {backup_root}: {details}"
            ) from exc
        raise


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


def install_agent_resources(agent_dir: Path) -> dict[str, object]:
    source = asset_root()
    skill_source = source / "skills"
    prompt_source = source / "prompts"
    _verify_packaged_manifest(skill_source, prompt_source)

    original_target = agent_dir.expanduser()
    assert_no_symlink_components(original_target, purpose="managed destination")
    target = original_target.resolve()
    skills_target = target / "skills"
    prompts_target = target / "prompts"
    try:
        stale = _preflight_resources(skill_source, prompt_source, skills_target, prompts_target)
        skills_target.mkdir(parents=True, exist_ok=True)
        prompts_target.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".dstack-install-", dir=target))
        retain = False
        try:
            resources = _stage_resources(skill_source, prompt_source, skills_target, prompts_target, staging)
            _apply_resources(resources, stale, staging / "backup")
        except IncompleteRollback:
            retain = True
            raise
        finally:
            if not retain:
                shutil.rmtree(staging)
    except DstackError:
        raise
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot install dStack agent resources under {target}: {exc}") from exc

    return {
        "status": "ok",
        "agent_dir": str(target),
        "skills": list(CURRENT_SKILLS),
        "prompts": list(CURRENT_PROMPTS),
        "removed_stale": [label for _path, label in stale],
    }


def cmd_install_agent_resources(args: argparse.Namespace) -> int:
    emit(install_agent_resources(args.agent_dir))
    return 0
