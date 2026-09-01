#!/usr/bin/env python3
"""Shared stateless adapters for dstack.

This module reads current state from Beads and Git on every invocation. It owns
no database, cache, packet format, readiness calculation, or workflow state.
"""

from __future__ import annotations

import builtins
from contextlib import contextmanager
from functools import wraps
import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO, cast

SUPPORTED_BEADS_VERSION_OUTPUT = "bd version 1.2.2 (6c124203e)"
FEATURE_STEPS = {
    "specification": "dstack:step:specification",
    "approval": "dstack:step:implementation-approval",
    "implementation": "dstack:step:implementation",
    "closeout": "dstack:step:closeout",
}


class DstackError(RuntimeError):
    """Raised when a stateless dstack operation cannot proceed safely."""


class FeatureNotFound(DstackError):
    """Raised when a feature selector has no matching native root."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


COMMAND_TIMEOUT_SECONDS = {
    "git": 120.0,
    "bd": 180.0,
    "gh": 180.0,
    "mdbook": 300.0,
    "python": 300.0,
    "python3": 300.0,
}


def command_timeout(command: Sequence[str]) -> float:
    override = os.environ.get("DSTACK_COMMAND_TIMEOUT_SECONDS", "").strip()
    if override:
        try:
            timeout = float(override)
        except ValueError as exc:
            raise DstackError("DSTACK_COMMAND_TIMEOUT_SECONDS must be numeric") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise DstackError("DSTACK_COMMAND_TIMEOUT_SECONDS must be positive and finite")
        return timeout
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
        if action == "ready" and "--claim" in command:
            return True
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
            "supersede",
            "todo",
            "update",
            "backup",
            "worktree",
        }
    return executable == "gh" and action == "pr"


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
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DstackError(f"command failed ({' '.join(command)}): {detail}")
    return result


_repository_lock_state = threading.local()


@contextmanager
def repository_mutation_lock(root: Path):
    """Serialize dstack graph/Git mutations for one repository.

    The lock lives in Git's common directory so linked worktrees share the
    same boundary. It intentionally protects only dstack controller
    operations; native mutations performed outside dstack are detected by the
    final rereads/generation checks at each boundary.
    """

    result = run(["git", "rev-parse", "--git-common-dir"], cwd=root, check=False)
    common = result.stdout.strip()
    if result.returncode == 0 and common:
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = (root / common_path).resolve()
        lock_path = common_path / "dstack-mutation.lock"
    else:
        # Protocol-focused unit tests use lightweight non-Git roots. Real CLI
        # invocations are still rooted by client_for/git_root.
        lock_path = root.resolve() / ".dstack-mutation.lock"
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


def serialized_repository_mutation(func):
    """Serialize one argparse controller mutation for its Git repository."""

    @wraps(func)
    def wrapped(args):
        try:
            root = git_root(args.root)
        except DstackError:
            root = Path(args.root).resolve()
        with repository_mutation_lock(root):
            return func(args)

    return wrapped


def repository_default_branch(root: Path) -> str:
    """Use the documented dev-first target policy with main as fallback."""

    if run(["git", "show-ref", "--verify", "--quiet", "refs/heads/dev"], cwd=root, check=False).returncode == 0:
        return "dev"
    return "main"


def parse_json(text: str, *, context: str) -> Any:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DstackError(f"{context} returned invalid JSON") from exc
    if isinstance(payload, dict) and payload.get("schema_version") == 1 and "data" in payload:
        # Beads 1.2.2 represents a valid empty collection as ``data: null``
        # for some list commands (notably ``bd gate list``). Normalize that
        # protocol representation here so strict issue parsing can continue to
        # reject every other malformed shape.
        data = payload["data"]
        return [] if data is None else data
    return payload


def canonical_positive_integer(value: str | int, *, field: str) -> int:
    """Parse one positive integer without signs, padding, or coercion."""

    raw = str(value)
    if re.fullmatch(r"[1-9][0-9]*", raw) is None:
        raise DstackError(f"{field} must be a positive canonical integer")
    return int(raw)


def as_items(payload: Any, *, context: str = "Beads response") -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("id"), str):
            values = [payload]
        else:
            found = [(key, payload[key]) for key in ("issues", "items", "data", "closed") if key in payload]
            if len(found) != 1:
                raise DstackError(f"{context} has an unknown object shape")
            key, values = found[0]
            if not isinstance(values, list):
                raise DstackError(f"{context} field {key!r} must be an array")
    else:
        raise DstackError(f"{context} must be an issue object or array")

    result: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise DstackError(f"{context} item {index} is not an object")
        issue_id = item.get("id")
        if not isinstance(issue_id, str) or not issue_id:
            raise DstackError(f"{context} item {index} has no issue ID")
        result.append(item)
    return result


def first_item(payload: Any, *, context: str) -> dict[str, Any]:
    items = as_items(payload, context=context)
    if len(items) != 1:
        raise DstackError(f"{context} returned {len(items)} issues; expected exactly one")
    return items[0]


def supersession_targets(issue: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    raw = issue.get("dependencies", [])
    if not isinstance(raw, list):
        return result
    for record in raw:
        if not isinstance(record, dict):
            continue
        relation = str(record.get("type") or record.get("dependency_type") or "")
        if relation not in {"supersedes", "superseded-by", "superseded_by"}:
            continue
        target = record.get("depends_on_id") or record.get("id")
        if isinstance(target, str) and target != issue.get("id"):
            result.add(target)
    return result


def git_root(path: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=path.resolve())
    return Path(result.stdout.strip()).resolve()


def safe_repository_path(root: Path, relative: str | Path, *, purpose: str = "repository path") -> Path:
    """Return a contained repository path without following symlink components."""

    _assert_no_symlink_components(root, purpose=f"{purpose} root")
    repository = root.resolve()
    candidate_relative = Path(relative)
    if not str(relative).strip() or candidate_relative.is_absolute() or ".." in candidate_relative.parts:
        raise DstackError(f"{purpose} must be repository-relative without parent traversal")
    candidate = repository
    for part in candidate_relative.parts:
        if part in {"", "."}:
            continue
        candidate = candidate / part
        if candidate.is_symlink():
            raise DstackError(f"{purpose} must not traverse a symlink: {candidate_relative.as_posix()}")
    probe = candidate if candidate.exists() else candidate.parent
    while not probe.exists() and probe != repository:
        probe = probe.parent
    try:
        probe.resolve().relative_to(repository)
    except ValueError as exc:
        raise DstackError(f"{purpose} escapes the repository: {candidate_relative.as_posix()}") from exc
    if candidate.exists():
        try:
            candidate.resolve().relative_to(repository)
        except ValueError as exc:
            raise DstackError(f"{purpose} escapes the repository: {candidate_relative.as_posix()}") from exc
    if candidate == repository:
        raise DstackError(f"{purpose} must name a file or directory below the repository root")
    return candidate


def git_common_dir(path: Path) -> Path:
    root = git_root(path)
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root).stdout.strip()
    if not common:
        raise DstackError("Git common directory is unavailable")
    return Path(common).resolve()


def git_common_root(path: Path) -> Path:
    common_path = git_common_dir(path)
    return common_path.parent if common_path.name == ".git" else common_path


def issue_type(issue: Mapping[str, Any]) -> str:
    return str(issue.get("issue_type") or issue.get("type") or "")


def issue_parent(issue: Mapping[str, Any]) -> str | None:
    parent = issue.get("parent") or issue.get("parent_id")
    return str(parent) if isinstance(parent, str) and parent else None


def issue_labels(issue: Mapping[str, Any]) -> list[str]:
    labels = issue.get("labels")
    return [str(item) for item in labels] if isinstance(labels, list) else []


def issue_metadata(issue: Mapping[str, Any]) -> dict[str, Any]:
    metadata = issue.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def dependency_records(issue: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = issue.get("dependencies")
    if not isinstance(raw, list):
        return []
    records: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            records.append({"depends_on_id": item, "type": "blocks"})
        elif isinstance(item, dict):
            records.append(item)
    return records


def blocker_ids(issue: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for record in dependency_records(issue):
        relation = str(record.get("type") or record.get("dependency_type") or "blocks")
        if relation != "blocks":
            continue
        blocker = record.get("depends_on_id") or record.get("id")
        if isinstance(blocker, str):
            result.append(blocker)
    raw = issue.get("gate_ids")
    if isinstance(raw, list):
        result.extend(str(item) for item in raw)
    return list(dict.fromkeys(result))


def has_label(issue: Mapping[str, Any], label: str) -> bool:
    return label in issue_labels(issue)


def gate_type(issue: Mapping[str, Any]) -> str:
    return str(issue.get("await_type") or issue.get("gate_type") or "")


def display_title(title: str) -> str:
    """Return a feature title without the optional ``Feature:`` prefix."""

    result = " ".join(title.strip().split())
    if result.casefold().startswith("feature: "):
        result = result[9:].strip()
    return result


def normalize_title(title: str) -> str:
    return display_title(title).casefold()


def slugify(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not result:
        raise DstackError("cannot derive a feature slug from empty input")
    return result


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise DstackError(f"required file does not exist: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_bytes(root: Path, path: str, ref: str = "HEAD") -> bytes | None:
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise DstackError(f"invalid Git blob path: {path!r}")
    command = ["git", "cat-file", "blob", f"{ref}:{path}"]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=command_timeout(command),
        )
    except subprocess.TimeoutExpired as exc:
        raise DstackError(f"command timed out ({' '.join(command)}) in {root}; operation was read-only") from exc
    return completed.stdout if completed.returncode == 0 else None


def git_blob_text(root: Path, path: str, ref: str = "HEAD") -> str | None:
    """Read one UTF-8 blob directly from an immutable Git revision."""

    blob = _git_blob_bytes(root, path, ref)
    if blob is None:
        return None
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DstackError(f"Git blob is not UTF-8 text: {ref}:{path}") from exc


def git_file_sha256(root: Path, path: str, ref: str = "HEAD") -> str | None:
    blob = _git_blob_bytes(root, path, ref)
    return None if blob is None else hashlib.sha256(blob).hexdigest()


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


def replace_text_if_unchanged(
    path: Path,
    *,
    expected: str | None,
    content: str,
    purpose: str,
) -> bool:
    """Atomically replace UTF-8 text only when its observed bytes are unchanged."""

    _assert_no_symlink_components(path, purpose=purpose)
    try:
        if path.is_symlink():
            raise DstackError(f"{purpose} must not be a symlink: {path}")
        current = path.read_text(encoding="utf-8") if path.exists() else None
    except DstackError:
        raise
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot read {purpose}: {path}") from exc
    if current != expected:
        raise DstackError(f"{purpose} changed while dStack was reconciling it: {path}")
    if current == content:
        return False

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_components(path, purpose=purpose)
        if path.is_symlink():
            raise DstackError(f"{purpose} must not be a symlink: {path}")
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                os.chmod(temporary_path, mode)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if path.is_symlink():
                raise DstackError(f"{purpose} must not be a symlink: {path}")
            latest = path.read_text(encoding="utf-8") if path.exists() else None
            if latest != expected:
                raise DstackError(f"{purpose} changed while dStack was reconciling it: {path}")
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
    except DstackError:
        raise
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot write {purpose}: {path}") from exc
    return True


def write_temp_text(text: str) -> TextIO:
    handle = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False)
    handle.write(text)
    handle.flush()
    return cast(TextIO, handle)


class BeadsClient:
    """Thin, stateless adapter around the supported Beads CLI."""

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
        if raw != SUPPORTED_BEADS_VERSION_OUTPUT:
            raise DstackError(f"dstack requires Beads 1.2.2 exactly ({SUPPORTED_BEADS_VERSION_OUTPUT}); found {raw}")
        return raw

    def show_optional(self, issue_id: str) -> dict[str, Any] | None:
        result = self._run(["bd", "show", issue_id, "--json"], check=False)
        if result.returncode != 0:
            detail = f"{result.stdout}\n{result.stderr}".casefold()
            if "not found" in detail or "no issues found" in detail:
                return None
            raise DstackError(result.stderr.strip() or result.stdout.strip())
        return first_item(
            parse_json(result.stdout, context=f"bd show {issue_id}"),
            context=f"bd show {issue_id}",
        )

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
        include_gates: bool = False,
        include_templates: bool = False,
        issue_type_filter: str | None = None,
    ) -> builtins.list[dict[str, Any]]:
        command = ["bd", "list", "--limit", "0", "--json"]
        if all_statuses:
            command.append("--all")
        if parent:
            command.extend(["--parent", parent])
        for label in labels:
            command.extend(["--label", label])
        if include_gates:
            command.append("--include-gates")
        if include_templates:
            command.append("--include-templates")
        if issue_type_filter:
            command.extend(["--type", issue_type_filter])
        return as_items(self.json(command), context="bd list")

    def children(self, parent: str, *, all_statuses: bool = True) -> builtins.list[dict[str, Any]]:
        return self.list(all_statuses=all_statuses, parent=parent)

    def gates(self, *, all_statuses: bool = True) -> builtins.list[dict[str, Any]]:
        command = ["bd", "gate", "list", "--limit", "0", "--json"]
        if all_statuses:
            command.append("--all")
        return as_items(self.json(command), context="bd gate list")

    def update(self, issue_id: str, *arguments: str) -> dict[str, Any]:
        payload = self.json(["bd", "update", issue_id, *arguments, "--json"])
        return first_item(payload, context=f"bd update {issue_id}")

    def update_many(self, issue_ids: Sequence[str], *arguments: str) -> builtins.list[dict[str, Any]]:
        ids = list(issue_ids)
        if not ids:
            return []
        payload = self.json(["bd", "update", *ids, *arguments, "--json"])
        return as_items(payload, context="bd update many")

    def close(self, issue_id: str, reason: str) -> dict[str, Any]:
        """Close one issue only after native Beads confirms current ownership.

        Beads 1.2.2 permits a direct close of an issue claimed by another actor.
        Re-claiming first delegates ownership validation to Beads and keeps dStack
        from inferring actor identity. A failed close is reconciled through a fresh
        native read because the mutation may already have committed.
        """

        current = self.show(issue_id)
        if current.get("status") == "closed":
            return current
        status = str(current.get("status") or "")
        if status not in {"open", "claimed", "in_progress"}:
            raise DstackError(f"cannot close {issue_id} from status {status!r}")
        try:
            claimed = self.update(issue_id, "--claim")
        except DstackError as exc:
            observed = self.show_optional(issue_id)
            if observed is not None and observed.get("status") == "closed":
                return observed
            observed_status = observed.get("status") if observed is not None else "missing"
            observed_assignee = observed.get("assignee") if observed is not None else None
            raise DstackError(
                f"cannot close {issue_id}: native ownership could not be confirmed for the current actor; "
                f"retained status={observed_status!r}, assignee={observed_assignee!r}"
            ) from exc
        if claimed.get("status") not in {"claimed", "in_progress"}:
            raise DstackError(f"native ownership claim did not converge before closing {issue_id}")
        try:
            payload = self.json(["bd", "close", issue_id, "--reason", reason, "--json"])
            as_items(payload, context=f"bd close {issue_id}")
        except DstackError as exc:
            observed = self.show_optional(issue_id)
            if observed is not None and observed.get("status") == "closed":
                return observed
            observed_status = observed.get("status") if observed is not None else "missing"
            raise DstackError(
                f"close outcome is uncertain for {issue_id}; retained native status={observed_status!r}: {exc}"
            ) from exc
        observed = self.show(issue_id)
        if observed.get("status") != "closed":
            raise DstackError(f"close did not converge: {issue_id}")
        return observed

    def reopen(self, issue_id: str, reason: str) -> dict[str, Any]:
        current = self.show(issue_id)
        if current.get("status") != "closed":
            return current
        try:
            payload = self.json(["bd", "reopen", issue_id, "--reason", reason, "--json"])
            first_item(payload, context=f"bd reopen {issue_id}")
        except DstackError as exc:
            observed = self.show_optional(issue_id)
            if observed is not None and observed.get("status") == "open":
                return observed
            observed_status = observed.get("status") if observed is not None else "missing"
            raise DstackError(
                f"reopen outcome is uncertain for {issue_id}; retained native status={observed_status!r}: {exc}"
            ) from exc
        observed = self.show(issue_id)
        if observed.get("status") != "open":
            raise DstackError(f"reopen did not converge: {issue_id}")
        return observed

    def resolve_gate(self, gate_id: str, reason: str) -> dict[str, Any]:
        """Resolve a gate, then read its authoritative state."""

        current = self.show(gate_id)
        if current.get("status") == "closed":
            return current
        self._run(["bd", "gate", "resolve", gate_id, "--reason", reason])
        resolved = self.show(gate_id)
        if resolved.get("status") != "closed":
            raise DstackError(f"gate did not resolve: {gate_id}")
        return resolved

    def create_gate(
        self,
        *,
        gate_type: str,
        blocks: str,
        await_id: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        command = [
            "bd",
            "gate",
            "create",
            "--type",
            gate_type,
            "--blocks",
            blocks,
            "--json",
        ]
        if await_id:
            command.extend(["--await-id", await_id])
        if reason:
            command.extend(["--reason", reason])
        return first_item(self.json(command), context="bd gate create")

    def add_comment(self, issue_id: str, text: str) -> None:
        if not text.strip():
            return
        handle = write_temp_text(text.rstrip() + "\n")
        name = handle.name
        handle.close()
        try:
            self._run(["bd", "comments", "add", issue_id, "-f", name])
        finally:
            Path(name).unlink(missing_ok=True)

    def create(
        self,
        title: str,
        *,
        issue_type_name: str = "task",
        parent: str | None = None,
        labels: Sequence[str] = (),
        dependencies: Sequence[str] = (),
        description: str = "",
        acceptance: str = "",
        priority: int = 2,
    ) -> dict[str, Any]:
        command = [
            "bd",
            "create",
            title,
            "--type",
            issue_type_name,
            "--priority",
            str(priority),
            "--json",
        ]
        if parent:
            command.extend(["--parent", parent])
        if labels:
            command.append("--no-inherit-labels")
            for label in labels:
                command.extend(["--labels", label])
        if dependencies:
            command.extend(["--deps", ",".join(dependencies)])
        if description:
            command.extend(["--description", description])
        if acceptance:
            command.extend(["--acceptance", acceptance])
        return first_item(self.json(command), context="bd create")

    def ready_children(
        self,
        parent: str,
        *,
        label: str | None = None,
        claim: bool = False,
    ) -> builtins.list[dict[str, Any]]:
        command = [
            "bd",
            "ready",
            "--parent",
            parent,
            "--exclude-type",
            "epic,molecule,gate",
            "--limit",
            "0" if not claim else "1",
            "--json",
        ]
        if label:
            command.extend(["--label", label])
        if claim:
            command.append("--claim")
        return as_items(self.json(command), context="bd ready")

    def progress(self, root_id: str) -> Any:
        return self.json(["bd", "mol", "progress", root_id, "--json"])

    def pour(self, formula: str, variables: Mapping[str, str]) -> dict[str, Any]:
        command = ["bd", "mol", "pour", formula]
        for key, value in variables.items():
            command.extend(["--var", f"{key}={value}"])
        command.append("--json")
        payload = self.json(command)
        if not isinstance(payload, dict):
            raise DstackError(f"bd mol pour {formula} returned a non-object")
        return payload

    def add_dependency(
        self,
        issue_id: str,
        depends_on_id: str,
        *,
        relation_type: str = "blocks",
    ) -> None:
        self._run(
            [
                "bd",
                "dep",
                "add",
                issue_id,
                depends_on_id,
                "--type",
                relation_type,
            ]
        )

    def remove_dependency(self, issue_id: str, depends_on_id: str) -> None:
        self._run(["bd", "dep", "remove", issue_id, depends_on_id])

    def relate(self, left_id: str, right_id: str) -> None:
        self._run(["bd", "dep", "relate", left_id, right_id])

    def supersede(self, old_id: str, new_id: str) -> None:
        old = self.show(old_id)
        if old.get("status") == "closed":
            if new_id not in supersession_targets(old):
                raise DstackError(f"closed issue {old_id} is not superseded by expected {new_id}")
            return
        try:
            self._run(["bd", "supersede", old_id, "--with", new_id])
        except DstackError as exc:
            try:
                observed = self.show_optional(old_id)
            except DstackError as reread_error:
                raise DstackError(
                    f"supersession outcome is uncertain for {old_id} -> {new_id}; native reread failed: {reread_error}"
                ) from reread_error
            if observed is not None and observed.get("status") == "closed" and new_id in supersession_targets(observed):
                return
            observed_status = observed.get("status") if observed is not None else "missing"
            raise DstackError(
                f"supersession outcome is uncertain for {old_id} -> {new_id}; "
                f"retained native status={observed_status!r}: {exc}"
            ) from exc
        try:
            observed = self.show(old_id)
        except DstackError as reread_error:
            raise DstackError(
                f"supersession outcome is uncertain for {old_id} -> {new_id}; "
                f"verification reread failed: {reread_error}"
            ) from reread_error
        if observed.get("status") != "closed" or new_id not in supersession_targets(observed):
            raise DstackError(f"supersession outcome is ambiguous and retained for inspection: {old_id} -> {new_id}")

    def gate_check(self) -> builtins.list[dict[str, Any]]:
        """Evaluate native gates and return their refreshed state."""

        self._run(["bd", "gate", "check"])
        return self.gates(all_statuses=True)


def step_by_label(children: Sequence[Mapping[str, Any]], label: str) -> dict[str, Any]:
    matches = [dict(item) for item in children if has_label(item, label)]
    if len(matches) != 1:
        ids = [str(item.get("id")) for item in matches]
        raise DstackError(f"expected one step labeled {label}; found {ids or 'none'}")
    return matches[0]


def _workflow_identity_values(
    issue: Mapping[str, Any],
    *,
    label_prefix: str,
    metadata_keys: Sequence[str],
) -> set[str]:
    values = {
        label.removeprefix(label_prefix)
        for label in issue_labels(issue)
        if label.startswith(label_prefix) and label != label_prefix
    }
    metadata = issue_metadata(issue)
    for key in metadata_keys:
        value = metadata.get(key)
        if isinstance(value, str) and value:
            values.add(value)
    variables = metadata.get("variables")
    if isinstance(variables, dict):
        key = metadata_keys[-1]
        value = variables.get(key)
        if isinstance(value, str) and value:
            values.add(value)
    return values


def feature_identity_values(issue: Mapping[str, Any]) -> set[str]:
    return _workflow_identity_values(
        issue,
        label_prefix="feature:",
        metadata_keys=("dstack.feature_slug", "feature_slug"),
    )


def feature_slug(issue: Mapping[str, Any]) -> str | None:
    values = feature_identity_values(issue)
    return next(iter(values)) if len(values) == 1 else None


def _has_one_canonical_identity(values: set[str]) -> bool:
    return len(values) == 1 and slugify(next(iter(values))) == next(iter(values))


def _is_feature_root_shape(issue: Mapping[str, Any]) -> bool:
    return (
        issue_parent(issue) is None
        and issue_type(issue) in {"epic", "molecule"}
        and _has_one_canonical_identity(feature_identity_values(issue))
        and not any(label.startswith("audit:") for label in issue_labels(issue))
    )


def is_feature_root(issue: Mapping[str, Any]) -> bool:
    return _is_feature_root_shape(issue) and (
        has_label(issue, "workflow:feature") or has_label(issue, "dstack:feature-idea")
    )


def feature_roots_from_inventory(issues: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in issues if is_feature_root(item)]


def canonical_feature_design_path(slug: str) -> str:
    if not slug or slugify(slug) != slug:
        raise DstackError("feature slug must be canonical lowercase kebab-case")
    return f"docs/src/features/{slug}/design.md"


def root_metadata_value(issue: Mapping[str, Any], *keys: str) -> str | None:
    metadata = issue_metadata(issue)
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    variables = metadata.get("variables")
    if isinstance(variables, dict):
        for key in keys:
            short = key.rsplit(".", 1)[-1]
            value = variables.get(short)
            if isinstance(value, str) and value:
                return value
    return None


def has_current_feature_steps(children: Sequence[Mapping[str, Any]]) -> bool:
    return all(any(has_label(child, label) for child in children) for label in FEATURE_STEPS.values())


def is_current_feature(client: BeadsClient, root_issue: Mapping[str, Any]) -> bool:
    root_id = root_issue.get("id")
    return isinstance(root_id, str) and has_current_feature_steps(client.children(root_id))


def feature_roots(client: BeadsClient) -> list[dict[str, Any]]:
    return feature_roots_from_inventory(client.list(all_statuses=True))


def _resolve_feature(
    client: BeadsClient,
    selector: str | None,
    *,
    root_predicate: Callable[[Mapping[str, Any]], bool],
) -> dict[str, Any]:
    if selector:
        exact = client.show_optional(selector)
        if exact is not None:
            if root_predicate(exact):
                return exact
            if (
                has_label(exact, "workflow:feature")
                or has_label(exact, "dstack:feature-idea")
                or feature_identity_values(exact)
            ):
                raise DstackError(f"Bead {selector} is not a feature workflow root")

    roots = [dict(item) for item in client.list(all_statuses=True) if root_predicate(item)]
    if not selector:
        branch = run(["git", "branch", "--show-current"], cwd=client.root).stdout.strip()
        if branch.startswith("feat/"):
            registered = worktree_for_branch(client.root, branch)
            if registered != client.root.resolve():
                raise DstackError("no feature selector was supplied outside its registered feature worktree")
            selector = branch[5:]
        else:
            raise DstackError("no feature selector was supplied and the current branch is not feat/<slug>")

    selector_slug = selector.casefold().strip()
    normalized_title = normalize_title(selector)
    candidates: list[dict[str, Any]] = []
    for root in roots:
        slug = feature_slug(root)
        if slug and slug.casefold() == selector_slug:
            candidates.append(root)
            continue
        if normalize_title(str(root.get("title", ""))) == normalized_title:
            candidates.append(root)

    if not candidates:
        raise FeatureNotFound(f"no feature matches selector: {selector}")

    open_current = [item for item in candidates if item.get("status") != "closed" and is_current_feature(client, item)]
    if len(open_current) == 1:
        return open_current[0]
    viable = [item for item in candidates if item.get("status") != "closed"]
    if len(viable) == 1:
        return viable[0]
    if len(candidates) == 1:
        return candidates[0]
    raise DstackError("feature selector is ambiguous: " + ", ".join(str(item.get("id")) for item in candidates))


def resolve_feature(client: BeadsClient, selector: str | None) -> dict[str, Any]:
    return _resolve_feature(client, selector, root_predicate=is_feature_root)


def human_gate_for_step(
    client: BeadsClient,
    *,
    root_id: str,
    step: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Resolve the human gate that blocks a stable workflow step.

    Beads stores gate relationships as ordinary blocking dependencies. The
    ``gate list`` JSON output is intentionally lightweight and does not include
    the derived parent relation, so gate identity must come from the blocked
    step rather than from fields projected onto the gate listing.
    """

    step_id = str(step["id"])
    full_step = step if dependency_records(step) else client.show(step_id)
    candidates: dict[str, dict[str, Any]] = {}

    for blocker_id in blocker_ids(full_step):
        blocker = client.show_optional(blocker_id)
        if blocker is None or issue_type(blocker) != "gate":
            continue
        if gate_type(blocker) == "human":
            candidates[str(blocker["id"])] = blocker

    return next(iter(candidates.values())) if len(candidates) == 1 else None


def feature_context(client: BeadsClient, selector: str | None) -> dict[str, Any]:
    """Return stable feature identity and steps without dashboard queries."""

    root = resolve_feature(client, selector)
    root_id = str(root["id"])
    children = client.children(root_id)
    current = has_current_feature_steps(children)
    slug = feature_slug(root)
    result: dict[str, Any] = {
        "root": root,
        "slug": slug,
        "current": current,
        "closed": root.get("status") == "closed",
    }
    if not current:
        return result

    if not slug:
        raise DstackError(f"current feature {root_id} has no feature slug")
    design_path = root_metadata_value(root, "dstack.design_path", "design_path")
    expected_design_path = canonical_feature_design_path(slug)
    if design_path != expected_design_path:
        raise DstackError(f"feature design path must be {expected_design_path} for the mdBook layout")

    result.update(
        {
            "steps": {name: step_by_label(children, label) for name, label in FEATURE_STEPS.items()},
            "base_branch": root_metadata_value(root, "dstack.base_branch", "base_branch"),
            "design_path": design_path,
            "pending_design_sha256": root_metadata_value(root, "dstack.pending_design_sha256"),
            "approved_design_sha256": root_metadata_value(root, "dstack.approved_design_sha256"),
        }
    )
    return result


def feature_design_state(client: BeadsClient, context: Mapping[str, Any]) -> dict[str, Any]:
    approved = context.get("approved_design_sha256")
    pending = context.get("pending_design_sha256")
    design_path = context.get("design_path")
    slug = context.get("slug")
    current: str | None = None
    head: str | None = None
    state = "design_state_unknown"
    if design_path and slug:
        worktree = worktree_for_branch(client.root, f"feat/{slug}")
        if worktree is None:
            state = "worktree_missing"
        else:
            design_file = safe_repository_path(worktree, str(design_path), purpose="feature design path")
            if not design_file.is_file():
                state = "design_missing"
            else:
                current = file_sha256(design_file)
                head = git_file_sha256(worktree, str(design_path))
                if head is None:
                    state = "untracked"
                else:
                    unchanged = (
                        run(
                            ["git", "diff", "--quiet", "HEAD", "--", str(design_path)],
                            cwd=worktree,
                            check=False,
                        ).returncode
                        == 0
                    )
                    state = "committed" if unchanged and current == head else "worktree_mismatch"
    return {
        "current_design_sha256": current,
        "head_design_sha256": head,
        "design_state": state,
        "design_approved": bool(not pending and approved and state == "committed" and current == head == approved),
    }


def feature_authorization_state(client: BeadsClient, context: Mapping[str, Any]) -> dict[str, Any]:
    steps = context.get("steps")
    if not isinstance(steps, Mapping):
        return {"human_gate": None, "native_approved": False}
    specification = client.show(str(steps["specification"]["id"]))
    approval = client.show(str(steps["approval"]["id"]))
    gate = human_gate_for_step(
        client,
        root_id=str(context["root"]["id"]),
        step=approval,
    )
    states = {
        "specification": specification.get("status"),
        "human_gate": gate.get("status") if isinstance(gate, Mapping) else None,
        "approval": approval.get("status"),
    }
    return {
        "human_gate": gate,
        "authorization_states": states,
        "native_approved": all(status == "closed" for status in states.values()),
    }


def feature_view(client: BeadsClient, selector: str | None, *, verbose: bool = False) -> dict[str, Any]:
    """Return native feature records plus deterministic Git/worktree facts.

    Readiness and lifecycle progression remain Beads authority.  In particular,
    this view never chooses or projects the next work item.
    """

    result = feature_context(client, selector)
    root = result["root"]
    branch: str | None = None
    worktree: Path | None = None
    if result.get("current") and result.get("slug"):
        branch = f"feat/{result['slug']}"
        worktree = worktree_for_branch(client.root, branch)

    if not verbose:
        return {
            "root": root,
            "branch": branch,
            "worktree": str(worktree) if worktree is not None else None,
        }

    if result.get("current"):
        steps = result["steps"]
        implementation_id = str(steps["implementation"]["id"])
        result.update(feature_design_state(client, result))
        result.update(feature_authorization_state(client, result))
        result["work_items"] = [
            item
            for item in client.children(implementation_id)
            if has_label(item, "dstack:work:implementation") or issue_type(item) not in {"epic", "molecule", "gate"}
        ]
    result["branch"] = branch
    result["worktree"] = str(worktree) if worktree is not None else None
    return result


def worktree_records(root: Path) -> list[dict[str, str | bool]]:
    output = run(["git", "worktree", "list", "--porcelain"], cwd=root).stdout
    records: list[dict[str, str | bool]] = []
    current: dict[str, str | bool] = {}
    for line in output.splitlines() + [""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key in {"bare", "detached", "prunable", "locked"}:
            current[key] = True
        else:
            current[key] = value
    return records


def worktree_for_branch(root: Path, branch: str) -> Path | None:
    expected = f"refs/heads/{branch}"
    for item in worktree_records(root):
        if item.get("branch") == expected and isinstance(item.get("worktree"), str):
            return Path(str(item["worktree"]))
    return None


def conventional_worktree(root: Path, branch: str) -> Path:
    common = run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=root,
        check=False,
    )
    primary = Path(common.stdout.strip()).parent if common.returncode == 0 else root
    return primary.parent / f"{primary.name}.{branch.replace('/', '-')}"


def ensure_clean_tracked(path: Path) -> None:
    status = run(["git", "status", "--short", "--untracked-files=no"], cwd=path).stdout.strip()
    if status:
        raise DstackError(f"tracked worktree changes prevent this operation in {path}:\n{status}")


def ensure_clean_worktree(path: Path) -> None:
    status = run(["git", "status", "--short", "--untracked-files=all"], cwd=path).stdout.strip()
    if status:
        raise DstackError(f"worktree changes prevent this operation in {path}:\n{status}")


def validate_git_branch(root: Path, branch: str, *, name: str = "branch") -> str:
    if not branch or branch.startswith("-") or any(char in branch for char in "\r\n\0"):
        raise DstackError(f"invalid {name}: {branch!r}")
    result = run(
        ["git", "check-ref-format", "--branch", branch],
        cwd=root,
        check=False,
    )
    if result.returncode:
        raise DstackError(f"invalid {name}: {branch!r}")
    return branch


def validate_git_revision(root: Path, ref: str, *, name: str = "revision") -> str:
    if not ref or ref.startswith("-") or any(char in ref for char in "\r\n\0"):
        raise DstackError(f"invalid {name}: {ref!r}")
    result = run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{ref}^{{commit}}",
        ],
        cwd=root,
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


def _assert_no_symlink_components(path: Path, *, purpose: str) -> None:
    current = Path(path)
    while True:
        if current.is_symlink():
            raise DstackError(f"{purpose} must not be a symlink: {path}")
        if current.parent == current:
            return
        current = current.parent


def verify_worktree_identity(
    root: Path,
    worktree: Path,
    branch: str,
    *,
    conventional: bool = True,
) -> Path:
    validate_git_branch(root, branch)
    _assert_no_symlink_components(worktree, purpose="worktree")
    expected_path = conventional_worktree(root, branch)
    _assert_no_symlink_components(expected_path, purpose="conventional worktree")
    expected = expected_path.resolve()
    resolved = worktree.resolve()
    if conventional and resolved != expected:
        raise DstackError(f"worktree for {branch} must use conventional path {expected}: {resolved}")
    try:
        expected_common = git_common_dir(root)
        actual_common = git_common_dir(resolved)
    except DstackError as exc:
        raise DstackError(f"worktree repository identity is unavailable for {branch}: {resolved}") from exc
    if actual_common != expected_common:
        raise DstackError(
            f"worktree repository identity mismatch for {branch}: expected={expected_common}, actual={actual_common}"
        )
    top = run(["git", "rev-parse", "--show-toplevel"], cwd=resolved, check=False)
    actual_branch = run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=resolved,
        check=False,
    )
    if (
        top.returncode
        or Path(top.stdout.strip()).resolve() != resolved
        or actual_branch.returncode
        or actual_branch.stdout.strip() != branch
    ):
        raise DstackError(
            f"worktree identity mismatch for {branch}: path={resolved}, "
            f"branch={actual_branch.stdout.strip() or '<detached>'}"
        )
    return resolved


def branch_exists(root: Path, branch: str) -> bool:
    result = run(
        ["git", "show-ref", "--verify", "--quiet", "--", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
    )
    return result.returncode == 0


def ref_exists(root: Path, ref: str) -> bool:
    return (
        run(
            ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", ref],
            cwd=root,
            check=False,
        ).returncode
        == 0
    )


def ancestry(root: Path, ancestor: str, descendant: str) -> bool:
    return (
        run(
            ["git", "merge-base", "--is-ancestor", "--", ancestor, descendant],
            cwd=root,
            check=False,
        ).returncode
        == 0
    )


def current_head(root: Path, ref: str = "HEAD") -> str:
    return run(["git", "rev-parse", "--verify", "--end-of-options", ref], cwd=root).stdout.strip()


def commit_records(root: Path, ref_range: str) -> list[dict[str, Any]]:
    """Return parsed reachable commits with their Beads footer identities."""

    validate_git_range(root, ref_range, name="evidence revision")
    format_string = "%x1e%H%x00%s%x00%B%x00"
    output = run(
        ["git", "log", f"--format={format_string}", "--name-only", ref_range],
        cwd=root,
    ).stdout
    records: list[dict[str, Any]] = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        parts = record.split("\x00", 3)
        if len(parts) != 4:
            continue
        commit, subject, body, path_text = parts
        commit = commit.strip()
        if not commit:
            continue
        records.append(
            {
                "commit": commit,
                "subject": subject.strip(),
                "body": body,
                "paths": [line for line in path_text.splitlines() if line.strip()],
                "footer_ids": tuple(match.group(1) for match in re.finditer(r"(?m)^Beads:\s*([^\s]+)\s*$", body)),
            }
        )
    return records


def footer_mapping(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for bead_id in record.get("footer_ids", ()):
            result.setdefault(str(bead_id), []).append(
                {
                    "commit": str(record["commit"]),
                    "subject": str(record["subject"]),
                    "paths": list(record.get("paths", [])),
                }
            )
    return result


def commit_footer_ids(root: Path, ref_range: str) -> dict[str, list[dict[str, Any]]]:
    """Return every reachable commit grouped by its ``Beads:`` footer."""

    return footer_mapping(commit_records(root, ref_range))


def commit_records_for_beads(
    root: Path,
    ref_range: str,
    bead_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Return full commit records matching any requested exact Beads footer.

    Git performs one commit traversal regardless of the number of expected
    Beads IDs. Only commits whose messages match one fixed-string candidate
    are expanded with ``--name-only``; dStack then verifies exact footer lines.
    """

    validate_git_range(root, ref_range, name="evidence revision")
    requested = tuple(dict.fromkeys(str(item) for item in bead_ids if item))
    if not requested:
        return []
    if any(any(character.isspace() for character in bead_id) for bead_id in requested):
        raise DstackError("Beads evidence ID must be one non-empty token")
    format_string = "%x1e%H%x00%s%x00%B%x00"
    command = [
        "git",
        "log",
        f"--format={format_string}",
        "--name-only",
        "--fixed-strings",
        *(f"--grep=Beads: {bead_id}" for bead_id in requested),
        ref_range,
    ]
    output = run(command, cwd=root).stdout
    wanted = set(requested)
    result: list[dict[str, Any]] = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        parts = record.split("\x00", 3)
        if len(parts) != 4:
            raise DstackError("Git evidence query returned a malformed record")
        commit, subject, body, path_text = parts
        commit = commit.strip()
        footer_ids = tuple(match.group(1) for match in re.finditer(r"(?m)^Beads:\s*([^\s]+)\s*$", body))
        if not commit or not wanted.intersection(footer_ids):
            continue
        result.append(
            {
                "commit": commit,
                "subject": subject.strip(),
                "body": body,
                "paths": [line for line in path_text.splitlines() if line.strip()],
                "footer_ids": footer_ids,
            }
        )
    return result


def commit_records_for_bead(root: Path, ref_range: str, bead_id: str) -> list[dict[str, Any]]:
    """Return full commit records matching one exact ``Beads: <id>`` footer."""

    if not bead_id:
        raise DstackError("Beads evidence ID must be one non-empty token")
    return commit_records_for_beads(root, ref_range, [bead_id])


def commits_for_bead(root: Path, ref_range: str, bead_id: str) -> list[dict[str, Any]]:
    """Return compact commits with one exact ``Beads: <id>`` footer.

    Git performs the cheap candidate filtering; dStack still verifies the
    footer exactly before accepting evidence. This avoids parsing complete
    repository history for every task transition.
    """

    return [
        {
            "commit": str(record["commit"]),
            "subject": str(record["subject"]),
            "paths": list(record.get("paths", [])),
        }
        for record in commit_records_for_bead(root, ref_range, bead_id)
    ]
