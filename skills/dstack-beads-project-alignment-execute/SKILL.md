---
name: dstack-beads-project-alignment-execute
description: "Resolve the native human approval gate and execute ready corrective work from a project-alignment molecule."
---

# Project alignment execute

Read the `dstack-beads-core` skill and every core reference before acting.

This is Tier 2. Use the user's input as an audit selector, optional correction
selector, and optional `--all`. Default to one correction.

Invoking this command is explicit approval of the Tier 1 plan represented by the
selected audit molecule. It authorizes resolving that audit's human gate; it
does not authorize final delivery.

## Preconditions and approval

1. Run the setup doctor.
2. Resolve exactly one open project-alignment root and its stable steps.
3. Verify the analysis step is closed and contains a durable plan summary.
4. Verify the recorded baseline commit and target branch still exist.
5. Resolve the unique open human gate blocking the corrections workstream.
6. Resolve that gate. Do not create or update a separate approval issue/state.
7. Verify corrective children now participate in the native ready frontier.

If the gate was already resolved, resume Tier 2 without asking for approval
again. If Tier 1 is incomplete, stop and route to `/project-alignment-review`.

## Native audit worktree

Create or reuse a Beads-managed worktree on:

```text
audit/<audit-slug>
```

Create the branch from the recorded baseline or current target as dictated by
the approved plan. Verify the exact path and branch before source changes. Tier
2 source mutations occur only in this worktree.

## Select and claim correction work

Without a named correction:

```bash
bd ready --mol <corrections-workstream-id> \
  --exclude-type epic \
  --claim \
  --json
```

For a named correction, verify ancestry and readiness before `bd update --claim`.

When no work is ready, use `bd mol current` and `bd mol progress` to report real
blockers. Do not compute an execution schedule or require global metadata.

## Execute one correction

1. read the selected Bead, direct blockers, Tier 1 evidence, accepted docs,
   relevant source/tests, and required validation;
2. implement only the bounded corrective outcome;
3. reconcile documentation when the correction changes supported behavior;
4. run focused validation and repository checks required by risk/policy;
5. create one correction-sized candidate commit;
6. run the shared independent review loop;
7. correct findings, revalidate, and safely amend the private commit;
8. use the discovery policy for incidental work;
9. add a durable Markdown review/validation comment to the correction Bead;
10. close the correction only after approval, permitted accepted risk, or an
    explicit later-stage validation contract.

A later correctness finding remains `changes requested`. Another review is
always available after user authorization. Do not create redesign or reviewer
replacement state.

## Continue or stop

Without `--all`, stop after one correction.

With `--all`, continue serially until no work is ready, a real user decision is
required, required correction-level validation cannot run, the worktree is
unsafe, or the user interrupts.

When every required corrective child is complete or explicitly accepted/deferred:

1. verify `bd mol progress <corrections-id> --json`;
2. close the corrections epic;
3. verify the formula's landing step becomes ready through native dependency and
   fan-in behavior;
4. recommend `/project-alignment-land <audit-slug>`.

Do not merge, open a PR, or close the audit root in Tier 2.

## Return

- audit, approval gate resolution, and worktree;
- claimed correction;
- behavior/files changed;
- validation and stage-specific pending evidence;
- review findings/corrections and authorization for extra reviews;
- correction commit/comment/closure;
- native corrections and audit progress;
- ready and blocked work;
- exact next command.
