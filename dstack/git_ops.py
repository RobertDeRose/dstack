"""Deterministic Git commit and correction operations."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path
from typing import Mapping

from .core import (
    BeadsClient,
    DstackError,
    commit_records,
    current_head,
    feature_identity,
    feature_steps,
    git_root,
    implementation_task_graph_errors,
    reject_beads_paths,
    run,
    serialized_repository_mutation,
    verify_worktree_identity,
    worktree_for_branch,
)
from .output import emit
from .policy import (
    MAX_IMPLEMENTATION_BODY_LENGTH,
    commit_subject,
    implementation_notes,
)


def staged_paths(root: Path) -> list[str]:
    output = run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"], cwd=root).stdout
    return [line for line in output.splitlines() if line]


def _unstaged_paths(root: Path) -> list[str]:
    unstaged = run(["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB"], cwd=root).stdout.splitlines()
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root).stdout.splitlines()
    return sorted({line for line in [*unstaged, *untracked] if line})


def build_commit_message(subject: str, body: str, task_id: str) -> str:
    if not subject or "\n" in subject:
        raise DstackError("commit subject must be one non-empty line")
    if not task_id or task_id != task_id.strip() or any(character.isspace() for character in task_id):
        raise DstackError("Task ID must be one non-empty token")
    if re.search(r"(?im)^(?:Task|Beads):\s*", body):
        raise DstackError("commit body must not contain an ownership footer; dStack adds it")
    parts = [subject]
    if body.strip():
        parts.extend(["", body.strip()])
    parts.extend(["", f"Task: {task_id}"])
    return "\n".join(parts).rstrip() + "\n"


def task_commit_body(task: Mapping[str, object]) -> str:
    notes = implementation_notes(task)
    if not notes:
        raise DstackError("implementation task requires at least one Implementation note before committing")
    body = "\n".join(f"- {note}" for note in notes)
    if len(body) > MAX_IMPLEMENTATION_BODY_LENGTH:
        raise DstackError(
            f"implementation commit body exceeds the bounded limit of {MAX_IMPLEMENTATION_BODY_LENGTH} characters"
        )
    return body


def _require_in_progress(task: Mapping[str, object]) -> None:
    status = str(task.get("status") or "")
    if status != "in_progress":
        raise DstackError(f"implementation task must be in_progress; observed {status or '<missing>'}")


def _prepare_staged_change(root: Path) -> list[str]:
    paths = staged_paths(root)
    if not paths:
        raise DstackError("no staged repository changes to commit")
    reject_beads_paths(paths)
    dirty = _unstaged_paths(root)
    if dirty:
        raise DstackError("commit refuses unstaged or untracked paths: " + ", ".join(dirty))
    run(["git", "diff", "--cached", "--check"], cwd=root)
    return paths


def _message_file(message: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
        handle.write(message)
        return Path(handle.name)


def _commit(root: Path, message: str) -> str:
    _prepare_staged_change(root)
    message_path = _message_file(message)
    try:
        run(["git", "commit", "-F", str(message_path)], cwd=root)
    finally:
        message_path.unlink(missing_ok=True)
    return current_head(root)


def _validate_feature_branch(client: BeadsClient, task: dict[str, object]) -> tuple[dict[str, object], str, str]:
    task_id = str(task.get("id") or "")
    root, slug, base = feature_identity(client, task_id)
    steps = feature_steps(client, str(root["id"]))
    graph_errors = implementation_task_graph_errors(client, task, root, steps)
    if graph_errors:
        raise DstackError("implementation Bead violates native graph policy: " + "; ".join(graph_errors))

    branch = f"feat/{slug}"
    _require_registered_feature_worktree(client, branch)
    return root, slug, base


def _require_registered_feature_worktree(client: BeadsClient, branch: str) -> Path:
    registered = worktree_for_branch(client, branch)
    if registered is None:
        raise DstackError(f"feature worktree is not registered for {branch}")
    verified = verify_worktree_identity(client.root, registered, branch)
    current = git_root(client.root).resolve()
    if current != verified:
        raise DstackError(
            f"commit must run from the registered feature worktree {verified}; current worktree is {current}"
        )
    return verified


def _commit_message(root: Path, revision: str) -> str:
    return run(["git", "show", "-s", "--format=%B", revision], cwd=root).stdout.rstrip("\n")


def canonical_task_message(task: Mapping[str, object], slug: str) -> str:
    task_id = str(task.get("id") or "")
    return build_commit_message(commit_subject(task, slug), task_commit_body(task), task_id)


def commit_record_matches_message(record: Mapping[str, object], message: str) -> bool:
    subject = str(record.get("subject") or "")
    body = str(record.get("body") or "")
    observed = f"{subject}\n\n{body}" if body else subject
    return observed.rstrip() == message.rstrip()


def _verify_commit_message(root: Path, revision: str, *, message: str) -> None:
    observed = _commit_message(root, revision)
    if observed.rstrip() != message.rstrip():
        raise DstackError("canonical commit does not match the deterministic message contract")


def _verify_head_message(root: Path, *, subject: str, task_id: str) -> None:
    _verify_commit_message(root, "HEAD", message=build_commit_message(subject, "", task_id))


def _published(root: Path, revision: str) -> bool:
    refs = run(
        ["git", "for-each-ref", "--contains", revision, "--format=%(refname)", "refs/remotes"],
        cwd=root,
    ).stdout
    return any(line.strip() and not line.strip().endswith("/HEAD") for line in refs.splitlines())


def _autosquash_correction(root: Path, *, target: str, base: str, message: str) -> str:
    if _published(root, target):
        raise DstackError("refusing to rewrite a task commit reachable from a remote-tracking branch")
    fixup_message = f"amend! {target}\n\n{message.rstrip()}\n"
    _commit(root, fixup_message)
    result = run(
        ["git", "rebase", "-i", "--autosquash", base],
        cwd=root,
        check=False,
        env={"GIT_SEQUENCE_EDITOR": "true", "GIT_EDITOR": "true"},
    )
    if result.returncode:
        details = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise DstackError(
            "autosquash stopped for deliberate conflict resolution; preserve unrelated descendant work, "
            f"then continue or abort the native rebase: {details}"
        )
    return current_head(root)


def _task_evidence(root: Path, base: str, task_id: str) -> list[dict[str, object]]:
    return [record for record in commit_records(root, f"{base}..HEAD") if task_id in record.get("footer_ids", ())]


@serialized_repository_mutation
def cmd_git_commit(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    client = BeadsClient(root)
    client.check_version()
    task = client.show(args.bead)
    _require_in_progress(task)
    feature_root, slug, base = _validate_feature_branch(client, task)
    evidence = _task_evidence(root, base, args.bead)
    message = canonical_task_message(task, slug)

    if not evidence:
        commit = _commit(root, message)
        mode = "created"
    elif len(evidence) == 1:
        target = str(evidence[0]["commit"])
        _autosquash_correction(root, target=target, base=base, message=message)
        corrected = _task_evidence(root, base, args.bead)
        if len(corrected) != 1:
            raise DstackError("autosquash did not leave exactly one canonical task commit")
        commit = str(corrected[0]["commit"])
        mode = "corrected"
    else:
        raise DstackError("task has multiple reachable commits; refusing ambiguous correction")

    _verify_commit_message(root, commit, message=message)
    canonical_subject = _commit_message(root, commit).splitlines()[0]
    emit(
        {
            "status": "ok",
            "mode": mode,
            "bead": args.bead,
            "feature": feature_root["id"],
            "commit": commit,
            "subject": canonical_subject,
        }
    )
    return 0
