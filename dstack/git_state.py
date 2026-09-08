"""Read-only Git state, evidence, worktree discovery, and mutation serialization."""

from __future__ import annotations

import fcntl
import re
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from .core import DstackError, assert_no_symlink_components, read_utf8_text, run, truncate_output

if TYPE_CHECKING:
    from .beads import BeadsClient


def git_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=resolved)
    return Path(result.stdout.strip()).resolve()


def git_common_dir(path: Path) -> Path:
    root = git_root(path)
    raw = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root).stdout.strip()
    if not raw:
        raise DstackError("Git common directory is unavailable")
    result = Path(raw)
    if not result.is_absolute():
        result = root / result
    return result.resolve()


_repository_lock_state = threading.local()


@contextmanager
def repository_mutation_lock(root: Path):
    """Serialize dStack repository mutations across linked worktrees."""

    repository = git_root(root)
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repository).stdout.strip()
    if not common:
        raise DstackError("Git common directory is unavailable")
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (repository / common_path).resolve()
    lock_path = common_path / "dstack-mutation.lock"
    key = str(lock_path.resolve(strict=False))
    held = getattr(_repository_lock_state, "held", None)
    if held is None:
        held = set()
        _repository_lock_state.held = held
    if key in held:
        yield
        return

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            handle.close()
            raise
    except OSError as exc:
        raise DstackError(f"cannot acquire repository mutation lock: {lock_path}") from exc

    with handle:
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def serialized_repository_mutation(func: Callable[..., int]) -> Callable[..., int]:
    @wraps(func)
    def wrapped(args: Any) -> int:
        with repository_mutation_lock(Path(args.root)):
            return func(args)

    return wrapped


def validate_git_branch(root: Path, branch: str, *, name: str = "branch") -> str:
    repository = git_root(root)
    if not branch or branch.startswith("-") or any(char in branch for char in "\r\n\0"):
        raise DstackError(f"invalid {name}: {branch!r}")
    if run(["git", "check-ref-format", "--branch", branch], cwd=repository, check=False).returncode:
        raise DstackError(f"invalid {name}: {branch!r}")
    return branch


def validate_git_revision(root: Path, ref: str, *, name: str = "revision") -> str:
    repository = git_root(root)
    if not ref or ref.startswith("-") or any(char in ref for char in "\r\n\0"):
        raise DstackError(f"invalid {name}: {ref!r}")
    result = run(
        ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=repository,
        check=False,
    )
    if result.returncode:
        raise DstackError(f"{name} does not resolve to a commit: {ref!r}")
    return ref


def validate_git_range(root: Path, value: str, *, name: str = "revision") -> str:
    separator = "..." if "..." in value else ".." if ".." in value else None
    if separator is None:
        return validate_git_revision(root, value, name=name)
    parts = value.split(separator)
    if len(parts) != 2 or not all(parts):
        raise DstackError(f"invalid {name} range: {value!r}")
    for part in parts:
        validate_git_revision(root, part, name=name)
    return value


def branch_exists(root: Path, branch: str) -> bool:
    repository = git_root(root)
    return (
        run(
            ["git", "show-ref", "--verify", "--quiet", "--", f"refs/heads/{branch}"],
            cwd=repository,
            check=False,
        ).returncode
        == 0
    )


def require_common_history(root: Path, base: str, branch: str) -> None:
    if run(["git", "merge-base", base, branch], cwd=root, check=False).returncode:
        raise DstackError(f"feature branch {branch} has no common history with base branch {base}")


def current_head(root: Path, ref: str = "HEAD") -> str:
    repository = git_root(root)
    return run(["git", "rev-parse", "--verify", "--end-of-options", ref], cwd=repository).stdout.strip()


def git_operation(root: Path) -> str | None:
    """Report Git's own interrupted-operation marker without managing its state."""

    directory = Path(run(["git", "rev-parse", "--absolute-git-dir"], cwd=root).stdout.strip())
    return next(
        (
            name
            for name in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "sequencer")
            if (directory / name).exists()
        ),
        None,
    )


def _rebasing_branch(worktree: Path) -> str | None:
    directory = Path(run(["git", "rev-parse", "--absolute-git-dir"], cwd=worktree).stdout.strip())
    for backend in ("rebase-merge", "rebase-apply"):
        head_name = directory / backend / "head-name"
        if head_name.is_file():
            ref = read_utf8_text(head_name, purpose="native rebase branch").strip()
            if ref.startswith("refs/heads/"):
                return ref.removeprefix("refs/heads/")
    return None


def worktree_for_branch(client: BeadsClient, branch: str) -> Path | None:
    matches = []
    for item in client.worktrees():
        path = Path(str(item["path"]))
        # Native Beads reports no branch while Git's rebase has detached HEAD.
        if item.get("branch") == branch or (
            not item.get("branch") and path.is_dir() and _rebasing_branch(path) == branch
        ):
            matches.append(path)
    if len(matches) > 1:
        raise DstackError(f"multiple worktrees are registered for {branch}")
    return matches[0] if matches else None


def conventional_worktree(root: Path, branch: str) -> Path:
    repository = git_root(root)
    common = git_common_dir(repository)
    primary = common.parent if common.name == ".git" else repository
    return primary.parent / f"{primary.name}.{branch.replace('/', '-')}"


def verify_worktree_identity(
    root: Path,
    worktree: Path,
    branch: str,
    *,
    conventional: bool = True,
    allow_rebase: bool = False,
) -> Path:
    repository = git_root(root)
    validate_git_branch(repository, branch)
    assert_no_symlink_components(worktree, purpose="worktree")
    resolved = worktree.resolve()
    expected = conventional_worktree(repository, branch).resolve()
    if conventional and resolved != expected:
        raise DstackError(f"worktree for {branch} must use conventional path {expected}: {resolved}")
    if git_common_dir(resolved) != git_common_dir(repository):
        raise DstackError(f"worktree repository identity mismatch for {branch}: {resolved}")
    top = run(["git", "rev-parse", "--show-toplevel"], cwd=resolved, check=False)
    active = run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=resolved, check=False)
    branch_matches = active.returncode == 0 and active.stdout.strip() == branch
    if allow_rebase and active.returncode:
        branch_matches = _rebasing_branch(resolved) == branch
    if top.returncode or Path(top.stdout.strip()).resolve() != resolved or not branch_matches:
        raise DstackError(
            f"worktree identity mismatch for {branch}: path={resolved}, branch={active.stdout.strip() or '<detached>'}"
        )
    return resolved


def worktree_status(path: Path) -> dict[str, Any]:
    result = run(["git", "status", "--short", "--untracked-files=all"], cwd=path, check=False)
    return {
        "status": "clean" if result.returncode == 0 and not result.stdout.strip() else "dirty",
        "returncode": result.returncode,
        "details": truncate_output(result.stderr) or truncate_output(result.stdout),
    }


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    repository = git_root(root)
    validate_git_revision(repository, base, name="base revision")
    validate_git_revision(repository, head, name="head revision")
    output = run(["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}"], cwd=repository).stdout
    return [path for path in output.split("\0") if path]


def diff_stat(root: Path, base: str, head: str) -> str:
    repository = git_root(root)
    return run(["git", "diff", "--shortstat", f"{base}...{head}"], cwd=repository).stdout.strip()


def commit_records(
    root: Path,
    ref_range: str,
    *,
    include_paths: bool = False,
    owner_id: str | None = None,
) -> list[dict[str, Any]]:
    repository = git_root(root)
    validate_git_range(repository, ref_range, name="evidence revision")
    # NUL is the only separator that cannot appear in a Git pathname. The
    # leading empty field marks a record; its three header fields are positional.
    command = ["git", "log", "-z", "--format=%x00%H%x00%s%x00%b"]
    if owner_id is not None:
        command.extend(["--fixed-strings", f"--grep=Task: {owner_id}", f"--grep=Beads: {owner_id}"])
    if include_paths:
        command.extend(["--name-only", "--no-renames", "--diff-merges=first-parent"])
    command.append(ref_range)
    fields = run(command, cwd=repository).stdout.split("\0")
    records: list[dict[str, Any]] = []
    position = 0
    while position < len(fields) - 1:
        if fields[position] != "" or position + 3 >= len(fields):
            raise DstackError("Git evidence query returned a malformed record")
        commit, subject, body = fields[position + 1 : position + 4]
        position += 4
        paths: list[str] = []
        if include_paths:
            while position < len(fields) and fields[position] != "":
                value = fields[position]
                # Git adds one formatting newline before the first path, even
                # when that path itself starts with a newline.
                paths.append(value.removeprefix("\n") if not paths else value)
                position += 1
        footer_ids = tuple(match.group(1) for match in re.finditer(r"(?m)^Task:\s*([^\s]+)\s*$", body))
        legacy_footer_ids = tuple(match.group(1) for match in re.finditer(r"(?m)^Beads:\s*([^\s]+)\s*$", body))
        records.append(
            {
                "commit": commit.strip(),
                "subject": subject.strip(),
                "body": body.rstrip("\n"),
                "paths": paths,
                "footer_ids": footer_ids,
                "legacy_footer_ids": legacy_footer_ids,
            }
        )
    return records


def footer_mapping(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return compact ownership evidence without duplicating changed paths."""

    result: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for bead_id in record.get("footer_ids", ()):
            result.setdefault(str(bead_id), []).append(
                {
                    "commit": str(record.get("commit") or ""),
                    "subject": str(record.get("subject") or ""),
                    "body": str(record.get("body") or ""),
                }
            )
    return result


def require_feature_worktree(client: BeadsClient, branch: str) -> Path:
    registered = worktree_for_branch(client, branch)
    if registered is None:
        raise DstackError(f"feature worktree is not registered for {branch}")
    verified = verify_worktree_identity(client.root, registered, branch)
    current = git_root(client.root).resolve()
    if current != verified:
        raise DstackError(
            f"operation must run from the registered feature worktree {verified}; current worktree is {current}"
        )
    return verified
