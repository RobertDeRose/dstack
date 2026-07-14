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

Generated projects expose the same five task names to contributors and future CI:

```bash
mise run check
mise run fix
mise run docs:check
mise run docs:build
mise run docs:serve [port]
```

`check` is read-only. `fix` applies deterministic changes. Pre-commit uses the same hk step map with fixes enabled and
`stash = "git"`, so unrelated unstaged work is restored after the hook. Overlapping fixers are serialized before final
read-only checks. `HK_MISE=1` makes installed hooks run tools through mise.

The generated baseline covers documentation, Markdown, typos, mise formatting, conflicts, private keys, BOM/newline and
whitespace hygiene, case conflicts, and executable/shebang consistency. It intentionally omits dstack's `release` task
and all language-profile automation.

## Documentation checker contract

The documentation checker validates the pages a project actually publishes rather than requiring a fixed taxonomy. A
project may omit architecture, operations, development overview, or reference overview pages until it has concrete
content for them. Existing links must resolve, internal feature designs and task files must stay out of reader
navigation, and delivered feature records must retain valid directories, sections, markers, and registrations in both
implemented-feature indexes. The repository and generated-project checker copies must remain identical.

## Scaffold matrix validation

The integration matrix renders every project kind through both the repository and bundled Copier entry points. It checks
raw structured-brief forwarding, punctuation-safe Markdown and TOML, the exact initial documentation destinations and
navigation, kind-specific guidance, source recording, generated checker success, and mdBook builds. Separate safety
regressions cover `unsafe=False`, no-overwrite and existing-project routing, Copier update preservation, and conditional
destination uniqueness.

## Change discipline

Keep both Copier entry points aligned. Template changes require generated-project tests and must preserve Copier update
compatibility. Skill versions are synchronized during semantic release. Changes to workflow behavior must update the
owning skill, tests, reader documentation, and feature evidence in the same work unit.

See [Feature lifecycle](feature-lifecycle.md) for the repository's planning and delivery workflow.
