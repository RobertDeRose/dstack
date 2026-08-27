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

- Never store Git commit identities in Beads as implementation, delivery, task, evidence, or bookkeeping mappings. Use
  one `Beads: <id>` commit footer.
- A Git revision may be stored only when it is explicit workflow input requiring an immutable repository snapshot. The
  sole current exception is the canonical project-alignment `baseline_commit`; it is not a work/evidence mapping.
- Never create dStack state files, packets, ledgers, schedulers, or review topology.
- Do not calculate a ready frontier; query Beads. For terminal fan-in only, reject nonterminal direct children before
  and after native ready claim because Beads 1.2.2 can miss them in `children-of(...)`.
- Do not put transient workflow state or IDs in repository docs.
- `planned`, `implemented`, and `deprecated` are durable product context.
- During normal delivery, Beads finalization must not mutate the delivered Git state or create bookkeeping commits.
  Explicit user-authorized recovery after a failed or incorrect delivery is a separate native Git operation.
- Use “independent review” only for a separate agent/session.
- Another review is always allowed when the user authorizes it.

## Command pattern

Invoke the bundled controller as `"{baseDir}/../../bin/dstack" ctl`; the package-relative locked mise launcher is the
only supported command entry point. If tools are missing, report the launcher's portable recovery command rather than
choosing an ambient substitute.

1. Run the relevant `"{baseDir}/../../bin/dstack" ctl ... inspect/claim` command.
2. Read only the Bead, design, source, tests, and docs needed for the decision.
3. Perform engineering work and validation.
4. Use `"{baseDir}/../../bin/dstack" ctl git commit` for a real repository change.
5. Use the relevant `finish-*` command for deterministic Beads transitions.

Persist a Beads comment only for a product decision, material unresolved finding, accepted risk, deferred validation, or
a meaningful final review outcome.
