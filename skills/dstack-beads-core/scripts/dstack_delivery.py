#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fnmatch
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from dstacklib import (
    BeadsClient,
    DstackError,
    alignment_context,
    ancestry,
    blocker_ids,
    commit_footer_ids,
    current_head,
    dependency_records,
    ensure_clean_worktree,
    feature_authorization_state,
    branch_exists,
    feature_context,
    feature_design_state,
    git_root,
    has_label,
    issue_parent,
    issue_type,
    read_text_file,
    ref_exists,
    run,
    validate_git_branch,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
    worktree_records,
)

from dstack_alignment_plan import canonical_description
from dstack_docs import validate_docs
from dstack_commands import (
    BEADS_RUNTIME_DIR_PREFIXES,
    BEADS_RUNTIME_TOP_LEVEL_PATTERNS,
    BEADS_SENSITIVE_BASENAMES,
    DSTACK_UNTRACKED_BEADS_FILES,
    FORBIDDEN_DOC_PATTERNS,
    NO_REPOSITORY_CHANGE_PREFIX,
    client_for,
    emit,
    feature_branch_context,
    require_approved_design,
    require_complete_fan_in,
    superseded_target,
)


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


def is_forbidden_tracked_beads_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in DSTACK_UNTRACKED_BEADS_FILES:
        return True
    if not normalized.startswith(".beads/"):
        return False
    if any(normalized.startswith(prefix) for prefix in BEADS_RUNTIME_DIR_PREFIXES):
        return True
    relative = normalized[len(".beads/") :]
    if ".corrupt.backup/" in relative:
        return True
    if relative.rsplit("/", 1)[-1] in BEADS_SENSITIVE_BASENAMES:
        return True
    if "/" in relative:
        return False
    return any(fnmatch.fnmatch(relative, pattern) for pattern in BEADS_RUNTIME_TOP_LEVEL_PATTERNS)


def reject_runtime_beads(paths: Sequence[str]) -> None:
    # Feature/audit commits may contain dStack formula source but no other
    # .beads content. Repository setup/configuration is committed separately.
    invalid = [
        path
        for path in paths
        if is_forbidden_tracked_beads_path(path)
        or (path.startswith(".beads/") and not path.startswith(".beads/formulas/"))
    ]
    if invalid:
        raise DstackError(
            "workflow commits may not include Beads setup/runtime paths; "
            "commit stable setup configuration separately with native Git: " + ", ".join(invalid)
        )


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


def footer_cardinality(
    mapping: Mapping[str, Sequence[Mapping[str, Any]]],
    expected: set[str],
) -> tuple[dict[str, list[Mapping[str, Any]]], list[str]]:
    multiple: dict[str, list[Mapping[str, Any]]] = {}
    malformed: list[str] = []
    for bead_id in sorted(expected):
        distinct: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        repeated = False
        for record in mapping.get(bead_id, []):
            commit = str(record.get("commit") or "")
            if commit in seen:
                repeated = True
            else:
                seen.add(commit)
                distinct.append(record)
        if repeated:
            malformed.append(bead_id)
        if len(distinct) > 1:
            multiple[bead_id] = distinct
    return multiple, malformed


def evidence_audit(
    client: BeadsClient,
    *,
    worktree: Path,
    base: str,
    branch: str,
    tasks: Sequence[Mapping[str, Any]],
    allowed_ids: Sequence[str],
) -> dict[str, Any]:
    mapping = commit_footer_ids(worktree, f"{base}..{branch}")
    closed = [item for item in tasks if item.get("status") == "closed"]
    no_repository_change = sorted(
        str(item["id"])
        for item in closed
        if str(item.get("close_reason") or "").startswith(NO_REPOSITORY_CHANGE_PREFIX)
    )
    expected = {str(item["id"]) for item in closed if str(item["id"]) not in no_repository_change}
    allowed = expected | {str(item) for item in allowed_ids}
    missing = sorted(item for item in expected if not mapping.get(item))
    multiple, malformed = footer_cardinality(mapping, expected)
    unexpected = sorted(key for key in mapping if key not in allowed)
    orphaned = sorted(bead_id for bead_id in unexpected if client.show_optional(bead_id) is None)
    return {
        "status": "ok" if not missing and not unexpected and not malformed else "issues",
        "range": f"{base}..{branch}",
        "missing": missing,
        "no_repository_change": no_repository_change,
        "multiple_commits": multiple,
        "malformed_footer_ids": malformed,
        "unexpected_footer_ids": unexpected,
        "orphaned_footer_ids": orphaned,
        "mapping": {key: value for key, value in mapping.items() if key in expected},
    }


def feature_delivery_context(client: BeadsClient, selector: str) -> dict[str, Any]:
    view = feature_context(client, selector)
    view.update(feature_design_state(client, view))
    view.update(feature_authorization_state(client, view))
    implementation_id = str(view["steps"]["implementation"]["id"])
    view["work_items"] = [
        item
        for item in client.children(implementation_id)
        if has_label(item, "dstack:work:implementation") or issue_type(item) not in {"epic", "molecule", "gate"}
    ]
    return view


def alignment_delivery_context(client: BeadsClient, selector: str) -> dict[str, Any]:
    view = alignment_context(client, selector)
    plan, _, _ = canonical_description(client.show(str(view["steps"]["analysis"]["id"])))
    view["baseline_commit"] = str(plan["baseline_commit"])
    view["corrections"] = [
        item
        for item in client.children(str(view["steps"]["corrections"]["id"]))
        if has_label(item, "dstack:work:correction") or issue_type(item) not in {"epic", "molecule", "gate"}
    ]
    return view


def immutable_candidate_revision(root: Path, search_ref: str, closeout_id: str) -> str:
    """Derive one closeout-footer commit without persisting a Git mapping."""

    validate_git_revision(root, search_ref, name="candidate search ref")
    matches = commit_footer_ids(root, search_ref).get(closeout_id, [])
    if len(matches) != 1:
        count = len(matches)
        raise DstackError(
            f"immutable candidate revision is ambiguous for {closeout_id} on "
            f"{search_ref}: expected exactly one closeout footer, found {count}"
        )
    return str(matches[0]["commit"])


def require_candidate_head(root: Path, search_ref: str, closeout_id: str, candidate_head: str) -> str:
    revision = immutable_candidate_revision(root, search_ref, closeout_id)
    if revision != candidate_head:
        raise DstackError(
            "candidate HEAD is not the unique closeout-footer revision; "
            f"candidate_head={candidate_head}, closeout_revision={revision}"
        )
    return revision


def delivered_candidate_revision(root: Path, target: str, closeout_id: str) -> tuple[str, str]:
    refs = [target]
    remote = f"origin/{target}"
    if ref_exists(root, remote):
        refs.append(remote)
    found: list[tuple[str, str]] = []
    for ref in refs:
        matches = commit_footer_ids(root, ref).get(closeout_id, [])
        commits = {str(item["commit"]) for item in matches}
        if len(commits) > 1:
            raise DstackError(
                f"immutable candidate revision is ambiguous for {closeout_id} on {ref}: found {len(commits)} commits"
            )
        if commits:
            found.append((ref, commits.pop()))
    revisions = {revision for _, revision in found}
    if len(revisions) != 1:
        detail = ", ".join(f"{ref}={revision}" for ref, revision in found) or "none"
        raise DstackError(f"immutable candidate revision is unavailable or inconsistent for {closeout_id}: {detail}")
    revision = revisions.pop()
    search_ref = next(ref for ref, value in found if value == revision)
    return search_ref, revision


def _require_linear_alignment_candidate(root: Path, baseline: str, candidate: str) -> None:
    if not ancestry(root, baseline, candidate):
        raise DstackError(
            f"alignment candidate is not descended from baseline_commit; baseline={baseline}, candidate={candidate}"
        )
    merges = run(
        ["git", "rev-list", "--merges", f"{baseline}..{candidate}"],
        cwd=root,
    ).stdout.splitlines()
    if merges:
        raise DstackError("alignment candidate evidence is nonlinear: " + ", ".join(merges))


def alignment_candidate_revision(
    root: Path,
    search_ref: str,
    view: Mapping[str, Any],
    *,
    allow_unavailable: bool = False,
) -> tuple[str, str] | None:
    """Derive an alignment candidate from reachable native Git evidence."""

    validate_git_revision(root, search_ref, name="alignment candidate search ref")
    baseline = str(view.get("baseline_commit") or "")
    validate_git_revision(root, baseline, name="alignment baseline_commit")
    if not ancestry(root, baseline, search_ref):
        raise DstackError(
            "alignment baseline_commit is not reachable from the candidate search ref; "
            f"baseline={baseline}, search_ref={search_ref}"
        )

    landing = view["steps"]["landing"]
    landing_id = str(landing["id"])
    mapping = commit_footer_ids(root, search_ref)
    landing_records = mapping.get(landing_id, [])
    landing_commits = {str(record["commit"]) for record in landing_records}
    if len(landing_records) != len(landing_commits) or len(landing_commits) > 1:
        raise DstackError(f"alignment candidate evidence is ambiguous for landing {landing_id} on {search_ref}")
    if landing_commits:
        candidate = landing_commits.pop()
        _require_linear_alignment_candidate(root, baseline, candidate)
        return candidate, "unique reachable landing Beads footer"

    corrections = list(view["corrections"])
    open_ids = sorted(str(item["id"]) for item in corrections if item.get("status") != "closed")
    if open_ids:
        raise DstackError("alignment candidate evidence has nonterminal corrections: " + ", ".join(open_ids))
    changing = [
        item for item in corrections if not str(item.get("close_reason") or "").startswith(NO_REPOSITORY_CHANGE_PREFIX)
    ]
    missing = sorted(str(item["id"]) for item in changing if not mapping.get(str(item["id"])))
    if missing:
        if allow_unavailable:
            return None
        raise DstackError(
            "alignment candidate revision is unavailable; missing correction evidence: " + ", ".join(missing)
        )
    if changing:
        expected = {str(item["id"]) for item in changing}
        _, malformed = footer_cardinality(mapping, expected)
        if malformed:
            raise DstackError("alignment correction evidence is ambiguous: " + ", ".join(malformed))
        commits = {str(record["commit"]) for correction_id in expected for record in mapping[correction_id]}
        outside_baseline = sorted(commit for commit in commits if not ancestry(root, baseline, commit))
        if outside_baseline:
            raise DstackError("alignment correction evidence predates baseline_commit: " + ", ".join(outside_baseline))
        latest = [candidate for candidate in commits if all(ancestry(root, other, candidate) for other in commits)]
        if len(latest) != 1:
            raise DstackError("alignment correction evidence is nonlinear or ambiguous")
        candidate = latest[0]
        _require_linear_alignment_candidate(root, baseline, candidate)
        return candidate, "latest reachable correction Beads footer"

    return baseline, "canonical alignment plan baseline_commit"


def delivered_alignment_candidate_revision(root: Path, target: str, view: Mapping[str, Any]) -> tuple[str, str, str]:
    refs = [target]
    remote = f"origin/{target}"
    if ref_exists(root, remote):
        refs.append(remote)
    found: list[tuple[str, str, str]] = []
    for ref in refs:
        derived = alignment_candidate_revision(root, ref, view, allow_unavailable=True)
        if derived is not None:
            found.append((ref, *derived))
    revisions = {candidate for _, candidate, _ in found}
    if len(revisions) != 1:
        if not found:
            alignment_candidate_revision(root, target, view)
        detail = ", ".join(f"{ref}={candidate}" for ref, candidate, _ in found)
        raise DstackError("alignment candidate revision is unavailable or inconsistent: " + detail)
    candidate = revisions.pop()
    search_ref, _, derivation = next(item for item in found if item[1] == candidate)
    return search_ref, candidate, derivation


def feature_evidence_audit(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    branch, worktree, base = feature_branch_context(client, view)
    steps = view["steps"]
    candidate_revision: str | None = None
    if view["steps"]["closeout"].get("status") == "closed":
        candidate_revision = require_candidate_head(
            client.root,
            branch,
            str(steps["closeout"]["id"]),
            current_head(worktree),
        )
    audit = evidence_audit(
        client,
        worktree=worktree,
        base=base,
        branch=branch,
        tasks=view["work_items"],
        allowed_ids=[
            str(steps["specification"]["id"]),
            str(steps["closeout"]["id"]),
        ],
    )
    result = {"feature": view["root"]["id"], **audit}
    if candidate_revision is not None:
        result.update(
            {
                "search_ref": branch,
                "candidate_revision": candidate_revision,
                "derivation": "unique reachable closeout Beads footer",
                "candidate_head": candidate_revision,
                "evidence_source": candidate_revision,
            }
        )
    return result


def _delivered_evidence_audit(client: BeadsClient, view: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    if kind == "feature":
        target = str(view.get("base_branch") or "")
        terminal = "closeout"
        initial = "specification"
        tasks = view["work_items"]
        branch = f"feat/{view['slug']}"
    else:
        target = str(view.get("target_branch") or "")
        terminal = "landing"
        initial = None
        tasks = view["corrections"]
        branch = f"audit/{view['slug']}"
    if not target or not ref_exists(client.root, target):
        raise DstackError(f"delivered {kind} target ref is unavailable: {target!r}")

    steps = view["steps"]
    terminal_id = str(steps[terminal]["id"])
    closed = [item for item in tasks if item.get("status") == "closed"]
    no_repository_change = sorted(
        str(item["id"])
        for item in closed
        if str(item.get("close_reason") or "").startswith(NO_REPOSITORY_CHANGE_PREFIX)
    )
    expected = {str(item["id"]) for item in closed if str(item["id"]) not in no_repository_change}
    if kind == "feature":
        search_ref, candidate = delivered_candidate_revision(client.root, target, terminal_id)
        derivation = "unique reachable closeout Beads footer"
        expected.add(terminal_id)
        if initial:
            expected.add(str(steps[initial]["id"]))
    else:
        search_ref, candidate, derivation = delivered_alignment_candidate_revision(client.root, target, view)
        if derivation == "unique reachable landing Beads footer":
            expected.add(terminal_id)
        elif str(steps[terminal].get("close_reason") or "").startswith(NO_REPOSITORY_CHANGE_PREFIX):
            no_repository_change.append(terminal_id)
            no_repository_change.sort()
    reachable = commit_footer_ids(client.root, candidate)
    missing = sorted(item for item in expected if not reachable.get(item))
    mapping = {item: reachable[item] for item in sorted(expected) if reachable.get(item)}
    multiple, malformed = footer_cardinality(reachable, expected)
    target_reachable = commit_footer_ids(client.root, search_ref)
    candidate_commits = {item: {str(record["commit"]) for record in reachable.get(item, [])} for item in expected}
    wrong_source = sorted(
        item
        for item in expected
        if any(str(record["commit"]) not in candidate_commits[item] for record in target_reachable.get(item, []))
    )
    present = branch_exists(client.root, branch)
    result = {
        kind: view["root"]["id"],
        "status": "ok" if not missing and not malformed and not wrong_source else "issues",
        "source": "delivered-target",
        "search_ref": search_ref,
        "target_ref": target,
        "candidate_revision": candidate,
        "derivation": derivation,
        "candidate_branch": branch,
        "candidate_branch_present": present,
        "worktree_present": worktree_for_branch(client.root, branch) is not None,
        "evidence_source": candidate,
        "missing": missing,
        "no_repository_change": no_repository_change,
        "multiple_commits": multiple,
        "malformed_footer_ids": malformed,
        "wrong_source_footer_ids": wrong_source,
        "mapping": mapping,
    }
    if kind == "feature":
        result.update({"feature_branch": branch, "feature_branch_present": present})
    return result


def delivered_feature_evidence_audit(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    return _delivered_evidence_audit(client, view, kind="feature")


def delivered_alignment_evidence_audit(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    return _delivered_evidence_audit(client, view, kind="alignment")


def alignment_evidence_audit(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    slug = str(view["slug"] or "")
    branch = f"audit/{slug}"
    base = str(view["target_branch"] or "")
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        raise DstackError(f"no worktree is registered for {branch}")
    steps = view["steps"]
    audit = evidence_audit(
        client,
        worktree=worktree,
        base=base,
        branch=branch,
        tasks=view["corrections"],
        allowed_ids=[
            str(steps["analysis"]["id"]),
            str(steps["landing"]["id"]),
        ],
    )
    result = {"alignment": view["root"]["id"], **audit}
    if steps["landing"].get("status") == "closed":
        derived = alignment_candidate_revision(client.root, branch, view)
        if derived is None:
            raise DstackError("alignment candidate revision is unavailable")
        candidate, derivation = derived
        head = current_head(worktree)
        if candidate != head:
            raise DstackError(
                "alignment candidate HEAD does not match immutable evidence; "
                f"candidate_head={head}, candidate_revision={candidate}"
            )
        result.update(
            {
                "search_ref": branch,
                "candidate_revision": candidate,
                "derivation": derivation,
                "candidate_head": head,
                "evidence_source": candidate,
            }
        )
    return result


def cmd_evidence_audit_feature(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_delivery_context(client, args.selector)
    audit = feature_evidence_audit(client, view)
    emit(audit)
    return 0 if audit["status"] == "ok" else 3


def diff_paths(root: Path, base: str, head: str) -> list[str]:
    output = run(["git", "diff", "--name-only", f"{base}...{head}"], cwd=root).stdout
    return [line for line in output.splitlines() if line]


def docs_check(root: Path, base: str, head: str) -> dict[str, Any]:
    paths = diff_paths(root, base, head)
    doc_paths = [path for path in paths if path.startswith("docs/") or path.endswith(".md")]
    violations: list[dict[str, str]] = []
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
            for pattern in FORBIDDEN_DOC_PATTERNS:
                if pattern.search(content):
                    violations.append({"path": current_path, "line": content.strip()})
                    break

    status_only = False

    return {
        "status": "ok" if not violations else "violations",
        "paths": paths,
        "documentation_paths": doc_paths,
        "violations": violations,
        "status_only": status_only,
    }


def cmd_docs_check(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    validate_git_revision(root, args.base, name="documentation base")
    validate_git_revision(root, args.head, name="documentation head")
    payload = docs_check(root, args.base, args.head)
    emit(payload)
    return 0 if payload["status"] == "ok" else 4


def tracked_runtime_beads(root: Path) -> list[str]:
    output = run(["git", "ls-files", ".beads"], cwd=root).stdout.splitlines()
    return sorted(path for path in output if is_forbidden_tracked_beads_path(path))


def delivery_view(client: BeadsClient, selector: str) -> dict[str, Any]:
    exact = client.show_optional(selector)
    if exact is not None and has_label(exact, "workflow:project-alignment"):
        view = alignment_delivery_context(client, str(exact["id"]))
        kind = "alignment"
    elif exact is not None and has_label(exact, "workflow:feature"):
        view = feature_delivery_context(client, str(exact["id"]))
        kind = "feature"
    else:
        feature_error: DstackError | None = None
        try:
            view = feature_delivery_context(client, selector)
            kind = "feature"
        except DstackError as exc:
            feature_error = exc
            try:
                view = alignment_delivery_context(client, selector)
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
    workstream = view["steps"]["corrections" if kind == "alignment" else "implementation"]
    require_complete_fan_in(
        client,
        parent_id=str(workstream["id"]),
        name=f"{kind} workstream",
    )
    validate_git_branch(client.root, target, name="target branch")
    validate_git_branch(client.root, branch, name="candidate branch")
    validate_git_revision(client.root, target, name="target branch")
    validate_git_revision(client.root, branch, name="candidate branch")
    candidate_worktree = worktree_for_branch(client.root, branch)
    if candidate_worktree is None:
        raise DstackError(f"no worktree found for {branch}")
    candidate_worktree = verify_worktree_identity(client.root, candidate_worktree, branch)
    candidate = current_head(candidate_worktree)
    if kind == "feature":
        require_approved_design(view)
        require_candidate_head(
            client.root,
            branch,
            str(view["steps"]["closeout"]["id"]),
            candidate,
        )
        evidence = feature_evidence_audit(client, view)
    else:
        evidence = alignment_evidence_audit(client, view)
    if evidence["status"] != "ok":
        details = []
        for key in (
            "missing",
            "malformed_footer_ids",
            "wrong_source_footer_ids",
            "unexpected_footer_ids",
            "orphaned_footer_ids",
        ):
            values = evidence.get(key) or []
            if values:
                details.append(f"{key}={','.join(str(value) for value in values)}")
        raise DstackError(f"{kind} delivery evidence audit failed" + (": " + "; ".join(details) if details else ""))
    target_worktree = worktree_for_branch(client.root, target)
    if target_worktree is not None:
        target_worktree = verify_worktree_identity(client.root, target_worktree, target, conventional=False)
    target_head = current_head(client.root, target)
    remote_ref = f"origin/{target}"
    remote_head = current_head(client.root, remote_ref) if ref_exists(client.root, remote_ref) else None
    remote_candidate_ref = f"origin/{branch}"
    remote_candidate_head = (
        current_head(client.root, remote_candidate_ref) if ref_exists(client.root, remote_candidate_ref) else None
    )
    merges = run(["git", "rev-list", "--merges", f"{target}..{branch}"], cwd=client.root).stdout.splitlines()
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
    stats = run(["git", "diff", "--stat", f"{target}...{branch}"], cwd=client.root).stdout
    return {
        "kind": kind,
        "root": root,
        "slug": slug,
        "target_branch": target,
        "candidate_branch": branch,
        "closeout_id": str(terminal["id"]) if kind == "feature" else None,
        "target_worktree": str(target_worktree) if target_worktree else None,
        "candidate_worktree": str(candidate_worktree),
        "target_head": target_head,
        "candidate_revision": candidate,
        "remote_target_head": remote_head,
        "remote_candidate_head": remote_candidate_head,
        "candidate_head": candidate,
        "target_is_ancestor": ancestry(client.root, target, branch),
        "remote_matches_local": remote_head is None or remote_head == target_head,
        "merge_commits": merges,
        "commits": commits,
        "paths": paths,
        "tracked_runtime_beads": tracked_runtime_beads(client.root),
        "evidence": evidence,
        "diff_stat": stats,
        "docs": docs_check(client.root, target, branch),
        "documentation": validate_docs(candidate_worktree),
    }


def _delivery_root(client: BeadsClient, selector: str) -> dict[str, Any]:
    exact = client.show_optional(selector)
    if exact is not None and (has_label(exact, "workflow:feature") or has_label(exact, "workflow:project-alignment")):
        return exact
    errors: list[str] = []
    for resolver in (feature_context, alignment_context):
        try:
            return dict(resolver(client, selector)["root"])
        except DstackError as exc:
            errors.append(str(exc))
    raise DstackError(f"selector is neither a feature nor a project alignment: {selector}; " + "; ".join(errors))


def delivery_inspection(client: BeadsClient, selector: str) -> dict[str, Any]:
    root = _delivery_root(client, selector)
    if root.get("status") != "closed":
        return delivery_view(client, selector)

    if has_label(root, "workflow:feature"):
        kind = "feature"
        view = feature_delivery_context(client, str(root["id"]))
        evidence = delivered_feature_evidence_audit(client, view)
        target = str(view["base_branch"])
        branch = f"feat/{view['slug']}"
        terminal = "closeout"
    else:
        kind = "alignment"
        view = alignment_delivery_context(client, str(root["id"]))
        evidence = delivered_alignment_evidence_audit(client, view)
        target = str(view["target_branch"])
        branch = f"audit/{view['slug']}"
        terminal = "landing"
    if evidence["status"] != "ok":
        details = []
        for key in ("missing", "malformed_footer_ids", "wrong_source_footer_ids"):
            values = evidence.get(key) or []
            if values:
                details.append(f"{key}={','.join(str(value) for value in values)}")
        raise DstackError(f"delivered {kind} evidence audit failed" + (": " + "; ".join(details) if details else ""))
    terminal_id = str(view["steps"][terminal]["id"])
    return {
        "kind": kind,
        "delivery_state": "delivered",
        "root": root,
        "slug": str(view["slug"]),
        "target_branch": target,
        "candidate_branch": branch,
        "closeout_id": terminal_id if kind == "feature" else None,
        "landing_id": terminal_id if kind == "alignment" else None,
        "target_worktree": None,
        "candidate_worktree": None,
        "target_head": current_head(client.root, target),
        "candidate_revision": evidence["candidate_revision"],
        "candidate_head": evidence["candidate_revision"],
        "evidence": evidence,
    }


def _git_snapshot(root: Path) -> tuple[str, str]:
    return (
        current_head(root),
        run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=root,
        ).stdout,
    )


def cmd_delivery_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    payload = delivery_inspection(client, args.selector)
    if args.fetch:
        remote = run(["git", "remote", "get-url", "origin"], cwd=client.root, check=False)
        if remote.returncode == 0:
            run(["git", "fetch", "origin", "--prune"], cwd=client.root)
            payload = delivery_inspection(client, args.selector)
    emit({"status": "ok", **payload})
    return 0


def ensure_clean_candidate(root: Path, payload: Mapping[str, Any]) -> str | None:
    worktree_value = payload.get("candidate_worktree")
    if not worktree_value:
        return None
    worktree = Path(str(worktree_value))
    ensure_clean_worktree(worktree)
    observed = current_head(worktree)
    if observed != payload.get("candidate_head"):
        raise DstackError("candidate HEAD changed after delivery inspection")
    closeout_id = payload.get("closeout_id")
    if closeout_id:
        require_candidate_head(
            root,
            str(payload["candidate_branch"]),
            str(closeout_id),
            observed,
        )
    return observed


def validate_delivery(payload: Mapping[str, Any], *, require_remote: bool) -> None:
    candidate_revision = payload.get("candidate_revision")
    candidate_head = payload.get("candidate_head")
    if candidate_revision is not None and candidate_head != candidate_revision:
        raise DstackError(
            "candidate HEAD is not the unique closeout-footer revision; "
            f"candidate_head={candidate_head}, closeout_revision={candidate_revision}"
        )
    if require_remote:
        if payload.get("remote_target_head") is None:
            raise DstackError("origin target branch is unavailable")
        if not payload.get("remote_matches_local"):
            raise DstackError("local target and origin target differ; synchronize the target before creating a PR")
    if payload.get("tracked_runtime_beads"):
        raise DstackError(
            "tracked Beads runtime state prevents safe delivery: "
            + ", ".join(str(item) for item in payload["tracked_runtime_beads"])
            + "; run /setup-project --force"
        )
    feature_paths = [
        str(path)
        for path in payload.get("paths", [])
        if str(path).startswith(".beads/") and not str(path).startswith(".beads/formulas/")
    ]
    if feature_paths:
        raise DstackError("candidate includes Beads runtime state: " + ", ".join(feature_paths))
    if not payload.get("target_is_ancestor"):
        raise DstackError(
            "candidate does not contain the target branch; rebase/cherry-pick instead of merging target into it"
        )
    if payload.get("merge_commits"):
        raise DstackError("candidate contains merge commits; dStack delivery requires a linear feature history")
    if payload.get("docs", {}).get("status") != "ok":
        raise DstackError("documentation policy check failed")
    if payload.get("documentation", {}).get("status") != "ok":
        raise DstackError("mdBook documentation validation failed")


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
        if not str(path).startswith("docs/") and not str(path).casefold().endswith((".md", ".mdx", ".rst"))
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
    ensure_clean_candidate(client.root, payload)
    validate_delivery(payload, require_remote=True)
    pr_copy = validate_pr_copy(
        payload,
        title=args.title,
        body_file=args.body_file,
    )
    emit({"status": "ok", "pr_copy": pr_copy, **payload})
    return 0


def pr_gate_state(client: BeadsClient, root_id: str) -> dict[str, list[dict[str, Any]]]:
    root = client.show(root_id)
    root_blockers = set(blocker_ids(root))
    associated = {
        str(record.get("depends_on_id") or record.get("id"))
        for record in dependency_records(root)
        if record.get("depends_on_id") or record.get("id")
    }
    summaries = [
        gate
        for gate in client.gates(all_statuses=True)
        if (
            str(gate.get("id")) in associated
            or str(gate.get("waiter_id") or "") == root_id
            or issue_parent(gate) == root_id
        )
        and str(gate.get("await_type") or gate.get("gate_type") or "") == "gh:pr"
    ]
    gates = [client.show(str(gate["id"])) for gate in summaries]
    gates.sort(key=lambda gate: str(gate["id"]))
    active = [
        gate
        for gate in gates
        if superseded_target(gate) is None
        and (
            str(gate["id"]) in root_blockers
            or (
                gate.get("status") != "closed"
                and (str(gate.get("waiter_id") or "") == root_id or issue_parent(gate) == root_id)
            )
        )
    ]
    return {"all": gates, "active": active}


def unique_pr_gate(client: BeadsClient, root_id: str) -> dict[str, Any]:
    active = pr_gate_state(client, root_id)["active"]
    if len(active) != 1:
        ids = ", ".join(str(gate["id"]) for gate in active) or "none"
        raise DstackError(f"root has no unique active PR gate: {ids}")
    return active[0]


def incomplete_pr_gate_cancellations(
    client: BeadsClient, root_id: str, state: Mapping[str, list[dict[str, Any]]]
) -> list[str]:
    gates = state.get("all", [])
    if not gates:
        return []
    root = client.show(root_id)
    relations = dependency_records(root)
    incomplete = []
    for gate in gates:
        gate_id = str(gate["id"])
        if gate.get("status") != "closed" or superseded_target(gate) is not None:
            continue
        types = [
            str(record.get("type") or record.get("dependency_type"))
            for record in relations
            if str(record.get("depends_on_id") or record.get("id")) == gate_id
        ]
        if "blocks" not in types and types.count("relates-to") != 1:
            incomplete.append(gate_id)
    return incomplete


def register_pr_gate(client: BeadsClient, root_id: str, pr_number: str) -> dict[str, Any]:
    active = pr_gate_state(client, root_id)["active"]
    if not active:
        return client.create_gate(
            gate_type="gh:pr",
            blocks=root_id,
            await_id=pr_number,
            reason="Await merged pull request",
        )
    if len(active) > 1:
        ids = ", ".join(str(gate["id"]) for gate in active)
        raise DstackError(f"ambiguous PR gates require explicit replacement: {ids}")
    if str(active[0].get("await_id") or "") != pr_number:
        raise DstackError(
            "conflicting PR gate requires explicit replacement: "
            f"{active[0]['id']} awaits PR {active[0].get('await_id')}"
        )
    return active[0]


def replace_pr_gates(
    client: BeadsClient, root_id: str, pr_number: str, reason: str
) -> tuple[dict[str, Any], list[str]]:
    reason = reason.strip()
    if not reason:
        raise DstackError("PR gate replacement requires a non-empty reason")
    active = pr_gate_state(client, root_id)["active"]
    matching = [
        gate for gate in active if gate.get("status") != "closed" and str(gate.get("await_id") or "") == pr_number
    ]
    if matching:
        target = matching[0]
    else:
        target = client.create_gate(
            gate_type="gh:pr",
            blocks=root_id,
            await_id=pr_number,
            reason=f"Await merged pull request; replacement reason: {reason}",
        )

    replaced = []
    for gate in active:
        gate_id = str(gate["id"])
        if gate_id == str(target["id"]):
            continue
        if gate.get("status") == "closed":
            client.reopen(gate_id, f"Replace PR gate: {reason}")
        client.supersede(gate_id, str(target["id"]))
        replaced.append(gate_id)

    observed = unique_pr_gate(client, root_id)
    if str(observed["id"]) != str(target["id"]) or str(observed.get("await_id") or "") != pr_number:
        raise DstackError("PR gate replacement did not converge")
    return observed, replaced


def cancel_pr_gate(client: BeadsClient, root_id: str, reason: str) -> dict[str, Any]:
    reason = reason.strip()
    if not reason:
        raise DstackError("PR gate cancellation requires a non-empty reason")
    before = _git_snapshot(client.root)
    state = pr_gate_state(client, root_id)
    active = state["active"]
    if len(active) == 1:
        gate = active[0]
    elif not active:
        recoverable = [
            item for item in state["all"] if item.get("status") == "closed" and superseded_target(item) is None
        ]
        if len(recoverable) != 1:
            ids = ", ".join(str(item["id"]) for item in recoverable) or "none"
            raise DstackError(f"root has no unique recoverable PR gate: {ids}")
        gate = recoverable[0]
    else:
        ids = ", ".join(str(item["id"]) for item in active)
        raise DstackError(f"root has no unique active PR gate: {ids}")

    gate_id = str(gate["id"])
    root = client.show(root_id)
    root_relations = [
        record for record in dependency_records(root) if str(record.get("depends_on_id") or record.get("id")) == gate_id
    ]
    blocking = [
        record for record in root_relations if str(record.get("type") or record.get("dependency_type")) == "blocks"
    ]
    related = [
        record for record in root_relations if str(record.get("type") or record.get("dependency_type")) == "relates-to"
    ]
    waiter = str(gate.get("waiter_id") or "")
    parent = issue_parent(gate)
    if (
        len(blocking) > 1
        or len(related) > 1
        or len(root_relations) != len(blocking) + len(related)
        or (blocking and related)
        or (not blocking and gate.get("status") != "closed")
        or (waiter and waiter != root_id)
        or (parent and parent != root_id)
    ):
        raise DstackError("PR gate has an unexpected blocker/waiter relation")

    try:
        cancellation_reason = f"Cancel PR gate: {reason}"
        if blocking:
            if gate.get("status") == "closed":
                client.add_comment(gate_id, cancellation_reason)
            else:
                client.resolve_gate(gate_id, cancellation_reason)
            client.remove_dependency(root_id, gate_id)
        if not related:
            client.relate(root_id, gate_id)

        observed = pr_gate_state(client, root_id)
        matches = [item for item in observed["all"] if str(item["id"]) == gate_id]
        root = client.show(root_id)
        related = [
            record
            for record in dependency_records(root)
            if str(record.get("depends_on_id") or record.get("id")) == gate_id
            and str(record.get("type") or record.get("dependency_type")) == "relates-to"
        ]
        if (
            observed["active"]
            or len(matches) != 1
            or matches[0].get("status") != "closed"
            or len(related) != 1
            or gate_id in blocker_ids(root)
        ):
            raise DstackError("PR gate cancellation did not converge")
    except DstackError as exc:
        if _git_snapshot(client.root) != before:
            raise DstackError(f"{exc}; PR gate cancellation changed Git HEAD or status") from exc
        raise

    if _git_snapshot(client.root) != before:
        raise DstackError("PR gate cancellation changed Git HEAD or status")
    return matches[0]


def cmd_delivery_register_pr(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    run(["git", "fetch", "origin", "--prune"], cwd=client.root)
    payload = delivery_view(client, args.selector)
    ensure_clean_candidate(client.root, payload)
    validate_delivery(payload, require_remote=True)
    if payload.get("remote_candidate_head") != payload.get("candidate_head"):
        raise DstackError(
            "origin candidate branch does not match the inspected candidate; "
            "push the exact branch before registering the PR"
        )
    root_id = str(payload["root"]["id"])
    gate = register_pr_gate(client, root_id, str(args.pr_number))
    emit({"status": "ok", "root": root_id, "gate": gate, "pr_number": args.pr_number})
    return 0


def cmd_delivery_cancel_pr_gate(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root = _delivery_root(client, args.selector)
    root_id = str(root["id"])
    gate = cancel_pr_gate(client, root_id, args.reason)
    emit({"status": "ok", "root": root_id, "gate": gate})
    return 0


def cmd_delivery_replace_pr(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    run(["git", "fetch", "origin", "--prune"], cwd=client.root)
    payload = delivery_view(client, args.selector)
    ensure_clean_candidate(client.root, payload)
    validate_delivery(payload, require_remote=True)
    if payload.get("remote_candidate_head") != payload.get("candidate_head"):
        raise DstackError(
            "origin candidate branch does not match the inspected candidate; "
            "push the exact branch before replacing the PR gate"
        )

    root_id = str(payload["root"]["id"])
    gate, replaced = replace_pr_gates(client, root_id, str(args.pr_number), args.reason)
    emit(
        {
            "status": "ok",
            "root": root_id,
            "gate": gate,
            "pr_number": args.pr_number,
            "replaced": replaced,
        }
    )
    return 0


def _cleanup_state(root: Path, worktree: Path, branch: str) -> tuple[bool | None, bool | None, bool | None]:
    try:
        path_exists: bool | None = worktree.exists()
    except OSError:
        path_exists = None

    try:
        expected_path = worktree.resolve(strict=False)
        expected_branch = f"refs/heads/{branch}"
        registered = any(
            (
                isinstance(record.get("worktree"), str)
                and Path(str(record["worktree"])).resolve(strict=False) == expected_path
            )
            or record.get("branch") == expected_branch
            for record in worktree_records(root)
        )
    except Exception:
        registered = None

    if path_exists is not True:
        return path_exists, registered, None
    try:
        dirty = bool(
            run(
                ["git", "status", "--short", "--untracked-files=all"],
                cwd=worktree,
            ).stdout.strip()
        )
    except Exception:
        dirty = None
    return path_exists, registered, dirty


def _cleanup_value(value: bool | None) -> str:
    return "unknown" if value is None else str(value).lower()


def _cleanup_failure(
    *,
    root: Path,
    worktree: Path,
    branch: str,
    error: str,
) -> str:
    path_exists, registered, dirty = _cleanup_state(root, worktree, branch)
    return (
        "temporary delivery worktree cleanup failed; "
        f"retained_path={worktree}; "
        f"path_exists={_cleanup_value(path_exists)}; "
        f"registered={_cleanup_value(registered)}; "
        f"dirty={_cleanup_value(dirty)}; "
        f"cleanup_error={error}; "
        "recovery_guidance=inspect the retained path and Git worktree list, "
        "then remove it manually only after reviewing its files"
    )


@contextmanager
def delivery_target_worktree(root: Path, branch: str, existing: str | None):
    """Yield a target worktree, retaining evidence when cleanup is uncertain."""

    if existing:
        yield Path(existing)
        return

    parent = Path(tempfile.mkdtemp(prefix="dstack-delivery-target-"))
    worktree = (parent / "target").resolve()
    try:
        run(["git", "worktree", "add", "--quiet", str(worktree), branch], cwd=root)
    except BaseException:
        try:
            parent.rmdir()
        except OSError:
            pass
        raise

    primary: BaseException | None = None
    try:
        yield worktree
    except BaseException as exc:
        primary = exc
        raise
    finally:
        cleanup_error: str | None = None
        try:
            removal = run(
                ["git", "worktree", "remove", str(worktree)],
                cwd=root,
                check=False,
            )
            if removal.returncode != 0:
                cleanup_error = removal.stderr.strip() or removal.stdout.strip()
                cleanup_error = cleanup_error or f"git worktree remove exited {removal.returncode}"
            else:
                path_exists, registered, _ = _cleanup_state(root, worktree, branch)
                if path_exists is not False or registered is not False:
                    cleanup_error = "successful worktree removal could not be verified"
                else:
                    try:
                        parent.rmdir()
                    except OSError as exc:
                        cleanup_error = f"temporary parent removal failed: {exc}"
        except Exception as exc:
            cleanup_error = str(exc)

        if cleanup_error is not None:
            message = _cleanup_failure(
                root=root,
                worktree=worktree,
                branch=branch,
                error=cleanup_error,
            )
            if primary is not None:
                primary.add_note(message)
            else:
                raise DstackError(message)


def finalize_beads_without_git_mutation(
    client: BeadsClient,
    *,
    root_id: str,
    worktree: Path,
    reason: str,
    expected_head: str,
    delivered_target_head: str,
    before_status: str,
    previous_target_head: str,
) -> tuple[str, str]:
    try:
        closed_root = client.close(root_id, reason)
    except DstackError as exc:
        try:
            observed_head = current_head(worktree)
        except DstackError:
            observed_head = "unknown"
        try:
            root_status = str(client.show(root_id).get("status") or "unknown")
        except DstackError:
            root_status = "unknown"
        raise DstackError(
            "delivery completed but Beads finalization failed; "
            "delivery_completed=true; "
            f"previous_target_head={previous_target_head}; "
            f"delivered_target_head={delivered_target_head}; "
            f"observed_target_head={observed_head}; root_status={root_status}; "
            f"finalization_error={exc}; mutation_uncertain=true; "
            "Git history was not rewritten"
        ) from exc
    after_head = current_head(worktree)
    after_status = run(["git", "status", "--short", "--untracked-files=all"], cwd=worktree).stdout
    if after_head == expected_head and after_status == before_status:
        return after_head, after_status

    reopened = False
    root_status = str(closed_root.get("status") or "unknown")
    try:
        if root_status == "closed":
            client.reopen(root_id, "Post-delivery Git invariant violation")
            reopened = True
            root_status = "open"
    except DstackError:
        pass
    changes = after_status.strip() or "<none>"
    raise DstackError(
        "delivery completed but Beads finalization changed Git state; "
        "delivery_completed=true; "
        f"previous_target_head={previous_target_head}; "
        f"delivered_target_head={delivered_target_head}; "
        f"observed_target_head={after_head}; root_status={root_status}; "
        "finalization_error=git state changed during Beads finalization; "
        "mutation_uncertain=false; "
        f"root_reopened={str(reopened).lower()}; changes={changes}; "
        "Git history was not rewritten"
    )


def cmd_delivery_merge(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    payload = delivery_view(client, args.selector)
    validate_delivery(payload, require_remote=False)
    root_id = str(payload["root"]["id"])
    pr_gates = pr_gate_state(client, root_id)
    active_pr_gates = pr_gates["active"]
    if active_pr_gates:
        ids = ", ".join(str(gate["id"]) for gate in active_pr_gates)
        raise DstackError(f"direct merge requires explicit cancellation of active PR gate: {ids}")
    incomplete = incomplete_pr_gate_cancellations(client, root_id, pr_gates)
    if incomplete:
        raise DstackError("direct merge rejects incomplete PR gate cancellation: " + ", ".join(incomplete))
    with delivery_target_worktree(
        client.root,
        str(payload["target_branch"]),
        str(payload["target_worktree"]) if payload.get("target_worktree") else None,
    ) as target_worktree:
        ensure_clean_worktree(target_worktree)
        candidate_revision = ensure_clean_candidate(client.root, payload)
        if candidate_revision is None:
            raise DstackError("delivery candidate worktree is unavailable")
        before_head = current_head(target_worktree)
        before_status = run(["git", "status", "--short", "--untracked-files=all"], cwd=target_worktree).stdout
        run(
            ["git", "merge", "--ff-only", candidate_revision],
            cwd=target_worktree,
        )
        merged_head = current_head(target_worktree)
        if merged_head != candidate_revision:
            raise DstackError("fast-forward completed at an unexpected target commit")
        after_head, _ = finalize_beads_without_git_mutation(
            client,
            root_id=root_id,
            worktree=target_worktree,
            reason="Delivered by fast-forward merge",
            expected_head=merged_head,
            delivered_target_head=merged_head,
            before_status=before_status,
            previous_target_head=before_head,
        )
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
    validate_delivery(payload, require_remote=False)
    root_id = str(payload["root"]["id"])
    client.gate_check()
    gate = unique_pr_gate(client, root_id)
    if gate.get("status") != "closed":
        emit({"status": "waiting", "root": root_id, "gate": gate})
        return 2
    run(["git", "fetch", "origin", "--prune"], cwd=client.root)
    remote_target = f"origin/{payload['target_branch']}"
    delivered_target_head = current_head(client.root, remote_target)
    target_ref = str(payload["target_branch"])
    target_worktree = worktree_for_branch(client.root, target_ref)
    with delivery_target_worktree(
        client.root,
        target_ref,
        str(target_worktree) if target_worktree else None,
    ) as observed_target:
        ensure_clean_worktree(observed_target)
        candidate_revision = ensure_clean_candidate(client.root, payload)
        if candidate_revision is None:
            raise DstackError("delivery candidate worktree is unavailable")
        if not ancestry(client.root, candidate_revision, remote_target):
            raise DstackError("PR gate closed but origin target does not contain the candidate commit")
        before_head = current_head(observed_target)
        before_status = run(["git", "status", "--short", "--untracked-files=all"], cwd=observed_target).stdout
        finalize_beads_without_git_mutation(
            client,
            root_id=root_id,
            worktree=observed_target,
            reason="Delivered through merged pull request",
            expected_head=before_head,
            delivered_target_head=delivered_target_head,
            before_status=before_status,
            previous_target_head=str(payload["target_head"]),
        )
    emit({"status": "ok", "root": client.show(root_id), "gate": gate})
    return 0
