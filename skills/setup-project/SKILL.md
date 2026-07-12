---
name: setup-project
description: Create a new Copier-managed dstack project from the template bundled with the installed skill. Use when asked to initialize a new project, with an explicit project name or basename($PWD) by default.
metadata:
  version: "0.1.0"
allowed-tools: Read Glob Bash
---

# Purpose

Use this skill for a new repository. It renders the Copier template installed alongside this `SKILL.md`, records the
published dstack source for future updates, initializes the project workflow, and validates the generated documentation
scaffold. Setup does not download the template from GitHub.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`. The bundled Copier source is `<skill-dir>` itself:
`copier.yml` selects the adjacent `template/` directory.

For an existing repository, use `/migrate-workflow` instead.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

Setup-specific authority:

- The supported default is the template bundled in the installed `setup-project` skill. Do not clone, download, or
  install another template for normal setup.
- The helper reads this skill's `metadata.version`, renders the local template with Copier `unsafe=False`, then records
  `gh:RobertDeRose/dstack` and `v<metadata.version>` in `.copier-answers.yml` as the baseline for `/update-project`.
- `--template-source` is a development/testing override only. A remote override requires an explicit `--vcs-ref` and
  never falls back silently to `HEAD`.
- Existing project content is overwritten only with explicit `--overwrite`.

## Defaults

- Project name: supplied value, otherwise `basename "$PWD"`.
- Destination: current working directory.
- Render source: `<skill-dir>/copier.yml` and `<skill-dir>/template/`.
- Recorded update source: `gh:RobertDeRose/dstack`.
- Recorded baseline revision: `v<metadata.version>` from this frontmatter.
- Default branch: `main`.
- Beads: initialized with `bd init --stealth --skip-agents` when `bd` is available; otherwise setup completes and
  reports the remaining step.

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

# Writes into another directory.
uv run <skill-dir>/scripts/setup-project.py "Reader Control Plane" \
  --destination ../reader-control-plane

# Omits the generated starter README.
uv run <skill-dir>/scripts/setup-project.py --delete-readme

# Development only: render a reviewed local checkout or an explicitly pinned remote source.
uv run <skill-dir>/scripts/setup-project.py --template-source ../dstack
uv run <skill-dir>/scripts/setup-project.py \
  --template-source gh:example/dstack-fork --vcs-ref <reviewed-tag-or-commit>
```

The destination may already contain project-local skill directories and `skills-lock.json` created by `npx skills`.
Existing project content belongs in `/migrate-workflow`, not new-project setup.

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
scripts/bootstrap.py
scripts/check-docs.py
scripts/migrate-legacy-workflow.py
```

Verify `.copier-answers.yml` records the official update source and the installed skill release, not a path inside the
agent's skill installation.

Then run:

```bash
uv run scripts/check-docs.py
```

Check availability before invoking Beads:

```bash
if command -v bd >/dev/null 2>&1; then
  bd prime
  bd ready --json
else
  printf '%s\n' 'Beads verification outstanding: install bd, then run bd prime and bd ready --json.'
fi
```

Do not run `bd prime` or `bd ready` when `bd` is unavailable. In that case, setup may complete, but the return must list
Beads initialization and verification as outstanding.

## Copier contract

- Commit `.copier-answers.yml` and the initial scaffold.
- Setup renders only bundled files; `/update-project` is the network-backed operation that discovers newer tags.
- `npx skills update` updates installed skill definitions, scripts, and the bundled setup template.
- `/update-project` applies newer published template releases to the repository.
- Do not edit `.copier-answers.yml` manually. The setup helper writes its initial remote update state after Copier
  renders the bundled template.

## Return

Report project name, slug, destination, bundled render source, skill version, recorded update source/revision, Git
result, bootstrap/Beads result, documentation validation, warnings, and the next `/plan-features` action.
