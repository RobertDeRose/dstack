#!/usr/bin/env python3
"""Shared stateless adapters for dStack.

When the dStack workflow is active, Beads owns durable workflow state. Git owns repository state. This module only
provides small, verifiable adapters over their native command-line interfaces.
"""

from __future__ import annotations

import builtins
import fcntl
import json
import math
import os
import re
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SUPPORTED_BEADS_VERSION = (1, 2, 2)
FEATURE_STEP_TYPES = {
    "plan": "task",
    "review": "task",
    "approval": "task",
    "implementation": "epic",
    "audit": "task",
}
FEATURE_STEP_LABELS = {step: f"dstack:step:{step}" for step in FEATURE_STEP_TYPES}
BEADS_VERSION_PATTERN = re.compile(r"\bbd version (\d+)\.(\d+)\.(\d+)\b")


class DstackError(RuntimeError):
    """Raised when a deterministic dStack operation cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


COMMAND_TIMEOUT_SECONDS = {
    "bd": 180.0,
    "git": 120.0,
    "hk": 900.0,
    "mdbook": 300.0,
    "python": 300.0,
    "python3": 300.0,
}


def command_timeout(command: Sequence[str]) -> float:
    override = os.environ.get("DSTACK_COMMAND_TIMEOUT_SECONDS", "").strip()
    if override:
        try:
            value = float(override)
        except ValueError as exc:
            raise DstackError("DSTACK_COMMAND_TIMEOUT_SECONDS must be numeric") from exc
        if not math.isfinite(value) or value <= 0:
            raise DstackError("DSTACK_COMMAND_TIMEOUT_SECONDS must be positive and finite")
        return value
    executable = Path(str(command[0])).name if command else ""
    return COMMAND_TIMEOUT_SECONDS.get(executable, 120.0)


def command_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["BD_JSON_ENVELOPE"] = "1"
    if extra:
        env.update(extra)
    return env


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    input_text: str | None = None,
    timeout: float | None = None,
) -> CommandResult:
    if not command:
        raise DstackError("cannot run an empty command")
    effective_timeout = command_timeout(command) if timeout is None else timeout
    if not math.isfinite(effective_timeout) or effective_timeout <= 0:
        raise DstackError("command timeout must be positive and finite")
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            check=False,
            input=input_text.encode("utf-8") if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=command_env(env),
            timeout=effective_timeout,
        )
    except FileNotFoundError as exc:
        raise DstackError(f"required executable not found on PATH: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DstackError(
            f"command timed out after {effective_timeout:g}s ({' '.join(command)}) in {cwd}; "
            "inspect native Git/Beads state before retrying because the operation may have partially completed"
        ) from exc

    # Do not let universal-newline decoding alter Git pathnames containing CR/LF.
    result = CommandResult(
        completed.returncode,
        completed.stdout.decode("utf-8", errors="surrogateescape"),
        completed.stderr.decode("utf-8", errors="surrogateescape"),
    )
    if check and completed.returncode != 0:
        detail = (
            truncate_output(result.stderr) or truncate_output(result.stdout) or f"exit {completed.returncode}"
        )
        raise DstackError(f"command failed ({' '.join(command)}): {detail}")
    return result


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
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise DstackError(f"cannot acquire repository mutation lock: {lock_path}") from exc


def serialized_repository_mutation(func: Callable[..., int]) -> Callable[..., int]:
    @wraps(func)
    def wrapped(args: Any) -> int:
        with repository_mutation_lock(Path(args.root)):
            return func(args)

    return wrapped


def parse_json(text: str, *, context: str) -> Any:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DstackError(f"{context} returned invalid JSON") from exc
    if isinstance(payload, dict) and "schema_version" in payload:
        version = payload["schema_version"]
        if type(version) is not int or version != 1:
            raise DstackError(f"{context} returned unsupported JSON schema version {version!r}")
        pagination = payload.get("pagination")
        if pagination is not None:
            if not isinstance(pagination, dict):
                raise DstackError(f"{context} returned invalid pagination metadata")
            if pagination.get("truncated"):
                raise DstackError(
                    f"{context} returned incomplete evidence: "
                    f"returned={pagination.get('returned', 'unknown')}, total={pagination.get('total', 'unknown')}"
                )
        if "data" in payload:
            return [] if payload["data"] is None else payload["data"]
    return payload


def as_items(payload: Any, *, context: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict) and isinstance(payload.get("id"), str):
        values = [payload]
    elif isinstance(payload, dict):
        candidates = [payload[key] for key in ("issues", "items", "data", "closed") if key in payload]
        if len(candidates) != 1 or not isinstance(candidates[0], list):
            raise DstackError(f"{context} has an unknown object shape")
        values = candidates[0]
    else:
        raise DstackError(f"{context} must be an issue object or array")

    result: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise DstackError(f"{context} item {index} is not a valid issue object")
        result.append(item)
    return result


def first_item(payload: Any, *, context: str) -> dict[str, Any]:
    items = as_items(payload, context=context)
    if len(items) != 1:
        raise DstackError(f"{context} returned {len(items)} issues; expected exactly one")
    return items[0]


def parse_beads_version(raw: str) -> tuple[int, int, int]:
    match = BEADS_VERSION_PATTERN.search(raw)
    if match is None:
        raise DstackError(f"cannot parse Beads version output: {raw or '<empty>'}")
    major, minor, patch = (int(g) for g in match.groups())
    return major, minor, patch


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


def _assert_no_symlink_components(path: Path, *, purpose: str) -> None:
    current = Path(path)
    while True:
        if current.is_symlink():
            raise DstackError(f"{purpose} must not be a symlink: {path}")
        if current.parent == current:
            return
        current = current.parent


def read_utf8_text(path: Path, *, purpose: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot read {purpose}: {path}") from exc


def issue_type(issue: Mapping[str, Any]) -> str:
    return str(issue.get("issue_type") or issue.get("type") or "")


def issue_labels(issue: Mapping[str, Any]) -> list[str]:
    labels = issue.get("labels")
    return [str(item) for item in labels] if isinstance(labels, list) else []


def has_label(issue: Mapping[str, Any], label: str) -> bool:
    return label in issue_labels(issue)


def issue_metadata(issue: Mapping[str, Any]) -> dict[str, Any]:
    raw = issue.get("metadata")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def metadata_value(issue: Mapping[str, Any], key: str) -> str | None:
    value = issue_metadata(issue).get(key)
    return str(value) if isinstance(value, (str, int, float, bool)) and str(value) else None


def dependency_records(issue: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = issue.get("dependencies")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            result.append({"depends_on_id": item, "type": "blocks"})
        elif isinstance(item, dict):
            result.append(dict(item))
    return result


def dependency_type(record: Mapping[str, Any]) -> str:
    return str(record.get("dependency_type") or record.get("type") or "")


def dependency_target(record: Mapping[str, Any]) -> str | None:
    value = record.get("depends_on_id") or record.get("target_id") or record.get("id")
    return str(value) if isinstance(value, str) and value else None


def dependency_targets(issue: Mapping[str, Any], relation: str) -> list[str]:
    targets: list[str] = []
    for record in dependency_records(issue):
        if dependency_type(record) != relation:
            continue
        target = dependency_target(record)
        if target is not None:
            targets.append(target)
    return targets


def issue_parent(issue: Mapping[str, Any]) -> str | None:
    direct = issue.get("parent") or issue.get("parent_id")
    if isinstance(direct, str) and direct:
        return direct
    for record in dependency_records(issue):
        relation = str(record.get("type") or record.get("dependency_type") or "")
        if relation != "parent-child":
            continue
        parent = record.get("depends_on_id") or record.get("id")
        if isinstance(parent, str) and parent:
            return parent
    return None


def step_by_label(children: Sequence[Mapping[str, Any]], label: str) -> dict[str, Any]:
    matches = [dict(item) for item in children if has_label(item, label)]
    if len(matches) != 1:
        ids = ", ".join(str(item.get("id")) for item in matches) or "none"
        raise DstackError(f"expected exactly one step labeled {label}; found {ids}")
    return matches[0]


class BeadsCommandError(DstackError):
    """A native command failure, retaining its machine-readable classification."""

    def __init__(self, message: str, *, code: str | None = None, hint: str | None = None):
        self.code = code
        self.hint = hint
        super().__init__(message + (f"; {hint}" if hint else ""))


def beads_command_error(result: CommandResult, *, context: str) -> BeadsCommandError:
    for text in (result.stderr, result.stdout):
        if not text.lstrip().startswith("{"):
            continue
        try:
            payload = parse_json(text, context=context)
        except DstackError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            code = payload.get("code")
            hint = payload.get("hint")
            return BeadsCommandError(
                f"{context}: {payload['error']}",
                code=code if isinstance(code, str) else None,
                hint=hint if isinstance(hint, str) else None,
            )
    detail = truncate_output(result.stderr) or truncate_output(result.stdout) or f"exit {result.returncode}"
    return BeadsCommandError(f"{context}: {detail}")


class BeadsClient:
    """Small stateless adapter over the native Beads CLI."""

    def __init__(self, root: Path):
        self.root = git_root(root)

    def _run(self, command: Sequence[str], **kwargs: Any) -> CommandResult:
        return run(command, cwd=self.root, **kwargs)

    def json(self, command: Sequence[str], *, check: bool = True) -> Any:
        result = self._run(command, check=False)
        if result.returncode != 0:
            if check:
                raise beads_command_error(result, context=" ".join(command))
            return None
        return parse_json(result.stdout, context=" ".join(command))

    def version(self) -> str:
        return self._run(["bd", "--version"]).stdout.strip()

    def check_version(self) -> str:
        raw = self.version()
        observed = parse_beads_version(raw)
        if observed != SUPPORTED_BEADS_VERSION:
            supported = ".".join(str(part) for part in SUPPORTED_BEADS_VERSION)
            raise DstackError(f"dStack requires Beads {supported}; found {raw}")
        return raw

    def show_optional(self, issue_id: str, *, include_comments: bool = False) -> dict[str, Any] | None:
        command = ["bd", "show", issue_id, "--json"]
        if include_comments:
            command.append("--include-comments")
        result = self._run(command, check=False)
        if result.returncode != 0:
            failure = beads_command_error(result, context=f"bd show {issue_id}")
            if failure.code == "not_found":
                return None
            # Some pinned native show failures are still plain text. Do not
            # mistake an unrelated missing database or connection for a Bead.
            if failure.code is None and re.search(
                r"(?i)(?:issue|bead)\s+(?:[^\n:]+\s+)?not found|no issues found", str(failure)
            ):
                return None
            raise failure
        return first_item(parse_json(result.stdout, context=f"bd show {issue_id}"), context=f"bd show {issue_id}")

    def show(self, issue_id: str, *, include_comments: bool = False) -> dict[str, Any]:
        issue = self.show_optional(issue_id, include_comments=include_comments)
        if issue is None:
            raise DstackError(f"Bead not found: {issue_id}")
        return issue

    def show_many(
        self, issue_ids: Sequence[str], *, include_comments: bool = False
    ) -> builtins.list[dict[str, Any]]:
        ids = [str(issue_id) for issue_id in issue_ids]
        if len(ids) != len(set(ids)):
            raise DstackError("batched Beads read contains duplicate IDs")
        result: list[dict[str, Any]] = []
        # Bound argv size, not the number of valid tasks or the completeness of evidence.
        for offset in range(0, len(ids), 100):
            batch = ids[offset : offset + 100]
            command = ["bd", "show", *batch, "--json"]
            if include_comments:
                command.append("--include-comments")
            items = as_items(self.json(command), context="bd show batch")
            by_id = {str(item["id"]): item for item in items}
            if len(by_id) != len(items):
                raise DstackError("Beads batch response contains duplicate IDs")
            missing = sorted(set(batch) - set(by_id))
            unexpected = sorted(set(by_id) - set(batch))
            if missing or unexpected:
                raise DstackError(f"Beads batch response omitted: {missing}; unexpected IDs: {unexpected}")
            result.extend(by_id[issue_id] for issue_id in batch)
        return result

    def list(
        self,
        *,
        all_statuses: bool = True,
        parent: str | None = None,
        labels: Sequence[str] = (),
        issue_type_filter: str | None = None,
        include_gates: bool = False,
        include_templates: bool = False,
        limit: int | None = None,
    ) -> builtins.list[dict[str, Any]]:
        if limit is not None and limit < 1:
            raise DstackError("Beads list limit must be positive")
        command = ["bd", "list", "--limit", str(limit if limit is not None else 0), "--json"]
        if all_statuses:
            command.append("--all")
        if parent:
            command.extend(["--parent", parent])
        for label in labels:
            command.extend(["--label", label])
        if issue_type_filter:
            command.extend(["--type", issue_type_filter])
        if include_gates:
            command.append("--include-gates")
        if include_templates:
            command.append("--include-templates")
        return as_items(self.json(command), context="bd list")

    def children(
        self, parent: str, *, all_statuses: bool = True, limit: int | None = None
    ) -> builtins.list[dict[str, Any]]:
        return self.list(all_statuses=all_statuses, parent=parent, limit=limit)


    def worktrees(self) -> builtins.list[dict[str, Any]]:
        payload = self.json(["bd", "worktree", "list", "--json"])
        if not isinstance(payload, list):
            raise DstackError("bd worktree list returned an unknown JSON shape")
        result: list[dict[str, Any]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise DstackError(f"bd worktree list item {index} is invalid")
            result.append(dict(item))
        return result


def find_feature_root(client: BeadsClient, selector: str) -> dict[str, Any]:
    current = client.show(selector)
    seen: set[str] = set()
    while True:
        issue_id = str(current["id"])
        if issue_id in seen:
            raise DstackError(f"parent cycle while resolving feature root from {selector}")
        seen.add(issue_id)
        if issue_type(current) == "molecule" or has_label(current, "workflow:feature"):
            return current
        parent = issue_parent(current)
        if parent is None:
            raise DstackError(f"Bead {selector} is not inside a feature molecule")
        current = client.show(parent)


def feature_steps(client: BeadsClient, root_id: str) -> dict[str, dict[str, Any]]:
    children = client.children(root_id)
    steps = {name: step_by_label(children, label) for name, label in FEATURE_STEP_LABELS.items()}
    for name, expected_type in FEATURE_STEP_TYPES.items():
        if issue_type(steps[name]) != expected_type:
            raise DstackError(f"{name} step must be a {expected_type}")
    return steps


def feature_identity(client: BeadsClient, selector: str) -> tuple[dict[str, Any], str, str]:
    root = find_feature_root(client, selector)
    labels = issue_labels(root)
    slugs = sorted({label.removeprefix("feature:") for label in labels if label.startswith("feature:")})
    if len(slugs) != 1 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slugs[0]):
        raise DstackError(f"feature root {root['id']} must have exactly one valid feature:<slug> label")
    slug = slugs[0]

    base = metadata_value(root, "dstack.base_branch")
    if not base:
        raise DstackError(f"feature root {root['id']} lacks dstack.base_branch metadata")
    return root, slug, base


def implementation_task_graph_errors(
    task: Mapping[str, Any], steps: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """Validate native graph membership without calculating task readiness."""

    errors: list[str] = []
    task_id = str(task.get("id") or "")
    implementation_id = str(steps["implementation"].get("id") or "")
    approval_id = str(steps["approval"].get("id") or "")

    parent_id = issue_parent(task)
    if parent_id != implementation_id:
        observed_parent = parent_id or "<none>"
        errors.append(
            f"implementation Bead must be a direct child of {implementation_id}; observed parent {observed_parent}"
        )
    implementation = steps["implementation"]
    if issue_type(implementation) != "epic":
        errors.append("feature implementation step is not an epic")
    if has_label(task, "dstack:step:implementation"):
        errors.append("implementation task inherited the structural dstack:step:implementation label")

    blockers = dependency_targets(task, "blocks")
    if approval_id not in blockers:
        errors.append(f"implementation Bead is not blocked by approval step {approval_id}")

    # Native Beads validates blocker existence, cross-feature relationships,
    # conditional dependencies, and readiness. Do not reconstruct that graph.

    if not task_id:
        errors.append("implementation Bead has no ID")
    return errors


def audit_fan_in_errors(
    audit: Mapping[str, Any],
    implementation_id: str,
    implementation_tasks: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Verify that native ``waits-for`` is the sole implementation fan-in."""

    errors: list[str] = []
    waits_for = dependency_targets(audit, "waits-for")
    if waits_for != [implementation_id]:
        errors.append(
            f"audit must have exactly one waits-for dependency on {implementation_id}; observed {waits_for or '<none>'}"
        )

    task_ids = {str(task.get("id") or "") for task in implementation_tasks}
    redundant: set[str] = set()
    for relation in ("blocks", "conditional-blocks"):
        redundant.update(task_ids.intersection(dependency_targets(audit, relation)))
    if redundant:
        errors.append("audit has redundant direct task readiness edges: " + ", ".join(sorted(redundant)))
    return errors


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
    _assert_no_symlink_components(worktree, purpose="worktree")
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


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    repository = git_root(root)
    validate_git_revision(repository, base, name="base revision")
    validate_git_revision(repository, head, name="head revision")
    output = run(["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}"], cwd=repository).stdout
    return [path for path in output.split("\0") if path]


def reject_beads_paths(paths: Sequence[str]) -> None:
    committed_policy = {
        ".beads/PRIME.md",
        ".beads/formulas/dstack-feature.formula.toml",
    }
    invalid = sorted(
        path for path in paths if (path == ".beads" or path.startswith(".beads/")) and path not in committed_policy
    )
    if invalid:
        raise DstackError(
            "implementation commits may not include Beads configuration or runtime state; "
            "commit intentional Beads maintenance separately: " + ", ".join(invalid)
        )


def diff_stat(root: Path, base: str, head: str) -> str:
    repository = git_root(root)
    return run(["git", "diff", "--shortstat", f"{base}...{head}"], cwd=repository).stdout.strip()


def commit_records(
    root: Path,
    ref_range: str,
    *,
    include_paths: bool = False,
    max_count: int | None = None,
    owner_id: str | None = None,
) -> list[dict[str, Any]]:
    repository = git_root(root)
    validate_git_range(repository, ref_range, name="evidence revision")
    if max_count is not None and max_count < 1:
        raise DstackError("Git evidence limit must be positive")
    # NUL is the only separator that cannot appear in a Git pathname. The
    # leading empty field marks a record; its three header fields are positional.
    command = ["git", "log", "-z", "--format=%x00%H%x00%s%x00%b"]
    if max_count is not None:
        command.append(f"--max-count={max_count}")
    if owner_id is not None:
        command.extend(["--fixed-strings", f"--grep=Task: {owner_id}", f"--grep=Beads: {owner_id}"])
    if include_paths:
        command.extend(["--name-only", "--no-renames"])
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
        footer_kind = "Task" if footer_ids else None
        records.append(
            {
                "commit": commit.strip(),
                "subject": subject.strip(),
                "body": body.rstrip("\n"),
                "paths": paths,
                "footer_ids": footer_ids,
                "legacy_footer_ids": legacy_footer_ids,
                "footer_kind": footer_kind,
            }
        )
    return records


def footer_mapping(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for bead_id in record.get("footer_ids", ()):
            row: dict[str, Any] = {
                "commit": str(record.get("commit") or ""),
                "subject": str(record.get("subject") or ""),
            }
            if record.get("paths"):
                row["paths"] = list(record["paths"])
            result.setdefault(str(bead_id), []).append(row)
    return result


def truncate_output(value: str, *, limit: int = 4000) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    marker = "\n... output truncated ...\n"
    if limit <= len(marker):
        return marker[:limit]
    remaining = limit - len(marker)
    head = remaining // 2
    tail = remaining - head
    suffix = text[-tail:] if tail else ""
    return text[:head] + marker + suffix


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
