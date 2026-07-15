# Design — Language quality profiles

## Metadata

- Beads feature root: `dstack-mol-ni2`
- Feature slug: `language-quality-profiles`
- Design path: `docs/src/features/language-quality-profiles/design.md`
- Implemented record: `docs/src/features/language-quality-profiles/index.md`
- Base branch: `main`
- Status: reviewed

## Feature Summary

Let new projects select Python, TypeScript, Rust, Go, Elixir, Nix, or other implementation languages. Recognized
profiles extend Universal project tooling's universal mise/hk/docs baseline without generating application source,
manifests, package roots, or workspace structure.

## User Intent

Setup should install an opinionated quality baseline for the implementation languages while remaining a workflow
scaffold. Multiple profiles support one repository containing several languages, such as Python with a TypeScript
frontend or a Rust extension. Language quality profiles still applies one root policy; package-local configuration and
monorepo layout remain Monorepo tooling layout.

## Goals

- Record a canonical, validated list of selected language profiles.
- Add only selected mise tools, hk steps, ignore rules, and factual contributor documentation.
- Run source-only checks without requiring a manifest and gate package-aware checks on project-owned root manifests.
- Use project-owned pytest, Vitest, and Credo versions rather than modifying manifests or fetching ephemeral packages.
- Preserve the five Universal project tooling task names and one project-owned four-platform `mise.lock`.

## Non-Goals

- Generate or modify `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `mix.exs`, `flake.nix`, source,
  frameworks, APIs, dependency declarations, package scripts, or build architecture.
- Discover or configure recursive package roots, workspaces, or monorepo execution.
- Support JavaScript as a separate profile.
- Infer languages without user confirmation.

## User-Facing Behavior

Setup records an explicit profile selection. Generated checks apply one root policy to matching files, while setup and
update never execute project scripts or create language manifests.

### Selection Contract

The Copier answer is `language_profiles`, a list whose stable values are ordered:

```text
python, typescript, rust, go, elixir, nix, other
```

The six recognized profiles may be combined. `other` is exclusive, renders no language tooling, and means no supported
profile was selected. An empty list, duplicates, unknown values, or `other` combined with another value are invalid.
Recorded values are canonicalized to schema order.

`/setup-project` asks for profiles when the user did not supply them and passes one repeatable
`--language-profile <value>` flag per selection. The direct helper requires at least one value; it never silently
chooses a language.

`/update-project` preserves recorded profiles unless the user explicitly supplies repeatable `--add-profile` or
`--remove-profile` operations. Repeated add/remove values and adding an already-present or removing an absent profile
are idempotent. The add and remove sets must be disjoint. Adding a recognized profile removes `other`; adding `other` is
valid only when all recognized profiles are removed in the same operation. The canonicalized result must satisfy the
selection contract. Copier reconciliation, lock resolution, locked installation, and hook installation then follow
Universal project tooling's conflict and recovery contract.

For a legacy project without `language_profiles`, the skill checks only these repository-root paths and offers the
matching suggestions for confirmation:

| Root path        | Suggested profile |
|------------------|-------------------|
| `pyproject.toml` | Python            |
| `tsconfig.json`  | TypeScript        |
| `package.json`   | TypeScript        |
| `Cargo.toml`     | Rust              |
| `go.mod`         | Go                |
| `mix.exs`        | Elixir            |
| `flake.nix`      | Nix               |

Suggestions are never applied automatically. If none are found or the user declines them, the skill offers `other`.
Detection remains root-only; recursive discovery belongs to Monorepo tooling layout. A direct noninteractive update of a
legacy project without explicit profile operations records `other` to preserve the universal Universal project tooling
baseline.

## Requirements

### Functional Requirements

- Both Copier entry points record the exact selection contract and render only selected profile content.
- Setup collects explicit profiles; update preserves, adds, or removes them through the reviewed interface.
- Each profile implements the exact tools, commands, globs, gates, ignores, and documentation in the normative table.
- All valid polyglot combinations retain one shared tooling surface without duplicate destinations or keys.

### Quality Requirements

- Source checks skip cleanly without matching files, and package checks skip without their manifest inputs.
- `check` is read-only; mutating tools are globally ordered; tests never run during fix or pre-commit.
- Generated documentation states only behavior present in the selected render.

### Compatibility and Migration Requirements

Pre-1.0 answer changes are allowed. Legacy projects receive confirmed root-only suggestions or retain the universal
baseline through `other`; Copier conflicts execute no newly rendered code.

## Manifest and Dependency Policy

No profile creates a manifest. Source-only format/lint steps run when matching files exist. Package-aware steps run only
when their root manifest and relevant input files exist. Missing required project-owned pytest, Vitest, or Credo
dependencies fail with a clear prerequisite message rather than being downloaded or written into a manifest.

Manifest-backed tests and expensive project checks run only under `mise run check`; they do not run in pre-commit or
`mise run fix`. Source formatters and linters participate in the shared pre-commit/check/fix policy as applicable.
`mise run check` stays read-only. For Go this means check uses `go mod tidy -diff && go mod verify`, while fix may run
`go mod tidy`.

## Existing Context

Universal project tooling owns the universal nine-tool baseline, stable five tasks, one mise/hk policy, four-platform
lock, conflict gate, provisioner, and generated tooling pages. Language quality profiles extends those surfaces and
preserves their recovery and trust boundaries.

## Proposed Design

Use direct membership-gated Copier/Jinja/Pkl sections in the existing files. Keep common source checks separate from
check-only manifest steps, render conditional docs/ignores from the same answer, and reuse the Universal project tooling
provisioner.

### Normative Profile Contract

All new mise entries use `latest`; the committed `mise.lock` still targets Universal project tooling's four platforms.
TypeScript reuses the universal `node = "lts"` entry rather than declaring Node again. Exact long identifiers may be
used where mise has no stable shorthand. The nixfmt-rs release lacks a macOS x64 asset, so its mise entry is explicitly
restricted with `os = ["linux", "macos/arm64"]`; every other profile tool resolves on all four targets.

| Profile    | Added mise tools                                                        | Source-scoped check/fix                                          | Root-manifest-gated checks                                                                                                              |
|------------|-------------------------------------------------------------------------|------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| Python     | `ruff`, `ty`                                                            | Ruff lint and format plus `ty check` on `**/*.py`, `**/*.pyi`    | With `pyproject.toml` and matching `tests/**/*.py`, `uv run pytest`; pytest must be project-declared                                    |
| TypeScript | `aube`, `biome`                                                         | Biome check/write on `**/*.{ts,tsx,mts,cts}`                     | With `package.json` and matching `**/*.{test,spec}.{ts,tsx,mts,cts}`, `aube exec vitest run`; Vitest must be project-declared           |
| Rust       | `rust`                                                                  | `rustfmt --check` / `rustfmt` on `**/*.rs` using edition 2024    | With `Cargo.toml`, `cargo clippy --all-targets --all-features -- -D warnings` and `cargo test --all-targets --all-features`             |
| Go         | `go`, `gofumpt`, `go:golang.org/x/tools/cmd/goimports`, `golangci-lint` | goimports then gofumpt check/write on `**/*.go`                  | With `go.mod`, read-only tidy diff plus verify, `golangci-lint run`, and `go test ./...`; fix may run `go mod tidy`                     |
| Elixir     | `erlang`, `elixir`                                                      | `mix format --check-formatted` / `mix format` on `**/*.{ex,exs}` | With `mix.exs`, warnings-as-errors compile, `mix credo --strict`, and tests when `test/**/*.exs` exists; Credo must be project-declared |
| Nix        | `github:Mic92/nixfmt-rs`, limited to Linux and macOS ARM64              | its `nixfmt --check` / `nixfmt` binary on `**/*.nix`             | With `flake.nix`, `nix flake check`; system `nix` is the sole executable prerequisite not provisioned by mise                           |

### Exact hk Step Contract

`{{ files }}` is hk's shell-escaped file list. Source steps run in `check`, `fix`, and `pre-commit`; check uses each
`check` command, while fix/pre-commit use `fix` when present and then run read-only source checks. Check-only project
steps never run in fix/pre-commit. Go module tidy is the sole fix-only manifest step and does not run in pre-commit.

| Step              | Check command                                              | Fix command                                                | Gate / hooks                                            |
|-------------------|------------------------------------------------------------|------------------------------------------------------------|---------------------------------------------------------|
| `ruff`            | `ruff check --force-exclude {{ files }}`                   | `ruff check --force-exclude --fix {{ files }}`             | Python files; all three hooks                           |
| `ruff-format`     | `ruff format --quiet --force-exclude --diff {{ files }}`   | `ruff format --quiet --force-exclude {{ files }}`          | Python files; after `ruff`; all three hooks             |
| `ty`              | `ty check {{ files }}`                                     | none                                                       | Python files; after `ruff-format`; all three hooks      |
| `biome`           | `biome check --no-errors-on-unmatched {{ files }}`         | `biome check --write --no-errors-on-unmatched {{ files }}` | TypeScript files; all three hooks                       |
| `rustfmt`         | `rustfmt --check --edition 2024 {{ files }}`               | `rustfmt --edition 2024 {{ files }}`                       | Rust files; all three hooks                             |
| `goimports`       | `output=$(goimports -l {{ files }}) && test -z "$output"`  | `goimports -w {{ files }}`                                 | Go files; all three hooks                               |
| `gofumpt`         | `output=$(gofumpt -l {{ files }}) && test -z "$output"`    | `gofumpt -w {{ files }}`                                   | Go files; after `goimports`; all three hooks            |
| `mix-format`      | `mix format --check-formatted {{ files }}`                 | `mix format {{ files }}`                                   | Elixir files; all three hooks                           |
| `nixfmt`          | `nixfmt --check {{ files }}`                               | `nixfmt {{ files }}`                                       | Nix files; supported platforms; all three hooks         |
| `pytest`          | prerequisite guard, then `uv run pytest`                   | none                                                       | root `pyproject.toml` plus `tests/**/*.py`; check only  |
| `vitest`          | prerequisite guard, then `aube exec vitest run`            | none                                                       | root `package.json` plus TS test/spec files; check only |
| `cargo-clippy`    | `cargo clippy --all-targets --all-features -- -D warnings` | none                                                       | root `Cargo.toml`; check only                           |
| `cargo-test`      | `cargo test --all-targets --all-features`                  | none                                                       | root `Cargo.toml`; check only                           |
| `go-mod`          | `go mod tidy -diff && go mod verify`                       | `go mod tidy`                                              | root `go.mod`; check and fix, never pre-commit          |
| `golangci-lint`   | `golangci-lint run`                                        | none                                                       | root `go.mod`; check only                               |
| `go-test`         | `go test ./...`                                            | none                                                       | root `go.mod`; check only                               |
| `mix-compile`     | `mix compile --warnings-as-errors`                         | none                                                       | root `mix.exs`; check only                              |
| `credo`           | prerequisite guard, then `mix credo --strict`              | none                                                       | root `mix.exs`; check only                              |
| `mix-test`        | `mix test --warnings-as-errors`                            | none                                                       | root `mix.exs` plus `test/**/*.exs`; check only         |
| `nix-flake-check` | `nix flake check`                                          | none                                                       | root `flake.nix`; check only                            |

The pytest guard runs `uv run python -c "import pytest"`; the Vitest guard runs `aube exec vitest --version`; the Credo
guard runs `mix help credo`. Each prints a profile-specific message requiring the missing project-owned dependency
before exiting nonzero. Nix source commands first reject `Darwin/x86_64` with the published unsupported-platform
message; on other targets `nixfmt` is mise-provisioned. Missing system Nix for `nix-flake-check` produces the documented
prerequisite message.

The global mutating order extends Universal project tooling's serialized chain in canonical profile order. Read-only
source linters depend on the final relevant formatter. Mixed selections must not duplicate keys, tools, task names, or
destinations.

## Generated Tasks and Documentation

Profiles add no top-level mise tasks. Contributors continue to use only:

```text
check, fix, docs:check, docs:build, docs:serve
```

Conditional sections extend the existing generated pages:

- `skills/setup-project/template/docs/src/development/tooling.md.jinja` explains selected check/fix behavior, manifest
  gates, project-owned test dependencies, and the Nix prerequisite.
- `skills/setup-project/template/docs/src/reference/tooling.md.jinja` lists the recorded profiles, exact added tools,
  globs, commands, and ignore rules.

Both pages remain unconditionally linked by the existing generated `docs/src/SUMMARY.md`; no new reader page or
navigation entry is added. With `other`, they remain the universal Universal project tooling pages and state that no
recognized language profile is active. Mixed selections render additive sections in canonical order.

## Ignore Ownership

Universal documentation, mise, environment, and operating-system ignores remain unconditional. Existing Python-only
ignores move behind the Python profile. Selected profiles add only:

| Profile    | Ignore entries                                                          |
|------------|-------------------------------------------------------------------------|
| Python     | `.venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.ruff_cache/` |
| TypeScript | `node_modules/`, `coverage/`                                            |
| Rust       | `target/`                                                               |
| Go         | `coverage.out`                                                          |
| Elixir     | `_build/`, `deps/`, `cover/`                                            |
| Nix        | `.direnv/`, `result`, `result-*`                                        |
| Other      | none                                                                    |

Removing a profile removes its template-owned tools, steps, docs sections, and ignores on a conflict-free Copier update.
Copier conflicts continue to skip provisioning and keep update readiness false.

## Architecture Consistency

### Existing Patterns Reused

Universal project tooling remains authoritative for one shared `mise.toml`, `hk.pkl`, provisioner, lock, hook
installation, five tasks, and generated tooling pages. Language quality profiles uses direct membership-gated Jinja/Pkl
sections; it adds no profile registry, generator, plugin system, or second provisioning path.

### Invariants Preserved

Copier only renders. Setup/update decide when generated code executes. User-global mise tools remain isolated. Profile
selection changes tooling only; lifecycle authority and documentation validation remain language-agnostic. Application
manifests and dependencies stay project-owned.

### New Decisions Introduced

The hk policy becomes a shared source-check map plus check-only manifest steps so tests never run during fix or
pre-commit. The Nix profile's system `nix` prerequisite is the single explicit exception to mise ownership. The
mise-provisioned nixfmt-rs binary provides formatting without Nix on Linux x64/ARM64 and macOS ARM64. Nix profile checks
are unsupported on macOS x64 and fail with an explicit platform message when matching Nix inputs exist.

## Operational Considerations

Setup and conflict-free update resolve and install selected tools into the existing four-platform lock; mise omits
nixfmt-rs only from the macOS x64 target. Tool or lock failure uses Universal project tooling's structured degraded
result and recovery. Adding/removing profiles can change `mise.lock`; no project script or manifest-backed check runs
during setup/update. Aube auto-install behavior occurs only later when contributors run the manifest-gated Vitest check.

## Documentation Impact

| Documentation concern | Exact page                                                                          | Change                                                                      | Owner                                                         |
|-----------------------|-------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|---------------------------------------------------------------|
| Architecture          | `docs/src/architecture/index.md`                                                    | Root profile composition, shared/check-only maps, no-monorepo boundary      | composition; final matrix reconciliation                      |
| Usage                 | `docs/src/operations/index.md`                                                      | Setup selection, legacy suggestions, add/remove update flow, manifest gates | matrix/docs task                                              |
| Development           | `docs/src/development/index.md`                                                     | Exact profile checks, fixtures, and matrix validation                       | matrix/docs task                                              |
| Reference             | `docs/src/reference/index.md`                                                       | Answer schema, profile/tool/command/ignore tables                           | composition selection contract; final matrix reconciliation   |
| Generated development | `skills/setup-project/template/docs/src/development/tooling.md.jinja`               | Conditional contributor behavior                                            | serialized profile tasks; final reconciliation by matrix/docs |
| Generated reference   | `skills/setup-project/template/docs/src/reference/tooling.md.jinja`                 | Conditional exact contracts                                                 | serialized profile tasks; final reconciliation by matrix/docs |
| Navigation            | `docs/src/SUMMARY.md` and `skills/setup-project/template/docs/src/SUMMARY.md.jinja` | No change; existing tooling pages remain linked                             | matrix assertion only                                         |
| Implemented feature   | `docs/src/features/language-quality-profiles/index.md`                              | Create during close-out                                                     | lifecycle close-out                                           |

## Validation Strategy

Structural validation covers 65 cases: the 63 nonempty subsets of the six recognized profiles, the exclusive `other`
selection, and one empty-list rejection. The 64 valid selections render through both Copier entry points. Tests check
canonical answers, selected-only tools/steps/docs/ignores, stable tasks, no duplicate destinations, TOML/Pkl validity,
generated docs/navigation, and `other` retaining the universal baseline.

Focused fixtures exercise source check/fix and manifest gates for each profile. Deterministic shims verify exact
manifest-backed commands, missing project-owned dependency errors, no-file/no-manifest skips, read-only check behavior,
global formatter ordering, and setup/update add/remove/conflict/relock behavior. A bounded marked external contract
resolves the combined four-platform lock, verifies nixfmt-rs is absent only for macOS x64, and executes representative
source-only tools on supported hosts. System Nix and project-owned ecosystem dependencies are classified separately
rather than silently downloaded.

Implementation uses these literal validation commands:

```bash
# composition
uv run pytest -q tests/test_repository.py \
  -k "language_profile_schema or language_profile_selection or language_profile_update or language_profile_matrix"
# Python/TypeScript
uv run pytest -q tests/test_repository.py -k "python_profile or typescript_profile"
# Rust/Go
uv run pytest -q tests/test_repository.py -k "rust_profile or go_profile"
# Elixir/Nix
uv run pytest -q tests/test_repository.py -k "elixir_profile or nix_profile"
# final focused and external contracts
uv run pytest -q tests/test_repository.py -k "language_profile"
uv run pytest -q tests/test_repository.py::test_generated_language_profiles_end_to_end
# final repository and documentation validation
uv run --frozen --group test pytest
mise run check
uv run scripts/check-docs.py
mdbook build docs
```

During iteration each task runs only its focused selector. The final task runs the focused and marked external
contracts, then the full repository suite and repository/documentation checks after review fixes stabilize.

## Dependencies and Parallelism

Language quality profiles depends on delivered Universal project tooling. Implementation is intentionally serialized
because every profile extends the same mise/hk/generated-documentation files. Each child directly depends on
specification reconciliation and its predecessor; no implementation child can become ready from hierarchy alone.

## Implementation Decomposition

1. Composition and workflow selection: Copier schema, setup/update UX and helpers, root-only legacy suggestions,
   conditional shared surfaces, ignores, architecture/reference contract, and exhaustive structural matrix.
2. Python and TypeScript profiles, fixtures, and their generated documentation sections.
3. Rust and Go profiles, fixtures, and their generated documentation sections.
4. Elixir and Nix profiles, fixtures, Nix prerequisite, and their generated documentation sections.
5. Cross-profile matrix, setup/update integration, external contract, and root/generated documentation reconciliation.

The tasks are serialized because they intentionally modify the same mise/hk/generated-documentation surfaces. Every
implementation child depends directly on specification reconciliation as well as its preceding implementation child.

## Rollout and Migration

New setup always obtains an explicit selection. Legacy update offers root-manifest suggestions and requires
confirmation. Explicit add/remove operations preserve application-owned files and use Copier's normal three-way
reconciliation. Language quality profiles does not recursively discover packages or initialize language projects.

## Risks and Tradeoffs

The exhaustive render matrix is cheap but live tool installation is not; structural coverage is exhaustive while the
external execution set is bounded. Fuzzy profile versions reduce template maintenance and are made deterministic per
project by `mise.lock`. Project-owned pytest, Vitest, and Credo can vary by project, so dstack validates invocation and
prerequisite behavior rather than controlling their versions.

## Rejected Alternatives

- Stub manifests or native project initialization: violates the workflow-scaffold boundary and would invent package
  identity/layout decisions.
- Manifest-defined tooling only: too inconsistent for an opinionated generated quality baseline.
- Ephemeral pytest/Vitest/Credo downloads: bypass project dependency authority.
- Whole-list update replacement: poor additive-migration UX; explicit add/remove is clearer.
- Recursive manifest discovery: package-root semantics belong to Monorepo tooling layout.
- `nixfmt-tree`: requires Nix/treefmt integration for source formatting; nixfmt-rs is standalone on its three published
  platform targets. The user explicitly accepted no Nix-profile support on macOS x64 rather than adding Rust solely to
  compile the formatter.
- Parallel profile tasks or generated fragment systems: shared files make parallel writes unsafe and direct conditionals
  are sufficient.
- JavaScript profile, framework starters, or one complete template per language: outside scope or duplicative.

## Open Questions

None.

## Deferred Decisions

Additional languages and package-local/monorepo profile configuration require demonstrated consumers and complete mise,
hk, and validation contracts.

## Planning Record

### Questions Asked and Answers

The user selected Python, TypeScript, Rust, Go, Elixir, Nix, and other; TypeScript uses Biome and Aube-run Vitest;
Python uses Ruff, ty, and uv-run pytest; Go adds gofumpt, goimports, module hygiene, golangci-lint, and tests; Elixir
adds strict Credo; Nix uses nixfmt-rs plus flake checks and intentionally excludes macOS x64. Manifests remain
project-owned, package-aware checks are manifest gated, and pytest/Vitest/Credo versions are project-owned. Legacy
discovery is root-only and confirmed by the user.

### Assumptions

Multiple profiles apply one root policy to a polyglot repository; they do not imply package-local execution or monorepo
support.

### Design Changes During Review

Review replaced undefined native conventions with the normative table, made setup/update selection explicit, moved
Python ignores behind its profile, serialized shared-file work, separated check-only tests from pre-commit/fix, added
exact generated documentation destinations, made structural validation exhaustive, and split native implementation.

### Source Material

Aube official documentation; mise registry identifiers; hk 1.49 built-ins; nixfmt-rs official repository; Universal
project tooling's delivered generated-tooling contract.
