# Install and use dstack

## Install the skills

```bash
npx skills@latest add RobertDeRose/dstack --all
```

## Create a project

Run `/setup-project` in a new project directory. The skill renders its bundled Copier template, initializes Git and
Beads when available, and validates the generated documentation. Existing repositories are routed to
`/migrate-workflow`; already managed repositories are routed to `/update-project` with explicit consent.

## Deliver features

```text
/plan-features
/start-feature 010-feature-name
/implement-feature 010-feature-name
/close-feature 010-feature-name
/audit-project
```

Use `bd prime` at session start. Beads owns live readiness and dependencies; `docs/src/planned-features.md` is only the
human roadmap.

## Update

- `npx skills update` refreshes installed skills and bundled assets.
- `/update-project` applies a newer published Copier template to a managed repository.
- `/migrate-workflow` adopts an existing legacy Markdown workflow before normal updates.

## Failure boundaries

Setup refuses non-empty unmanaged destinations. Update refuses missing or invalid Copier state and does not silently
select untagged template code. If Beads is unavailable, setup reports initialization and verification as outstanding
rather than claiming a complete workflow installation.
