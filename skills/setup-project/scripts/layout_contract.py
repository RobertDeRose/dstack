# ruff: noqa: EM101, EM102
"""Shared repository-layout answer validation and preflight."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any


LANGUAGE_PROFILES = ("python", "typescript", "rust", "go", "elixir", "nix", "other")
PACKAGE_KEYS = {"display_name", "slug", "path", "language_profiles"}
RESERVED_ROOTS = {".git", ".beads", "docs", "migration", "scripts", "skills"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _profiles(value: Any, *, package: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{package}.language_profiles must be a nonempty list")
    unknown = sorted(set(value) - set(LANGUAGE_PROFILES))
    if unknown:
        raise ValueError(f"{package}.language_profiles contains unknown profiles: {', '.join(unknown)}")
    if len(value) != len(set(value)):
        raise ValueError(f"{package}.language_profiles must not contain duplicates")
    canonical = [profile for profile in LANGUAGE_PROFILES if profile in value]
    if value != canonical:
        raise ValueError(f"{package}.language_profiles must use canonical order: {', '.join(canonical)}")
    if "other" in value and len(value) > 1:
        raise ValueError(f"{package}.language_profiles cannot combine other with recognized profiles")
    return value


def _path(value: Any, *, package: str, root: Path) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{package}.path must be a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if not path.parts:
        raise ValueError(f"{package}.path cannot be .")
    if path.is_absolute():
        raise ValueError(f"{package}.path must be relative")
    if value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{package}.path must be normalized and cannot contain . or ..")
    if path.parts[0].casefold() in RESERVED_ROOTS:
        raise ValueError(f"{package}.path is reserved for root-owned state: {value}")
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{package}.path resolves through a symlink: {value}")
    return path


def validate_layout(layout: Any, packages: Any, root: Path) -> dict[str, Any]:
    """Validate exact layout answers and return deterministic preflight state."""
    if layout not in {"single-package", "monorepo"}:
        raise ValueError("repository_layout must be single-package or monorepo")
    if not isinstance(packages, list):
        raise ValueError("monorepo_packages must be a list")
    if layout == "single-package":
        if packages:
            raise ValueError("monorepo_packages must be empty in single-package mode")
        return {"repository_layout": layout, "packages": [], "collisions": []}
    if not 1 <= len(packages) <= 32:
        raise ValueError("monorepo mode requires 1-32 packages")

    normalized: list[dict[str, Any]] = []
    slugs: set[str] = set()
    paths: list[PurePosixPath] = []
    folded_paths: set[str] = set()
    collisions: list[str] = []
    for index, value in enumerate(packages, 1):
        label = f"monorepo_packages[{index - 1}]"
        if not isinstance(value, dict) or set(value) != PACKAGE_KEYS:
            raise ValueError(f"{label} must contain exactly: {', '.join(sorted(PACKAGE_KEYS))}")
        display_name = value["display_name"]
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError(f"{label}.display_name must be nonempty text")
        slug = value["slug"]
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise ValueError(f"{label}.slug must match [a-z0-9]+(?:-[a-z0-9]+)*")
        folded_slug = slug.casefold()
        if folded_slug in slugs:
            raise ValueError(f"Package slug is not case-fold unique: {slug}")
        slugs.add(folded_slug)
        path = _path(value["path"], package=label, root=root)
        folded_path = path.as_posix().casefold()
        if folded_path in folded_paths:
            raise ValueError(f"Package path is not case-fold unique: {path}")
        folded = PurePosixPath(folded_path)
        for previous in paths:
            folded_previous = PurePosixPath(previous.as_posix().casefold())
            if folded.is_relative_to(folded_previous) or folded_previous.is_relative_to(folded):
                raise ValueError(f"Package paths cannot overlap: {previous} and {path}")
        folded_paths.add(folded_path)
        paths.append(path)
        destination = root.joinpath(*path.parts)
        if destination.exists() or destination.is_symlink():
            collisions.append(path.as_posix())
        normalized.append(
            {
                "display_name": display_name,
                "slug": slug,
                "path": path.as_posix(),
                "language_profiles": _profiles(value["language_profiles"], package=label),
                "destination": str(destination),
                "occupied": destination.exists() or destination.is_symlink(),
            }
        )
    return {"repository_layout": layout, "packages": normalized, "collisions": collisions}
