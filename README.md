# dstack

A documentation-first, Beads-backed workflow for agent-assisted software projects. The repository is both an installable
Skills CLI package and a versioned Copier template.

## Install

```bash
npx skills@latest add RobertDeRose/dstack
```

The command discovers all skills under `skills/` and lets you choose skills and target agents. Install every skill
non-interactively with:

```bash
npx skills@latest add RobertDeRose/dstack --all
```

Supporting scripts, references, and the complete Copier template are installed recursively with their owning skills.

## Create a New Project

From the target directory:

```text
/setup-project
```

The project name defaults to `basename "$PWD"`. Override it explicitly:

```text
/setup-project Reader Control Plane
```

The setup skill renders the Copier template bundled inside the installed skill, without downloading a second copy from
GitHub. It creates `.copier-answers.yml`, records the corresponding published dstack release as the future update
baseline, initializes Git when needed, initializes Beads when available, and validates the documentation scaffold.

Direct invocation for a Codex/universal project installation:

```bash
uv run .agents/skills/setup-project/scripts/setup-project.py "Reader Control Plane"
```

## Update Skills and Generated Projects

These are separate operations:

```bash
# Update installed skill definitions, scripts, and bundled assets.
npx skills update

# Apply newer tagged template changes to this repository.
/update-project
```

The project update helper reads the Git source recorded in `.copier-answers.yml`, queries its published tags, selects
the newest stable PEP 440 release, and then runs Copier's three-way update. Project-specific evolution is preserved
where possible. Use `--vcs-ref` only for an explicitly reviewed development revision.

## Migrate an Existing Project

For a repository using the original `planned-features.md` plus per-feature `tasks.md` workflow:

```text
/migrate-workflow
```

The migration skill adopts Copier state, preserves the existing reader-facing documentation hierarchy, migrates live
task state into Beads, and archives legacy task files after verification.

## Feature Workflow

```text
/plan-features
/start-feature
/implement-feature
/close-feature
/audit-project
```

## Repository Layout

```text
pyproject.toml                     # package version, pytest, Ruff, and uv configuration
uv.lock                            # reproducible test dependency lock
mise.toml                          # tools and release publication task
copier.yml                         # Git-repository Copier entry point
scripts/release.py                 # synchronized version, commit, tag, and push helper
skills/
  dstack-core/
    SKILL.md
    references/TRUST-AND-AUTHORITY.md
  setup-project/
    SKILL.md
    copier.yml                     # bundled/local Copier entry point
    scripts/setup-project.py
    template/                      # complete generated-project scaffold
  update-project/
    SKILL.md
    scripts/update-project.py
  migrate-workflow/
    SKILL.md
    scripts/adopt-template.py
    scripts/migrate-legacy-workflow.py
    references/MIGRATION.md
  gh-pr-review/
    SKILL.md
    scripts/fetch_comments.py
    scripts/review_state.py
    scripts/wait_for_review.sh
  ...workflow skills...
tests/
```

Normal setup renders from the installed `skills/setup-project` directory. Its nested `copier.yml` selects
`skills/setup-project/template`, so setup remains self-contained after Skills CLI installation. The setup helper records
`gh:RobertDeRose/dstack` and the installed skill's `metadata.version` in Copier state so later `/update-project` runs
can query published Git tags. The root `copier.yml` remains the Git-repository entry point for local development and
tests.

Every skill declares the synchronized release in frontmatter as `metadata.version` and declares its required tools in
the space-separated `allowed-tools` field.

## Release and Validation

dstack releases use stable `vX.Y.Z` Git tags. `/update-project` discovers the latest eligible published tag and refuses
to fall back to an untagged `HEAD`.

Prepare a release with the mise task. It updates `[project].version`, `uv.lock`, and every skill's `metadata.version`;
creates a `chore(release): <version>` commit; and creates an annotated `v<version>` tag:

```bash
mise run publish <version>
```

After preparation, mise prompts before pushing the release commit and tag. The prompt defaults to no. Bypass the prompt
and push automatically with the opt-in switch:

```bash
mise run publish <version> --push
```

Use the fast static suite while editing:

```bash
uv run --frozen --group test pytest -m "not integration and not external"
```

Run the local end-to-end Copier and migration suites before opening a pull request:

```bash
uv run --frozen --group test pytest -m integration
```

Run the network-backed Skills CLI smoke test before tagging, or let the scheduled/tag workflow run it:

```bash
uv run --frozen --group test pytest -m external
```

Run everything serially only when a single-process full validation is specifically needed:

```bash
uv run --frozen --group test pytest
```

GitHub Actions runs static validation and the two integration suites as parallel jobs. The external Skills CLI check is
isolated in a scheduled, manually dispatched, and tag-triggered workflow so npm cold-start latency does not slow every
pull request.
