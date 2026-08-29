## dStack workflow contract

Use the `dstack` CLI for deterministic workflow mechanics and the installed `dstack-beads-*` skills for engineering
decisions.

**Central rule:** formulas define how dStack creates and reviews new work; they are not schemas that existing work must
migrate to. Historical Beads remain execution evidence. Never rewrite closed historical work merely because dStack or a
formula changed.

Before a dStack transition, trust the controller's infrastructure/formula checks. If a controller exits with
`status: audit_required`, immediately load the skill named in that payload using its exact `user_input`. This is an
internal semantic compatibility review, not a user-visible migration command. If the existing approved design/tasks
already satisfy the current formula contract, run the returned `feature audit-complete` action and retry the original
command without asking the user. If a material delta is required, show only that minimal design/task/dependency delta
and obtain user approval before reauthorization or task mutation.

Guardrails:

- Beads owns work, dependencies, gates, readiness, claims, and completion; Git owns code, tests, durable docs, commits,
  and delivery history.
- Use `dstack ctl ...`; do not call dStack Python modules directly or reproduce controller mechanics in shell.
- Do not create dStack state files, migration ledgers, readiness caches, Git-to-Beads mappings, or shadow workflow
  graphs.
- Fix clear in-scope discoveries inside the selected task. Use native Beads follow-up work only for genuinely separate
  work; do not broaden scope mechanically.
- A review supplies evidence, not workflow authority. Another review is allowed when the user authorizes it; call it
  independent only when a separate read-only agent/session performed it.
- Implementation/correction tasks do not update durable documentation. Feature closeout or alignment landing is the
  final reconciliation boundary.
