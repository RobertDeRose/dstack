"""Git repository/session authority and path confinement adapters."""

# ruff: noqa: S603, S607

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from migration_core import (
    _path_has_symlink,
    DEFAULT_TASK_ARCHIVE,
    DELIVERED_CANDIDATE_DIR,
    dump_json,
    FEATURES_PATH,
    load_json,
    MigrationError,
    SESSION_AUTHORITY_PATH,
    SESSION_RESUME_LOG_PATH,
    shell_command,
    utc_now,
)


def git_output(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = f"Git command failed: git {shell_command(arguments)}\n{result.stderr.strip()}"
        raise MigrationError(message)
    return result.stdout.strip()


def git_repository(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def session_resume_approval(branch: str, root: Path) -> str:
    return f"RESUME DSTACK MIGRATION {branch} IN {root.resolve()}"


def authorize_session(
    root: Path,
    *,
    mode: str,
    base_branch: str,
    migration_branch: str,
    approval: str,
) -> None:
    if not git_repository(root):
        msg = "Migration session authority requires a Git repository"
        raise MigrationError(msg)
    current_branch = git_output(root, "branch", "--show-current")
    if not current_branch:
        msg = "Migration must run on a named branch, not detached HEAD"
        raise MigrationError(msg)
    if current_branch != migration_branch:
        msg = f"Current branch {current_branch!r} is not the explicitly selected migration branch {migration_branch!r}"
        raise MigrationError(msg)
    if migration_branch == base_branch:
        msg = "The migration branch must differ from the explicitly selected base branch"
        raise MigrationError(msg)
    root_path = root.resolve()
    common_dir = Path(git_output(root, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    authority_path = root / SESSION_AUTHORITY_PATH
    base_sha = git_output(root, "rev-parse", f"{base_branch}^{{commit}}")
    head_sha = git_output(root, "rev-parse", "HEAD")

    if mode == "fresh":
        if authority_path.exists():
            msg = "Migration session authority already exists; fresh mode cannot adopt or overwrite resumable state"
            raise MigrationError(msg)
        if head_sha != base_sha:
            msg = "Fresh migration branch must point exactly at the selected base-branch HEAD before any checkpoint"
            raise MigrationError(msg)
        if git_output(root, "status", "--porcelain"):
            msg = "Fresh migration authority requires a clean worktree"
            raise MigrationError(msg)
        authority: dict[str, Any] = {
            "schema_version": 1,
            "mode": "fresh",
            "base_branch": base_branch,
            "base_sha": base_sha,
            "migration_branch": migration_branch,
            "worktree_path": str(root_path),
            "git_common_dir": str(common_dir),
            "created_at": utc_now(),
        }
    else:
        authority = load_json(authority_path) or {}
        if not authority:
            msg = (
                "Resume requires existing session authority from a previously authorized fresh migration; "
                "checkpoint commits or a manifest are not authority"
            )
            raise MigrationError(msg)
        expected = session_resume_approval(migration_branch, root)
        if approval.strip() != expected:
            msg = f"Resume requires the user's exact approval phrase: {expected}"
            raise MigrationError(msg)
        require_session_authority(root, authority=authority)
        if authority.get("base_branch") != base_branch:
            msg = "Resume base branch does not match the recorded migration authority"
            raise MigrationError(msg)
        resume_log_path = root / SESSION_RESUME_LOG_PATH
        resume_log = load_json(resume_log_path) or {"schema_version": 1, "approvals": []}
        approvals = resume_log.setdefault("approvals", [])
        if not isinstance(approvals, list):
            msg = "Migration resume approval audit has an invalid approvals collection"
            raise MigrationError(msg)
        approvals.append(
            {
                "approved_at": utc_now(),
                "approval": expected,
                "head_sha": head_sha,
                "worktree_path": str(root_path),
            }
        )
        dump_json(resume_log_path, resume_log)
    if mode == "fresh":
        dump_json(authority_path, authority)
    print(f"Authorized {mode} migration session on {migration_branch} from {base_branch}.")


def require_session_authority(
    root: Path,
    *,
    authority: Mapping[str, Any] | None = None,
    require_committed: bool = True,
) -> None:
    if not git_repository(root):
        msg = "Workflow migration requires a Git worktree; non-Git execution has no branch or checkpoint authority"
        raise MigrationError(msg)
    authority_path = root / SESSION_AUTHORITY_PATH
    state = dict(authority or load_json(authority_path) or {})
    if not state:
        msg = (
            "Migration session authority is missing. Do not inspect or auto-resume existing migration branches; "
            "checkpoint commits or a manifest are not authority. Obtain explicit base/branch intent and run "
            "authorize-session first."
        )
        raise MigrationError(msg)
    current_branch = git_output(root, "branch", "--show-current")
    expected_branch = str(state.get("migration_branch", ""))
    if not current_branch or current_branch != expected_branch:
        msg = f"Current branch {current_branch!r} is not the authorized migration branch {expected_branch!r}"
        raise MigrationError(msg)
    if str(root.resolve()) != str(state.get("worktree_path", "")):
        msg = "Current worktree path does not match the authorized migration worktree"
        raise MigrationError(msg)
    common_dir = Path(git_output(root, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    if str(common_dir) != str(state.get("git_common_dir", "")):
        msg = "Current Git repository does not match the authorized migration repository"
        raise MigrationError(msg)
    base_sha = str(state.get("base_sha", ""))
    if not base_sha:
        msg = "Migration authority does not record the selected base SHA"
        raise MigrationError(msg)
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        msg = "Authorized base SHA is not an ancestor of the current migration branch"
        raise MigrationError(msg)
    if require_committed:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(SESSION_AUTHORITY_PATH)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        committed = subprocess.run(
            ["git", "show", f"HEAD:{SESSION_AUTHORITY_PATH.as_posix()}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if tracked.returncode != 0 or committed.returncode != 0:
            msg = "Migration session authority must be committed before leaving the baseline gate"
            raise MigrationError(msg)
        authority_bytes = authority_path.read_bytes()
        if committed.stdout != authority_bytes:
            msg = "Working migration session authority differs from the committed checkpoint"
            raise MigrationError(msg)
        introduction = subprocess.run(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--reverse",
                "--",
                SESSION_AUTHORITY_PATH.as_posix(),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        introduction_commits = [line for line in introduction.stdout.splitlines() if line]
        if introduction.returncode != 0 or len(introduction_commits) != 1:
            msg = "Migration session authority must have exactly one immutable introduction commit"
            raise MigrationError(msg)
        original = subprocess.run(
            ["git", "show", f"{introduction_commits[0]}:{SESSION_AUTHORITY_PATH.as_posix()}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if original.returncode != 0 or original.stdout != authority_bytes:
            msg = "Migration session authority differs from its original authorization commit"
            raise MigrationError(msg)


def safe_repository_path(
    root: Path,
    value: Any,
    *,
    description: str,
    required_prefix: PurePosixPath,
) -> Path:
    rendered = str(value)
    pure = PurePosixPath(rendered)
    if (
        not rendered
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in rendered
        or re.match(r"^[A-Za-z]:", rendered)
        or not pure.is_relative_to(required_prefix)
    ):
        msg = f"Unsafe migration path for {description}: {rendered!r}"
        raise MigrationError(msg)
    candidate = root.joinpath(*pure.parts)
    resolved_root = root.resolve()
    if _path_has_symlink(resolved_root, candidate) or not candidate.resolve().is_relative_to(resolved_root):
        msg = f"Unsafe migration path for {description}: {rendered!r} resolves through or beyond repository authority"
        raise MigrationError(msg)
    return candidate


def validate_manifest_paths(root: Path, manifest: Mapping[str, Any]) -> None:
    feature_prefix = PurePosixPath(FEATURES_PATH.as_posix())
    archive_prefix = PurePosixPath(DEFAULT_TASK_ARCHIVE.as_posix())
    candidate_prefix = PurePosixPath(DELIVERED_CANDIDATE_DIR.as_posix())
    for feature in manifest.get("features", []):
        if not isinstance(feature, dict):
            continue
        slug = str(feature.get("slug", "unknown"))
        for key in (
            "source_dir",
            "target_dir",
            "design_path",
            "implemented_path",
            "legacy_tasks_path",
        ):
            safe_repository_path(
                root,
                feature.get(key, ""),
                description=f"{slug}.{key}",
                required_prefix=feature_prefix,
            )
        optional = feature.get("legacy_open_questions_path")
        if optional:
            safe_repository_path(
                root,
                optional,
                description=f"{slug}.legacy_open_questions_path",
                required_prefix=feature_prefix,
            )
        for index, source in enumerate(feature.get("legacy_source_dirs", [])):
            safe_repository_path(
                root,
                source,
                description=f"{slug}.legacy_source_dirs[{index}]",
                required_prefix=feature_prefix,
            )
        archive = feature.get("legacy_tasks_archive")
        if archive and not str(archive).startswith("deleted;"):
            safe_repository_path(
                root,
                archive,
                description=f"{slug}.legacy_tasks_archive",
                required_prefix=archive_prefix,
            )
    for candidate in manifest.get("delivered_record_candidates", []):
        if not isinstance(candidate, dict):
            continue
        candidate_slug = str(candidate.get("slug", "unknown"))
        if candidate.get("path"):
            safe_repository_path(
                root,
                candidate["path"],
                description=f"{candidate_slug}.delivered_candidate",
                required_prefix=candidate_prefix,
            )
        if candidate.get("record_path"):
            safe_repository_path(
                root,
                candidate["record_path"],
                description=f"{candidate_slug}.record_path",
                required_prefix=feature_prefix,
            )
        for index, evidence in enumerate(candidate.get("semantic_evidence", [])):
            if isinstance(evidence, dict):
                safe_repository_path(
                    root,
                    evidence.get("path", ""),
                    description=f"{candidate_slug}.semantic_evidence[{index}]",
                    required_prefix=PurePosixPath("."),
                )
