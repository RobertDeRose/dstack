# dStack repository contract

Read `docs/src/development/index.md` and `docs/src/architecture/index.md` before changing workflow
architecture.

## Authorities

- Beads: work, dependencies, gates, ready/blocked/closed state, decisions.
- Git: code, tests, configuration, durable docs, commits, delivery history.
- Documentation: stable product and architecture intent.
- `dstack` CLI: stateless deterministic orchestration only.
- Pi skills/agents: engineering judgment and user interaction.

## Non-negotiable constraints

- KISS and YAGNI are release requirements.
- Do not add a dStack database, state file, packet protocol, scheduler, ready calculation,
  dependency graph, ownership ledger, reviewer topology, or CI/PR poller.
- Stateless helpers are encouraged for repeatable mechanics. They must query Beads/Git each time,
  use native operations, be idempotent, and persist no custom state.
- Never store Git commit identities in Beads as implementation, delivery, task, evidence, or
  bookkeeping mappings. Commits reference work only through `Beads: <id>` footers.
- Do not store Git revisions or repository snapshots in Beads. Alignment plans store reviewed
  intent only and revalidates the current repository evidence at execution and delivery boundaries.
- Do not store branch/worktree paths or Git-history mirrors in Beads.
- Do not duplicate feature identity on children when parentage/root labels already establish it.
- Do not put transient lifecycle state, Beads IDs, branches, commits, gates, or next commands in
  user/developer documentation.
- Implementation and correction tasks do not create documentation or reconciliation work; each
  feature/alignment has one final closeout/landing reconciliation.
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

**Central rule:** formulas define how dStack creates and reviews new work; they are not schemas that existing work must
migrate to. Historical feature graphs remain valid execution records and are never normalized merely because dStack or
a formula changed.

Formulas contain only the stable four-step lifecycle skeleton and a semantic contract version. Dynamic product work is
ordinary child Beads. Packaged formulas are authoritative; native pours expose the packaged source only for the pour and
restore any historical tracked formula copy unchanged. No persistent formula cache becomes repository authority. When an approved active feature
has a missing/stale audited formula version, the controller requests an internal semantic specification audit. A
no-change audit stamps the current contract version and continues without user involvement; a material design/task delta
requires renewed user approval before mutation. Compare semantic coverage, not task names or topology.

Use a task-sized approval milestone and native `children-of(...)` fan-in. Do not encode reviewer seats or delivery
ceremony. Do not add formula-migration state, historical graph normalization, or setup/recovery workflows.

## Installed CLI and Pi resource constraints

`dstack` is a normal Python tool installed with `uv tool install`; controller code lives in the top-level `dstack/`
package, never inside a skill. `dstack install_skills` owns installation of dStack prompt templates and decision skills
into Pi. The stable cross-workflow guardrails are installed as a managed block in Pi's `APPEND_SYSTEM.md`; there is no
`dstack-beads-core` skill.

Public slash commands are prompt aliases. Decision skills stay under the `dstack-beads-*` namespace and call `dstack ctl
...` from `PATH`. Keep skills short and decision-oriented; exact mechanical choreography belongs in the tested CLI.
The installer may overwrite dStack-owned prompt/skill names and its own marked system-prompt block, but must preserve
unrelated user Pi configuration and system-prompt content.

## Release checks

- YAML/TOML/JSON metadata parses.
- Python compiles and tests pass.
- Installed skills/system guidance do not reintroduce prohibited state or SHA mappings.
- `uv build` includes the CLI, formulas, prompts, skills, and system-prompt additive; `dstack install_skills` is idempotent.
- Required CI jobs run fast tests and each real-Beads acceptance scenario separately.
- `git diff --check`, `git fsck`, bundle verification, and clean-clone tests pass.
