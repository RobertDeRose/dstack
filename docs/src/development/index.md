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

Use `mise run fix` for deterministic formatting fixes. The canonical full suite is
`uv run --frozen --group test pytest`; pytest uses four bounded xdist workers with load-group scheduling. Mark tests
that mutate shared repository state with `xdist_group` so those tests remain serialized.

Migration checkpoint fixtures must exercise the rendered project-local provisioner and ordinary Git commits. They cover
provisioning failure, installed hook routing, hook failure recovery, and the narrow approved docs-step exception without
bypassing unrelated checks.

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
navigation, generated checker success, and mdBook builds. Single-profile fixtures execute source and manifest gates with
shims; the full polyglot external fixture runs real source fix-to-check convergence. Bounded external validation
resolves the combined four-platform lock, exercises check/fix/pre-commit/commit-message contracts, and verifies
unrelated unstaged bytes are restored exactly. Separate regressions cover invalid selections, no-overwrite routing,
update preservation, explicit add/remove transitions, conflicts, relocking, and conditional destination uniqueness.

## Large migration imports

Beads mutations run with `--dolt-auto-commit=batch`. Migration commits bounded root/state work per feature and performs
a separate relationship reconciliation commit, while the JSON manifest preserves finer recovery phases. The
deterministic large-import fixture creates at least 300 Beads records, bounds batch-commit count, records elapsed time,
and proves a relationship-interrupted retry mutates only its missing outgoing dependency and does not replay completed
dependents.

## Migration reconciliation automation

Before finalization, `verify` automatically runs `check-docs.py --migration-mode`; afterward it runs strict mode. The
migration checker operates on reader documentation, so generated assets and legacy command directories are not broadened
into its input, and it never rewrites project acronyms or mdBook H1 part headings. Prepare regenerates only bounded
implemented-feature marker bodies. Delivered-record drafts include legacy tasks/design, imported Beads identity, Git
commits, and changed paths, remain candidates, and block verification and finalization until semantic review is
recorded.

## Change discipline

Keep both Copier entry points aligned. Template changes require generated-project tests and must preserve Copier update
compatibility. Skill versions are synchronized during semantic release. Changes to workflow behavior must update the
owning skill, tests, reader documentation, and feature evidence in the same work unit.

See [Feature lifecycle](feature-lifecycle.md) for the repository's planning and delivery workflow.
