"""Thin adapter over the native Beads CLI and its issue shapes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core import CommandResult, DstackError, assert_no_symlink_components, run, truncate_output
from .git_state import git_root

SUPPORTED_BEADS_VERSION = (1, 2, 2)
BEADS_VERSION_PATTERN = re.compile(r"\bbd version (\d+)\.(\d+)\.(\d+)\b")


def run_beads(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    **kwargs: Any,
) -> CommandResult:
    if not command or Path(str(command[0])).name != "bd":
        raise DstackError("Beads adapter may only execute bd commands")
    beads_env = {"BD_JSON_ENVELOPE": "1"}
    if env:
        beads_env.update(env)
    kwargs.setdefault("timeout", 180.0)
    return run(command, cwd=cwd, check=check, env=beads_env, **kwargs)


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
    major, minor, patch = (int(group) for group in match.groups())
    return major, minor, patch


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
        return run_beads(command, cwd=self.root, **kwargs)

    def json(self, command: Sequence[str]) -> Any:
        result = self._run(command, check=False)
        if result.returncode != 0:
            raise beads_command_error(result, context=" ".join(command))
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

    def show_many(self, issue_ids: Sequence[str], *, include_comments: bool = False) -> list[dict[str, Any]]:
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

    def list_issues(
        self,
        *,
        parent: str | None = None,
        labels: Sequence[str] = (),
        issue_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        # Recovery requires complete lifecycle state, so native list reads are always unbounded and include all statuses.
        command = ["bd", "list", "--limit", "0", "--json", "--all"]
        if parent:
            command.extend(["--parent", parent])
        for label in labels:
            command.extend(["--label", label])
        if issue_type_filter:
            command.extend(["--type", issue_type_filter])
        return as_items(self.json(command), context="bd list")

    def children(self, parent: str) -> list[dict[str, Any]]:
        return self.list_issues(parent=parent)

    def worktrees(self) -> list[dict[str, Any]]:
        payload = self.json(["bd", "worktree", "list", "--json"])
        if not isinstance(payload, list):
            raise DstackError("bd worktree list returned an unknown JSON shape")
        result: list[dict[str, Any]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise DstackError(f"bd worktree list item {index} is invalid")
            result.append(dict(item))
        return result

    def create_worktree(self, path: Path, branch: str) -> CommandResult:
        return self._run(["bd", "worktree", "create", str(path), "--branch", branch])

    def remove_worktree(self, path: Path) -> CommandResult:
        return self._run(["bd", "worktree", "remove", str(path), "--force"], check=False)


def beads_workspace_optional(root: Path) -> Path | None:
    """Resolve the authoritative workspace through native ``bd where``."""

    repository = git_root(root)
    result = run_beads(["bd", "where", "--json"], cwd=repository, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        if (repository / ".beads").exists():
            details = result.stderr.strip() or result.stdout.strip() or "bd where returned no workspace"
            raise DstackError(f"existing Beads workspace is unhealthy: {details}")
        return None
    payload = parse_json(result.stdout, context="bd where")
    if not isinstance(payload, dict) or not isinstance(payload.get("path"), str) or not payload["path"].strip():
        raise DstackError("bd where returned an invalid Beads workspace payload")
    workspace = Path(payload["path"]).expanduser()
    if not workspace.is_absolute():
        workspace = repository / workspace
    assert_no_symlink_components(workspace, purpose="Beads workspace")
    resolved = workspace.resolve()
    if resolved.name != ".beads" or not resolved.is_dir():
        raise DstackError(f"bd where returned an invalid Beads workspace: {resolved}")
    return resolved


def beads_workspace(root: Path) -> Path:
    workspace = beads_workspace_optional(root)
    if workspace is None:
        raise DstackError(
            "Beads is not initialized for this repository; run `dstack init` before using this lower-level command"
        )
    return workspace


def client_for(root: Path) -> BeadsClient:
    repository = Path(root).expanduser()
    beads_workspace(repository)
    client = BeadsClient(repository)
    client.check_version()
    return client
