---
name: dstack-beads-core
description: "Shared dStack authority, state, documentation, review, and deterministic-controller rules."
---

# dStack core

Apply these rules to every dStack command.

## Authority

- Beads owns work, dependencies, gates, readiness, and completion.
- Git owns code, tests, durable docs, commits, and delivery history.
- `dstackctl` owns repeatable stateless mechanics.
- The agent owns engineering decisions and user interaction.

Read `docs/src/development/index.md` and `docs/src/architecture/index.md` when changing the workflow itself. Ordinary
command execution does not require loading every reference document.

## Hard rules

- Never store Git SHAs in Beads. Use one `Beads: <id>` commit footer.
- Never create dStack state files, packets, ledgers, schedulers, or review
  topology.
- Do not calculate readiness; query Beads.
- Do not put transient workflow state or IDs in repository docs.
- `planned`, `implemented`, and `deprecated` are durable product context.
- During normal delivery, Beads finalization must not mutate the delivered Git state or create bookkeeping commits.
  Explicit user-authorized recovery after a failed or incorrect delivery is a separate native Git operation.
- Use “independent review” only for a separate agent/session.
- Another review is always allowed when the user authorizes it.

## Command pattern

Use the bundled controller at `{baseDir}/scripts/dstackctl.py`. References below to `dstackctl.py` mean that exact
script; do not search for or install another executable.

1. Run the relevant `dstackctl.py ... inspect/claim` command.
2. Read only the Bead, design, source, tests, and docs needed for the decision.
3. Perform engineering work and validation.
4. Use `dstackctl git commit` for a real repository change.
5. Use the relevant `finish-*` command for deterministic Beads transitions.

Persist a Beads comment only for a product decision, material unresolved finding, accepted risk, deferred validation, or
a meaningful final review outcome.
