# Beads interaction boundary

Native Beads keeps issue authority shared across linked Git worktrees. `bd -C <worktree>` selects the worktree for
command discovery, but it does not create an isolated issue database or make concurrent interaction writes safe. Treat
`.beads/interactions.jsonl` as a shared append-only audit stream.

## Mutation lease

Every dstack Beads mutation interval must run under the repository-scoped lease. The lease is process-backed, lives
outside the repository, and does not add lock files to Git:

```bash
workflow_run_id="<stable workflow run id>"
uv run <core-dir>/scripts/beads-workflow-lock.py exec \
  --repository-root "$repository_root" \
  --run-id "$workflow_run_id" \
  --timeout 0 \
  -- bash -eu -c '<contiguous Beads mutation and interaction finalization commands>'
```

Use one invocation for a contiguous claim/note/close/finalization boundary. Do not hold the lease while waiting for a
user, running reviews, or running long validation. A busy lease is a blocking repository-state result; do not bypass it
with a raw `bd` write.

Before the first close-out mutation, run the clean preflight from the canonical base worktree:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py preflight \
  --worktree "$base_worktree" --root-id <root-id>
```

If it fails, inspect without mutation:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py inspect \
  --worktree "$base_worktree" --root-id <root-id>
```

The inspector reports every selected and foreign appended record with interaction ID, issue ID, title, actor, and
creation time. Foreign records remain owned by their originating work unit. Do not broaden acceptance to `blocks` or
`related`, discard rows, restore over them, or add artificial lineage edges.

Recheck the interaction snapshot immediately before staging, restoration, merge, and delivery closure. Any change
outside the selected lineage or any snapshot race blocks the operation without mutation.

## Guarded publication

Publish native Dolt history only from a clean canonical worktree through the shared guard:

```bash
uv run <core-dir>/scripts/guarded-beads-push.py \
  --worktree "$repository_root" --run-id "$workflow_run_id"
```

The guard acquires the same repository lease, snapshots repository-local Beads authority and the configured remote,
fetches remote-tracking evidence, and permits only a non-force new-branch or fast-forward push. It binds the captured
remote URL to a private per-run alias, rechecks the configured remote after binding, pushes through that alias, and
removes it; evidence exposes only the URL digest. A busy lease, dirty or linked worktree, changed authority/remote,
missing common ancestor, behind local branch, or divergent history blocks before push and emits the local head, remote
head, merge base, and an evidence-preserving recovery path. It has no force or remote-replacement mode. Never replace it
with raw `bd dolt push`, retry with `--force`, or treat a failed guard as permission to discard either history.

## Delivery ordering

`ready` and no-action close-out leave the delivery issue and feature root open. Only the guarded delivery finalizer may
close them, and only after it verifies:

- the recorded merge SHA is an ancestor of the base branch;
- the post-merge finalizer commit is after the merge and updates the implemented record;
- semantic delivery and documentation verification passed;
- the base worktree is clean before the final Beads mutation.

```bash
uv run <core-dir>/scripts/finalize-feature-delivery.py \
  --base-worktree "$base_worktree" --base-branch <base-branch> \
  --record <implemented-record> --merge-sha "$merge_sha" \
  --finalizer-sha "$finalizer_sha" \
  --path <reader-facing-path> \
  --delivery-id <delivery-id> --root-id <root-id>
```

If any guard fails, preserve both worktrees and leave delivery/root open for retry.
