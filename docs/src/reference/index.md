# Repository and command reference

## Primary commands

| Command                           | Purpose                                                               |
|-----------------------------------|-----------------------------------------------------------------------|
| `mise run check`                  | Run the shared read-only hk validation policy.                        |
| `mise run fix`                    | Apply deterministic fixes from the shared hk policy.                  |
| `mise run docs:check`             | Validate documentation structure and build the mdBook.                |
| `mise run docs:serve`             | Serve the documentation locally.                                      |
| `mise run docs:deployment:enable` | Configure and enable generated GitHub Pages through external `gh`.    |
| `mise run release`                | Run semantic-release with signed commits and tags; pushing is opt-in. |
| `cog changelog`                   | Render the concise user-facing changelog from Conventional Commits.   |
| `uv run pytest`                   | Run all repository tests.                                             |

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

Releases use `vX.Y.Z` tags. Python Semantic Release synchronizes the project version, lockfile, and skill metadata
versions. Git configuration injected by the mise task requires both the release commit and annotated tag to be signed.
The task does not create a remote VCS release and does not push unless requested. Generated projects do not receive this
release task.

## Changelog contract

`cog.toml` configures `cog changelog` to render `.config/cog-changelog.tera`. It uses plain Markdown for breaking
changes, concise `Added`, `Fixed`, `Changed`, and `Performance` groups, short commit hashes, and no author suffix.
Internal build, chore, CI, documentation, release, style, and test commits are omitted. Tags use the `vX.Y.Z` prefix.

## Generated tooling files

| Path                                  | Contract                                                                       |
|---------------------------------------|--------------------------------------------------------------------------------|
| `mise.toml`                           | Declares seven tools, six tasks, hk routing, and fast-forward-only merges.     |
| `mise.lock`                           | Project-owned, nonempty resolved lock for four supported platforms; commit it. |
| `hk.pkl`                              | One shared step map for `check`, `fix`, and `pre-commit`.                      |
| `.config/rumdl.toml`                  | Markdown policy compatible with the generated scaffold.                        |
| `scripts/setup-tooling.py`            | Stdlib provisioner used by setup, update, and manual recovery.                 |
| `scripts/enable-docs-deployment.py`   | External-`gh` Pages configuration and enablement helper.                       |
| `.github/workflows/validate.yml`      | Locked push and pull-request validation with `contents: read`.                 |
| `.github/workflows/docs.yml`          | Default-branch/manual gated Pages build and deployment.                        |
| `docs/src/development/tooling.md`     | Generated contributor commands and recovery.                                   |
| `docs/src/reference/tooling.md`       | Generated exact tooling contract.                                              |
| `docs/src/operations/github-pages.md` | Generated enablement, recovery, and URL instructions.                          |

### GitHub workflow contract

Validation grants only `contents: read`. Documentation build grants only `contents: read`; deployment alone grants
`pages: write` and `id-token: write` and targets `github-pages`. Both documentation jobs require
`DOCS_DEPLOYMENT_ENABLED == 'true'`. The enable helper configures Pages with `build_type=workflow`, sets that variable
as its last mutation, and returns the Pages `html_url`; external `gh` is not a universal mise tool.

### Universal tools

| Tool                           | Template version |
|--------------------------------|------------------|
| `hk`                           | `1.49.0`         |
| `node`                         | `lts`            |
| `mdbook`                       | `latest`         |
| `uv`                           | `latest`         |
| `rumdl`                        | `latest`         |
| `typos`                        | `latest`         |
| `npm:markdown-table-formatter` | `latest`         |

The mise environment sets `HK_MISE=1` and `GIT_CONFIG_PARAMETERS="'merge.ff=only'"`. Git commands run through mise
therefore reject merges that require a merge commit.

Both hk Pkl imports use `1.49.0`. Supported lock targets are `linux-x64`, `linux-arm64`, `macos-x64`, and `macos-arm64`;
Windows is outside the POSIX task contract. With the Nix profile, nixfmt-rs is retained only for Linux x64/ARM64 and
macOS ARM64 while every other tool keeps the four-platform lock.

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
