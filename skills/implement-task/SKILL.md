---
name: implement-task
description: Implement exactly one standalone Beads task, bug, chore, spike, or feature with scoped context, validation, review, commit evidence, and closure. Use when asked to execute an individual task outside a workflow:feature epic.
metadata:
  version: "0.8.9"
allowed-tools: Read Glob Grep Edit Write Bash Task AskUserQuestion
---

# Implement one standalone task

Use this skill for exactly one standalone executable Beads issue. It provides the bounded claim, implementation,
validation, review, commit, and closure lifecycle that conversational task requests otherwise bypass.

Do not use it for a `workflow:feature` epic or a child of one. Those issues belong to `/start-feature` and
`/implement-feature`. Do not turn a standalone maintenance or audit task into a feature merely to use the feature
workflow.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

## Startup version evidence

Before claiming or mutating the issue, follow
[`../dstack-core/references/SKILL-VERSION.md`](../dstack-core/references/SKILL-VERSION.md) for `implement-task`. After
read-only selector and readiness checks, first capture the clean worktree and commit baseline required by section 1,
then capture the exact one-line output and append it to the selected issue's Beads notes before the claim. A `stale`
result warns with `npx skills update`; `unavailable` records that no freshness claim was made and does not block offline
work.

## 1. Resolve and claim exactly one issue

Require a task selector: an exact Beads ID, exact title, or unique human title fragment. Resolve it before making any
mutation:

```bash
bd prime
bd show "<task-selector>" --json
bd ready --json
```

Read structured fields before prose. The issue must be open, ready, and one of `task`, `bug`, `chore`, `spike`, or a
standalone `feature`. Inspect its parent and ancestry. Stop without changing state when it is an epic, molecule,
decision, milestone, story, ambiguous, blocked, or carries/inherits `workflow:feature`; report the canonical human title
and recommend the command that owns it:

```text
/implement-feature <feature-slug>
```

For a valid standalone issue, verify the selected issue appears in `bd ready --json`. Before the first Beads or file
mutation, require a clean current task worktree and capture its immutable interaction baseline:

```bash
test -z "$(git status --porcelain)"
task_worktree=$(git rev-parse --show-toplevel)
task_base_commit=$(git rev-parse HEAD)
```

This clean-start check precedes the startup-version note because that note and the claim may append tracked
`.beads/interactions.jsonl` evidence. After recording the required skill-version line, claim only the selected issue:

```bash
bd update <issue-id> --claim
bd show <issue-id> --json
```

If the claim or readiness check fails, stop. Never claim the next unrelated ready issue. Report the human title first;
retain the Beads ID, `task_worktree`, and `task_base_commit` for mutations, notes, commit evidence, closure, and final
interaction verification.

Do not silently switch branches, create a feature worktree, alter `dstack.activeFeature`, or absorb pre-existing
changes. If the clean-start check fails, the current branch is not authorized for the task, or repository ownership is
unclear, stop and ask for the exact recovery or worktree. Standalone tasks do not receive feature design or feature
close-out records.

## 2. Load only task context

Read the issue description, acceptance criteria, dependencies, linked design or documentation paths, and relevant
provenance such as `discovered-from`. Validate every evidence-derived path against the repository root before reading
it. Inspect only the affected code, tests, configuration, migrations, and reader-facing documentation needed to define
the task boundary. Do not use legacy `tasks.md` as live state.

If the issue lacks executable intent, boundaries, or acceptance evidence, stop and ask one focused question. Do not
invent product policy or silently expand the task into feature planning.

## 3. Implement the bounded outcome

Write or update behavior tests before implementation when practical. Implement the smallest complete change satisfying
the selected issue. Keep code, tests, configuration, migrations, failure behavior, and affected reader-facing
documentation aligned in the same work unit. Do not modify unrelated findings; create them as separate Beads issues with
`discovered-from:<issue-id>` provenance.

## 4. Validate and review

Run focused checks while iterating. After review fixes stabilize, run the task-specific checks, documentation checks
when docs changed, and the repository-standard suite once before committing. Record exact commands, outcomes, skipped
checks, and limitations. Do not reuse validation from before the final fix.

Launch exactly one fresh, read-only reviewer for correctness, security, maintainability, test adequacy, and compliance
with the selected issue. A context builder is unnecessary. Give the reviewer the issue metadata, intended boundary,
changed paths, validation evidence, and diff.

### Standalone review evidence

The selected standalone issue's Beads notes are the authoritative review record. Do not create or claim a separate
review bead. Append all machine-readable `Review state:` and `Finding:` records to the selected issue's notes, using the
shared schemas in `../dstack-core/references/REVIEW-STATE.md` and `../dstack-core/references/REVIEW-FINDINGS.md`. The
last `Review state:` line is the current review state; the last record for each `finding_id` is its current finding
projection. Do not treat the packet, reviewer transcript, controller memory, or prose note as a substitute.

Before launching the reviewer, append an `active` state containing the run ID, reviewer session ID supplied by the
harness, packet ID/path/digest, reviewed commit and diff boundary, review round, finding domains, and review boundary.
Use `status: active` and `disposition: pending`. After review, append each `Finding:` record and a new current state.
Use `status: verified` and `disposition: approved` only after actionable findings are resolved and affected checks pass.
An unresolved review remains `status: findings` with `disposition: changes_required` and current open `Finding:`
records; do not close the issue. Resume the same reviewer and run ID after fixes, preserving the packet identity and
updating the reviewed commit/diff boundary.

If the reviewer harness is unavailable before any reviewer session launches, append `status: unavailable` with
`disposition: pending` and a concrete `unavailable_reason`, then stop; the controller must not substitute self-review,
omit evidence, or close the issue. If an already-launched reviewer becomes unavailable or cannot be resumed after a fix,
preserve its unavailable record. At most one replacement is allowed: the original run's existing `supersedes_run_id` is
preserved (`null` only for an initial run); mark that run `status: replaced` with `disposition: replaced` and
`replacement_reason`, then create a new replacement run with a new run ID, `status: active`, `disposition: pending`,
`supersedes_run_id` pointing to the original run. The replacement run preserves the existing `replacement_count`; this
field counts only bounded redesign replacements, so ordinary unavailability does not consume the redesign-replacement
allowance. Record the replacement reason on both runs and pass the replacement the original packet identity, findings
ledger, resolutions, and post-fix diff. If the replacement itself is unavailable, append its `status: unavailable` state
and stop; do not launch a second replacement. If a fix materially changes the reviewed boundary, stop and reconcile the
scope rather than using reviewer replacement. Do not add confidence reviewers without a distinct uncovered risk or
explicit user request.

Record evidence before closure:

```bash
bd update <issue-id> --append-notes "Validation and review evidence: <commands, outcomes, findings, resolutions>"
```

## 5. Commit, close, and finalize only this issue

Invoking `/implement-task` authorizes the local implementation commit and, when needed, one interaction-evidence audit
commit. It does not authorize pushes, pull requests, merges, or remote delivery.

Run `git status --short` and confirm every intended implementation path belongs to the selected issue. An unstaged
`.beads/interactions.jsonl` append may also exist from this workflow; it is audit evidence, not an implementation path.
Never stage it with the implementation. Stage only explicit intended paths, confirm the staged set excludes the
interaction export, follow the repository's conventional commit and scope policy, and use the canonical Beads footer:

```text
<type>(<scope>): <summary>

- <bounded change or validation result>

Beads: <issue-id>
```

Capture and record the exact implementation commit before closing:

```bash
implementation_sha=$(git rev-parse HEAD)
bd update <issue-id> --append-notes "Commit evidence: ${implementation_sha}"
bd close <issue-id> --reason "Acceptance criteria satisfied; commit ${implementation_sha}"
```

If the task legitimately requires no implementation commit, record a specific reason instead of a placeholder SHA:

```bash
bd update <issue-id> --append-notes "Commit evidence: no commit required — <specific reason>"
bd close <issue-id> --reason "Acceptance criteria satisfied; no commit required — <specific reason>"
```

The close is the final Beads mutation. Do not append another note afterward. Verify the complete clean-start boundary
against the selected issue before staging or restoring anything:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py verify-standalone \
  --worktree "$task_worktree" --issue-id <issue-id> \
  --baseline-commit "$task_base_commit"
```

The verifier accepts a clean worktree when the interaction export is not tracked or no rows were appended. Otherwise it
requires that `.beads/interactions.jsonl` be the only dirty path, remain unstaged, have no commit touching that path
since `task_base_commit`, be append-only and valid JSONL, and contain only rows whose `issue_id` is the selected issue.
It rejects rewritten, malformed, duplicate, unrelated, staged, mode/type-changed, prematurely committed,
commit-then-reverted, or mixed dirty state without restoring or committing anything. If it rejects the state, stop and
preserve it for explicit recovery.

When verified interaction rows remain, commit exactly that path in a separate audit commit. Create the message first,
fail closed on every guard, and rerun the verifier against the staged index immediately before committing so rows added
between worktree verification and staging cannot be absorbed:

```bash
set -euo pipefail
if test -n "$(git status --porcelain)"; then
  cat > /tmp/dstack-task-interactions-message <<'EOF'
chore: Record standalone task evidence

Beads: <issue-id>
EOF
  git add -- .beads/interactions.jsonl
  test "$(git diff --cached --name-only)" = ".beads/interactions.jsonl"
  uv run <core-dir>/scripts/reconcile-beads-interactions.py verify-standalone \
    --worktree "$task_worktree" --issue-id <issue-id> \
    --baseline-commit "$task_base_commit" --staged
  git commit -F /tmp/dstack-task-interactions-message
  interaction_commit_sha=$(git rev-parse HEAD)
else
  interaction_commit_sha="not required — no tracked interaction append"
fi
test -z "$(git status --porcelain)"
```

Never close another issue, close with a placeholder SHA, absorb unrelated interaction rows, or claim completion while
intended implementation or audit evidence remains uncommitted.

## Return

Return the human title first, then the issue ID, classification, changed paths, validation and review evidence,
implementation commit SHA or specific no-commit reason, interaction audit commit SHA or specific no-commit reason, and
closure state. State that exactly one standalone issue was processed. Include a `Recommended next step` line: suggest
`/implement-task <next human selector>` only when the user asks for another standalone issue; otherwise report that the
task is complete and no feature close-out is required. Do not recommend `/start-feature` for a standalone issue.
