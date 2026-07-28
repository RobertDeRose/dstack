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
manual baseline. `backup-disposition <retain|remove> --reason <evidence>` resolves conditional backup state. Final
verification requires tracked manifests, reports, baselines, and archived legacy tasks; it rejects candidate directories
and inconsistent backup presence/disposition. Migration stores only answers required for safety/resume, such as
classification, dependency, collision, and artifact dispositions; question prose is not schema state. Checkpoints
require successful `scripts/setup-tooling.py --json`, Pkl evaluation, installed hook routing, and an ordinary commit.
The only intermediate exception is user-approved `HK_SKIP_STEPS=docs` after migration-mode docs. The exact response
`APPROVE HK_SKIP_STEPS=docs`, approved step, reason, equivalent result, and risk are durable evidence.
`checkpoint-evidence --hook <hook> --status <passed|failed|exception> --command <command>` appends
`checkpoint_evidence[]`; exceptions additionally require `--reason`, `--equivalent-result`, `--residual-risk`,
`--approved-step`, and the exact `--approval` phrase.

`beads-authority --init` treats formula-only state as uninitialized, runs non-stealth `bd init` in an isolated temporary
Git repository, and moves the authority into the primary repository without accepting `bd`'s automatic Git commit. It
removes a broad legacy stealth exclude in a primary worktree, or retains a repository-local `.beads/` mirror exclusion
for linked migration isolation. It exposes `.beads/.gitignore`, `README.md`, `config.yaml`, `interactions.jsonl`,
`metadata.json`, and the formula for the workflow-owned commit, makes initialization failure fatal, rejects symlinks,
and validates database path/name, project ID, repository root, and issue prefix. Generated Beads README content carries
an exact machine-authored Markdown exclusion rather than requiring repository formatters to rewrite authority controls.
Global/shared/redirected fallback is never accepted. Later Beads commands carry the validated `.beads` path explicitly;
mutations compare authority digests before and after, while dry-run/verify preserve authority bytes. Embedded database
history is synchronized through a configured Dolt remote and `bd dolt push`; fresh clones use `bd bootstrap` rather than
reconstructing live authority from ordinary branch files or JSONL.

`import-beads` uses `bd --dolt-auto-commit=batch` and commits bounded per-feature state plus relationship phases. Apply
selects at most two incomplete features by default; `--batch-size 1..14` changes that bound and repeatable
`--feature <slug>` narrows scope. It is dry-run by default, reconciles all recorded IDs against actual migration
metadata, and reports `existing`, `recovered`, `pending`, `conflicting`, `completed`, `remaining`, and `total`; only a
separate invocation with `--apply` mutates Beads. Missing completed IDs are conflicts, not existing state. Verification
derives the complete expected roots, lifecycle steps, implementation tasks, reconciliation tasks, statuses, exact
migration-owned labels, parentage, and root relationships; missing, unexpected, malformed-metadata, and unindexable
migration-labeled records are errors. Apply prints `APPLY STARTED` before mutation. Each feature's `beads.import_phase`
is `root-created`, `state`, `relationships`, or `completed`. `beads_import_started_at`, `beads_import_completed_at`,
`beads_import_progress`, imported IDs, and feature phases survive rescans. Empty explicit task status uses checkbox
fallback: `[ ]` is `open`, `[-]` is `in_progress`, and `[x]` is `closed`. A nonempty recognized explicit status takes
precedence.

`prepare --apply` replaces implemented-feature marker bodies from completed features with standalone `index.md` records.
`draft-delivered-records` previews; with `--apply` it writes candidates under
`migration/delivered-record-candidates/<slug>/index.md` and records `delivered_record_candidates[]` with
`reviewed: false`. `review-delivered-record <slug>` requires `--summary`, at least one `--evidence` path, at least one
`--commit`, and `--reason`; it digests the actual implemented record and evidence. Every evidence path must be touched
by a supplied commit. `verify` recomputes commit paths and rejects any completed feature without review,
substituted/duplicate summaries, reused/generated/self evidence, unrelated commits, and missing or changed evidence.
Finalization first reconciles the complete live Beads graph, preflights every destination, journals and stages all
moves, rolls back failed strict documentation validation, and durably saves state before deleting staged evidence.
Manifest/report/baseline paths must be distinct safe migration files and cannot overlap reserved evidence. Finalization
seals archive digests and parsed task identity; final verification recursively compares the exact current archive set
plus feature, design, and legacy-task inventory rather than trusting a finalized manifest alone. Recursive archive
sealing rejects file and directory symlink aliases before reading any candidate bytes.

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
The result JSON and `.copier-answers.yml` record all five values.

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

## Workflow paths

| Path                                          | Contract                                               |
|-----------------------------------------------|--------------------------------------------------------|
| `skills/<name>/SKILL.md`                      | Canonical installed workflow instructions and version. |
| `skills/setup-project/template/`              | Bundled generated-project scaffold.                    |
| `.beads/formulas/dstack-feature.formula.toml` | Project-local feature lifecycle graph.                 |
| `docs/src/features/<slug>/design.md`          | Intended behavior and design decisions.                |
| `docs/src/features/<slug>/index.md`           | Delivered feature reconciliation and evidence.         |
| `docs/src/planned-features.md`                | Human roadmap; not executable state.                   |
| `.copier-answers.yml`                         | Copier-managed template source, revision, and answers. |

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
| `scripts/enable-docs-deployment.py`   | External-`gh` Pages configuration and enablement helper.                        |
| `.github/workflows/validate.yml`      | Locked push and pull-request validation with `contents: read`.                  |
| `.github/workflows/docs.yml`          | Default-branch/manual gated Pages build and deployment.                         |
| `docs/src/development/tooling.md`     | Generated contributor commands and recovery.                                    |
| `docs/src/reference/tooling.md`       | Generated exact tooling contract.                                               |
| `docs/src/operations/github-pages.md` | Generated enablement, recovery, and URL instructions.                           |

### GitHub workflow contract

Validation grants only `contents: read`. Documentation build grants only `contents: read`; deployment alone grants
`pages: write` and `id-token: write` and targets `github-pages`. Both documentation jobs require
`DOCS_DEPLOYMENT_ENABLED == 'true'`. The enable helper configures Pages with `build_type=workflow`, sets that variable
as its last mutation, and returns the Pages `html_url`; external `gh` is not a universal mise tool.

### Universal tools

| Tool                           | Template version |
|--------------------------------|------------------|
| `hk`                           | `1.49.0`         |
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

Both hk Pkl imports use `1.49.0`. Matching validations use hk built-ins and native file locking rather than explicit
ordering. Supported lock targets are `linux-x64`, `linux-arm64`, `macos-x64`, and `macos-arm64`; Windows is outside the
POSIX task contract. With the Nix profile, nixfmt-rs is retained only for Linux x64/ARM64 and macOS ARM64 while every
other tool keeps the four-platform lock.

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
