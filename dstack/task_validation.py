"""Shared deterministic validation for one implementation task and its Git evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .core import DstackError
from .git_ops import canonical_task_message, commit_record_matches_message, validate_commit_paths
from .policy import implementation_notes, no_repository_change_reason, validate_task_issue
from .workflow import implementation_task_graph_errors


def validate_implementation_task(
    task: Mapping[str, Any],
    steps: Mapping[str, Mapping[str, Any]],
    slug: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate task policy, graph membership, and its canonical repository evidence."""

    task_id = str(task.get("id") or "")
    policy = validate_task_issue(task)
    errors = [str(error) for error in policy["errors"]]
    errors.extend(implementation_task_graph_errors(task, steps))

    try:
        execution_notes = implementation_notes(task)
    except DstackError:
        # validate_task_issue already reports the native note-shape error.
        execution_notes = []
        notes_valid = False
    else:
        notes_valid = True
    no_change = no_repository_change_reason(task) if notes_valid else None
    if notes_valid and not no_change and not execution_notes:
        errors.append("implementation task requires at least one Implementation note before committing")

    task_records = [record for record in records if task_id in record.get("footer_ids", ())]
    for record in task_records:
        try:
            validate_commit_paths(record.get("paths", ()), slug, documentation=False)
        except DstackError as exc:
            errors.append(f"{record.get('commit')}: {exc}")

    expected_count = 0 if no_change else 1
    if len(task_records) != expected_count:
        errors.append(
            f"implementation task {task_id} must own {expected_count} canonical commit(s); observed {len(task_records)}"
        )
    elif task_records:
        try:
            expected_message = canonical_task_message(task, slug)
        except DstackError:
            errors.append("implementation task canonical commit does not match the deterministic message contract")
        else:
            if not commit_record_matches_message(task_records[0], expected_message):
                errors.append("implementation task canonical commit does not match the deterministic message contract")

    invalid_footer_commits = sorted(
        str(record.get("commit") or "")
        for record in records
        if (
            task_id in record.get("legacy_footer_ids", ())
            or (task_id in record.get("footer_ids", ()) and tuple(record.get("footer_ids", ())) != (task_id,))
        )
    )
    if invalid_footer_commits:
        errors.append(
            "task evidence commits must contain exactly one ownership footer for this task: "
            + ", ".join(invalid_footer_commits)
        )

    return {
        "policy": policy,
        "errors": errors,
        "no_repository_change": no_change,
        "records": task_records,
        "commits": [
            {
                "commit": str(record.get("commit") or ""),
                "subject": str(record.get("subject") or ""),
            }
            for record in task_records
        ],
        "invalid_footer_commits": invalid_footer_commits,
    }
