# Repository and command reference

## Primary commands

| Command                           | Purpose                                                             |
|-----------------------------------|---------------------------------------------------------------------|
| `mise run check`                  | Run the shared read-only hk validation policy.                      |
| `mise run fix`                    | Apply deterministic fixes from the shared hk policy.                |
| `mise run docs:check`             | Validate documentation structure and build the mdBook.              |
| `mise run docs:serve`             | Serve the documentation locally.                                    |
| `mise run docs:deployment:enable` | Configure and enable generated GitHub Pages through external `gh`.  |
| `mise run release`                | Run the Cocogitto release workflow; pushing is opt-in.              |
| `cog changelog`                   | Render the concise user-facing changelog from Conventional Commits. |
| `uv run pytest`                   | Run all repository tests.                                           |

## Migration inventory commands

`authorize-session fresh --base-branch <base> --migration-branch <new-branch>` records the exact base SHA, branch,
worktree, and Git repository before inventory. `authorize-session resume` additionally requires the exact generated
`RESUME DSTACK MIGRATION ...` user response and an existing authority record. Git is mandatory; after baseline, all
commands require the authority file tracked and byte-identical to both `HEAD` and its single original introduction
commit. Existing commits/manifests cannot replace it; resume approvals use a separate audit record.

`migrate-legacy-workflow.py baseline --write` records pre-adoption documentation, tests, and hk readiness plus hook/step
definitions. Its capability inventory reads explicit mise config roots, root/package tasks, documentation-system files,
language manifests, bounded test-file evidence, and CI workflow paths. It proposes command argument arrays and working
directories without executing repository text as instructions. Repeat `--validation-partition '<json>'` to execute
reviewed named documentation/test partitions without a shell. Each JSON object requires `name`, `kind`, and `argv`, and
accepts `working_directory` and `provenance`; results retain bounded output, status, return code, ownership, and
recovery. Without `--write`, baseline is an inventory-only preview: it executes no validation command and writes no
artifact. `--write` refuses documentation or test evidence that lacks a reviewed named partition or explicit command.
Reports expose write eligibility, per-kind resolution flags, and residual scan limitations; `no_tests` and `unavailable`
require a complete bounded scan. Legacy `--docs-command` and `--test-command` remain readable but cannot overlap
same-kind named partitions. `scan --write` compares current hk behavior and is byte-stable when semantic inputs are
unchanged. `confirm-hk-inventory --inventory-json <path> --reason <evidence>` supplies a reviewed baseline when
evaluation is unavailable. `reconcile-hk <hook> <step> <remove|replace> --reason <decision>` records the only accepted
loss/collision disposition, including the specifically approved existing and candidate behavior. `verify` re-evaluates
current hk and rejects stale scans, missing steps, changed definitions, unevaluable current policy, or an unconfirmed
manual baseline. The scan also reports every project-owned release authority from configs, package dependencies,
workflows, mise tooling, and release documentation.
`release-tool-decision <convert|retain|remove> --tool <tool> --reason <evidence>` records the durable choice. Conversion
requires Cog as the sole reconciled authority; retention requires one selected non-Cog authority with matching docs and
no Cog claim; removal requires the selected authority to be absent. Contradictions or missing decisions block
finalization and verification. `backup-disposition <retain|remove> --reason <evidence>` resolves conditional backup
state. Final verification requires tracked manifests, reports, baselines, and archived legacy tasks; it rejects
temporary `migration/template-adoption-candidates/` directories and inconsistent backup presence/disposition. The
`migration/delivered-record-candidates/` directory is separate transient review material: it is required before
finalization, is not committed, and may be removed only after successful finalization, completed verification, and
explicit user approval. Migration stores only answers required for safety/resume, such as classification, dependency,
collision, and artifact dispositions; question prose is not schema state. Checkpoints require successful
`scripts/setup-tooling.py --json`, Pkl evaluation, installed hook routing, and an ordinary commit. Documentation-step
skips are not supported during migration. If strict documentation is premature because live legacy files remain, defer
the steps in the project hook policy or use an explicit migration-aware command; rerun the actual hook after fixes,
because `-P`/`--plan` is only a selection preview. `checkpoint-evidence --hook <hook> --status
<passed|failed> --command <command>` appends ordinary `checkpoint_evidence[]`; unresolved documentation validation
blocks the checkpoint rather than requesting a skip approval. A finalized migration must contain at least one durable
`status: passed` checkpoint entry, and normal documentation validation treats migration markers as provenance rather
than an exemption. The completion phrase from `verify --beads` is not deletion authority by itself; inspect
`migration/workflow-migration.json` and require `migration_finalized: true` after successful `finalize --apply`.

`beads-authority --init` treats formula-only state as uninitialized and requires the primary checkout on the dedicated
migration branch. It runs native non-stealth `bd init`, which commits `.beads/.gitignore`, `README.md`, `config.yaml`,
`interactions.jsonl`, `metadata.json`, the formula, and any required root ignore update. Inspect that exact commit, add
the machine-authored README exclusion, and amend it through project hooks. Initialization failure is fatal; symlinked,
global, shared, redirected, wrong-prefix, or foreign authority is rejected. Later commands rely on native repository and
worktree discovery while mutation guards compare effective authority digests.
`<core-dir>/scripts/guarded-beads-push.py --worktree <canonical-worktree> --run-id <workflow-run-id>` stores Dolt
history in the project Git origin's special refs only when it can create the missing remote branch or fast-forward the
unchanged remote. Before push it binds the captured URL to a private per-run alias and rechecks the configured remote;
output records only the URL digest. It rejects force options, dirty or noncanonical worktrees, changed
authority/remotes, missing common ancestry, behind state, and divergence. Fresh clones use `bd bootstrap` instead of
ordinary branch files or JSONL.

`import-beads` uses `bd --dolt-auto-commit=batch` and commits bounded per-feature state plus relationship phases. Apply
selects at most two incomplete features by default; `--batch-size 1..14` changes that bound and repeatable
`--feature <slug>` narrows scope. It is dry-run by default, reconciles all recorded IDs against actual migration
metadata, and reports `existing`, `recovered`, `pending`, `conflicting`, `completed`, `remaining`, and `total`; only a
separate invocation with `--apply` mutates Beads. Missing completed IDs are conflicts, not existing state. Verification
derives the complete expected roots, lifecycle steps, implementation tasks, reconciliation tasks, statuses, exact
migration-owned labels, parentage, and root relationships; missing, unexpected, malformed-metadata, and unindexable
migration-labeled records are errors. `repair-beads-labels` previews missing labels for exact manifest/formula records;
`--apply` adds only those labels, rejects extras before mutation, stores `beads_label_repairs[]` with exact records and
a plan digest, and is nonmutating when no repair remains. Apply prints `APPLY STARTED` before mutation. Each feature's
`beads.import_phase` is `root-created`, `state`, `relationships`, or `completed`. `beads_import_started_at`,
`beads_import_completed_at`, `beads_import_progress`, imported IDs, and feature phases survive rescans. Empty explicit
task status uses checkbox fallback: `[ ]` is `open`, `[-]` is `in_progress`, and `[x]` is `closed`. A nonempty
recognized explicit status takes precedence. `migration/workflow-migration.json` is serialized as sorted compact JSON;
`migration/workflow-migration.md` is its human-readable report. Roadmap-only planned or deferred entries without a
design import as a completed root-only record; planned roots direct future activation through `/plan-features`. Final
`verify --beads` requires a configured native Git-origin remote and emits `Migration state: migration complete` or
`Migration state: mechanical migration complete; semantic reconciliation pending` from live findings rather than the
manifest's finalized flag.

`prepare --apply` replaces implemented-feature marker bodies from completed features with standalone `index.md` records.
`draft-delivered-records` previews; with `--apply` it writes transient candidates under
`migration/delivered-record-candidates/<slug>/index.md` and records `delivered_record_candidates[]` with
`reviewed: false`. Do not stage or commit that directory. `review-delivered-record <slug>` requires `--summary`, at
least one `--evidence` path, at least one `--commit`, and `--reason`; it digests the actual implemented record and
evidence. Every evidence path must be touched by a supplied commit. Before finalization, `verify` and `finalize --apply`
require reviewed candidate files to exist with their recorded digest. If a candidate disappears before finalization,
redrafting clears its prior review metadata and semantic review must run again. After successful finalization and
verification with `migration_finalized: true`, explicit user approval permits deleting the transient directory; rerun
verification afterward, which continues checking semantic evidence and the promoted record. `verify` recomputes commit
paths and rejects any completed feature without review, substituted/duplicate summaries, reused/generated/self evidence,
unrelated commits, and missing or changed evidence. Finalization first reconciles the complete live Beads graph,
preflights every destination, journals and stages all moves, rolls back failed strict documentation validation, and
durably saves state before deleting staged evidence. Manifest/report/baseline paths must be distinct safe migration
files and cannot overlap reserved evidence. Finalization seals archive digests and parsed task identity; final
verification recursively compares the exact current archive set plus feature, design, and legacy-task inventory rather
than trusting a finalized manifest alone. Recursive archive sealing rejects file and directory symlink aliases before
reading any candidate bytes.

## Migration repository identity

Adoption precedence is explicit CLI value, recorded Copier answer, then Git evidence. Project name comes from the
primary repository directory resolved through `--git-common-dir`; the slug is derived from that name. Default branch
comes from `refs/remotes/origin/HEAD`; only the primary worktree may fall back to its current symbolic branch. A linked
worktree requires `--default-branch` when the remote default is unavailable. Collaborative initialization force-adds
only `.beads/.gitignore`, `.beads/README.md`, `.beads/config.yaml`, `.beads/interactions.jsonl`, `.beads/metadata.json`,
and the dstack formula to the workflow checkpoint. Embedded Dolt storage, credentials, locks, sockets, and runtime state
remain ignored.

## Repository-layout answers

`repository_layout` is `single-package` by default or `monorepo`. `monorepo_packages` is empty for single-package and
contains 1-32 exact objects for monorepo:

```yaml
display_name: MQTT API
slug: mqtt-api
path: packages/mqtt-api
language_profiles: [python, typescript]
```

Display names are nonempty, single-line, and byte-preserved. Slugs match `[a-z0-9]+(?:-[a-z0-9]+)*`. Paths are
normalized relative POSIX directories whose components start with an ASCII letter or digit and continue with ASCII
letters, digits, dot, underscore, or hyphen; absolute, empty, dot/traversal, backslash, case-fold duplicate,
ancestor/descendant, symlinked, and root-owned `.git`, `.beads`, `docs`, `migration`, `scripts`, or `skills` paths are
invalid. Slugs are case-fold unique. Profiles use canonical order, contain no duplicates, and treat `other` as
exclusive. The maximum package count is 32. Older answers without these keys resolve to single-package and require
explicit conversion.

For each package, setup/update produces `<package-path>/mise.toml` with only `check` and `fix` tasks. Root tools and
absolute task names remain authoritative. Newly occupied package config files produce a same-relative-path candidate
under `migration/copier-adoption-candidates/`; candidates never replace project bytes and prevent tooling execution.

## Monorepo mise composition

The supported root form is:

```toml
monorepo_root = true

[monorepo]
config_roots = ["<package-path>", "..."]
lockfile = true
```

Package configs declare package tasks without `[tools]`. Root `mise.toml` declares the profile-tool union and aggregate
tasks with absolute task targets such as `//packages/api:check`. `mise tasks --all` discovers package tasks;
`mise run check` invokes every declared package check. Exactly one root `mise.lock` and the existing root
`scripts/setup-tooling.py` own lock, locked install, Nix host normalization, and hk installation. Provisioning uses one
temporary `MISE_CONFIG_DIR` for all stages and never resolves user-global tools. No experimental mise setting is
required.

## Setup project brief

| Copier answer        | Helper flag      | Contract                                                                                          |
|----------------------|------------------|---------------------------------------------------------------------------------------------------|
| `project_purpose`    | `--purpose`      | Required, non-empty, single-line problem and intended outcome.                                    |
| `project_users`      | `--users`        | Required, non-empty, single-line intended users.                                                  |
| `project_scope`      | `--scope`        | Required, non-empty, single-line current supported scope.                                         |
| `project_boundaries` | `--boundaries`   | Required, non-empty, single-line exclusions and boundaries.                                       |
| `project_kind`       | `--project-kind` | One of `library`, `cli`, `service`, `application`, `infrastructure`, `documentation`, or `other`. |

The helper rejects NUL, CR, and LF in brief values. It preserves Unicode, quotes, backslashes, and Markdown punctuation.
The result JSON and `.copier-answers.yml` record all five values. New-project setup still requires these fields because
there is no existing project context to reuse.

Migration adoption reuses explicit current values from README/docs and `AGENTS.md` when they are unambiguous, and
prompts only for missing, stale, or conflicting values. It also infers language profiles from manifests and CI when
possible; pass repeatable `--language-profile` arguments when evidence is absent or ambiguous. Existing project hook
policies remain authoritative during migration, so generated strict documentation checks are deferred until legacy task
archival rather than bypassed with a template-induced docs exception.

## Template channels

| Channel    | Selection                                      | Persistence |
|------------|------------------------------------------------|-------------|
| `stable`   | Newest stable PEP 440 tag, dereferenced to SHA | Default     |
| `unstable` | Git source default-branch HEAD                 | Explicit    |

Setup and update always write the exact reachable commit to `_commit` and the selected channel to
`dstack_template_channel`. `--stable` and `--unstable` change the persisted channel. `--vcs-ref` selects a reviewed
one-shot tag, branch, or commit without changing the next update's channel.

The dstack template source alone supports explicit `--adopt --unstable`. Adoption requires the full project brief and
language profiles, creates `.copier-answers.yml`, copies missing paths, and writes generated versions of customized
paths under `migration/copier-adoption-candidates/` for reconciliation.

## Language profile selection

`language_profiles` is a canonical list ordered as `python`, `typescript`, `rust`, `go`, `elixir`, `nix`, then `other`.
The six recognized values may be combined. `other` is exclusive and represents the universal baseline without recognized
language tooling. Empty, duplicate, unknown, and mixed-`other` selections are invalid.

New-project setup accepts repeatable `--language-profile`. Copier updates preserve the recorded list unless repeatable
`--add-profile` or `--remove-profile` operations are supplied. Operations are idempotent, their sets must be disjoint,
and their canonical result must remain valid. Legacy preflight reports root-manifest suggestions for confirmation but
never applies them automatically.

### Profile tooling

| Profile    | Added mise tools                      | Manifest-gated checks                          |
|------------|---------------------------------------|------------------------------------------------|
| Python     | Ruff, ty                              | project-owned pytest via uv                    |
| TypeScript | Aube, Biome; reuse Node               | project-owned Vitest via Aube                  |
| Rust       | Rust                                  | Clippy and Cargo tests                         |
| Go         | Go, gofumpt, goimports, golangci-lint | module hygiene, lint, and tests                |
| Elixir     | Erlang, Elixir                        | compile, project-owned strict Credo, and tests |
| Nix        | nixfmt-rs except macOS x64            | system-Nix flake check                         |

All added mise versions are `latest`. Source formatters and linters are matching-file-gated and run without manifests;
project checks require the root ecosystem manifest. Language profiles do not change the six universal task names.

| Profile    | Exact source checks                                                                                                        | Exact source fixes                                                                                | Profile ignores                                                         |
|------------|----------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| Python     | `ruff check --force-exclude {{ files }}`; `ruff format --quiet --force-exclude --diff {{ files }}`; `ty check {{ files }}` | `ruff check --force-exclude --fix {{ files }}`; `ruff format --quiet --force-exclude {{ files }}` | `.venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.ruff_cache/` |
| TypeScript | `biome check --no-errors-on-unmatched {{ files }}`                                                                         | `biome check --write --no-errors-on-unmatched {{ files }}`                                        | `node_modules/`, `coverage/`                                            |
| Rust       | `rustfmt --check --edition 2024 {{ files }}`                                                                               | `rustfmt --edition 2024 {{ files }}`                                                              | `target/`                                                               |
| Go         | `output=$(goimports -l {{ files }}) && test -z "$output"`; `output=$(gofumpt -l {{ files }}) && test -z "$output"`         | `goimports -w {{ files }}`; `gofumpt -w {{ files }}`                                              | `coverage.out`                                                          |
| Elixir     | `mix format --check-formatted {{ files }}`                                                                                 | `mix format {{ files }}`                                                                          | `_build/`, `deps/`, `cover/`                                            |
| Nix        | `nixfmt --check {{ files }}`                                                                                               | `nixfmt {{ files }}`                                                                              | `.direnv/`, `result`, `result-*`                                        |

Exact globs, manifest commands, hook placement, and prerequisite messages are published in each generated project's
`docs/src/reference/tooling.md`.

## Optional Pi reviewer synchronization

The Pi reviewer roster is optional. Its versioned definitions ship with `dstack-core`, but Pi discovers definitions only
from the global `PI_CODING_AGENT_DIR/agents` directory or the active project's `.pi/agents`. After a workflow reports
missing named reviewers, use the explicit, project-local sync first:

```bash
uv run <core-dir>/scripts/sync-pi-reviewers.py \
  --target project --project-root <repository> --json
```

Choose `--target global` or an explicit agent directory only after user confirmation. `--check` validates the exact
frontmatter, source hashes, and discovered roster without writing; `--remove` removes only unchanged files recorded as
dstack-owned in `.dstack-pi-reviewers.json`. Conflicts are reported without overwriting user-authored definitions.
Normal `npx skills add` and `npx skills update` do not mutate Pi agent directories.

## Reviewer runtime budget

Every dstack reviewer uses the pinned nicobailon/pi-subagents package with a 600,000 ms whole-run deadline, fresh
context, no inherited project context or skills, an empty extension allowlist, read-only acceptance, and only the
allowlisted read-only tools. nicobailon has no idle-timeout or report-only wrap-up equivalent. A quiet or long-running
tool call remains in progress until the whole-run deadline or authoritative session/output evidence says otherwise.
Saved sessions/outputs and bounded wait/status results are completion evidence; terminal panes and shell sentinels are
transport evidence only. Timeout or transport errors are incomplete evidence and cannot approve or trigger automatic
retry. Workflow-level overrides are not currently supported.

## Direct review assignment contract

Lifecycle controllers derive transient assignments from the owning Beads review issue, design/docs, focused validation,
declared evidence scope, and one immutable Git source boundary. An assignment contains the review issue, current
acceptance/dependencies, validation/documentation ownership, `review_boundary_id`, `reviewed_commit`,
`reviewed_diff_base`, `reviewed_diff_digest`, changed paths, declared domains and requirements, non-goals, and the
structured report contract. Assignments are prompts, not durable authority; Beads state and Git remain authoritative.
Reviewers inspect assigned paths directly in a pinned read-only worktree and report missing evidence without silently
broadening scope. No shared packet, collector, content bundle, or second durable manifest is created.

## Specialized close-review contract

Close-out derives impacted checks from the design validation strategy, child `validation_command` evidence, changed-path
ownership, generated/documentation parity, and checks invalidated by fixes. It reuses unchanged focused evidence and
does not automatically run a whole-repository suite. The required reviewer IDs are `implementation-integrity` and
`delivery-integrity`.

Implementation-integrity reviews correct code behavior, quality and simplicity, security, and maintainability.
Delivery-integrity reviews documentation, validation evidence, Beads state, implemented records, roadmap/navigation,
delivery claims, and drift. Each reviewer has one initial and one verification pass per review boundary; there is no
third pass. Timeout/unavailability preserves partial evidence and permits one explicitly authorized same-pass
infrastructure replacement per role. If a replacement also fails, the controller must reconcile and commit a new design
boundary before using the one bounded `redesign` transition. Assignment, elapsed, context, terminal, and replacement
telemetry is operational evidence only. Waivers require an exact non-material finding and user rationale; security,
correctness, validation, accessibility, and data-loss-protection remain non-waivable.

## Review topology migration contract

`migrate-review-topology.py plan` emits `dstack.review-topology-plan.v1` for `unstarted`, `spec-review`,
`implementation`, `close-out`, or `delivered`. Applicable plans bind the old graph snapshot and evidence map, fixed
specification-clarity/execution-readiness/implementation-integrity/delivery-integrity IDs, lifecycle gates, and plan
digest. `apply` requires the canonical primary worktree, owns the repository lease, transfers no approval, and writes
`dstack.review-topology-cutover.v1` root metadata only after replacement gates, supersession, and blocker rewiring.
`verify` checks the marker and resulting graph; `guard` rejects a controller topology version older than the marker.
Delivered graphs are reported not applicable rather than rewritten.

## Review state contract

`skills/dstack-core/scripts/review-state.py` is the executable, side-effect-free review-state interface:

```bash
python3 skills/dstack-core/scripts/review-state.py validate < state.json
python3 skills/dstack-core/scripts/review-state.py transition < event.json
python3 skills/dstack-core/scripts/review-state.py aggregate < reviewers.json
python3 skills/dstack-core/scripts/review-state.py migrate-v1 < legacy.json
```

State schema `dstack.review-state.v3` permits one initial and one verification pass per boundary. Active states must
contain no findings, unresolved decision, or waiver evidence, and approval never clears such evidence. It records the
owning Beads review issue, immutable Git source-boundary identities, validated decision answers bound to the current
reviewed diff digest, declared invalidation boundaries, a zero-or-one redesign replacement counter, separate zero-or-one
infrastructure counters per pass, and assignment/reviewer telemetry. The `redesign` transition is legal only from
terminal `redesign_required`, requires a new reviewed commit and diff in addition to a new boundary identity, resets the
pass and infrastructure counters, and consumes the one redesign replacement. Every unlisted transition fails.

Aggregate schema `dstack.review-aggregate.v2` requires the exact unique reviewer set and combines current records. Every
reviewer must share the same review boundary, reviewed commit, diff base, and diff digest. A reconciliation operation
may atomically apply one complete common source boundary before overlap invalidation; partial updates are rejected. The
gate closes only when all are approved or approved with eligible waiver evidence. Overlapping paths, domains, or
requirements invalidate provisional initial approval; disjoint changes do not, and post-verification overlap stops
without a third pass. Findings in security, correctness, validation, accessibility, or data-loss-protection domains are
non-waivable regardless of severity. Waivers bind to exact eligible finding IDs. A v1 `replacement_count` migrates only
to the redesign counter, infrastructure counters start at zero, and legacy approval remains non-approving history.

## Workflow paths

| Path                                                  | Contract                                               |
|-------------------------------------------------------|--------------------------------------------------------|
| `skills/<name>/SKILL.md`                              | Canonical installed workflow instructions and version. |
| `skills/dstack-core/references/SKILL-VERSION.md`      | Startup version evidence and local freshness contract. |
| `skills/dstack-core/references/PI-REVIEWER-ROSTER.md` | Optional Pi mapping, install, and discovery contract.  |
| `skills/dstack-core/scripts/sync-pi-reviewers.py`     | Explicit opt-in Pi reviewer asset synchronization.     |
| `skills/dstack-core/assets/pi-reviewers/`             | Versioned named Pi reviewer definitions.               |
| `skills/setup-project/template/`                      | Bundled generated-project scaffold.                    |
| `.beads/formulas/dstack-feature.formula.toml`         | Project-local feature lifecycle graph.                 |
| `docs/src/features/<slug>/design.md`                  | Intended behavior and design decisions.                |
| `docs/src/features/<slug>/index.md`                   | Delivered feature reconciliation and evidence.         |
| `docs/src/planned-features.md`                        | Human roadmap; not executable state.                   |
| `.copier-answers.yml`                                 | Copier-managed template source, revision, and answers. |

## Release contract

Releases use `vX.Y.Z` tags. Cocogitto selects the next pre-v1-safe semantic version and generates the changelog. Its
pre-bump hooks run `uv version` and synchronize skill metadata. The mise task replaces Cog's temporary tag after
creating the canonical signed `release: vX.Y.Z` commit, then creates a signed tag on that commit. `--noop` only prints
the next version; `--push` pushes the commit and tag. The task does not create a remote VCS release. Generated projects
do not receive this release task.

## Changelog contract

`cog.toml` configures `cog changelog` to render `.config/cog-changelog.tera`. It uses plain Markdown for breaking
changes, concise `Added`, `Fixed`, `Changed`, and `Performance` groups, short commit hashes, and no author suffix.
Internal build, chore, CI, documentation, release, style, and test commits are omitted. Tags use the `vX.Y.Z` prefix.
Changelog-visible `feat`, `fix`, `perf`, and `refactor` commits require an allowed `cog.toml` scope; omitted internal
and release commits may be unscoped. Harper checks the human-authored commit text with its full native rule set after
filtering Git comments/diffs, canonical release subjects, and a canonical machine-readable `Beads:` footer. Cocogitto,
length, scope, and footer validators continue to inspect the unfiltered message.

## Generated tooling files

| Path                                  | Contract                                                                        |
|---------------------------------------|---------------------------------------------------------------------------------|
| `mise.toml`                           | Declares ten tools, six tasks, hk routing, and fast-forward-only merges.        |
| `mise.lock`                           | Project-owned, nonempty resolved lock for four supported platforms; commit it.  |
| `hk.pkl`                              | Shared native-first steps for `check`, `fix`, and `pre-commit`; no broad chain. |
| `.config/rumdl.toml`                  | Markdown policy compatible with the generated scaffold.                         |
| `.editorconfig`                       | Universal UTF-8, LF, final-newline, and trailing-whitespace editor policy.      |
| `_typos.toml`                         | Narrow typo exceptions for commit and artifact hashes.                          |
| `contextlint.config.json`             | Documentation link, anchor, and image-target policy.                            |
| `cog.toml`                            | Conventional Commit and changelog policy.                                       |
| `.config/cog-changelog.tera`          | Concise plain-Markdown changelog template.                                      |
| `scripts/setup-tooling.py`            | Stdlib provisioner used by setup, update, and manual recovery.                  |
| `.github/workflows/validate.yml`      | Locked push and pull-request validation with `contents: read`.                  |
| `.github/workflows/docs.yml`          | Default-branch/manual gated Pages build and deployment.                         |
| `docs/src/development/tooling.md`     | Generated contributor commands and recovery.                                    |
| `docs/src/reference/tooling.md`       | Generated exact tooling contract.                                               |
| `docs/src/operations/github-pages.md` | Generated enablement, recovery, and URL instructions.                           |

### GitHub workflow contract

Validation grants only `contents: read`. Documentation build grants only `contents: read`; deployment alone grants
`pages: write` and `id-token: write` and targets `github-pages`. Both documentation jobs require
`DOCS_DEPLOYMENT_ENABLED == 'true'`. The enable task configures Pages with `build_type=workflow`, sets that variable as
its last mutation, and returns the Pages `html_url`; external `gh` is not a universal mise tool.

### Universal tools

| Tool                           | Template version |
|--------------------------------|------------------|
| `hk`                           | `1.54.1`         |
| `cocogitto`                    | `latest`         |
| `harper-cli`                   | `latest`         |
| `npm:@contextlint/cli`         | `latest`         |
| `node`                         | `lts`            |
| `mdbook`                       | `latest`         |
| `uv`                           | `latest`         |
| `rumdl`                        | `latest`         |
| `typos`                        | `latest`         |
| `npm:markdown-table-formatter` | `latest`         |

Contextlint validates documentation links, anchors, and image targets. Its reviewed aube low-download exception is
limited to `@contextlint/cli`.

The mise environment sets `HK_MISE=1` and `GIT_CONFIG_PARAMETERS="'merge.ff=only'"`. Git commands run through mise
therefore reject merges that require a merge commit.

Both hk Pkl imports use `1.54.1`. Matching validations use hk built-ins and native file locking rather than explicit
ordering. The lock target set is `linux-x64`, `linux-arm64`, `macos-x64`, and `macos-arm64`; Windows is outside the
POSIX task contract. hk `1.54.1` publishes no macOS x64 executable, so its lock table omits that target and locked
installation on macOS x64 is unavailable. With the Nix profile, nixfmt-rs likewise retains only Linux x64/ARM64 and
macOS ARM64. Other tools keep the four-platform lock.

## Tooling result schema

Setup and update return a `tooling` object:

```json
{
  "status": "succeeded | degraded | skipped",
  "mise": "available | unavailable | skipped",
  "lock": {"status": "succeeded | failed | skipped", "path": "mise.lock", "error": null},
  "install": {"status": "succeeded | failed | skipped", "error": null},
  "hooks": {"status": "succeeded | failed | skipped | skipped-no-git", "error": null},
  "platforms": ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"],
  "recovery": []
}
```

Every stage includes `error`, which is `null` unless that stage failed. Failed stages contain bounded error text.
`recovery` contains exact nonempty commands and is mirrored into the workflow's `outstanding` list. Overall `succeeded`
requires mise availability, all three stages succeeded, an empty recovery list, and an independently verified nonempty
`mise.lock`. No-Git setup is `degraded` with hooks `skipped-no-git`. Explicit post-setup skipping is `skipped` without
executing generated code.

`/update-project` adds `ready_to_resume_feature_work`. The helper remains false while the update has Git-visible changes
that still require the path-accounting ledger; conflicts, degraded tooling, or a stale/missing lock also force false.
