# Optional Pi reviewer roster adapter

This reference defines `dstack.pi-reviewer-roster.v2`, the optional mapping from dstack's tool-agnostic review roles to
Pi agent definitions. It does not make Pi mandatory or change Beads authority.

## Logical review contract

| Workflow | Beads review role(s) | Independent reviewer(s) |
|---|---|---|
| `/start-feature` | `specification-clarity`, `execution-readiness` | clarity and readiness, concurrently |
| `/implement-feature` | `task` | one task reviewer |
| `/implement-task` | `task` | one task reviewer |
| `/close-feature` | `implementation-integrity`, `delivery-integrity` | both close reviewers, concurrently |

Beads is the workflow manifest. The controller derives a transient assignment from the owning Beads issue, design/docs,
validation evidence, and an immutable Git source boundary. Reviewers read their assigned evidence directly in a pinned
read-only worktree. There is no shared evidence packet, collector, context-builder, or union-of-all-inputs projection.
Beads `Review state:` and `Finding:` records remain authority; reviewer sessions and prompts are supporting evidence.

## Exact Pi mapping

| Logical role | Exact Pi definition |
|---|---|
| `specification-clarity` | `dstack-clarity-reviewer` |
| `execution-readiness` | `dstack-readiness-reviewer` |
| `task` | `dstack-task-reviewer` |
| `implementation-integrity` | `dstack-implementation-reviewer` |
| `delivery-integrity` | `dstack-delivery-integrity-reviewer` |

The former context-builder, architecture, simplicity, documentation, execution, delivery, drift, and holistic
definitions are obsolete. Synchronization removes an obsolete file only when its prior manifest entry proves dstack
ownership and its bytes still match; modified or unowned files remain visible conflicts. Historical role names and
packet-era assignments do not authorize current review decisions.

## Enforced runtime and capability policy

The definitions target nicobailon/pi-subagents (installed as a pinned package source by the operator). Resolve each
assignment synchronously before launch. Each declares a 600,000 ms whole-run deadline, fresh context, and read-only
acceptance role. nicobailon has no idle-timeout equivalent: a quiet or long-running tool call is not treated as a failed
reviewer. Its lifecycle artifacts, `subagent_wait`, bounded status views, and persisted output/session paths are the
completion evidence; controllers must not wait on a shell sentinel or infer failure from a pane state.

Definitions replace old extension-specific fields with nicobailon's supported controls: `systemPromptMode: replace`,
`inheritProjectContext: false`, `inheritSkills: false`, an empty `extensions` allowlist, and only `read,grep,find,ls`.
No shell, mutation, or nested-delegation tool is available. `sync-pi-reviewers.py` rejects absent, malformed, changed,
duplicate, or unexpected metadata.

## Explicit installation and synchronization

Definitions live under `skills/dstack-core/assets/pi-reviewers/`; Pi does not discover that directory automatically.
When required names are missing, offer the project-local sync:

```bash
uv run <core-dir>/scripts/sync-pi-reviewers.py \
  --target project --project-root <repository> --json
```

Use `--check` for a read-only verification or `--remove` to remove only unchanged dstack-owned definitions.

A user may instead select `--target global` (`PI_CODING_AGENT_DIR/agents`) or an explicit agent directory. The command
writes `.dstack-pi-reviewers.json` with schema `dstack.pi-reviewer-install.v1`, source version, content digests, and
ownership. The adapter itself never performs synchronization without explicit confirmation. Conflicts never overwrite
user files.

## Adapter invocation rules

1. Resolve every required exact name before launch. Missing/unavailable roles fail visibly after declined or failed
   sync; there is no silent role substitution or count change.
2. Derive and verify each transient assignment from current Beads/design/docs/Git authority before launch.
3. Launch independent start and close reviewers concurrently. Task reviewers are single bounded sessions.
4. Resume only the same logical reviewer/run after fixes. Follow finite state, replacement, waiver, and convergence
   rules in [`REVIEW-STATE.md`](REVIEW-STATE.md).
5. Persist owning Beads issue, reviewer session, source boundary, declared assignment scope, findings, resolutions,
   telemetry, and disposition. Never persist a second assignment manifest.
