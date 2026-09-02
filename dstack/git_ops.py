"""Deterministic Git commit and evidence operations."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

from .core import (
    BeadsClient,
    DstackError,
    commits_for_bead,
    current_head,
    feature_identity,
    git_root,
    has_label,
    issue_parent,
    read_text_file,
    run,
    serialized_repository_mutation,
)
from .output import emit
from .policy import commit_subject


def staged_paths(root: Path) -> list[str]:
    output = run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"], cwd=root).stdout
    return [line for line in output.splitlines() if line]


def reject_beads_paths(paths: list[str]) -> None:
    invalid = sorted(path for path in paths if path == ".beads" or path.startswith(".beads/"))
    if invalid:
        raise DstackError(
            "implementation commits may not include Beads configuration or runtime state; "
            "commit intentional Beads maintenance separately: " + ", ".join(invalid)
        )


def build_commit_message(subject: str, body: str, bead_id: str) -> str:
    if not subject or "\n" in subject:
        raise DstackError("commit subject must be one non-empty line")
    if not bead_id or bead_id != bead_id.strip() or any(character.isspace() for character in bead_id):
        raise DstackError("Bead ID must be one non-empty token")
    if re.search(r"(?im)^Beads:\s*", body):
        raise DstackError("commit body must not contain a Beads footer; dStack adds it")
    parts = [subject]
    if body.strip():
        parts.extend(["", body.strip()])
    parts.extend(["", f"Beads: {bead_id}"])
    return "\n".join(parts).rstrip() + "\n"


def _commit(root: Path, message: str, *, amend: bool) -> str:
    paths = staged_paths(root)
    if not paths and not amend:
        raise DstackError("no staged repository changes to commit")
    reject_beads_paths(paths)
    run(["git", "diff", "--cached", "--check"], cwd=root)

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


def _validate_feature_branch(client: BeadsClient, task: dict[str, object]) -> tuple[str, str]:
    bead_id = str(task.get("id") or "")
    parent_id = issue_parent(task)
    if parent_id is None:
        raise DstackError(f"implementation Bead {bead_id} has no native parent")
    parent = client.show(parent_id)
    if not has_label(parent, "dstack:step:implementation"):
        raise DstackError(f"implementation Bead {bead_id} is not a child of the implementation epic")

    root, slug, base = feature_identity(client, bead_id)
    branch = f"feat/{slug}"
    active = run(["git", "branch", "--show-current"], cwd=client.root).stdout.strip()
    if active != branch:
        raise DstackError(f"commit must run in feature worktree {branch}; active branch is {active or '<detached>'}")
    return str(root["id"]), base


def _verify_head_message(root: Path, *, subject: str, bead_id: str) -> None:
    observed = run(["git", "log", "-1", "--format=%B"], cwd=root).stdout.rstrip("\n")
    lines = observed.splitlines()
    footers = re.findall(r"(?m)^Beads:\s*([^\s]+)\s*$", observed)
    if not lines or lines[0] != subject or footers != [bead_id]:
        raise DstackError("created commit does not match the deterministic message contract")


@serialized_repository_mutation
def cmd_git_commit(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    client = BeadsClient(root)
    client.check_version()
    task = client.show(args.bead)
    feature_root, _ = _validate_feature_branch(client, task)
    subject = commit_subject(task)
    message = build_commit_message(subject, read_text_file(args.body_file), args.bead)
    commit = _commit(root, message, amend=False)
    _verify_head_message(root, subject=subject, bead_id=args.bead)
    emit({"status": "ok", "bead": args.bead, "feature": feature_root, "commit": commit, "subject": subject})
    return 0


@serialized_repository_mutation
def cmd_git_amend(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    client = BeadsClient(root)
    client.check_version()
    task = client.show(args.bead)
    feature_root, _ = _validate_feature_branch(client, task)
    head_message = run(["git", "log", "-1", "--format=%B"], cwd=root).stdout
    footers = re.findall(r"(?m)^Beads:\s*([^\s]+)\s*$", head_message)
    if footers != [args.bead]:
        raise DstackError(f"HEAD must contain exactly one Beads footer for {args.bead} before amend")
    subject = commit_subject(task)
    message = build_commit_message(subject, read_text_file(args.body_file), args.bead)
    commit = _commit(root, message, amend=True)
    _verify_head_message(root, subject=subject, bead_id=args.bead)
    emit({"status": "ok", "bead": args.bead, "feature": feature_root, "commit": commit, "subject": subject})
    return 0


def cmd_evidence_commits(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    emit({"status": "ok", "bead": args.bead, "ref": args.ref, "commits": commits_for_bead(root, args.ref, args.bead)})
    return 0
