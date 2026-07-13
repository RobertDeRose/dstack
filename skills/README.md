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
- `close-feature`
- `audit-project`
- `migrate-workflow`
- `gh-pr-review`

Supporting scripts, references, and the Copier project template live inside their owning skill directories, so the
Skills CLI installs the complete runtime surface recursively.

`setup-project` is new-project only. Existing Copier-managed repositories route to `update-project` after explicit
approval; legacy repositories route through `migrate-workflow`. Features are represented by one Beads epic/molecule with
lifecycle and implementation tasks beneath it and are selected by number, slug, or human name.
