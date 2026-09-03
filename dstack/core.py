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


def command_may_mutate(command: Sequence[str]) -> bool:
    if len(command) < 2:
        return False
    executable = Path(str(command[0])).name
    action = str(command[1])
    if executable == "git":
        return action in {
            "add",
            "am",
            "branch",
            "checkout",
            "commit",
            "fetch",
            "merge",
            "mv",
            "push",
            "rebase",
            "reset",
            "restore",
            "rm",
            "switch",
            "tag",
            "worktree",
        }
    if executable == "bd":
        return action in {
            "close",
            "comments",
            "create",
            "delete",
            "dep",
            "gate",
            "init",
            "mol",
            "reopen",
            "update",
            "worktree",
        } or (action == "ready" and "--claim" in command)
    return False


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
            text=True,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=command_env(env),
            timeout=effective_timeout,
        )
    except FileNotFoundError as exc:
        raise DstackError(f"required executable not found on PATH: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        mutation = "may have changed state" if command_may_mutate(command) else "was read-only"
        raise DstackError(
            f"command timed out after {effective_timeout:g}s ({' '.join(command)}) in {cwd}; operation {mutation}"
        ) from exc

    result = CommandResult(completed.returncode, completed.stdout, completed.stderr)
    if check and completed.returncode != 0:
        detail = (
            truncate_output(completed.stderr) or truncate_output(completed.stdout) or f"exit {completed.returncode}"
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
    if isinstance(payload, dict) and payload.get("schema_version") == 1 and "data" in payload:
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


def read_text_file(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot read text file: {path}") from exc


def read_utf8_text(path: Path, *, purpose: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
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


class BeadsClient:
    """Small stateless adapter over the native Beads CLI."""

    def __init__(self, root: Path):
        self.root = git_root(root)

    def _run(self, command: Sequence[str], **kwargs: Any) -> CommandResult:
        return run(command, cwd=self.root, **kwargs)

    def json(self, command: Sequence[str], *, check: bool = True) -> Any:
        result = self._run(command, check=check)
        if result.returncode != 0:
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

    def show_optional(self, issue_id: str) -> dict[str, Any] | None:
        result = self._run(["bd", "show", issue_id, "--json"], check=False)
        if result.returncode != 0:
            detail = f"{result.stdout}\n{result.stderr}".casefold()
            if "not found" in detail or "no issues found" in detail:
                return None
            raise DstackError(result.stderr.strip() or result.stdout.strip() or f"cannot read Bead {issue_id}")
        return first_item(parse_json(result.stdout, context=f"bd show {issue_id}"), context=f"bd show {issue_id}")

    def show(self, issue_id: str) -> dict[str, Any]:
        issue = self.show_optional(issue_id)
        if issue is None:
            raise DstackError(f"Bead not found: {issue_id}")
        return issue

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

    def history(self, issue_id: str) -> Any:
        result = self._run(["bd", "history", issue_id, "--json"], check=False)
        if result.returncode != 0:
            return {
                "status": "unavailable",
                "error": result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}",
            }
        return parse_json(result.stdout, context=f"bd history {issue_id}")

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
    client: BeadsClient,
    task: Mapping[str, Any],
    root: Mapping[str, Any],
    steps: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Validate native graph membership without calculating task readiness."""

    errors: list[str] = []
    task_id = str(task.get("id") or "")
    root_id = str(root.get("id") or "")
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

    unsupported_readiness_edges = sorted(
        {
            dependency_type(record)
            for record in dependency_records(task)
            if dependency_type(record) in {"conditional-blocks", "waits-for"}
        }
    )
    if unsupported_readiness_edges:
        errors.append(
            "implementation Bead uses unsupported readiness dependencies: " + ", ".join(unsupported_readiness_edges)
        )

    blockers = dependency_targets(task, "blocks")
    if approval_id not in blockers:
        errors.append(f"implementation Bead is not blocked by approval step {approval_id}")

    for blocker_id in blockers:
        if blocker_id == approval_id:
            continue
        blocker = client.show_optional(blocker_id)
        if blocker is None:
            errors.append(f"implementation Bead depends on missing blocker {blocker_id}")
            continue
        try:
            blocker_root = find_feature_root(client, blocker_id)
        except DstackError:
            errors.append(f"implementation Bead has cross-feature blocker {blocker_id}")
            continue
        if str(blocker_root.get("id") or "") != root_id:
            errors.append(f"implementation Bead has cross-feature blocker {blocker_id}")

    if not task_id:
        errors.append("implementation Bead has no ID")
    return errors


def audit_fan_in_errors(
    client: BeadsClient,
    steps: Mapping[str, Mapping[str, Any]],
    implementation_tasks: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Verify that native ``waits-for`` is the sole implementation fan-in."""

    errors: list[str] = []
    implementation_id = str(steps["implementation"].get("id") or "")
    audit_id = str(steps["audit"].get("id") or "")
    audit = client.show(audit_id)
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


def ancestry(root: Path, ancestor: str, descendant: str) -> bool:
    repository = git_root(root)
    return (
        run(["git", "merge-base", "--is-ancestor", "--", ancestor, descendant], cwd=repository, check=False).returncode
        == 0
    )


def current_head(root: Path, ref: str = "HEAD") -> str:
    repository = git_root(root)
    return run(["git", "rev-parse", "--verify", "--end-of-options", ref], cwd=repository).stdout.strip()


def worktree_for_branch(client: BeadsClient, branch: str) -> Path | None:
    matches = [Path(str(item["path"])) for item in client.worktrees() if item.get("branch") == branch]
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
    if (
        top.returncode
        or Path(top.stdout.strip()).resolve() != resolved
        or active.returncode
        or active.stdout.strip() != branch
    ):
        raise DstackError(
            f"worktree identity mismatch for {branch}: path={resolved}, branch={active.stdout.strip() or '<detached>'}"
        )
    return resolved


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    repository = git_root(root)
    validate_git_revision(repository, base, name="base revision")
    validate_git_revision(repository, head, name="head revision")
    output = run(["git", "diff", "--name-only", f"{base}...{head}"], cwd=repository).stdout
    return [line for line in output.splitlines() if line]


def reject_beads_paths(paths: Sequence[str]) -> None:
    invalid = sorted(path for path in paths if path == ".beads" or path.startswith(".beads/"))
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
    include_paths: bool = True,
    max_count: int | None = None,
) -> list[dict[str, Any]]:
    repository = git_root(root)
    validate_git_range(repository, ref_range, name="evidence revision")
    if max_count is not None and max_count < 1:
        raise DstackError("Git evidence limit must be positive")
    format_string = "%x1e%H%x00%s%x00%B%x00"
    command = ["git", "log"]
    if max_count is not None:
        command.append(f"--max-count={max_count}")
    command.append(f"--format={format_string}")
    if include_paths:
        command.append("--name-only")
    command.append(ref_range)
    output = run(command, cwd=repository).stdout
    records: list[dict[str, Any]] = []
    for raw in output.split("\x1e"):
        if not raw.strip():
            continue
        parts = raw.split("\x00", 3)
        if len(parts) != 4:
            raise DstackError("Git evidence query returned a malformed record")
        commit, subject, body, paths = parts
        footer_ids = tuple(match.group(1) for match in re.finditer(r"(?m)^Beads:\s*([^\s]+)\s*$", body))
        records.append(
            {
                "commit": commit.strip(),
                "subject": subject.strip(),
                "paths": [line for line in paths.splitlines() if line.strip()] if include_paths else [],
                "footer_ids": footer_ids,
            }
        )
    return records


def footer_mapping(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for bead_id in record.get("footer_ids", ()):
            result.setdefault(str(bead_id), []).append(
                {
                    "commit": str(record.get("commit") or ""),
                    "subject": str(record.get("subject") or ""),
                    "paths": list(record.get("paths", [])),
                }
            )
    return result


def commits_for_bead(root: Path, ref_range: str, bead_id: str) -> list[dict[str, Any]]:
    if not bead_id or any(character.isspace() for character in bead_id):
        raise DstackError("Beads evidence ID must be one non-empty token")
    return [
        {
            "commit": str(record["commit"]),
            "subject": str(record["subject"]),
            "paths": list(record.get("paths", [])),
        }
        for record in commit_records(root, ref_range)
        if bead_id in record.get("footer_ids", ())
    ]


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
