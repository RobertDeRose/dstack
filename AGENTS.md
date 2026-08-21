# dStack repository contract

Read `docs/src/development/index.md` and `docs/src/architecture/index.md` before changing workflow
architecture.

## Authorities

- Beads: work, dependencies, gates, ready/blocked/closed state, decisions.
- Git: code, tests, configuration, durable docs, commits, delivery history.
- Documentation: stable product and architecture intent.
- `dstackctl`: stateless deterministic orchestration only.
- Pi skills/agents: engineering judgment and user interaction.

## Non-negotiable constraints

- KISS and YAGNI are release requirements.
- Do not add a dStack database, state file, packet protocol, scheduler, ready
  calculation, dependency graph, ownership ledger, reviewer topology, or CI/PR
  poller.
- Stateless helpers are encouraged for repeatable mechanics. They must query
  Beads/Git each time, use native operations, be idempotent, and persist no
  custom state.
- Never store Git commit hashes in Beads. Commits reference work only through
  `Beads: <id>` footers.
- Do not store branch/worktree paths or Git-history mirrors in Beads.
- Do not duplicate feature identity on children when parentage/root labels already establish it.
- Do not put transient lifecycle state, Beads IDs, branches, commits, gates, or next commands in
  user/developer documentation.
- Durable `planned`, `implemented`, and `deprecated` product classification is allowed. It must be
  part of the candidate before delivery.
- During normal delivery, Beads finalization must not mutate the delivered Git state or create a
  post-merge bookkeeping commit. Explicit user-authorized recovery after a failed or incorrect
  delivery is a separate native Git operation.
- Do not require a Git commit when specification review changes no repository content; design
  approval is a content digest.
- Do not claim independent review without a separate reviewer session.
- No finite review counter may override explicit user authorization.
- Normal workflow commands never run legacy repair or rewrite old topology.

## Formula constraints

Formulas contain only the stable four-step lifecycle skeleton. Dynamic product work is ordinary
child Beads. Use a task-sized approval milestone and native `children-of(...)` fan-in. Do not encode
reviewer seats or delivery ceremony.

## Pi package constraints

Public slash commands are prompt aliases. Internal skills stay under the `dstack-beads-*` namespace.
Keep skills short and decision-oriented; exact mechanical choreography belongs in tested scripts.

## Release checks

- YAML/TOML/JSON metadata parses.
- Python compiles and tests pass.
- Skills do not reintroduce prohibited state or SHA mappings.
- Required CI jobs run fast tests and each real-Beads acceptance scenario separately.
- `git diff --check`, `git fsck`, bundle verification, and clean-clone tests pass.
