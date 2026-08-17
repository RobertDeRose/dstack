#!/usr/bin/env python3
"""Shared stateless adapters for dstack.

This module reads current state from Beads and Git on every invocation. It owns
no database, cache, packet format, readiness calculation, or workflow state.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

MIN_BEADS_VERSION = (1, 2, 2)
FEATURE_STEPS = {
    "specification": "dstack:step:specification",
    "approval": "dstack:step:implementation-approval",
    "implementation": "dstack:step:implementation",
    "closeout": "dstack:step:closeout",
}
ALIGNMENT_STEPS = {
    "analysis": "dstack:step:alignment-analysis",
    "approval": "dstack:step:alignment-approval",
    "corrections": "dstack:step:alignment-corrections",
    "landing": "dstack:step:alignment-landing",
}


class DstackError(RuntimeError):
    """Raised when a stateless dstack operation cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


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
) -> CommandResult:
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
        )
    except FileNotFoundError as exc:
        raise DstackError(f"required executable not found: {command[0]}") from exc

    result = CommandResult(completed.returncode, completed.stdout, completed.stderr)
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DstackError(f"command failed ({' '.join(command)}): {detail}")
    return result


def parse_json(text: str, *, context: str) -> Any:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DstackError(f"{context} returned invalid JSON") from exc
    if isinstance(payload, dict) and payload.get("schema_version") == 1 and "data" in payload:
        return payload["data"]
    return payload


def as_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("id"), str):
            return [payload]
        for key in ("issues", "items", "data", "closed"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def first_item(payload: Any, *, context: str) -> dict[str, Any]:
    items = as_items(payload)
    if len(items) != 1:
        raise DstackError(f"{context} returned {len(items)} issues; expected exactly one")
    return items[0]


def git_root(path: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=path.resolve())
    return Path(result.stdout.strip()).resolve()


def git_common_root(path: Path) -> Path:
    root = git_root(path)
    common = run(["git", "rev-parse", "--git-common-dir"], cwd=root).stdout.strip()
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (root / common_path).resolve()
    return common_path.parent if common_path.name == ".git" else root


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


def label_value(issue: Mapping[str, Any], prefix: str) -> str | None:
    matches = [label[len(prefix) :] for label in issue_labels(issue) if label.startswith(prefix)]
    return matches[0] if len(matches) == 1 and matches[0] else None


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


def read_text_file(path: Path | None) -> str:
    if path is None:
        return ""
    return path.read_text().strip()


def write_temp_text(text: str) -> TextIO:
    handle = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False)
    handle.write(text)
    handle.flush()
    return cast(TextIO, handle)


def parse_version(raw: str) -> tuple[int, int, int]:
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", raw)
    if not match:
        raise DstackError(f"cannot parse Beads version: {raw!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


class BeadsClient:
    """Thin, stateless adapter around the supported Beads CLI."""

    def __init__(self, root: Path):
        self.root = git_root(root)

    def json(self, command: Sequence[str], *, check: bool = True) -> Any:
        result = run(command, cwd=self.root, check=check)
        if result.returncode != 0:
            return None
        return parse_json(result.stdout, context=" ".join(command))

    def version(self) -> str:
        return run(["bd", "--version"], cwd=self.root).stdout.strip()

    def check_version(self) -> str:
        raw = self.version()
        if parse_version(raw) < MIN_BEADS_VERSION:
            minimum = ".".join(str(item) for item in MIN_BEADS_VERSION)
            raise DstackError(f"dstack requires Beads {minimum} or newer; found {raw}")
        return raw

    def check_capabilities(self) -> None:
        for command in (
            ["bd", "formula", "show", "--help"],
            ["bd", "mol", "pour", "--help"],
            ["bd", "gate", "list", "--help"],
            ["bd", "ready", "--help"],
            ["bd", "worktree", "list", "--help"],
        ):
            run(command, cwd=self.root)

    def show_optional(self, issue_id: str) -> dict[str, Any] | None:
        result = run(["bd", "show", issue_id, "--json"], cwd=self.root, check=False)
        if result.returncode != 0:
            detail = f"{result.stdout}\n{result.stderr}".casefold()
            if "not found" in detail or "no issues found" in detail:
                return None
            raise DstackError(result.stderr.strip() or result.stdout.strip())
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
        return as_items(self.json(command))

    def children(self, parent: str, *, all_statuses: bool = True) -> builtins.list[dict[str, Any]]:
        return self.list(all_statuses=all_statuses, parent=parent)

    def gates(self, *, all_statuses: bool = True) -> builtins.list[dict[str, Any]]:
        command = ["bd", "gate", "list", "--limit", "0", "--json"]
        if all_statuses:
            command.append("--all")
        return as_items(self.json(command))

    def update(self, issue_id: str, *arguments: str) -> dict[str, Any]:
        payload = self.json(["bd", "update", issue_id, *arguments, "--json"])
        return first_item(payload, context=f"bd update {issue_id}")

    def close(self, issue_id: str, reason: str) -> dict[str, Any]:
        current = self.show(issue_id)
        if current.get("status") == "closed":
            return current
        payload = self.json(["bd", "close", issue_id, "--reason", reason, "--json"])
        items = as_items(payload)
        if items:
            return items[0]
        return self.show(issue_id)

    def resolve_gate(self, gate_id: str, reason: str) -> dict[str, Any]:
        """Resolve a gate, then read its authoritative state.

        Beads 1.2.2 accepts the global ``--json`` flag for ``gate resolve`` but
        still emits human-readable text. Treat the command as a state-changing
        operation rather than a JSON endpoint, then query the gate separately.
        """

        current = self.show(gate_id)
        if current.get("status") == "closed":
            return current
        run(
            ["bd", "gate", "resolve", gate_id, "--reason", reason],
            cwd=self.root,
        )
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
        try:
            run(["bd", "comments", "add", issue_id, "-f", handle.name], cwd=self.root)
        finally:
            Path(handle.name).unlink(missing_ok=True)

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
        return as_items(self.json(command))

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
        run(
            [
                "bd",
                "dep",
                "add",
                issue_id,
                depends_on_id,
                "--type",
                relation_type,
            ],
            cwd=self.root,
        )

    def supersede(self, old_id: str, new_id: str) -> None:
        old = self.show(old_id)
        if old.get("status") == "closed":
            # Existing supersession is sufficient; do not reopen history.
            return
        run(["bd", "supersede", old_id, "--with", new_id], cwd=self.root)

    def gate_check(self) -> builtins.list[dict[str, Any]]:
        """Evaluate native gates and return their refreshed state.

        Beads 1.2.2 mixes progress text with JSON for ``gate check --json``.
        dStack needs only the side effect, so run the command in its supported
        human-output mode and read gates through ``gate list --json`` afterward.
        """

        run(["bd", "gate", "check"], cwd=self.root)
        return self.gates(all_statuses=True)


def step_by_label(children: Sequence[Mapping[str, Any]], label: str) -> dict[str, Any]:
    matches = [dict(item) for item in children if has_label(item, label)]
    if len(matches) != 1:
        ids = [str(item.get("id")) for item in matches]
        raise DstackError(f"expected one step labeled {label}; found {ids or 'none'}")
    return matches[0]


def feature_slug(issue: Mapping[str, Any]) -> str | None:
    slug = label_value(issue, "feature:")
    if slug:
        return slug
    metadata = issue_metadata(issue)
    for key in ("dstack.feature_slug", "feature_slug"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    variables = metadata.get("variables")
    if isinstance(variables, dict):
        value = variables.get("feature_slug")
        if isinstance(value, str) and value:
            return value
    return None


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
    return [
        item
        for item in client.list(all_statuses=True, labels=["workflow:feature"])
        if issue_type(item) in {"epic", "molecule"}
    ]


def resolve_feature(client: BeadsClient, selector: str | None) -> dict[str, Any]:
    if selector:
        exact = client.show_optional(selector)
        if (
            exact is not None
            and issue_type(exact) in {"epic", "molecule"}
            and (has_label(exact, "workflow:feature") or feature_slug(exact))
        ):
            return exact

    roots = feature_roots(client)
    if not selector:
        branch = run(["git", "branch", "--show-current"], cwd=client.root).stdout.strip()
        if branch.startswith("feat/"):
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
        raise DstackError(f"no feature matches selector: {selector}")

    open_current = [item for item in candidates if item.get("status") != "closed" and is_current_feature(client, item)]
    if len(open_current) == 1:
        return open_current[0]
    viable = [item for item in candidates if item.get("status") != "closed"]
    if len(viable) == 1:
        return viable[0]
    if len(candidates) == 1:
        return candidates[0]
    raise DstackError("feature selector is ambiguous: " + ", ".join(str(item.get("id")) for item in candidates))


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
    full_step = client.show(step_id)
    candidates: dict[str, dict[str, Any]] = {}

    for blocker_id in blocker_ids(full_step):
        blocker = client.show_optional(blocker_id)
        if blocker is None or issue_type(blocker) != "gate":
            continue
        if gate_type(blocker) == "human":
            candidates[str(blocker["id"])] = blocker

    if not candidates:
        # Compatibility fallback for older or partially hydrated Beads output:
        # query gates through the native parent filter, which evaluates the
        # parent-child dependency in Beads instead of requiring a ``parent``
        # field in ``bd gate list`` output.
        for gate in client.list(
            all_statuses=True,
            parent=root_id,
            include_gates=True,
            issue_type_filter="gate",
        ):
            if gate_type(gate) == "human":
                candidates[str(gate["id"])] = gate

    return next(iter(candidates.values())) if len(candidates) == 1 else None


def feature_context(client: BeadsClient, selector: str | None) -> dict[str, Any]:
    """Return stable feature identity and steps without dashboard queries."""
    root = resolve_feature(client, selector)
    root_id = str(root["id"])
    children = client.children(root_id)
    current = has_current_feature_steps(children)
    result: dict[str, Any] = {
        "root": root,
        "slug": feature_slug(root),
        "current": current,
        "closed": root.get("status") == "closed",
    }
    if not current:
        return result

    result.update(
        {
            "steps": {
                name: step_by_label(children, label) for name, label in FEATURE_STEPS.items()
            },
            "base_branch": root_metadata_value(
                root, "dstack.base_branch", "base_branch"
            ),
            "design_path": root_metadata_value(
                root, "dstack.design_path", "design_path"
            ),
            "approved_design_sha256": root_metadata_value(
                root, "dstack.approved_design_sha256"
            ),
        }
    )
    return result


def feature_design_state(client: BeadsClient, context: Mapping[str, Any]) -> dict[str, Any]:
    approved = context.get("approved_design_sha256")
    design_path = context.get("design_path")
    slug = context.get("slug")
    current: str | None = None
    if design_path and slug:
        worktree = worktree_for_branch(client.root, f"feat/{slug}")
        design_file = (worktree or client.root) / str(design_path)
        if design_file.is_file():
            current = file_sha256(design_file)
    return {
        "current_design_sha256": current,
        "design_approved": bool(approved and current == approved),
    }


def feature_view(client: BeadsClient, selector: str | None) -> dict[str, Any]:
    result = feature_context(client, selector)
    if not result["current"]:
        return result

    root = result["root"]
    root_id = str(root["id"])
    steps = result["steps"]
    implementation_id = str(steps["implementation"]["id"])
    work_items = [
        item
        for item in client.children(implementation_id)
        if has_label(item, "dstack:work:implementation")
        or issue_type(item) not in {"epic", "molecule", "gate"}
    ]
    result.update(feature_design_state(client, result))
    result.update(
        {
            "human_gate": human_gate_for_step(
                client,
                root_id=root_id,
                step=steps["approval"],
            ),
            "work_items": work_items,
            "ready_work": client.ready_children(implementation_id, label="dstack:work:implementation"),
            "progress": client.progress(root_id),
            "delivery_ready": steps["closeout"].get("status") == "closed" and root.get("status") != "closed",
        }
    )
    return result


def alignment_slug(issue: Mapping[str, Any]) -> str | None:
    slug = label_value(issue, "audit:")
    if slug:
        return slug
    return root_metadata_value(issue, "dstack.audit_slug", "audit_slug")


def alignment_roots(client: BeadsClient) -> list[dict[str, Any]]:
    return [
        item
        for item in client.list(all_statuses=True, labels=["workflow:project-alignment"])
        if issue_type(item) in {"epic", "molecule"}
    ]


def resolve_alignment(client: BeadsClient, selector: str) -> dict[str, Any]:
    exact = client.show_optional(selector)
    if (
        exact is not None
        and issue_type(exact) in {"epic", "molecule"}
        and has_label(exact, "workflow:project-alignment")
    ):
        return exact
    normalized = normalize_title(selector)
    candidates = [
        item
        for item in alignment_roots(client)
        if (alignment_slug(item) or "").casefold() == selector.casefold()
        or normalize_title(str(item.get("title", ""))) == normalized
    ]
    if len(candidates) != 1:
        raise DstackError(
            f"alignment selector resolved to {len(candidates)} roots: "
            + ", ".join(str(item.get("id")) for item in candidates)
        )
    return candidates[0]


def alignment_context(client: BeadsClient, selector: str) -> dict[str, Any]:
    """Return stable alignment identity and steps without dashboard queries."""

    root = resolve_alignment(client, selector)
    children = client.children(str(root["id"]))
    return {
        "root": root,
        "slug": alignment_slug(root),
        "steps": {name: step_by_label(children, label) for name, label in ALIGNMENT_STEPS.items()},
        "target_branch": root_metadata_value(root, "dstack.target_branch", "target_branch"),
        "scope": root_metadata_value(root, "dstack.scope", "scope"),
    }


def alignment_view(client: BeadsClient, selector: str) -> dict[str, Any]:
    result = alignment_context(client, selector)
    root = result["root"]
    root_id = str(root["id"])
    steps = result["steps"]
    corrections_id = str(steps["corrections"]["id"])
    result.update(
        {
            "human_gate": human_gate_for_step(
                client,
                root_id=root_id,
                step=steps["approval"],
            ),
            "corrections": client.children(corrections_id),
            "ready_work": client.ready_children(corrections_id, label="dstack:work:correction"),
            "progress": client.progress(root_id),
            "delivery_ready": steps["landing"].get("status") == "closed" and root.get("status") != "closed",
        }
    )
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
            return Path(str(item["worktree"])).resolve()
    return None


def conventional_worktree(root: Path, branch: str) -> Path:
    return root.parent / f"{root.name}.{branch.replace('/', '-')}"


def ensure_clean_tracked(path: Path) -> None:
    status = run(["git", "status", "--short", "--untracked-files=no"], cwd=path).stdout.strip()
    if status:
        raise DstackError(f"tracked worktree changes prevent this operation in {path}:\n{status}")


def branch_exists(root: Path, branch: str) -> bool:
    result = run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=root, check=False)
    return result.returncode == 0


def ref_exists(root: Path, ref: str) -> bool:
    return run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=root, check=False).returncode == 0


def ancestry(root: Path, ancestor: str, descendant: str) -> bool:
    return run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=root, check=False).returncode == 0


def current_head(root: Path, ref: str = "HEAD") -> str:
    return run(["git", "rev-parse", ref], cwd=root).stdout.strip()


def commit_footer_ids(root: Path, ref_range: str) -> dict[str, list[dict[str, Any]]]:
    """Return every reachable commit grouped by its ``Beads:`` footer."""

    format_string = "%H%x00%s%x00%B%x00"
    output = run(["git", "log", f"--format={format_string}", ref_range], cwd=root).stdout
    chunks = output.split("\x00")
    result: dict[str, list[dict[str, Any]]] = {}
    for index in range(0, len(chunks) - 2, 3):
        commit = chunks[index].strip()
        subject = chunks[index + 1].strip()
        body = chunks[index + 2]
        if not commit:
            continue
        paths = run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "--root",
                commit,
            ],
            cwd=root,
        ).stdout.splitlines()
        for match in re.finditer(r"(?m)^Beads:\s*([^\s]+)\s*$", body):
            result.setdefault(match.group(1), []).append(
                {"commit": commit, "subject": subject, "paths": paths}
            )
    return result
