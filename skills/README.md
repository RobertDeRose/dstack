# dstack Skills

Install from GitHub:

```bash
npx skills@latest add RobertDeRose/dstack
```

Install everything without prompts:

```bash
npx skills@latest add RobertDeRose/dstack --all
```

Available skills:

- `dstack-core` (shared support contracts and feature resolver)
- `setup-project`
- `update-project`
- `plan-features`
- `start-feature`
- `implement-feature`
- `implement-task`
- `close-feature`
- `audit-project`
- `migrate-workflow`
- `gh-pr-review`

Supporting scripts, references, optional Pi reviewer assets, and the Copier project template live inside their owning
skill directories, so the Skills CLI installs the complete runtime surface recursively. Pi reviewer assets are not
copied into global or project agent directories automatically; use `dstack-core/scripts/sync-pi-reviewers.py` only after
explicit user opt-in. Workflow startup records the executing skill's `metadata.version` and compares it with local
canonical evidence when available; stale installs warn with `npx skills update` without silently changing the executing
skill.

`setup-project` is new-project only. Existing Copier-managed repositories route to `update-project` after explicit
approval; legacy repositories route through `migrate-workflow`. Features are represented by one Beads epic/molecule with
lifecycle and implementation tasks beneath it and are selected by number, slug, or human name. Standalone Beads `task`,
`bug`, `chore`, `spike`, and `feature` issues are executed one at a time with `implement-task`.
