"""Deterministic Git commit and correction operations."""

from __future__ import annotations

import argparse
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .beads import BeadsClient, client_for, issue_type
from .core import DstackError, run
from .git_state import (
    commit_records,
    current_head,
    git_operation,
    git_root,
    reject_beads_paths,
    require_feature_worktree,
    serialized_repository_mutation,
)
from .workflow import feature_identity, feature_steps, implementation_task_graph_errors
from .docs import markdown_links, validate_docs, validate_docs_revision
from .output import emit
from .policy import (
    MAX_IMPLEMENTATION_BODY_LENGTH,
    commit_subject,
    implementation_notes,
    validate_task_issue,
)


def staged_paths(root: Path) -> list[str]:
    output = run(["git", "diff", "--cached", "--name-only", "--no-renames", "-z"], cwd=root).stdout
    return [path for path in output.split("\0") if path]


def _unstaged_paths(root: Path) -> list[str]:
    unstaged = run(["git", "diff", "--name-only", "--no-renames", "-z"], cwd=root).stdout.split("\0")
    untracked = run(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root).stdout.split("\0")
    return sorted({path for path in [*unstaged, *untracked] if path})


def _require_no_git_operation(root: Path) -> None:
    operation = git_operation(root)
    if operation:
        raise DstackError("finish or abort the existing native Git operation before committing: " + operation)


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


def _commit(root: Path, message: str, *, allow_empty: bool = False) -> str:
    _require_no_git_operation(root)
    if allow_empty:
        dirty = [*staged_paths(root), *_unstaged_paths(root)]
        if dirty:
            raise DstackError("message-only correction requires a clean worktree: " + ", ".join(sorted(set(dirty))))
    else:
        _prepare_staged_change(root)
    message_path = _message_file(message)
    try:
        command = ["git", "commit"]
        if allow_empty:
            command.append("--allow-empty")
        run([*command, "-F", str(message_path)], cwd=root)
    finally:
        message_path.unlink(missing_ok=True)
    return current_head(root)


def _validate_feature_branch(client: BeadsClient, task: dict[str, object]) -> tuple[dict[str, object], str, str]:
    task_id = str(task.get("id") or "")
    root, slug, base = feature_identity(client, task_id)
    steps = feature_steps(client, str(root["id"]))
    graph_errors = implementation_task_graph_errors(task, steps)
    if graph_errors:
        raise DstackError("implementation Bead violates native graph policy: " + "; ".join(graph_errors))

    branch = f"feat/{slug}"
    require_feature_worktree(client, branch)
    return root, slug, base


def _commit_message(root: Path, revision: str) -> str:
    return run(["git", "show", "-s", "--format=%B", revision], cwd=root).stdout.rstrip("\n")


def canonical_docs_message(feature: Mapping[str, object], slug: str, task_id: str) -> str:
    title = str(feature.get("title") or "").strip().removeprefix("Feature: ").strip()
    if not title or "\n" in title:
        raise DstackError("feature title must be one non-empty line for the documentation commit")
    return build_commit_message(f"docs({slug}): {title}", "", task_id)


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


def _autosquash_correction(
    root: Path,
    *,
    target: str,
    message: str,
    allow_empty: bool = False,
) -> str:
    """Fold one correction into its exact owner, without autosquashing other work."""

    _require_no_git_operation(root)
    if _published(root, target):
        raise DstackError("refusing to rewrite a task commit reachable from a remote-tracking branch")
    parent = current_head(root, f"{target}^")
    if run(["git", "rev-list", "--merges", f"{parent}..HEAD"], cwd=root).stdout.strip():
        raise DstackError("correction requires linear history; reconcile merge commits with native Git first")
    fixup_message = f"amend! {target}\n\n{message.rstrip()}\n"
    correction = _commit(root, fixup_message, allow_empty=allow_empty)
    # Only this initial todo edit needs the temporary helper. Once rebase starts,
    # all recovery state lives in Git and survives removal of the helper.
    with tempfile.TemporaryDirectory(prefix="dstack-rebase-") as directory:
        editor = Path(directory) / "sequence.py"
        editor.write_text(
            "import pathlib, sys\n"
            "path = pathlib.Path(sys.argv[1])\n"
            "lines = path.read_text().splitlines()\n"
            f"target, correction = {target!r}, {correction!r}\n"
            "def matches(line, revision):\n"
            "    parts = line.split()\n"
            "    return len(parts) >= 2 and parts[0] == 'pick' and revision.startswith(parts[1])\n"
            "if sum(matches(line, target) for line in lines) != 1 or "
            "sum(matches(line, correction) for line in lines) != 1:\n"
            "    raise SystemExit('cannot identify the selected correction in the native rebase todo')\n"
            "result = []\n"
            "for line in lines:\n"
            "    if matches(line, correction):\n"
            "        continue\n"
            "    result.append(line)\n"
            "    if matches(line, target):\n"
            "        result.append('fixup -C ' + correction)\n"
            "path.write_text('\\n'.join(result) + '\\n')\n",
            encoding="utf-8",
        )
        result = run(
            [
                "git",
                "-c",
                "rebase.abbreviateCommands=false",
                "rebase",
                "-i",
                "--no-autosquash",
                "--no-autostash",
                "--no-update-refs",
                "--keep-empty",
                "--empty=keep",
                "--reapply-cherry-picks",
                parent,
            ],
            cwd=root,
            check=False,
            env={"GIT_SEQUENCE_EDITOR": shlex.join([sys.executable, str(editor)]), "GIT_EDITOR": "true"},
        )
    if result.returncode:
        details = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise DstackError(
            "correction stopped; preserve unrelated descendant work, then continue or abort the native rebase. "
            f"If aborted, the correction commit remains for explicit recovery: {details}"
        )
    return current_head(root)


def _correct_or_reuse(root: Path, target: str, message: str) -> tuple[str, str]:
    _require_no_git_operation(root)
    paths = staged_paths(root)
    if not paths:
        dirty = _unstaged_paths(root)
        if dirty:
            raise DstackError("commit refuses unstaged or untracked paths: " + ", ".join(dirty))
        if _commit_message(root, target).rstrip() == message.rstrip():
            return target, "unchanged"
    _autosquash_correction(root, target=target, message=message, allow_empty=not paths)
    return target, "corrected"


def _task_evidence(root: Path, base: str, task_id: str) -> list[dict[str, Any]]:
    return [
        record
        for record in commit_records(root, f"{base}..HEAD", owner_id=task_id, include_paths=True)
        if task_id in record.get("footer_ids", ())
    ]


def validate_commit_paths(paths: Sequence[str], slug: str, *, documentation: bool) -> None:
    """Enforce only the Beads-state exclusion and the feature publication boundary."""

    reject_beads_paths(paths)
    directory = f"docs/src/features/{slug}"
    if documentation:
        invalid = [path for path in paths if path != "docs/src/SUMMARY.md" and not path.startswith(directory + "/")]
        if invalid:
            raise DstackError("close documentation commit contains non-feature paths: " + ", ".join(invalid))
    else:
        invalid = [path for path in paths if path == directory or path.startswith(directory + "/")]
        if invalid:
            raise DstackError(
                "feature publication belongs to the close step, not an implementation task: " + ", ".join(invalid)
            )


def publication_changed(root: Path, base: str, head: str, slug: str) -> bool:
    """Do not demand an empty close commit for publication already inherited from the base."""

    changed = run(
        ["git", "diff", "--name-only", "-z", f"{base}...{head}", "--", f"docs/src/features/{slug}"], cwd=root
    ).stdout
    if changed:
        return True
    ancestor = run(["git", "merge-base", base, head], cwd=root).stdout.strip()
    summary = run(["git", "show", f"{ancestor}:docs/src/SUMMARY.md"], cwd=root, check=False)
    # Current publication is validated separately. Unrelated SUMMARY changes do
    # not require a close commit when this feature's navigation already existed.
    return summary.returncode != 0 or markdown_links(summary.stdout).count(f"features/{slug}/index.md") != 1


def _validate_staged_docs(root: Path, slug: str, expected_design: str) -> None:
    """Validate the exact tree that Git would commit, not merely working files."""
    tree = run(["git", "write-tree"], cwd=root).stdout.strip()
    validate_docs_revision(root, feature=slug, revision=tree, expected_design=expected_design)


def _require_valid_task(task: Mapping[str, object]) -> None:
    result = validate_task_issue(task)
    errors = [str(error) for error in result.get("errors", [])]
    if errors:
        raise DstackError("implementation Bead is mechanically invalid: " + "; ".join(errors))


@serialized_repository_mutation
def cmd_git_commit_docs(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    _require_no_git_operation(root)
    client = client_for(root)
    feature_root, slug, base = feature_identity(client, args.bead)
    steps = feature_steps(client, str(feature_root["id"]))
    close_step = client.show(str(steps["audit"]["id"]))
    _require_in_progress(close_step)
    implementation_id = str(steps["implementation"]["id"])
    open_tasks = [
        str(child["id"])
        for child in client.children(implementation_id)
        if issue_type(child) not in {"epic", "molecule", "gate"} and str(child.get("status") or "") != "closed"
    ]
    if open_tasks:
        raise DstackError("cannot document while implementation tasks remain open: " + ", ".join(open_tasks))

    branch = f"feat/{slug}"
    require_feature_worktree(client, branch)
    close_id = str(close_step["id"])
    evidence = _task_evidence(root, base, close_id)
    message = canonical_docs_message(feature_root, slug, close_id)

    paths = staged_paths(root)
    validate_commit_paths(paths, slug, documentation=True)
    for record in evidence:
        validate_commit_paths(record["paths"], slug, documentation=True)
    plan = client.show(str(steps["plan"]["id"]))
    expected_design = str(plan.get("design") or "")
    validate_docs(root, feature=slug, expected_design=expected_design)
    _validate_staged_docs(root, slug, expected_design)

    if not evidence:
        if paths:
            commit = _commit(root, message)
            mode = "created"
        else:
            dirty = _unstaged_paths(root)
            if dirty:
                raise DstackError("commit refuses unstaged or untracked paths: " + ", ".join(dirty))
            if publication_changed(root, base, "HEAD", slug):
                raise DstackError(
                    "publication changed without a close-owned commit; inspect Git ownership before retrying"
                )
            commit, mode = None, "unchanged"
    elif len(evidence) == 1:
        target = str(evidence[0]["commit"])
        _, mode = _correct_or_reuse(root, target, message)
        corrected = _task_evidence(root, base, close_id)
        if len(corrected) != 1:
            raise DstackError("correction did not leave exactly one close documentation commit")
        commit = str(corrected[0]["commit"])
    else:
        raise DstackError("close step has multiple reachable commits; refusing ambiguous correction")

    revision = commit or "HEAD"
    validate_docs_revision(root, feature=slug, revision=revision, expected_design=expected_design)
    if commit is not None:
        records = _task_evidence(root, base, close_id)
        if len(records) != 1:
            raise DstackError("close step must own exactly one documentation commit after publication")
        validate_commit_paths(records[0]["paths"], slug, documentation=True)
        _verify_commit_message(root, commit, message=message)
    subject = message.splitlines()[0] if commit is not None else None
    emit(
        {
            "status": "ok",
            "mode": mode,
            "bead": close_id,
            "feature": feature_root["id"],
            "commit": commit,
            "subject": subject,
        }
    )
    return 0


@serialized_repository_mutation
def cmd_git_commit(args: argparse.Namespace) -> int:
    root = git_root(args.root)
    _require_no_git_operation(root)
    client = client_for(root)
    task = client.show(args.bead)
    task_id = str(task["id"])
    _require_in_progress(task)
    _require_valid_task(task)
    feature_root, slug, base = _validate_feature_branch(client, task)
    evidence = _task_evidence(root, base, task_id)
    validate_commit_paths(staged_paths(root), slug, documentation=False)
    for record in evidence:
        validate_commit_paths(record["paths"], slug, documentation=False)
    message = canonical_task_message(task, slug)

    if not evidence:
        commit = _commit(root, message)
        mode = "created"
    elif len(evidence) == 1:
        target = str(evidence[0]["commit"])
        _, mode = _correct_or_reuse(root, target, message)
        corrected = _task_evidence(root, base, task_id)
        if len(corrected) != 1:
            raise DstackError("correction did not leave exactly one canonical task commit")
        commit = str(corrected[0]["commit"])
    else:
        raise DstackError("task has multiple reachable commits; refusing ambiguous correction")

    records = _task_evidence(root, base, task_id)
    if len(records) != 1:
        raise DstackError("implementation task must own exactly one canonical commit after committing")
    validate_commit_paths(records[0]["paths"], slug, documentation=False)
    _verify_commit_message(root, commit, message=message)
    canonical_subject = _commit_message(root, commit).splitlines()[0]
    emit(
        {
            "status": "ok",
            "mode": mode,
            "bead": task_id,
            "feature": feature_root["id"],
            "commit": commit,
            "subject": canonical_subject,
        }
    )
    return 0
