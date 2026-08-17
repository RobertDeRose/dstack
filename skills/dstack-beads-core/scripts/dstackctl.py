#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from dstacklib import (
    BeadsClient,
    DstackError,
    alignment_view,
    ancestry,
    blocker_ids,
    branch_exists,
    commit_footer_ids,
    conventional_worktree,
    current_head,
    dependency_records,
    display_title,
    ensure_clean_tracked,
    feature_slug,
    feature_view,
    file_sha256,
    git_root,
    has_label,
    issue_labels,
    issue_metadata,
    issue_parent,
    read_text_file,
    ref_exists,
    resolve_feature,
    root_metadata_value,
    run,
    slugify,
    worktree_for_branch,
)

RUNTIME_BEADS_PREFIXES = (
    ".beads/interactions.jsonl",
    ".beads/embeddeddolt/",
    ".beads/dolt-backup",
)
FORBIDDEN_DOC_PATTERNS = (
    re.compile(r"(?i)^\s*[-*]?\s*status:\s*(in[- ]?progress|delivery[- ]?ready|blocked|review[- ]?active|completed)\b"),
    re.compile(r"(?i)^\s*[-*]?\s*beads?\s+(root|id|task):"),
    re.compile(
        r"(?i)^\s*[-*]?\s*(gate id|feature branch|worktree|candidate commit|"
        r"reviewed commit|delivery commit):"
    ),
    re.compile(
        r"(?i)^\s*[-*]?\s*(next command|next action|resume with|suggested command):"
        r"\s*/(start-feature|review-feature-spec|implement-feature|close-feature)\b"
    ),
)
DURABLE_STATUS_PATTERN = re.compile(
    r"(?i)^\s*[-*]?\s*status:\s*(planned|implemented|deprecated)\s*$"
)


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def fail(message: str) -> int:
    json.dump({"status": "error", "error": message}, sys.stderr)
    sys.stderr.write("\n")
    return 1


def package_root() -> Path:
    return Path(__file__).resolve().parents[3]


def client_for(root: Path) -> BeadsClient:
    client = BeadsClient(root)
    client.check_version()
    return client


def require_installed_formula(root: Path, name: str) -> None:
    source = package_root() / "formulas" / f"{name}.formula.toml"
    installed = root / ".beads" / "formulas" / f"{name}.formula.toml"
    if not installed.is_file():
        raise DstackError(
            f"dStack formula is not installed: {name}; run /setup-project"
        )
    if installed.read_bytes() != source.read_bytes():
        raise DstackError(
            f"installed formula {name} differs from this dStack package; "
            "run /setup-project --force before pouring new work"
        )


def update_root_identity(
    client: BeadsClient,
    root_id: str,
    *,
    title: str,
    slug: str,
    base_branch: str,
    design_path: str,
) -> dict[str, Any]:
    return client.update(
        root_id,
        "--title",
        f"Feature: {title}",
        "--add-label",
        "workflow:feature",
        "--add-label",
        f"feature:{slug}",
        "--set-metadata",
        f"dstack.base_branch={base_branch}",
        "--set-metadata",
        f"dstack.design_path={design_path}",
    )


def ensure_feature_worktree(client: BeadsClient, slug: str, base_branch: str) -> tuple[str, Path, bool, bool]:
    branch = f"feat/{slug}"
    if not ref_exists(client.root, base_branch):
        raise DstackError(f"base branch/ref does not exist: {base_branch}")

    created_branch = False
    created_worktree = False
    worktree = worktree_for_branch(client.root, branch)
    if worktree is not None:
        return branch, worktree, created_branch, created_worktree

    worktree = conventional_worktree(client.root, branch)
    if worktree.exists():
        raise DstackError(
            f"conventional worktree path exists but is not registered for {branch}: {worktree}"
        )

    if not branch_exists(client.root, branch):
        run(["git", "branch", branch, base_branch], cwd=client.root)
        created_branch = True

    try:
        run(
            ["bd", "worktree", "create", str(worktree), "--branch", branch],
            cwd=client.root,
        )
        created_worktree = True
    except Exception:
        if created_branch and branch_exists(client.root, branch):
            run(["git", "branch", "-D", branch], cwd=client.root, check=False)
        raise

    resolved = worktree_for_branch(client.root, branch)
    if resolved is None:
        raise DstackError(f"Beads created no discoverable worktree for {branch}")
    return branch, resolved, created_branch, created_worktree


def cmd_feature_resolve(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root = resolve_feature(client, args.selector)
    emit(
        {
            "status": "ok",
            "root": root,
            "slug": feature_slug(root),
            "current": feature_view(client, str(root["id"]))["current"],
        }
    )
    return 0


def cmd_feature_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    emit({"status": "ok", **feature_view(client, args.selector)})
    return 0


def is_planned_legacy_feature(issue: Mapping[str, Any]) -> bool:
    metadata = issue_metadata(issue)
    classification = str(metadata.get("migration_classification") or "").casefold()
    roadmap = str(metadata.get("legacy_roadmap_status") or "").casefold()
    return (
        classification == "planned"
        or "planned" in roadmap
        or has_label(issue, "dstack:feature-idea")
    )


def cmd_feature_initialize(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    selector = (args.selector or args.title or "").strip()
    if not selector:
        raise DstackError("feature selector/title is required")

    existing: dict[str, Any] | None = None
    try:
        existing = resolve_feature(client, selector)
    except DstackError as exc:
        if "no feature matches selector" not in str(exc):
            raise

    planned_source: dict[str, Any] | None = None
    if existing is not None:
        view = feature_view(client, str(existing["id"]))
        if existing.get("status") == "closed":
            raise DstackError(f"feature is already closed: {existing['id']}")
        if view["current"]:
            branch, worktree, _, _ = ensure_feature_worktree(
                client,
                str(view["slug"]),
                str(view.get("base_branch") or args.base_branch),
            )
            emit(
                {
                    "status": "ok",
                    "created": False,
                    "branch": branch,
                    "worktree": str(worktree),
                    **view,
                }
            )
            return 0
        if not is_planned_legacy_feature(existing):
            raise DstackError(
                f"feature {existing['id']} uses the active legacy workflow; "
                f"run /adopt-feature {existing['id']}"
            )
        planned_source = existing

    title = (
        args.title
        or (display_title(str(planned_source.get("title", ""))) if planned_source else selector)
    ).strip()
    slug = (
        args.slug
        or (feature_slug(planned_source) if planned_source else None)
        or slugify(title)
    )
    inherited_design = (
        root_metadata_value(planned_source, "design_path") if planned_source else None
    )
    inherited_base = (
        root_metadata_value(planned_source, "base_branch") if planned_source else None
    )
    base_branch = inherited_base or args.base_branch
    design_path = (
        args.design_path
        or inherited_design
        or f"docs/src/features/{slug}/design.md"
    )
    require_installed_formula(client.root, "dstack-feature")
    pour = client.pour(
        "dstack-feature",
        {
            "feature_title": title,
            "feature_slug": slug,
            "design_path": design_path,
        },
    )
    root_id = str(pour.get("root_id") or pour.get("new_epic_id") or "")
    if not root_id:
        raise DstackError("bd mol pour returned no feature root")

    created_branch = False
    created_worktree = False
    try:
        update_root_identity(
            client,
            root_id,
            title=title,
            slug=slug,
            base_branch=base_branch,
            design_path=design_path,
        )
        branch, worktree, created_branch, created_worktree = ensure_feature_worktree(
            client, slug, base_branch
        )
        if planned_source is not None:
            client.supersede(str(planned_source["id"]), root_id)
    except Exception:
        if created_worktree:
            run(
                [
                    "bd",
                    "worktree",
                    "remove",
                    str(conventional_worktree(client.root, f"feat/{slug}")),
                    "--force",
                ],
                cwd=client.root,
                check=False,
            )
        if created_branch and branch_exists(client.root, f"feat/{slug}"):
            run(
                ["git", "branch", "-D", f"feat/{slug}"],
                cwd=client.root,
                check=False,
            )
        run(
            ["bd", "delete", root_id, "--cascade", "--force"],
            cwd=client.root,
            check=False,
        )
        raise

    emit(
        {
            "status": "ok",
            "created": True,
            "planned_source": planned_source["id"] if planned_source else None,
            "branch": branch,
            "worktree": str(worktree),
            **feature_view(client, root_id),
        }
    )
    return 0


def task_text(path: Path | None, inline: str | None) -> str:
    if path:
        return path.read_text().strip()
    return (inline or "").strip()


def cmd_feature_add_task(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    if not view["current"]:
        raise DstackError("feature is not a current dstack molecule")
    implementation = view["steps"]["implementation"]
    approval = view["steps"]["approval"]
    dependencies = [str(approval["id"]), *args.depends_on]
    item = client.create(
        args.title,
        parent=str(implementation["id"]),
        labels=["dstack:work:implementation"],
        dependencies=dependencies,
        description=task_text(args.description_file, args.description),
        acceptance=task_text(args.acceptance_file, args.acceptance),
        priority=args.priority,
    )
    emit({"status": "ok", "task": item})
    return 0


def claim_issue_if_needed(client: BeadsClient, issue: Mapping[str, Any]) -> dict[str, Any]:
    if issue.get("status") == "in_progress":
        return dict(issue)
    if issue.get("status") == "closed":
        return dict(issue)
    return client.update(str(issue["id"]), "--claim")


def cmd_feature_claim_spec(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    specification = view["steps"]["specification"]
    claimed = claim_issue_if_needed(client, specification)
    emit({"status": "ok", "feature": view["root"]["id"], "specification": claimed})
    return 0


def cmd_feature_approve_spec(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    design_path = view.get("design_path")
    if not design_path:
        raise DstackError("feature root has no dstack.design_path metadata")
    _, feature_worktree, _ = feature_branch_context(client, view)
    digest = file_sha256(feature_worktree / str(design_path))
    root_id = str(view["root"]["id"])
    client.update(
        root_id,
        "--set-metadata",
        f"dstack.approved_design_sha256={digest}",
    )

    specification = claim_issue_if_needed(client, view["steps"]["specification"])
    if args.summary_file:
        client.add_comment(str(specification["id"]), read_text_file(args.summary_file))
    client.close(str(specification["id"]), "Specification approved")

    gate = view.get("human_gate")
    if not isinstance(gate, dict):
        raise DstackError("feature has no unique human approval gate")
    client.resolve_gate(str(gate["id"]), "Specification approved")

    approval = claim_issue_if_needed(client, client.show(str(view["steps"]["approval"]["id"])))
    client.close(str(approval["id"]), "Implementation authorized")
    emit({"status": "ok", **feature_view(client, root_id)})
    return 0


def require_approved_design(view: Mapping[str, Any]) -> None:
    if not view.get("approved_design_sha256"):
        raise DstackError("feature specification has no approved design digest")
    if not view.get("design_approved"):
        raise DstackError(
            "feature design differs from the approved specification; rerun /review-feature-spec"
        )


def cmd_feature_claim_next(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    require_approved_design(view)
    implementation_id = str(view["steps"]["implementation"]["id"])
    if args.task:
        item = client.show(args.task)
        if issue_parent(item) != implementation_id:
            raise DstackError(f"task {args.task} is not a child of {implementation_id}")
        if item.get("status") == "open":
            ready_ids = {
                str(candidate["id"])
                for candidate in client.ready_children(
                    implementation_id,
                    label="dstack:work:implementation",
                )
            }
            if args.task not in ready_ids:
                raise DstackError(f"task {args.task} is not currently ready")
        claimed = claim_issue_if_needed(client, item)
        emit({"status": "ok", "task": claimed, "feature": view["root"]["id"]})
        return 0

    claimed = client.ready_children(
        implementation_id,
        label="dstack:work:implementation",
        claim=True,
    )
    emit({"status": "ok", "task": claimed[0] if claimed else None, "feature": view["root"]["id"]})
    return 0


def feature_branch_context(client: BeadsClient, view: Mapping[str, Any]) -> tuple[str, Path, str]:
    slug = str(view.get("slug") or "")
    base = str(view.get("base_branch") or "")
    if not slug or not base:
        raise DstackError("feature root lacks slug or base branch")
    branch = f"feat/{slug}"
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        raise DstackError(f"no worktree is registered for {branch}")
    return branch, worktree, base


def evidence_for_bead(root: Path, bead_id: str, ref_range: str) -> list[dict[str, Any]]:
    return commit_footer_ids(root, ref_range).get(bead_id, [])


def cmd_feature_finish_task(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    implementation_id = str(view["steps"]["implementation"]["id"])
    task = client.show(args.task)
    if issue_parent(task) != implementation_id:
        raise DstackError(f"task {args.task} is not in feature implementation {implementation_id}")

    branch, worktree, base = feature_branch_context(client, view)
    evidence = evidence_for_bead(worktree, args.task, f"{base}..{branch}")
    if not evidence and not args.allow_no_commit:
        raise DstackError(
            f"no reachable commit on {branch} has footer 'Beads: {args.task}'"
        )
    summary = read_text_file(args.summary_file)
    if summary:
        client.add_comment(args.task, summary)
    client.close(args.task, args.reason)
    cmd_feature_finish_workstream(
        argparse.Namespace(root=client.root, selector=str(view["root"]["id"]), quiet=True)
    )
    updated = feature_view(client, str(view["root"]["id"]))
    emit({"status": "ok", "task": client.show(args.task), "evidence": evidence, **updated})
    return 0


def cmd_feature_finish_workstream(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    implementation = client.show(str(view["steps"]["implementation"]["id"]))
    children = [
        item
        for item in client.children(str(implementation["id"]))
        if has_label(item, "dstack:work:implementation")
    ]
    open_items = [item for item in children if item.get("status") != "closed"]
    closed = False
    if not open_items and implementation.get("status") != "closed":
        client.close(str(implementation["id"]), "All implementation work completed")
        closed = True
    payload = {
        "status": "ok",
        "workstream": client.show(str(implementation["id"])),
        "open_items": [item["id"] for item in open_items],
        "closed_now": closed,
        "closeout": client.show(str(view["steps"]["closeout"]["id"])),
    }
    if not getattr(args, "quiet", False):
        emit(payload)
    return 0


def cmd_feature_claim_closeout(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    closeout = client.show(str(view["steps"]["closeout"]["id"]))
    if closeout.get("status") == "closed":
        emit({"status": "ok", "closeout": closeout, "already_closed": True})
        return 0
    if blocker_ids(closeout):
        open_blockers = [
            blocker
            for blocker in blocker_ids(closeout)
            if client.show(blocker).get("status") != "closed"
        ]
        if open_blockers:
            raise DstackError(
                "closeout remains blocked by: " + ", ".join(open_blockers)
            )
    claimed = claim_issue_if_needed(client, closeout)
    emit({"status": "ok", "closeout": claimed, "feature": view["root"]["id"]})
    return 0


def cmd_feature_finish_closeout(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    closeout_id = str(view["steps"]["closeout"]["id"])
    closeout = client.show(closeout_id)
    if closeout.get("status") != "closed":
        closeout = claim_issue_if_needed(client, closeout)
        if args.summary_file:
            client.add_comment(closeout_id, read_text_file(args.summary_file))
        client.close(closeout_id, args.reason)
    emit({"status": "ok", **feature_view(client, str(view["root"]["id"]))})
    return 0


def read_commit_message(subject: str, body_file: Path | None, bead: str) -> str:
    subject = subject.strip()
    if not subject or "\n" in subject:
        raise DstackError("commit subject must be one non-empty line")
    body = read_text_file(body_file)
    if re.search(r"(?m)^Beads:\s*", body):
        raise DstackError("commit body must not contain a Beads footer; dstack adds it")
    parts = [subject]
    if body:
        parts.extend(["", body])
    parts.extend(["", f"Beads: {bead}"])
    return "\n".join(parts).rstrip() + "\n"


def staged_paths(root: Path) -> list[str]:
    output = run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD"], cwd=root).stdout
    return [line for line in output.splitlines() if line]


def reject_runtime_beads(paths: Sequence[str]) -> None:
    invalid = [
        path
        for path in paths
        if any(path == prefix or path.startswith(prefix) for prefix in RUNTIME_BEADS_PREFIXES)
        or (path.startswith(".beads/") and not path.startswith(".beads/formulas/"))
    ]
    if invalid:
        raise DstackError("workflow commits may not include Beads runtime state: " + ", ".join(invalid))


def commit_with_message(root: Path, message: str, *, amend: bool) -> str:
    paths = staged_paths(root)
    if not paths and not amend:
        raise DstackError("no staged repository changes to commit")
    reject_runtime_beads(paths)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
        handle.write(message)
        message_path = Path(handle.name)
    try:
        command = ["git", "commit", "-F", str(message_path)]
        if amend:
            command.insert(2, "--amend")
        run(command, cwd=root)
    finally:
        message_path.unlink(missing_ok=True)
    return current_head(root)


def cmd_git_commit(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    commit = commit_with_message(
        root,
        read_commit_message(args.subject, args.body_file, args.bead),
        amend=False,
    )
    emit({"status": "ok", "commit": commit, "bead": args.bead})
    return 0


def cmd_git_amend(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    head_message = run(["git", "log", "-1", "--format=%B"], cwd=root).stdout
    if not re.search(rf"(?m)^Beads:\s*{re.escape(args.bead)}\s*$", head_message):
        raise DstackError(f"HEAD is not associated with Bead {args.bead}")
    commit = commit_with_message(
        root,
        read_commit_message(args.subject, args.body_file, args.bead),
        amend=True,
    )
    emit({"status": "ok", "commit": commit, "bead": args.bead})
    return 0


def cmd_evidence_commits(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    mapping = commit_footer_ids(root, args.ref)
    emit({"status": "ok", "bead": args.bead, "commits": mapping.get(args.bead, [])})
    return 0


def cmd_evidence_audit_feature(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_view(client, args.selector)
    branch, worktree, base = feature_branch_context(client, view)
    mapping = commit_footer_ids(worktree, f"{base}..{branch}")
    tasks = [
        item
        for item in view["work_items"]
        if item.get("status") == "closed"
    ]
    expected = {str(item["id"]) for item in tasks}
    missing = sorted(item for item in expected if not mapping.get(item))
    duplicate = {key: value for key, value in mapping.items() if key in expected and len(value) > 1}
    orphaned: list[str] = []
    for bead_id in mapping:
        if bead_id in expected or bead_id in {
            str(view["steps"]["specification"]["id"]),
            str(view["steps"]["closeout"]["id"]),
        }:
            continue
        if client.show_optional(bead_id) is None:
            orphaned.append(bead_id)
    emit(
        {
            "status": "ok" if not missing and not orphaned else "issues",
            "feature": view["root"]["id"],
            "range": f"{base}..{branch}",
            "missing": missing,
            "multiple_commits": duplicate,
            "orphaned_footer_ids": sorted(orphaned),
            "mapping": {key: value for key, value in mapping.items() if key in expected},
        }
    )
    return 0 if not missing and not orphaned else 3


def diff_paths(root: Path, base: str, head: str) -> list[str]:
    output = run(["git", "diff", "--name-only", f"{base}...{head}"], cwd=root).stdout
    return [line for line in output.splitlines() if line]


def docs_check(root: Path, base: str, head: str) -> dict[str, Any]:
    paths = diff_paths(root, base, head)
    doc_paths = [path for path in paths if path.startswith("docs/") or path.endswith(".md")]
    violations: list[dict[str, str]] = []
    status_lines: list[str] = []
    non_status_added: list[str] = []

    if doc_paths:
        diff = run(
            ["git", "diff", "--unified=0", f"{base}...{head}", "--", *doc_paths],
            cwd=root,
        ).stdout
        current_path = ""
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                current_path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            content = line[1:]
            if DURABLE_STATUS_PATTERN.match(content):
                status_lines.append(content.strip())
            elif content.strip():
                non_status_added.append(content.strip())
            for pattern in FORBIDDEN_DOC_PATTERNS:
                if pattern.search(content):
                    violations.append({"path": current_path, "line": content.strip()})
                    break

    status_only = (
        bool(status_lines)
        and not non_status_added
        and len(paths) == len(doc_paths)
        and all(path.endswith("planned-features.md") for path in doc_paths)
    )
    if status_only:
        violations.append(
            {
                "path": ", ".join(doc_paths),
                "line": (
                    "status-only documentation change; fold durable product "
                    "documentation into the feature candidate"
                ),
            }
        )

    return {
        "status": "ok" if not violations else "violations",
        "paths": paths,
        "documentation_paths": doc_paths,
        "violations": violations,
        "status_only": status_only,
    }


def cmd_docs_check(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    payload = docs_check(root, args.base, args.head)
    emit(payload)
    return 0 if payload["status"] == "ok" else 4


def tracked_runtime_beads(root: Path) -> list[str]:
    output = run(["git", "ls-files", ".beads"], cwd=root).stdout.splitlines()
    return [
        path
        for path in output
        if any(path == prefix or path.startswith(prefix) for prefix in RUNTIME_BEADS_PREFIXES)
        or (path.startswith(".beads/") and not path.startswith(".beads/formulas/"))
    ]


def delivery_view(client: BeadsClient, selector: str) -> dict[str, Any]:
    exact = client.show_optional(selector)
    if exact is not None and has_label(exact, "workflow:project-alignment"):
        view = alignment_view(client, str(exact["id"]))
        kind = "alignment"
    elif exact is not None and has_label(exact, "workflow:feature"):
        view = feature_view(client, str(exact["id"]))
        kind = "feature"
    else:
        feature_error: DstackError | None = None
        try:
            view = feature_view(client, selector)
            kind = "feature"
        except DstackError as exc:
            feature_error = exc
            try:
                view = alignment_view(client, selector)
                kind = "alignment"
            except DstackError as alignment_error:
                raise DstackError(
                    f"selector is neither a feature nor a project alignment: {selector}; "
                    f"feature lookup: {feature_error}; alignment lookup: {alignment_error}"
                ) from alignment_error

    root = view["root"]
    if kind == "alignment":
        terminal = view["steps"]["landing"]
        slug = str(view["slug"])
        target = str(view["target_branch"])
        branch = f"audit/{slug}"
    else:
        terminal = view["steps"]["closeout"]
        slug = str(view["slug"])
        target = str(view["base_branch"])
        branch = f"feat/{slug}"

    if terminal.get("status") != "closed":
        raise DstackError(f"{kind} terminal step is not closed")
    candidate_worktree = worktree_for_branch(client.root, branch)
    if candidate_worktree is None:
        raise DstackError(f"no worktree found for {branch}")
    target_worktree = worktree_for_branch(client.root, target) or client.root
    candidate = current_head(candidate_worktree)
    target_head = current_head(target_worktree)
    remote_ref = f"origin/{target}"
    remote_head = (
        current_head(client.root, remote_ref)
        if ref_exists(client.root, remote_ref)
        else None
    )
    remote_candidate_ref = f"origin/{branch}"
    remote_candidate_head = (
        current_head(client.root, remote_candidate_ref)
        if ref_exists(client.root, remote_candidate_ref)
        else None
    )
    merges = run(
        ["git", "rev-list", "--merges", f"{target}..{branch}"], cwd=client.root
    ).stdout.splitlines()
    commits = run(
        [
            "git",
            "log",
            "--reverse",
            "--no-merges",
            "--format=%H%x09%s",
            f"{target}..{branch}",
        ],
        cwd=client.root,
    ).stdout.splitlines()
    paths = diff_paths(client.root, target, branch)
    stats = run(
        ["git", "diff", "--stat", f"{target}...{branch}"], cwd=client.root
    ).stdout
    return {
        "kind": kind,
        "root": root,
        "slug": slug,
        "target_branch": target,
        "candidate_branch": branch,
        "target_worktree": str(target_worktree),
        "candidate_worktree": str(candidate_worktree),
        "target_head": target_head,
        "remote_target_head": remote_head,
        "remote_candidate_head": remote_candidate_head,
        "candidate_head": candidate,
        "target_is_ancestor": ancestry(client.root, target, branch),
        "remote_matches_local": remote_head is None or remote_head == target_head,
        "merge_commits": merges,
        "commits": commits,
        "paths": paths,
        "tracked_runtime_beads": tracked_runtime_beads(client.root),
        "diff_stat": stats,
        "docs": docs_check(client.root, target, branch),
    }


def cmd_delivery_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    if args.fetch:
        remote = run(["git", "remote", "get-url", "origin"], cwd=client.root, check=False)
        if remote.returncode == 0:
            run(["git", "fetch", "origin", "--prune"], cwd=client.root)
    emit({"status": "ok", **delivery_view(client, args.selector)})
    return 0


def validate_delivery(payload: Mapping[str, Any], *, require_remote: bool) -> None:
    if require_remote:
        if payload.get("remote_target_head") is None:
            raise DstackError("origin target branch is unavailable")
        if not payload.get("remote_matches_local"):
            raise DstackError(
                "local target and origin target differ; synchronize the target "
                "before creating a PR"
            )
    if payload.get("tracked_runtime_beads"):
        raise DstackError(
            "tracked Beads runtime state prevents safe delivery: "
            + ", ".join(str(item) for item in payload["tracked_runtime_beads"])
            + "; run /setup-project --force"
        )
    feature_paths = [
        str(path)
        for path in payload.get("paths", [])
        if str(path).startswith(".beads/")
        and not str(path).startswith(".beads/formulas/")
    ]
    if feature_paths:
        raise DstackError(
            "candidate includes Beads runtime state: " + ", ".join(feature_paths)
        )
    if not payload.get("target_is_ancestor"):
        raise DstackError(
            "candidate does not contain the target branch; rebase/cherry-pick "
            "instead of merging target into it"
        )
    if payload.get("merge_commits"):
        raise DstackError(
            "candidate contains merge commits; dStack delivery requires a "
            "linear feature history"
        )
    if payload.get("docs", {}).get("status") != "ok":
        raise DstackError("documentation policy check failed")


def validate_pr_copy(
    payload: Mapping[str, Any],
    *,
    title: str | None,
    body_file: Path | None,
) -> dict[str, Any] | None:
    if title is None and body_file is None:
        return None
    if not title or body_file is None:
        raise DstackError("PR copy validation requires both --title and --body-file")
    normalized_title = title.strip()
    body = read_text_file(body_file)
    if not normalized_title or "\n" in normalized_title:
        raise DstackError("PR title must be one non-empty line")
    if not body:
        raise DstackError("PR body must not be empty")
    non_docs = [
        str(path)
        for path in payload.get("paths", [])
        if not str(path).startswith("docs/")
        and not str(path).casefold().endswith((".md", ".mdx", ".rst"))
    ]
    if non_docs and re.match(r"(?i)^docs(?:\([^)]*\))?:", normalized_title):
        raise DstackError(
            "PR title is docs-only but the candidate contains code, tests, or "
            "configuration; summarize the complete feature"
        )
    return {
        "title": normalized_title,
        "body": body,
        "non_documentation_paths": non_docs,
    }


def cmd_delivery_pr_preflight(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    run(["git", "fetch", "origin", "--prune"], cwd=client.root)
    payload = delivery_view(client, args.selector)
    validate_delivery(payload, require_remote=True)
    pr_copy = validate_pr_copy(
        payload,
        title=args.title,
        body_file=args.body_file,
    )
    emit({"status": "ok", "pr_copy": pr_copy, **payload})
    return 0


def existing_pr_gate(client: BeadsClient, root_id: str, pr_number: str | None = None) -> dict[str, Any] | None:
    root_blockers = set(blocker_ids(client.show(root_id)))
    candidates = [
        gate
        for gate in client.gates(all_statuses=True)
        if str(gate.get("id")) in root_blockers
        or str(gate.get("waiter_id") or "") == root_id
        or issue_parent(gate) == root_id
    ]
    candidates = [
        gate
        for gate in candidates
        if str(gate.get("await_type") or gate.get("gate_type") or "") == "gh:pr"
    ]
    if pr_number:
        candidates = [gate for gate in candidates if str(gate.get("await_id") or "") == pr_number]
    return candidates[0] if len(candidates) == 1 else None


def cmd_delivery_register_pr(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    run(["git", "fetch", "origin", "--prune"], cwd=client.root)
    payload = delivery_view(client, args.selector)
    validate_delivery(payload, require_remote=True)
    if payload.get("remote_candidate_head") != payload.get("candidate_head"):
        raise DstackError(
            "origin candidate branch does not match the inspected candidate; "
            "push the exact branch before registering the PR"
        )
    root_id = str(payload["root"]["id"])
    gate = existing_pr_gate(client, root_id, str(args.pr_number))
    if gate is None:
        gate = client.create_gate(
            gate_type="gh:pr",
            blocks=root_id,
            await_id=str(args.pr_number),
            reason="Await merged pull request",
        )
    emit({"status": "ok", "root": root_id, "gate": gate, "pr_number": args.pr_number})
    return 0


def cmd_delivery_merge(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    payload = delivery_view(client, args.selector)
    validate_delivery(payload, require_remote=False)
    target_worktree = Path(str(payload["target_worktree"]))
    candidate_worktree = Path(str(payload["candidate_worktree"]))
    ensure_clean_tracked(target_worktree)
    ensure_clean_tracked(candidate_worktree)
    before_head = current_head(target_worktree)
    before_status = run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=target_worktree
    ).stdout
    run(
        ["git", "merge", "--ff-only", str(payload["candidate_branch"])],
        cwd=target_worktree,
    )
    merged_head = current_head(target_worktree)
    if merged_head != payload["candidate_head"]:
        raise DstackError("fast-forward completed at an unexpected target commit")
    root_id = str(payload["root"]["id"])
    client.close(root_id, "Delivered by fast-forward merge")
    after_head = current_head(target_worktree)
    after_status = run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=target_worktree
    ).stdout
    if after_head != merged_head or after_status != before_status:
        raise DstackError("Beads finalization changed tracked Git state after delivery")
    emit(
        {
            "status": "ok",
            "root": root_id,
            "previous_target_head": before_head,
            "delivered_head": after_head,
        }
    )
    return 0


def cmd_delivery_finalize_pr(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    payload = delivery_view(client, args.selector)
    root_id = str(payload["root"]["id"])
    client.gate_check()
    gate = existing_pr_gate(client, root_id)
    if gate is None:
        raise DstackError("no unique gh:pr gate is associated with this root")
    gate = client.show(str(gate["id"]))
    if gate.get("status") != "closed":
        emit({"status": "waiting", "root": root_id, "gate": gate})
        return 2
    run(["git", "fetch", "origin", "--prune"], cwd=client.root)
    remote_target = f"origin/{payload['target_branch']}"
    if not ancestry(client.root, str(payload["candidate_head"]), remote_target):
        raise DstackError("PR gate closed but origin target does not contain the candidate commit")
    target_ref = str(payload["target_branch"])
    target_worktree = worktree_for_branch(client.root, target_ref) or client.root
    before_head = current_head(target_worktree)
    before_status = run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=target_worktree
    ).stdout
    client.close(root_id, "Delivered through merged pull request")
    after_head = current_head(target_worktree)
    after_status = run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=target_worktree
    ).stdout
    if before_head != after_head or before_status != after_status:
        raise DstackError("Beads finalization changed tracked Git state after PR delivery")
    emit({"status": "ok", "root": client.show(root_id), "gate": gate})
    return 0


def cmd_alignment_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    emit({"status": "ok", **alignment_view(client, args.selector)})
    return 0


def cmd_alignment_initialize(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    slug = args.slug or slugify(args.title)
    try:
        existing = alignment_view(client, slug)
    except DstackError as exc:
        if "resolved to 0 roots" not in str(exc):
            raise
    else:
        if existing["root"].get("status") != "closed":
            branch = f"audit/{slug}"
            worktree = worktree_for_branch(client.root, branch)
            if worktree is None:
                target_branch = str(existing.get("target_branch") or args.target_branch)
                if not branch_exists(client.root, branch):
                    run(["git", "branch", branch, target_branch], cwd=client.root)
                path = conventional_worktree(client.root, branch)
                run(["bd", "worktree", "create", str(path), "--branch", branch], cwd=client.root)
                worktree = worktree_for_branch(client.root, branch)
            emit({"status": "ok", "created": False, "worktree": str(worktree), **existing})
            return 0
        raise DstackError(f"project alignment is already closed: {existing['root']['id']}")

    require_installed_formula(client.root, "dstack-project-alignment")
    pour = client.pour(
        "dstack-project-alignment",
        {
            "audit_title": args.title,
            "audit_slug": slug,
            "scope": args.scope,
        },
    )
    root_id = str(pour.get("root_id") or pour.get("new_epic_id") or "")
    if not root_id:
        raise DstackError("bd mol pour returned no alignment root")
    client.update(
        root_id,
        "--title",
        f"Project alignment: {args.title}",
        "--add-label",
        "workflow:project-alignment",
        "--add-label",
        f"audit:{slug}",
        "--set-metadata",
        f"dstack.target_branch={args.target_branch}",
        "--set-metadata",
        f"dstack.scope={args.scope}",
    )
    branch = f"audit/{slug}"
    if not branch_exists(client.root, branch):
        run(["git", "branch", branch, args.target_branch], cwd=client.root)
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        path = conventional_worktree(client.root, branch)
        run(["bd", "worktree", "create", str(path), "--branch", branch], cwd=client.root)
        worktree = worktree_for_branch(client.root, branch)
    emit({"status": "ok", "worktree": str(worktree), **alignment_view(client, root_id)})
    return 0


def cmd_alignment_add_correction(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    item = client.create(
        args.title,
        parent=str(view["steps"]["corrections"]["id"]),
        labels=["dstack:work:correction"],
        dependencies=[str(view["steps"]["approval"]["id"]), *args.depends_on],
        description=task_text(args.description_file, args.description),
        acceptance=task_text(args.acceptance_file, args.acceptance),
        priority=args.priority,
    )
    emit({"status": "ok", "correction": item})
    return 0


def cmd_alignment_finish_plan(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    analysis = claim_issue_if_needed(client, view["steps"]["analysis"])
    if args.summary_file:
        client.add_comment(str(analysis["id"]), read_text_file(args.summary_file))
    client.close(str(analysis["id"]), "Corrective plan prepared")
    emit({"status": "ok", **alignment_view(client, str(view["root"]["id"]))})
    return 0


def cmd_alignment_approve(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    gate = view.get("human_gate")
    if not isinstance(gate, dict):
        raise DstackError("alignment workflow has no unique human gate")
    client.resolve_gate(str(gate["id"]), "Corrective plan approved")
    approval = claim_issue_if_needed(client, view["steps"]["approval"])
    client.close(str(approval["id"]), "Corrective execution authorized")
    emit({"status": "ok", **alignment_view(client, str(view["root"]["id"]))})
    return 0


def cmd_alignment_claim_next(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    parent = str(view["steps"]["corrections"]["id"])
    if args.task:
        task = client.show(args.task)
        if issue_parent(task) != parent:
            raise DstackError(f"task {args.task} is not a correction under {parent}")
        if task.get("status") == "open":
            ready_ids = {
                str(candidate["id"])
                for candidate in client.ready_children(
                    parent,
                    label="dstack:work:correction",
                )
            }
            if args.task not in ready_ids:
                raise DstackError(f"correction {args.task} is not currently ready")
        claimed = claim_issue_if_needed(client, task)
    else:
        items = client.ready_children(parent, label="dstack:work:correction", claim=True)
        claimed = items[0] if items else None
    emit({"status": "ok", "correction": claimed, "audit": view["root"]["id"]})
    return 0


def cmd_alignment_finish_task(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    parent = str(view["steps"]["corrections"]["id"])
    task = client.show(args.task)
    if issue_parent(task) != parent:
        raise DstackError(f"task {args.task} is not a correction under {parent}")
    slug = str(view["slug"])
    branch = f"audit/{slug}"
    base = str(view["target_branch"])
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        raise DstackError(f"no worktree for {branch}")
    evidence = evidence_for_bead(worktree, args.task, f"{base}..{branch}")
    if not evidence and not args.allow_no_commit:
        raise DstackError(f"no commit on {branch} references Bead {args.task}")
    if args.summary_file:
        client.add_comment(args.task, read_text_file(args.summary_file))
    client.close(args.task, args.reason)
    cmd_alignment_finish_workstream(
        argparse.Namespace(root=client.root, selector=str(view["root"]["id"]), quiet=True)
    )
    emit({"status": "ok", "correction": client.show(args.task), "evidence": evidence})
    return 0


def cmd_alignment_finish_workstream(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    workstream = client.show(str(view["steps"]["corrections"]["id"]))
    items = [item for item in client.children(str(workstream["id"])) if has_label(item, "dstack:work:correction")]
    open_items = [item for item in items if item.get("status") != "closed"]
    if not open_items and workstream.get("status") != "closed":
        client.close(str(workstream["id"]), "All corrections completed")
    payload = {
        "status": "ok",
        "open_items": [item["id"] for item in open_items],
        "workstream": client.show(str(workstream["id"])),
    }
    if not getattr(args, "quiet", False):
        emit(payload)
    return 0


def cmd_alignment_claim_landing(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    landing = client.show(str(view["steps"]["landing"]["id"]))
    if landing.get("status") == "closed":
        emit({"status": "ok", "landing": landing, "already_closed": True})
        return 0
    open_blockers = [
        blocker
        for blocker in blocker_ids(landing)
        if client.show(blocker).get("status") != "closed"
    ]
    if open_blockers:
        raise DstackError(
            "alignment landing remains blocked by: " + ", ".join(open_blockers)
        )
    claimed = claim_issue_if_needed(client, landing)
    emit({"status": "ok", "landing": claimed, "audit": view["root"]["id"]})
    return 0


def cmd_alignment_finish_landing(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    landing_id = str(view["steps"]["landing"]["id"])
    landing = client.show(landing_id)
    if landing.get("status") != "closed":
        landing = claim_issue_if_needed(client, landing)
        if args.summary_file:
            client.add_comment(landing_id, read_text_file(args.summary_file))
        client.close(landing_id, args.reason)
    emit({"status": "ok", **alignment_view(client, str(view["root"]["id"]))})
    return 0


def classify_legacy_item(item: Mapping[str, Any]) -> str:
    title = str(item.get("title", "")).casefold()
    labels = set(issue_labels(item))
    metadata = issue_metadata(item)
    phase = str(metadata.get("workflow_phase") or "").casefold()
    if "phase:implementation" in labels or phase == "implementation" or " t00" in title:
        return "implementation"
    if title.startswith("implement:"):
        return "implementation-coordinator"
    if any(label.startswith("review:") for label in labels) or title.startswith("review "):
        return "spec-ceremony" if phase in {"spec-review", "specification"} else "closeout-ceremony"
    if any(word in title for word in ("validate:", "deliver:", "reconcile documentation", "documentation drift")):
        return "closeout-ceremony"
    if "reconcile specification" in title:
        return "spec-ceremony"
    return "ambiguous"


def descendants(client: BeadsClient, root_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    queue = [root_id]
    seen = {root_id}
    while queue:
        parent = queue.pop(0)
        for child in client.children(parent):
            child_id = str(child["id"])
            if child_id in seen:
                continue
            seen.add(child_id)
            result.append(child)
            queue.append(child_id)
    return result


def cmd_adopt_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root = resolve_feature(client, args.selector)
    if root.get("status") == "closed":
        raise DstackError(f"legacy feature is already closed: {root['id']}")
    if feature_view(client, str(root["id"]))["current"]:
        raise DstackError(f"feature already uses current dstack workflow: {root['id']}")
    items = [item for item in descendants(client, str(root["id"])) if item.get("status") != "closed"]
    classified: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        classified.setdefault(classify_legacy_item(item), []).append(item)
    emit({"status": "ok", "legacy_root": root, "classified": classified})
    return 0


def superseded_target(issue: Mapping[str, Any]) -> str | None:
    for record in dependency_records(issue):
        relation = str(record.get("type") or record.get("dependency_type") or "")
        if relation not in {"superseded-by", "superseded_by", "supersedes"}:
            continue
        target = record.get("depends_on_id") or record.get("id")
        if isinstance(target, str) and target != issue.get("id"):
            return target
    return None


def current_feature_for_slug(
    client: BeadsClient,
    slug: str,
    *,
    exclude_id: str,
) -> dict[str, Any] | None:
    matches = [
        root
        for root in client.list(all_statuses=True, labels=["workflow:feature"])
        if str(root.get("id")) != exclude_id
        and root.get("status") != "closed"
        and feature_slug(root) == slug
        and feature_view(client, str(root["id"]))["current"]
    ]
    if len(matches) > 1:
        raise DstackError(
            "multiple current feature roots already exist for slug "
            f"{slug}: " + ", ".join(str(item["id"]) for item in matches)
        )
    return matches[0] if matches else None


def cmd_adopt_apply(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    legacy = resolve_feature(client, args.selector)
    existing_replacement = superseded_target(legacy)
    if legacy.get("status") == "closed":
        if existing_replacement:
            emit(
                {
                    "status": "ok",
                    "already_adopted": True,
                    "legacy_root": legacy["id"],
                    "new_root": existing_replacement,
                    **feature_view(client, existing_replacement),
                }
            )
            return 0
        raise DstackError("legacy feature is already closed")
    if feature_view(client, str(legacy["id"]))["current"]:
        raise DstackError("feature already uses current dStack workflow")

    title = args.title or display_title(str(legacy.get("title", "")))
    slug = args.slug or feature_slug(legacy) or slugify(title)
    base = args.base_branch or root_metadata_value(legacy, "base_branch") or "main"
    design = (
        args.design_path
        or root_metadata_value(legacy, "design_path")
        or f"docs/src/features/{slug}/design.md"
    )

    current = current_feature_for_slug(
        client, slug, exclude_id=str(legacy["id"])
    )
    if current is None:
        require_installed_formula(client.root, "dstack-feature")
        pour = client.pour(
            "dstack-feature",
            {
                "feature_title": title,
                "feature_slug": slug,
                "design_path": design,
            },
        )
        root_id = str(pour.get("root_id") or pour.get("new_epic_id") or "")
        if not root_id:
            raise DstackError("bd mol pour returned no feature root")
        update_root_identity(
            client,
            root_id,
            title=title,
            slug=slug,
            base_branch=base,
            design_path=design,
        )
    else:
        root_id = str(current["id"])
    view = feature_view(client, root_id)

    mapping: dict[str, str] = {}
    for old_id in args.remaining:
        old = client.show(old_id)
        target = superseded_target(old)
        if target:
            mapping[old_id] = target
            continue
        replacement = client.create(
            str(old.get("title", old_id)),
            parent=str(view["steps"]["implementation"]["id"]),
            labels=["dstack:work:implementation"],
            dependencies=[str(view["steps"]["approval"]["id"])],
            description=str(old.get("description") or ""),
            acceptance=str(
                old.get("acceptance_criteria") or old.get("acceptance") or ""
            ),
            priority=int(old.get("priority") or 2),
        )
        mapping[old_id] = str(replacement["id"])
        client.supersede(old_id, str(replacement["id"]))

    categories = (
        (args.spec_ceremony, str(view["steps"]["specification"]["id"])),
        (args.implementation_coordinator, str(view["steps"]["implementation"]["id"])),
        (args.closeout_ceremony, str(view["steps"]["closeout"]["id"])),
    )
    for old_ids, target in categories:
        for old_id in old_ids:
            mapping[old_id] = target
            client.supersede(old_id, target)

    if args.spec_note_file:
        client.add_comment(
            str(view["steps"]["specification"]["id"]),
            read_text_file(args.spec_note_file),
        )
    if args.closeout_note_file:
        client.add_comment(
            str(view["steps"]["closeout"]["id"]),
            read_text_file(args.closeout_note_file),
        )

    legacy_ids = {str(legacy["id"]), *[str(item["id"]) for item in descendants(client, str(legacy["id"]))]}
    preserved_blockers: list[str] = []
    for record in dependency_records(legacy):
        relation = str(record.get("type") or record.get("dependency_type") or "blocks")
        target = record.get("depends_on_id") or record.get("id")
        if relation != "blocks" or not isinstance(target, str) or target in legacy_ids:
            continue
        blocker = client.show_optional(target)
        if blocker is None or blocker.get("status") == "closed":
            continue
        client.add_dependency(root_id, target)
        preserved_blockers.append(target)

    client.supersede(str(legacy["id"]), root_id)
    emit(
        {
            "status": "ok",
            "legacy_root": legacy["id"],
            "new_root": root_id,
            "mapping": mapping,
            "external_blockers_preserved": preserved_blockers,
            **feature_view(client, root_id),
        }
    )
    return 0


def add_common_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=Path.cwd())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_root(parser)
    top = parser.add_subparsers(dest="area", required=True)

    feature = top.add_parser("feature")
    feature_sub = feature.add_subparsers(dest="command", required=True)
    resolve = feature_sub.add_parser("resolve")
    resolve.add_argument("selector", nargs="?")
    resolve.set_defaults(func=cmd_feature_resolve)
    inspect = feature_sub.add_parser("inspect")
    inspect.add_argument("selector", nargs="?")
    inspect.set_defaults(func=cmd_feature_inspect)
    initialize = feature_sub.add_parser("initialize")
    initialize.add_argument("selector", nargs="?")
    initialize.add_argument("--title")
    initialize.add_argument("--slug")
    initialize.add_argument("--base-branch", default="main")
    initialize.add_argument("--design-path")
    initialize.set_defaults(func=cmd_feature_initialize)
    add_task = feature_sub.add_parser("add-task")
    add_task.add_argument("selector")
    add_task.add_argument("--title", required=True)
    add_task.add_argument("--description")
    add_task.add_argument("--description-file", type=Path)
    add_task.add_argument("--acceptance")
    add_task.add_argument("--acceptance-file", type=Path)
    add_task.add_argument("--priority", type=int, default=2)
    add_task.add_argument("--depends-on", action="append", default=[])
    add_task.set_defaults(func=cmd_feature_add_task)
    claim_spec = feature_sub.add_parser("claim-spec")
    claim_spec.add_argument("selector", nargs="?")
    claim_spec.set_defaults(func=cmd_feature_claim_spec)
    approve = feature_sub.add_parser("approve-spec")
    approve.add_argument("selector", nargs="?")
    approve.add_argument("--summary-file", type=Path)
    approve.set_defaults(func=cmd_feature_approve_spec)
    claim = feature_sub.add_parser("claim-next")
    claim.add_argument("selector", nargs="?")
    claim.add_argument("--task")
    claim.set_defaults(func=cmd_feature_claim_next)
    finish = feature_sub.add_parser("finish-task")
    finish.add_argument("selector")
    finish.add_argument("--task", required=True)
    finish.add_argument("--reason", default="Implementation completed")
    finish.add_argument("--summary-file", type=Path)
    finish.add_argument("--allow-no-commit", action="store_true")
    finish.set_defaults(func=cmd_feature_finish_task)
    finish_workstream = feature_sub.add_parser("finish-workstream")
    finish_workstream.add_argument("selector")
    finish_workstream.set_defaults(func=cmd_feature_finish_workstream)
    claim_closeout = feature_sub.add_parser("claim-closeout")
    claim_closeout.add_argument("selector", nargs="?")
    claim_closeout.set_defaults(func=cmd_feature_claim_closeout)
    finish_closeout = feature_sub.add_parser("finish-closeout")
    finish_closeout.add_argument("selector", nargs="?")
    finish_closeout.add_argument("--reason", default="Closeout completed")
    finish_closeout.add_argument("--summary-file", type=Path)
    finish_closeout.set_defaults(func=cmd_feature_finish_closeout)

    alignment = top.add_parser("alignment")
    alignment_sub = alignment.add_subparsers(dest="command", required=True)
    alignment_inspect = alignment_sub.add_parser("inspect")
    alignment_inspect.add_argument("selector")
    alignment_inspect.set_defaults(func=cmd_alignment_inspect)
    alignment_init = alignment_sub.add_parser("initialize")
    alignment_init.add_argument("--title", required=True)
    alignment_init.add_argument("--slug")
    alignment_init.add_argument("--target-branch", default="main")
    alignment_init.add_argument("--scope", default="whole repository")
    alignment_init.set_defaults(func=cmd_alignment_initialize)
    correction = alignment_sub.add_parser("add-correction")
    correction.add_argument("selector")
    correction.add_argument("--title", required=True)
    correction.add_argument("--description")
    correction.add_argument("--description-file", type=Path)
    correction.add_argument("--acceptance")
    correction.add_argument("--acceptance-file", type=Path)
    correction.add_argument("--priority", type=int, default=2)
    correction.add_argument("--depends-on", action="append", default=[])
    correction.set_defaults(func=cmd_alignment_add_correction)
    finish_plan = alignment_sub.add_parser("finish-plan")
    finish_plan.add_argument("selector")
    finish_plan.add_argument("--summary-file", type=Path)
    finish_plan.set_defaults(func=cmd_alignment_finish_plan)
    alignment_approve = alignment_sub.add_parser("approve")
    alignment_approve.add_argument("selector")
    alignment_approve.set_defaults(func=cmd_alignment_approve)
    alignment_claim = alignment_sub.add_parser("claim-next")
    alignment_claim.add_argument("selector")
    alignment_claim.add_argument("--task")
    alignment_claim.set_defaults(func=cmd_alignment_claim_next)
    alignment_finish = alignment_sub.add_parser("finish-task")
    alignment_finish.add_argument("selector")
    alignment_finish.add_argument("--task", required=True)
    alignment_finish.add_argument("--reason", default="Correction completed")
    alignment_finish.add_argument("--summary-file", type=Path)
    alignment_finish.add_argument("--allow-no-commit", action="store_true")
    alignment_finish.set_defaults(func=cmd_alignment_finish_task)
    alignment_workstream = alignment_sub.add_parser("finish-workstream")
    alignment_workstream.add_argument("selector")
    alignment_workstream.set_defaults(func=cmd_alignment_finish_workstream)
    claim_landing = alignment_sub.add_parser("claim-landing")
    claim_landing.add_argument("selector")
    claim_landing.set_defaults(func=cmd_alignment_claim_landing)
    finish_landing = alignment_sub.add_parser("finish-landing")
    finish_landing.add_argument("selector")
    finish_landing.add_argument("--reason", default="Alignment landing completed")
    finish_landing.add_argument("--summary-file", type=Path)
    finish_landing.set_defaults(func=cmd_alignment_finish_landing)

    git_parser = top.add_parser("git")
    git_sub = git_parser.add_subparsers(dest="command", required=True)
    for name, handler in (("commit", cmd_git_commit), ("amend", cmd_git_amend)):
        item = git_sub.add_parser(name)
        item.add_argument("--bead", required=True)
        item.add_argument("--subject", required=True)
        item.add_argument("--body-file", type=Path)
        item.set_defaults(func=handler)

    evidence = top.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="command", required=True)
    commits = evidence_sub.add_parser("commits")
    commits.add_argument("--bead", required=True)
    commits.add_argument("--ref", default="HEAD")
    commits.set_defaults(func=cmd_evidence_commits)
    audit = evidence_sub.add_parser("audit-feature")
    audit.add_argument("selector")
    audit.set_defaults(func=cmd_evidence_audit_feature)

    docs = top.add_parser("docs")
    docs_sub = docs.add_subparsers(dest="command", required=True)
    docs_check_parser = docs_sub.add_parser("check")
    docs_check_parser.add_argument("--base", required=True)
    docs_check_parser.add_argument("--head", required=True)
    docs_check_parser.set_defaults(func=cmd_docs_check)

    delivery = top.add_parser("delivery")
    delivery_sub = delivery.add_subparsers(dest="command", required=True)
    delivery_inspect = delivery_sub.add_parser("inspect")
    delivery_inspect.add_argument("selector")
    delivery_inspect.add_argument("--fetch", action="store_true")
    delivery_inspect.set_defaults(func=cmd_delivery_inspect)
    preflight = delivery_sub.add_parser("pr-preflight")
    preflight.add_argument("selector")
    preflight.add_argument("--title")
    preflight.add_argument("--body-file", type=Path)
    preflight.set_defaults(func=cmd_delivery_pr_preflight)
    register = delivery_sub.add_parser("register-pr")
    register.add_argument("selector")
    register.add_argument("--pr-number", type=int, required=True)
    register.set_defaults(func=cmd_delivery_register_pr)
    merge = delivery_sub.add_parser("merge")
    merge.add_argument("selector")
    merge.set_defaults(func=cmd_delivery_merge)
    finalize = delivery_sub.add_parser("finalize-pr")
    finalize.add_argument("selector")
    finalize.set_defaults(func=cmd_delivery_finalize_pr)

    adopt = top.add_parser("adopt")
    adopt_sub = adopt.add_subparsers(dest="command", required=True)
    adopt_inspect = adopt_sub.add_parser("inspect")
    adopt_inspect.add_argument("selector")
    adopt_inspect.set_defaults(func=cmd_adopt_inspect)
    adopt_apply = adopt_sub.add_parser("apply")
    adopt_apply.add_argument("selector")
    adopt_apply.add_argument("--title")
    adopt_apply.add_argument("--slug")
    adopt_apply.add_argument("--base-branch")
    adopt_apply.add_argument("--design-path")
    adopt_apply.add_argument("--remaining", action="append", default=[])
    adopt_apply.add_argument("--spec-ceremony", action="append", default=[])
    adopt_apply.add_argument("--implementation-coordinator", action="append", default=[])
    adopt_apply.add_argument("--closeout-ceremony", action="append", default=[])
    adopt_apply.add_argument("--spec-note-file", type=Path)
    adopt_apply.add_argument("--closeout-note-file", type=Path)
    adopt_apply.set_defaults(func=cmd_adopt_apply)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DstackError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
