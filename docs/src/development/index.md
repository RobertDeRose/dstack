# Developing dstack

## Repository areas

- `skills/`: canonical skill definitions, scripts, references, and the bundled setup template.
- `tests/`: repository, migration, setup, update, and workflow validation.
- `copier.yml`: repository-development Copier entry point.
- `mise.toml`: reproducible tool and task interface.
- `hk.pkl`: shared local and CI quality policy.
- `docs/`: this mdBook and feature planning records.

## Setup

Install declared tools with `mise install`. The post-install hook installs hk through mise so Git hooks use the same
tool versions as manual checks.

## Validation

```bash
mise run check
mise run docs:build
uv run --frozen --group test pytest -m "not integration and not external"
uv run --frozen --group test pytest -m integration
uv run --frozen --group test pytest -m external
```

Use `mise run fix` for deterministic formatting fixes. The full serial test suite is
`uv run --frozen --group test pytest`.

## Generated project command contract

Generated projects expose six stable task names to contributors, operators, and future CI:

```bash
mise run check
mise run fix
mise run docs:check
mise run docs:build
mise run docs:deployment:enable
mise run docs:serve [port]
```

`check` is read-only. `fix` applies deterministic changes. Pre-commit uses the same hk step map with fixes enabled and
`stash = "git"`, so unrelated unstaged work is restored after the hook. Native hk steps and file locking coordinate
independent checks without a broad dependency chain. `HK_MISE=1` makes installed hooks run tools through mise.

The generated baseline covers documentation, Markdown, typos, mise formatting, conflicts, private keys, BOM/newline and
whitespace hygiene, case conflicts, and executable/shebang consistency. Commit-message Harper linting keeps its full
native rule set but filters Git comments/diffs, a canonical release subject, and a canonical machine-readable `Beads:`
footer before checking the human-authored text. Selected profiles extend the same hooks:

| Profile    | Source check/fix          | Root-manifest checks                                 |
|------------|---------------------------|------------------------------------------------------|
| Python     | Ruff lint/format and ty   | pytest through uv                                    |
| TypeScript | Biome check/write         | Vitest through Aube                                  |
| Rust       | rustfmt edition 2024      | Clippy and Cargo tests                               |
| Go         | goimports, then gofumpt   | tidy diff/verify, golangci-lint, tests; fix may tidy |
| Elixir     | Mix format                | warnings-as-errors compile, strict Credo, tests      |
| Nix        | nixfmt on supported hosts | system-Nix flake check                               |

Source steps are file-gated; project checks are root-manifest-gated and check-only except Go's explicit tidy fix.
Profiles add no tasks, manifests, dependencies, or source. The scaffold intentionally omits dstack's `release` task.

## Generated GitHub validation

Generated `.github/workflows/validate.yml` runs on every push and pull request with `contents: read`. It disables
automatic mise installation, isolates user-global mise configuration, installs the committed lock, and invokes only
`mise run check`. The workflow therefore reuses hk and the generated documentation contract instead of defining a second
CI policy or regenerating `mise.lock`.

## Documentation checker contract

The documentation checker validates the pages a project actually publishes rather than requiring a fixed taxonomy. A
project may omit architecture, operations, development overview, or reference overview pages until it has concrete
content for them. Existing links must resolve, feature designs remain published audit records, legacy task files stay
out of reader navigation, and delivered feature records must retain valid directories, sections, markers, and
registrations in both implemented-feature indexes. The repository and generated-project checker copies must remain
identical.

## Scaffold matrix validation

The integration matrix renders every project kind and all 64 valid language-profile selections through both Copier entry
points. It checks structured answers, conditional tools/hooks/ignores/docs, Pkl and TOML parsing, stable tasks and
navigation, generated checker success, and mdBook builds. Profile fixtures execute source and manifest gates with shims;
bounded external checks resolve the combined four-platform lock. Separate regressions cover invalid selections,
no-overwrite routing, update preservation, explicit add/remove transitions, conflicts, relocking, and conditional
destination uniqueness.

## Change discipline

Keep both Copier entry points aligned. Template changes require generated-project tests and must preserve Copier update
compatibility. Skill versions are synchronized during semantic release. Changes to workflow behavior must update the
owning skill, tests, reader documentation, and feature evidence in the same work unit.

See [Feature lifecycle](feature-lifecycle.md) for the repository's planning and delivery workflow.
