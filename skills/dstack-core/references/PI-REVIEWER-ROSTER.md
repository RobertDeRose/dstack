# Optional Pi reviewer roster adapter

This reference defines schema `dstack.pi-reviewer-roster.v1`. It is an optional adapter from the dstack
**tool-agnostic logical review roles** to named Pi agent definitions. It does not make Pi a prerequisite for any dstack
workflow and does not change workflow counts, review schemas, convergence policy, or delivery authority.

## Logical review contract

The workflow remains authoritative for the number, freshness, packet boundary, and durable evidence ownership of its
reviewers:

| Workflow             | Context packet              | Independent reviewers                                                          | Launch relation                                                                                                            |
|----------------------|-----------------------------|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| `/start-feature`     | One fresh `context-builder` | Fresh `architecture`, `simplicity`, `documentation`, and `execution` reviewers | The context builder completes synchronously; the four independent reviewers then launch concurrently with the same packet. |
| `/implement-feature` | None                        | One fresh `task` reviewer per selected child                                   | No context builder; the one reviewer is launched for the bounded child.                                                    |
| `/implement-task`    | None                        | One fresh `task` reviewer                                                      | No context builder; the one reviewer is launched for the bounded issue.                                                    |
| `/close-feature`     | One fresh `context-builder` | Fresh `delivery` and `drift` reviewers                                         | The context builder completes synchronously; the two independent reviewers then launch concurrently with the same packet.  |

A Pi adapter selects names for these logical roles; it never adds, removes, serializes, or substitutes reviewers. Each
fresh reviewer receives the exact packet and source boundary required by its owning workflow. Resumption uses the same
logical role, review run, reviewer session, packet identity, and source-boundary rules defined by
[`REVIEW-STATE.md`](REVIEW-STATE.md). The selected feature review bead or standalone task remains the authoritative
owner of `Review state:` and `Finding:` records; the Pi agent definition is not an evidence store.

## Exact Pi mapping

These names are the optional adapter's exact roster. The definitions are discovered from the Pi global agent directory
or project `.pi/agents`; skill assets are not automatically discovered as agent definitions.

| Logical role      | Exact Pi agent definition       | Workflow use                            |
|-------------------|---------------------------------|-----------------------------------------|
| `context-builder` | `dstack-context-builder`        | `/start-feature`, `/close-feature`      |
| `architecture`    | `dstack-architecture-reviewer`  | `/start-feature`                        |
| `simplicity`      | `dstack-simplicity-reviewer`    | `/start-feature`                        |
| `documentation`   | `dstack-documentation-reviewer` | `/start-feature`                        |
| `execution`       | `dstack-execution-reviewer`     | `/start-feature`                        |
| `task`            | `dstack-task-reviewer`          | `/implement-feature`, `/implement-task` |
| `delivery`        | `dstack-delivery-reviewer`      | `/close-feature`                        |
| `drift`           | `dstack-drift-reviewer`         | `/close-feature`                        |

## Explicit installation and synchronization

The versioned definitions are bundled under `skills/dstack-core/assets/pi-reviewers/`; the Pi loader does not discover
skill assets there automatically. When a selected Pi review is missing required names, offer this explicit project-local
sync first:

```bash
uv run <core-dir>/scripts/sync-pi-reviewers.py \
  --target project --project-root <repository> --json
```

A user may instead choose `--target global` (using `PI_CODING_AGENT_DIR/agents`) or an explicit agent-directory path.
The sync command copies definitions, writes `.dstack-pi-reviewers.json` (`dstack.pi-reviewer-install.v1`) with
source/version/hash ownership, validates frontmatter and discovery, and never changes Pi settings. Definitions require
interactive, cmux-capable Pi sessions; context-builder and task reviewers are synchronous, other mapped reviewers are
asynchronous, and model/thinking fields are omitted so they inherit the parent. `--check` is read-only; `--remove`
removes only unchanged files previously installed by dstack. Conflicts are reported without overwriting user files.
Normal `npx skills add` and `npx skills update` remain non-mutating with respect to Pi agent directories.

The interactive workflow offer names the missing logical roles and exact definitions, defaults to project-local sync,
and requires explicit confirmation for every write target. A declined or failed sync returns to the visible
missing-agent failure below; non-interactive controllers print the exact command instead of prompting.

## Adapter invocation rules

1. **Use without mutation.** A Pi-based controller may use this mapping when the named definitions are available. The
   adapter itself must not install, overwrite, copy, or modify global or project Pi configuration. A non-Pi controller
   uses the same logical contract through its own reviewer mechanism.
2. **Resolve before launch.** Resolve every required exact name for the selected workflow before starting its review. If
   a named agent is absent, offer the explicit sync operation above; after a decline or failed sync, fail visibly with
   the logical role and exact name. If an agent is unavailable, fail visibly as well; there is no silent role
   substitution. Do not substitute another agent, reduce or increase the count, or continue with incomplete evidence.
3. **Build packets synchronously.** For `/start-feature` and `/close-feature`, run `dstack-context-builder` to
   completion and verify the supplied packet identity before launching any role reviewer. Do not launch role reviewers
   concurrently with packet creation, and do not let a role reviewer create or replace the shared packet.
4. **Run independent roles concurrently.** Once the packet is complete, launch the independent role reviewers
   concurrently with the same packet, current open finding projection, and source boundary. Their independent sessions
   must not share mutable controller state or launch additional reviewers.
5. **Preserve fresh-context and resumption boundaries.** Every mapped reviewer starts in fresh context as required by
   its workflow. After a fix, resume the same logical role and review run. If that reviewer is unavailable, follow the
   ordinary replacement and convergence rules in `REVIEW-STATE.md`; a replacement remains the same logical role and
   cannot create a second replacement beyond those rules.
6. **Keep evidence in Beads.** Record packet identity, reviewer session, source boundary, findings, resolutions, and
   disposition in the owning review bead or standalone task notes. Pi roster discovery, prompts, and transcripts are
   supporting evidence only and never replace the durable Beads record.

The adapter is unavailable when any required named agent cannot be resolved. That condition is a visible workflow
failure, not permission to change the review plan or make Pi mandatory for other agent harnesses.
