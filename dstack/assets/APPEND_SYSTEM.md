## dStack workflow contract

Use the `dstack` CLI for deterministic workflow mechanics, Beads as the sole ready-work surface, and the installed
`dstack-beads-*` skills for engineering decisions.

**Central rule:** formulas define how dStack creates and reviews new work; they are not schemas that existing work must
migrate to. Historical Beads remain execution evidence. Never rewrite closed historical work merely because dStack or a
formula changed.

Use native `bd ready`/claims to select work. dStack inspection may add deterministic Git/worktree facts, but it does not
project the next task, required evidence, or lifecycle state. When Beads surfaces a ready Bead labeled
`dstack:work:formula-audit`, use the feature-specification review skill for the semantic compatibility decision. The Bead
itself blocks affected work; the skill decides whether the existing approved design/tasks still satisfy the current
contract. A no-change audit ends with `dstack ctl feature audit-complete`; a material delta requires user approval before
reauthorization or task mutation.

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
