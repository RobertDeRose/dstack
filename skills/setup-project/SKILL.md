---
name: setup-project
description: Create and initialize a new Copier-managed dstack project from the template bundled with the installed skill. Use only for a new project, with an explicit project name or basename($PWD) by default.
metadata:
  version: "0.1.0"
allowed-tools: Read Glob Bash AskUserQuestion
---

# Purpose

Use this skill only for a new repository. It renders the Copier template installed alongside this `SKILL.md`, records
the published dstack source for future updates, initializes the new-project workflow, and validates the generated
documentation. It does not download the template from GitHub and does not migrate legacy project state.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`. The bundled Copier source is `<skill-dir>` itself:
`copier.yml` selects the adjacent `template/` directory.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

Setup-specific authority:

- The default source is the template bundled in the installed `setup-project` skill. Do not clone, download, or install
  another template for normal setup.
- The helper reads this skill's `metadata.version`, renders the local template with Copier `unsafe=False`, then records
  `gh:RobertDeRose/dstack` and `v<metadata.version>` in `.copier-answers.yml` for `/update-project`.
- `--template-source` is a development/testing override only. A remote override requires an explicit `--vcs-ref` and
  never falls back silently to `HEAD`.
- Existing project content is never interpreted as migration input by this workflow. The helper has no overwrite mode
  for project files; route existing repositories through `/migrate-workflow`.

## Routing preflight

Inspect the destination before invoking the helper.

1. If `.copier-answers.yml` exists, do not run setup. Explain that the project is already Copier-managed and ask exactly
   one question with `AskUserQuestion`: `Run /update-project instead?`
2. Run `/update-project` only when the user agrees. If the user declines, stop without modifying the repository.
3. If project files exist but `.copier-answers.yml` does not, stop and route the user to `/migrate-workflow`; do not
   copy migration utilities into the project and do not merge an existing repository from this workflow.
4. Continue with setup only when the destination is a new project directory, apart from an installed local skills tree
   or `skills-lock.json`.

The helper independently refuses an existing `.copier-answers.yml`; this is a non-interactive safety backstop, not
permission to invoke `/update-project` automatically.

## Defaults

- Project name: supplied value, otherwise `basename "$PWD"`.
- Destination: current working directory.
- Render source: `<skill-dir>/copier.yml` and `<skill-dir>/template/`.
- Recorded update source: `gh:RobertDeRose/dstack`.
- Recorded baseline revision: `v<metadata.version>` from this frontmatter.
- Default branch: `main`.
- Beads: initialize with `bd init --stealth --skip-agents` when `bd` is available; otherwise complete documentation
  setup and report Beads initialization as outstanding.

## Execution

```bash
uv run <skill-dir>/scripts/setup-project.py [project-name]
```

Examples:

```bash
# Uses basename "$PWD" and writes into the current directory.
uv run <skill-dir>/scripts/setup-project.py

# Uses an explicit name and writes into the current directory.
uv run <skill-dir>/scripts/setup-project.py "Reader Control Plane"

# Writes into another new directory.
uv run <skill-dir>/scripts/setup-project.py "Reader Control Plane" \
  --destination ../reader-control-plane

# Omits the generated starter README.
uv run <skill-dir>/scripts/setup-project.py --delete-readme

# Development only: render a reviewed local checkout or an explicitly pinned remote source.
uv run <skill-dir>/scripts/setup-project.py --template-source ../dstack
uv run <skill-dir>/scripts/setup-project.py \
  --template-source gh:example/dstack-fork --vcs-ref <reviewed-tag-or-commit>
```

The setup helper performs post-render initialization itself. It does not generate `scripts/bootstrap.py`,
`scripts/migrate-legacy-workflow.py`, or a migration guide in the new project.

## Verification

Confirm at least:

```text
.copier-answers.yml
AGENTS.md
.beads/formulas/feature-lifecycle.formula.toml
docs/book.toml
docs/src/SUMMARY.md
docs/src/planned-features.md
docs/src/features/_template/design.md
docs/src/features/_template/index.md
scripts/check-docs.py
```

Confirm these new-project-inappropriate paths do not exist:

```text
MIGRATION.md
scripts/bootstrap.py
scripts/migrate-legacy-workflow.py
```

Verify `.copier-answers.yml` records the official update source and installed skill release, not a path inside the skill
installation. The helper runs `uv run scripts/check-docs.py` as part of setup.

Check availability before invoking Beads verification:

```bash
if command -v bd >/dev/null 2>&1; then
  bd prime
  bd list --type epic --label workflow:feature --all --json --limit 0
else
  printf '%s\n' 'Beads verification outstanding: install bd, initialize it, then run bd prime.'
fi
```

Do not run `bd prime` when `bd` is unavailable. In that case setup may complete, but the return must list Beads
initialization and verification as outstanding.

## Copier contract

- Commit `.copier-answers.yml` and the initial scaffold.
- Setup renders only bundled files; `/update-project` is the network-backed operation that discovers newer tags.
- `npx skills update` updates installed skill definitions, scripts, and the bundled setup template.
- `/update-project` applies newer published template releases to the repository.
- Do not edit `.copier-answers.yml` manually.

## Return

Report project name, slug, destination, bundled render source, skill version, recorded update source/revision, Git
result, Beads result, documentation validation, outstanding work, and the next `/plan-features` action. If setup was
routed to `/update-project`, report the user's consent decision and do not claim setup ran.
