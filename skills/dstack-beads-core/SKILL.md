---
name: dstack-beads-core
description: "Shared dStack authority, formula-contract, and deterministic-controller rules."
---

# dStack core

Apply these rules to every dStack command.

## Authority

- Beads owns work, dependencies, gates, readiness, and completion.
- Git owns code, tests, durable docs, commits, and delivery history.
- `dstackctl` owns repeatable stateless mechanics.
- The agent owns engineering decisions and user interaction.

## Central compatibility rule

**Formulas define how dStack creates and reviews new work; they are not schemas that existing work must migrate to.**
Historical feature graphs remain valid execution records. dStack uses its packaged formulas as authority before
controller operations. Native pours expose the packaged formula only for that operation; any historical tracked formula
copy is restored unchanged and no persistent formula cache is a dStack authority. Formula `version` is the semantic planning/review contract version, not the dStack package
version.

When a controller returns `status: audit_required`, immediately follow the named skill with the exact returned
`user_input`; this is an internal compatibility audit, not a new user command. Compare the existing approved design and
tasks semantically with the current contract. Do not regenerate, normalize, or relabel historical work merely to match
the current formula shape.

- If no material change is needed, run the returned `feature audit-complete` action and retry the original controller
  command. Do not ask the user for permission.
- If material changes are needed, present only the minimal design/task/dependency delta. Ask for permission before
  reauthorization or task mutation. After the approved delta is reauthorized, `feature approve-spec` records the
  current contract version.

## Hard rules

- Never store Git commit identities in Beads as implementation, delivery, task, evidence, or bookkeeping mappings. Use
  one `Beads: <id>` commit footer.
- Do not store Git revisions in Beads. Alignment plans record reviewed intent only; each execution and delivery boundary
  revalidates the current repository and reconstructs evidence from reachable Git history.
- Never create dStack state files, packets, ledgers, schedulers, migration state, or shadow workflow graphs.
- Do not calculate a ready frontier; query Beads.
- Do not rewrite closed historical Beads because labels, metadata, or task grouping differ from the current formula.
- Do not put transient workflow state or IDs in repository docs. Implementation tasks do not update durable
  documentation; feature closeout or alignment landing is the sole final reconciliation boundary.
- During normal delivery, Beads finalization must not mutate delivered Git state or create bookkeeping commits.
  Explicit user-authorized recovery is a separate native Git operation.
- Use “independent review” only for a separate agent/session. Another review is always allowed when the user authorizes
  it.

## Command pattern

Invoke the bundled controller as `"{baseDir}/../../bin/dstack" ctl`. The controller uses the package-relative locked
runtime while preserving the caller repository as its working directory. Controller commands initialize Beads when needed and use packaged dStack formulas as authority without migrating
historical tracked formula copies or creating persistent formula state.

Read only the Beads, design, source, tests, and docs needed for the current decision. Persist a Beads comment only for a
product decision, material unresolved finding, accepted risk, deferred validation, or meaningful final review outcome.
