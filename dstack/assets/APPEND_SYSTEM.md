## dStack workflow contract

Use the `dstack` CLI for deterministic workflow mechanics, Beads as the sole ready-work surface, and the installed
`dstack-beads-*` skills for engineering decisions.

**Central rule:** formulas define how dStack creates and reviews new work; they are not schemas that existing work must
migrate to. Historical Beads remain execution evidence. Never rewrite historical topology merely because dStack or a
formula changed; there is no setup or adoption migration workflow.

Use native `bd ready`/claims to select work. dStack inspection may add deterministic Git/worktree facts, but it does not
project the next task, required evidence, or lifecycle state. Formula drift never creates workflow work or rewires the
approved graph and never overrides native Beads readiness. When explicitly reviewing an approved feature under a newer
or unknown formula contract, use the feature-specification review skill to compare the existing approved Beads intent
semantically. A no-change audit ends with the explicit `dstack ctl feature audit-complete` root-version update; a
material delta requires user approval and reuses the existing reauthorization/specification boundary.

Guardrails:

- Beads owns work, dependencies, gates, readiness, claims, and completion; Git owns code, tests, durable docs, commits,
  and delivery history.
- Use `dstack ctl ...`; do not call dStack Python modules directly or reproduce controller mechanics in shell.
- Do not create dStack state files, migration ledgers, readiness caches, Git-to-Beads mappings, shadow workflow graphs,
  or inter-agent handoff packets.
- Fix clear in-scope discoveries inside the selected task. Use native Beads follow-up work only for genuinely separate
  work; do not broaden scope mechanically.
- A review supplies evidence, not workflow authority. Another review is allowed when the user authorizes it; call it
  independent only when a separate read-only agent/session performed it.
- Implementation/correction tasks do not update durable documentation. Feature closeout or alignment landing is the
  final reconciliation boundary.
