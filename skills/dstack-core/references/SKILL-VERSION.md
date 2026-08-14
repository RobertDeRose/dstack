# Executing Skill Version Evidence

Machine-readable evidence uses schema `dstack.skill-version.v1`.

## Authority

The installed skill is execution authority. Its frontmatter `metadata.version` is the version that actually runs. A
local canonical dstack checkout is comparison evidence only; it must never replace the installed skill implicitly.
`npx skills update` is the supported refresh command.

## Startup check

Before the first lifecycle mutation, run the diagnostic for the skill that is executing:

```bash
skill_version_evidence=$(python3 <core-dir>/scripts/check-skill-version.py \
  --skill-name <skill-name> \
  --format line)
printf '%s\n' "$skill_version_evidence"
```

When `<core-dir>` is the installed `dstack-core` directory, the diagnostic finds the sibling installed skill and safely
checks a dstack checkout in the current path. Skills that expose only `<skill-dir>` use `<skill-dir>/../dstack-core`. To
compare against another local canonical checkout, set `DSTACK_CANONICAL_ROOT` or pass `--canonical-root <path>`. The
path must be local; the diagnostic never fetches a remote source or runs `npx skills update` itself.

Run this check after read-only selector/preflight work is complete but before any claim, branch, worktree, file, Beads,
Copier, or migration mutation. Capture the exact `Skill version evidence:` line in the workflow's durable evidence:

- append it to the selected Beads record with `bd update <id> --append-notes "$skill_version_evidence"` when a record
  already exists;
- include it in the workflow's existing JSON/report/response when no Beads record exists yet.

Do not discard the line after displaying it. It records the executing version even when canonical comparison is
unavailable.

## Refresh session boundary

The controller must establish `workflow_run_id` before this diagnostic: use the harness-provided stable value, or create
one once and retain it for the session's durable evidence. The evidence line binds the installed skill bytes to the
current workflow session. If `npx skills update` or another explicit refresh changes an installed skill, the current
session must stop before its next mutation; it may not silently continue under refreshed instructions. The current
session must stop before using refreshed skill bytes. Start a new session and rerun the diagnostic before resuming.
Record this canonical rebind object with the new session's stable `workflow_run_id`:

```json
{
  "schema": "dstack.skill-session-rebind.v1",
  "prior_evidence": "<exact line>",
  "new_evidence": "<exact line>",
  "refresh_action": "npx skills update",
  "new_session_id": "<workflow_run_id>"
}
```

Persist the object with the workflow's durable evidence: Beads-backed workflows append it to the owning issue/root
notes; migration appends it to its migration audit; response/JSON workflows include it in their existing JSON/report
output. A stale result is not current evidence, and an unavailable result is not a freshness approval; both remain
visible until a new session records its own result.

## Results

The command emits one machine-readable line on standard output and a human diagnostic on standard error:

- `current`: installed and canonical versions match; continue;
- `stale`: versions differ; warn before mutation and show `npx skills update`, but do not silently change global
  configuration or substitute another skill in the current run;
- `unavailable`: no trustworthy local canonical version is available; report that no freshness claim was made and
  continue without unsafe network assumptions;
- `invalid-installed`: the executing skill's frontmatter lacks `metadata.version` or cannot be read; stop because
  execution authority cannot be identified.

A canonical checkout is considered trustworthy only when its skill metadata is readable and its package version, when
present, agrees with that skill metadata. A commit SHA is recorded as supplemental evidence when the checkout is a Git
repository; version equality remains the comparison contract.
