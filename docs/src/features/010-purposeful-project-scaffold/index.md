# F010 — Purposeful project scaffold

## Delivery Summary

- Beads feature root: `dstack-mol-ln9`
- Status: ready for delivery; delivery pending
- Pull request: not created
- Merge commit: not merged
- Design record: [design.md](design.md)

## Delivered Capability

New-project setup now requires an explicit purpose, intended users, current scope, boundaries, and one of seven project
kinds. Copier renders a small factual mdBook from that brief instead of generating empty documentation categories or
replacement instructions.

## User-Facing Behavior

`/setup-project` asks one question for each missing brief field and project kind. Direct helper invocation requires
`--purpose`, `--users`, `--scope`, `--boundaries`, and `--project-kind`. Blank values, NUL, CR, LF, and unsupported
kinds fail before rendering with field-specific guidance.

Every kind receives the same initial reader pages: project overview, documentation conventions, feature lifecycle,
planned features, and implemented features. Kind changes only future documentation-concern guidance. Brief punctuation
is preserved literally in Markdown and safely encoded in `book.toml`.

## Design Integration

The implementation preserves Copier's two entry points, update-source recording, `unsafe=False`, no-overwrite behavior,
existing-project routing, Git/Beads setup, and post-render validation. The structured brief is the only source for
initial product facts. Both documentation checker copies now validate the pages a project publishes without requiring a
fixed taxonomy.

## Operational Impact

This is an intentional pre-1.0 breaking input change. Old `project_description` answer sets are not accepted or silently
translated. New setup calls must provide the five structured fields. Existing managed-project and migration routing
remains unchanged.

## Reference and Contracts

- [Project overview](../../introduction/project-overview.md)
- [Workflow architecture](../../architecture/index.md)
- [Install and use dstack](../../operations/index.md)
- [Developing dstack](../../development/index.md)
- [Repository and command reference](../../reference/index.md)

## Validation Evidence

- `uv run pytest -m "not external"`: all 116 applicable tests passed; 1 tag-only test skipped and 1 external test
  deselected.
- Scaffold matrix: 14 independent kind/entrypoint cases and 28 real Copier renders across both README states passed.
- `uv run scripts/check-docs.py`: passed.
- `mise run check`: passed, including mdBook build and repository quality checks.
- Generated documentation checker and mdBook build passed for every matrix render.
- Final holistic delivery and documentation-drift reviews passed with no unresolved blocker after fixes.

## Design Reconciliation

### Delivered as Designed

The exact structured input contract, seven kinds, universal factual reader file set, kind-specific future guidance,
variable documentation checker, and safety regression matrix match the reviewed design.

### Intentional Changes

None from the reviewed implementation-ready design.

### Deferred Work

Restoring structured-brief support in managed-project adoption is tracked by `dstack-ub6`. Universal tooling, language
profiles, GitHub delivery, and monorepo layout remain owned by F020 through F050.

### Rejected or Removed Scope

The feature does not infer missing answers, preserve the old free-form description, generate application source, or
create speculative architecture, operations, development-overview, or reference-overview pages.

## Documentation Updated

- `docs/src/introduction/project-overview.md`
- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/development/index.md`
- `docs/src/reference/index.md`
- `docs/src/planned-features.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/features/010-purposeful-project-scaffold/index.md`

## Audit Trail

- Specification reconciliation: `ec4cc05`, with roadmap readiness at `6d9018e`.
- Structured inputs (`dstack-mol-a8i.1`): `3ce9e434b2c133ff3d2ad629d8c9e2ae49f8301f`.
- Factual generated documentation (`dstack-mol-a8i.2`): `5ca20d3bd39825ee894eaa284053a4dfe7078a94`.
- Variable-taxonomy checker (`dstack-mol-a8i.3`): `ea080d65f4373b41faf52a437228930a9d6b9ac2`.
- Complete scaffold matrix (`dstack-mol-a8i.4`): `8b9a5705ac9f1fc36f31d0ea14c6e16a36567216`.
- Implementation coordinator `dstack-mol-a8i` closed after all four children and acceptance checks completed.
