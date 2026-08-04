---
name: implement-task
description: Implement exactly one standalone Beads task, bug, chore, spike, or feature with scoped context, validation, review, commit evidence, and closure. Use when asked to execute an individual task outside a workflow:feature epic.
metadata:
  version: "0.8.2"
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
read-only selector and readiness checks, capture the exact one-line output and append it to the selected issue's Beads
notes before the claim. A `stale` result warns with `npx skills update`; `unavailable` records that no freshness claim
was made and does not block offline work.

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

For a valid standalone issue, verify the selected issue appears in `bd ready --json`, then claim only that issue:

```bash
bd update <issue-id> --claim
bd show <issue-id> --json
```

If the claim or readiness check fails, stop. Never claim the next unrelated ready issue. Report the human title first;
retain the Beads ID for mutations, notes, commit evidence, and closure.

Require a clean current task worktree before editing:

```bash
git status --porcelain
```

Do not silently switch branches, create a feature worktree, alter `dstack.activeFeature`, or absorb pre-existing
changes. If the worktree is dirty, the current branch is not authorized for the task, or repository ownership is
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
changed paths, validation evidence, and diff. Follow `../dstack-core/references/REVIEW-STATE.md` and
`../dstack-core/references/REVIEW-FINDINGS.md`; persist the review bead's run ID, reviewer session, packet
identity/digest, reviewed commit/diff boundary, current disposition, and current open findings before launch. Resume the
same reviewer and run ID after fixes; use a replacement only when the original is unavailable or the fix materially
changes scope. Do not add confidence reviewers without a distinct uncovered risk or explicit user request.

Record evidence before closure:

```bash
bd update <issue-id> --append-notes "Validation and review evidence: <commands, outcomes, findings, resolutions>"
```

## 5. Commit and close only this issue

Run `git status --short` and confirm every intended path belongs to the selected issue. Follow the repository's
conventional commit and scope policy, include the issue ID, and use the canonical Beads footer:

```text
<type>(<scope>): <summary>

- <bounded change or validation result>

Beads: <issue-id>
```

Capture and record the exact commit before closing:

```bash
commit_sha=$(git rev-parse HEAD)
bd update <issue-id> --append-notes "Commit evidence: ${commit_sha}"
bd close <issue-id> --reason "Acceptance criteria satisfied; commit ${commit_sha}"
```

If the task legitimately requires no repository change, record a specific reason instead of a placeholder SHA:

```bash
bd update <issue-id> --append-notes "Commit evidence: no commit required — <specific reason>"
bd close <issue-id> --reason "Acceptance criteria satisfied; no commit required — <specific reason>"
```

Never close another issue, close with a placeholder SHA, or claim completion while intended changes remain uncommitted.

## Return

Return the human title first, then the issue ID, classification, changed paths, validation and review evidence, commit
SHA or specific no-commit reason, and closure state. State that exactly one standalone issue was processed. Include a
`Recommended next step` line: suggest `/implement-task <next human selector>` only when the user asks for another
standalone issue; otherwise report that the task is complete and no feature close-out is required. Do not recommend
`/start-feature` for a standalone issue.
