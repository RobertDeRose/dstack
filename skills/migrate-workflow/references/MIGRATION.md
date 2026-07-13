# Migrating the original Markdown workflow to Beads

This reference supplies conditional procedures for the ordered gates in `../SKILL.md`. The skill defines execution order
and completion criteria; this file explains edge cases and resolution commands.

Resolve `<skill-dir>` as the installed `migrate-workflow` skill directory.

## Target model

```text
Beads                                            live feature/task state and dependencies
docs/src/features/<num>-<slug>/design.md         intended behavior and design
docs/src/features/<num>-<slug>/index.md          standalone delivery/audit record
docs/src/planned-features.md                     human roadmap narrative
docs/src/**/*.md                                 current reader-facing behavior
migration/workflow-migration.json                resumable migration state and decisions
migration/workflow-migration.md                  human migration report
migration/legacy-tasks/<num>-<slug>.md           archived legacy task evidence
```

Mechanical conversion includes numbering, path rewriting, task parsing, and graph creation. Semantic reconciliation
determines what was actually delivered and must use code, tests, current docs, commits, or operational evidence.

## Baseline interpretation

Record the pre-adoption baseline while the repository still reflects the legacy workflow:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py baseline --write
```

The command writes `migration/baseline.json` and `migration/baseline.md`.

Statuses mean:

- `passed`: the discovered or explicit command succeeded;
- `failed`: an existing authoritative command failed and must be investigated;
- `unavailable`: no pre-adoption documentation checker or executable command was available;
- `no_tests`: no tests existed, or pytest returned exit code 5 with zero collected tests.

Use repository-specific commands when discovery is wrong:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py baseline --write \
  --docs-command '<authoritative-docs-command>' \
  --test-command '<authoritative-test-command>'
```

Because `adopt-template.py` requires a clean worktree, commit the written baseline before adoption. Do not use
`--allow-dirty` merely to bypass this checkpoint.

## Template source and revision

Adoption renders the current tagged **new-project** template into a temporary directory first. It does not depend on a
migration script copied into the target project. Commit the reconciled Copier adoption before initializing Beads so the
framework and workflow-state boundaries remain distinct.

Default adoption:

```bash
uv run <skill-dir>/scripts/adopt-template.py --json
```

The installed skill defaults to `gh:RobertDeRose/dstack`, discovers the latest stable release tag, and verifies it before
Copier runs. If tags cannot be discovered, supply an explicitly reviewed revision; never silently use GitHub `HEAD`.

For a fork, local repository, branch, or commit:

```bash
uv run <skill-dir>/scripts/adopt-template.py \
  --template-source <git-url-or-path> \
  --vcs-ref <tag-branch-or-commit> \
  --json
```

Adoption merges marked dstack sections into `AGENTS.md` and `.gitignore`. It installs dstack-owned files such as the
lifecycle formula, documentation checker, feature templates, and Copier state. Existing Copier answers are backed up,
then rebased to the tagged template that was rendered so later updates start from the reconciled baseline. Missing
project scaffold files are copied. Existing project-owned files are preserved; the generated alternatives are placed under
`migration/template-adoption-candidates/` for explicit manual reconciliation. Replaced dstack framework files are
backed up under `migration/template-adoption-backup/`.

For every `manual_merge` path, compare the current file with the candidate and merge only the needed documentation
structure, links, markers, or conventions. Preserve project-specific content. Remove the candidate directory before the
adoption checkpoint:

```bash
uv run scripts/check-docs.py --migration-mode
test ! -e migration/template-adoption-candidates
```

Migration mode keeps broken links and unsafe paths as errors while reporting legacy headings, missing taxonomy
concerns, unnumbered feature paths, task files, and missing implemented-feature markers as warnings.

Initialize Beads only after adoption is committed:

```bash
bd init --stealth --skip-agents
bd formula show feature-lifecycle --json
```

## Task parser coverage

Scan with:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py scan --write
```

Supported checkbox form:

```md
- [x] `T010` Implement feature
  - Depends on: T000
```

Supported heading/status form:

```md
## T010: Implement feature

Status: done Depends on: T000 Validation: pytest
```

Review these report counters:

```text
Legacy task files
Parsed task files
Unparsed task files
Parsed legacy tasks
```

If any task file is unparsed, stop before `prepare` or `import-beads`. Extend the parser or map the state explicitly.
Never continue while silently dropping task history.

Recognized statuses include open/todo/pending, in progress, blocked, deferred, skipped, and done/completed. Explicit
validation commands and `Depends on:` relationships are retained when parseable.

## Roadmap identity

The canonical heading is:

```md
### F010 — Human title (`stable-slug`)
```

The number is immutable identity, the human title is reader-facing, and the backticked slug is the parser identity. The
scanner also accepts legacy slug-only headings and numbered headings without a title.

Roadmap-only `planned` or `deferred` entries legitimately may have no feature directory. Missing `design.md` or
`tasks.md` evidence for those untouched features is not a migration conflict.

## Semantic decisions

Override inferred classification:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py classify F010 completed \
  --reason "Code, tests, docs, and delivery history confirm completion."
```

Return to scanner-derived classification:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py classify F010 auto
```

Resolve one finding using its stable ID:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py resolve-findings F010 \
  --finding <finding-id> \
  --reason "Repository evidence resolves this historical contradiction."
```

Resolve all currently open findings only after reviewing each one:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py resolve-findings F010 \
  --all \
  --reason "All findings were reconciled against code, docs, tests, and Git history."
```

Resolutions and rationale survive rescans and remain visible as audit history. Do not hand-edit generated finding
arrays.

## Dependency cycles

`blocks` affects ready-work calculation. Both `blocks` and `related` relationships are traversed by commands such as
`bd list`, and parent relationships are part of the same feature-root traversal graph. Therefore, a relation may be
non-blocking and still be unsafe when it closes a recursive traversal path.

Allowed relations:

```text
blocks   hard prerequisite; affects bd ready and is traversed by bd list
related  contextual relationship; does not block, but is still traversed by bd list
remove   remove a false, redundant, or directionally duplicated inferred relationship
```

Use `related` only when the complete graph remains acyclic. It is not a way to break a reciprocal dependency. When F030
already blocks on F050, a reverse F050-to-F030 relationship normally adds no information and should be removed instead:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py dependency F050 F030 remove \
  --reason "F030 already blocks on F050; the reverse inferred edge is redundant and would create recursive traversal."
```

Preserve useful context in the reason, roadmap prose, design, or Beads notes rather than adding a redundant reverse
edge. The migration command validates the blocking DAG and the complete `blocks`/`related`/parent traversal graph before
Beads mutation. Update roadmap prose whenever the semantic relationship changes.

## Preparing numbered paths

Preview and apply:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py prepare
uv run <skill-dir>/scripts/migrate-legacy-workflow.py prepare --apply
```

Preparation:

- assigns immutable zero-padded numbers;
- renames feature directories;
- rewrites structural links without rewriting unrelated URL/path text;
- creates `docs/src/features/index.md` when needed;
- adds implemented-feature navigation markers;
- converts roadmap headings to canonical identity form;
- marks legacy records for migration-aware validation.

A target-path collision is blocking. Inspect both directories and choose one canonical feature identity before retrying.
Commit this mechanical boundary separately.

## Beads import and recovery

Preflight without mutation:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py import-beads
```

The preflight validates:

- lifecycle formula syntax and unique step IDs;
- formula dependency cycles;
- Beads issue-type blocker compatibility;
- the blocking feature dependency DAG;
- the complete feature-root traversal graph across `blocks`, `related`, and parent relationships;
- legacy task parser coverage.

A clean `bd dep cycles` result is not sufficient evidence for the complete graph because that command reports blocking
cycles. The migration preflight additionally rejects mixed relationship cycles that would make recursive traversal
commands such as `bd list` repeat indefinitely.

Apply only after preflight succeeds:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py import-beads --apply
```

The importer searches existing Beads records by deterministic migration metadata before creating anything. It restores
manifest IDs for roots, lifecycle steps, implementation tasks, and reconciliation tasks. Repeated import must be
idempotent.

When a partial import exists:

1. rerun the dry-run;
2. inspect recovered IDs in `migration/workflow-migration.json`;
3. rerun `--apply` only when no duplicate identity is reported.

When duplicates are reported, do not delete issues blindly. Compare migration identity, parent/root, notes, and history;
retain the manifest-backed canonical record, record the decision, and remove only a proven duplicate.

When an imported feature relationship must be corrected, rerun the same `dependency` command with an evidence-backed
reason. After import has started, the helper reconciles the Beads edge and migration manifest together. Do not run
`bd dep remove` and then hand-edit `migration/workflow-migration.json`; that can leave the durable audit state and Beads
state disagreeing.

The importer creates one feature root per roadmap feature, lifecycle/review tasks, live implementation tasks, hard and
related dependencies, evidence notes, and reconciliation work. Legacy `T000` and `T999` become lifecycle evidence rather
than ordinary implementation tasks.

## Semantic reconciliation

For each active design:

- preserve concrete intent, constraints, interfaces, examples, rejected alternatives, and validation detail;
- align the design with current architecture and exact documentation ownership;
- preserve unresolved decisions explicitly;
- record actual Beads IDs and paths in metadata;
- distinguish intentional evolution from accidental drift.

For each genuinely delivered feature, create a standalone `index.md` from `docs/src/features/_template/index.md`. It
must explain delivered behavior without requiring the internal design or archived task file.

Do not fabricate designs or delivered records for untouched planned/deferred features. Legacy-format designs may remain
a warning during migration, but active or delivered features must be reconciled before strict completion.

dstack checks required headings case-insensitively. The bundled templates use Title Case as a default, but migration
must adapt the newly adopted `_template` files and reconciled feature records to the repository's existing Markdown
capitalization policy. Run the repository-native formatter or linter on those files and apply its style; do not weaken
or disable the host rule merely to satisfy dstack.

## Legacy task archival

Preview and apply:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py finalize
uv run <skill-dir>/scripts/migrate-legacy-workflow.py finalize --apply
```

The script refuses archival while a reader-facing Markdown page includes or links to `tasks.md`.

Default archive location:

```text
migration/legacy-tasks/<num>-<slug>.md
```

Use `--delete-tasks` only when deletion is deliberate and Git history is sufficient.

## Verification and completion

Run:

```bash
uv run <skill-dir>/scripts/migrate-legacy-workflow.py verify --beads
uv run scripts/check-docs.py
bd dep cycles
bd blocked --json
bd ready --json
```

`verify --beads` validates both the manifest relationships and the actual imported feature-root graph. Keep
`bd dep cycles` as a blocking/readiness diagnostic, but do not use it as the sole graph-safety check because it does not
report mixed `blocks`/`related` traversal cycles.

Run repository-native formatting, linting, documentation build, tests, and feature-specific checks. If no tests exist,
record that limitation instead of treating pytest exit code 5 as a failed suite. After any fix, rerun every affected
check and the final documentation check.

Prefer separate commits for:

1. pre-adoption baseline;
2. Copier adoption and workflow tooling;
3. scan decisions and migration plan;
4. numbered directory and link conversion;
5. Beads import and dependency decisions;
6. design and delivered-record reconciliation;
7. task archival and final drift fixes.
