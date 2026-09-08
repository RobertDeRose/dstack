# Command contracts

Agent-facing operational commands emit deterministic compact JSON on standard output in every terminal. Runtime
validation failures emit JSON diagnostics on standard error and return a nonzero status. Set
`DSTACK_OUTPUT_FORMAT=pretty` for standard-library indented JSON. Top-level help, version, unknown-command, and argparse
output remains human-readable.

The canonical command surface is:

```text
dstack init [--root PATH] [--update]
dstack install skills [--agent-dir PATH]
dstack check formula [--root PATH]
dstack check plan --bead ID [--root PATH]
dstack check review --bead ID [--root PATH]
dstack check task --bead ID [--root PATH]
dstack check docs --slug SLUG [--root PATH]
dstack docs export-design --bead ID [--root PATH]
dstack docs commit --bead ID [--root PATH]
dstack commit -b|--bead ID [--root PATH]
dstack worktree -b|--bead ID [--root PATH]
dstack audit --bead ID [--offset N] [--include-plan] [--require-docs] [--root PATH]
```

Setup and deterministic checks do not create workflow issues. The workflow is activated only by an explicitly invoked
workflow skill or an explicit request to use dStack.

## Initialization and installation

`init` initializes a missing Beads workspace with `--skip-agents`, installs the packaged `dstack-feature` formula and
scoped `PRIME.md`, then validates the resulting contract. It is idempotent, does not create workflow issues, and refuses
to replace a different project formula or prime unless `--update` is explicitly supplied. Existing generic Beads
integrations are not removed.

```text
dstack install skills [--agent-dir PATH]
```

`install skills` installs or updates the five hidden dStack skills and public prompts under the configured Pi agent
directory. It preflights every managed destination and rolls back replacements and stale-resource removal if
installation fails. `install formula` installs or verifies the packaged formula and scoped prime in an already
initialized Beads workspace.

## Checks and repository operations

```text
dstack check formula
dstack check plan --bead <plan-bead>
dstack check review --bead <feature-root>
dstack check task --bead <task>
dstack check docs --slug <slug>
dstack docs export-design --bead <feature-root>
dstack docs commit --bead <feature-root>

dstack worktree --bead <feature-or-descendant>
dstack commit --bead <task>
```

Formula checks validate installed policy against the package and committed `HEAD`. Plan checks bind the requested Bead
to the fixed plan step and require the six level-three publishable sections, allowing nested subsections. They do not
classify prose keywords or checkbox syntax as unresolved decisions; skills and human gates own that judgment.
Review checks validate the complete
native graph and separate task fields (`description`, `design`, and `acceptance_criteria`) before approval. Task checks
validate graph membership, approval dependencies, Git evidence, and worktree cleanliness. Target repositories own their
documented project-validation contract. Standalone feature-document checks validate structure and nonempty content;
docs commit and audit also compare the exported design with the native plan; repository tooling owns whole-book builds and broader documentation policy. Worktree
checks derive `feat/<slug>` from native identity and verify its branch, path, repository, and common history with the
base. Advancing the base does not force a rebase during resume. Titles default to `feat(<slug>)`; an explicit native
conventional title prefix selects another type. Implementation notes supply the bullets, not planned description or
design. Each fragment is one line, no more than 96 characters, and preserves technical punctuation. Verb-led wording is
writing guidance, not an English whitelist. Each commit has exactly one `Task:` trailer; committing requires an
in-progress task with at least one implementation note. Corrections rewrite the exact owner and replay descendants,
leaving unrelated fixups separate. Clean retries are no-ops; notes-only changes can reword unpublished evidence.
`docs commit` accepts only the feature directory and its SUMMARY entry. Both new and reused documentation commits
must have permitted paths and the canonical `docs(<slug>): <feature title>` message with one close-step `Task:` trailer.
With one unpublished close-owned commit and a clean worktree, rerunning the command can reword its title. Ambiguous or
published evidence stops without rewriting. If validated publication is already inherited unchanged from the base,
no new commit is required: the result has `mode: unchanged` and `commit: null`. dStack does not generate empty
publication commits.

`audit --require-docs` requires close ownership when the feature publication changed. It validates exported content
against the native plan, checks publication paths in each commit, and rejects forbidden Beads state anywhere in the
feature history, including files later removed. Implementation commit and task checks reject the feature publication
directory, but still permit ordinary current-documentation changes outside it. Whole-book and project validation remain
owned by the target repository.

## Audit

```text
dstack audit --bead <feature> [--include-plan] [--offset N] [--require-docs]
```

Audit validates Beads-to-Git and publication evidence, not semantic compliance. Task, decision, gate, and commit
summaries are bounded to 100 rows per page; all evidence is checked regardless of the page. Error output is capped with
the total count reported. The already-loaded plan is available through `--include-plan` for semantic close review.

Read task and decision details with `bd show ID --include-comments --json`, issue history with `bd history ID --json`,
and commit contents with `git show SHA`. Audit does not wrap these native detail interfaces. The former
`--include-task`, `--include-decision`, `--history-for`, and `--include-commit-paths` options have been removed.

## Selectors, retries, and evidence size

Use `--bead ID` for Bead identity across `worktree`, `commit`, `check review`, `docs export-design`, `docs commit`, and
`audit`. Use `--slug SLUG` only for the Beads-independent documentation check. dStack intentionally keeps one selector
vocabulary rather than maintaining parallel aliases.

Audit checks all relevant evidence, regardless of feature size. Summary collections include counts and `next_offset`
when more rows exist; pass `--offset N` to read that page. `--include-plan` supplies approved intent for close review;
use focused native reads for task comments, decisions, and history. Missing/truncated native evidence is an error, not
an empty result. The Beads v2-default envelope still uses `schema_version: 1`, already enabled through
`BD_JSON_ENVELOPE=1`; unsupported schema versions are rejected.

Task titles default to conventional `feat` commits. A native title such as `fix: Preserve inbound timestamps` selects a
different type without introducing labels or separate metadata. Notes retain technical punctuation; dStack enforces
mechanical length/ownership rules, not an English verb whitelist. Clean canonical retries are no-ops; notes-only changes
can reword unpublished commits. Correcting one task does not autosquash another task's pending fixups.
