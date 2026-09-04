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
dstack check review --feature ID [--root PATH]
dstack check task --bead ID [--root PATH]
dstack check docs --feature SLUG [--root PATH]
dstack docs export-design --feature ID [--root PATH]
dstack docs commit --feature ID [--root PATH]
dstack commit -b|--bead ID [--root PATH]
dstack worktree -b|--bead ID [--root PATH]
dstack audit FEATURE [detail flags] [--require-docs] [--root PATH]
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
dstack check review --feature <feature-root>
dstack check task --bead <task>
dstack check docs --feature <slug>
dstack docs export-design --feature <feature-root>
dstack docs commit --feature <feature-root>

dstack worktree --bead <feature-or-descendant>
dstack commit --bead <task>
```

Formula checks validate installed policy against the package and committed `HEAD`. Plan checks bind the requested Bead
to the fixed plan step and require exactly the six publishable design headings. Review checks validate the complete
native graph and separate task fields (`description`, `design`, and `acceptance_criteria`) before approval. Task checks
validate graph membership, approval dependencies, Git evidence, and worktree cleanliness. Target repositories own their
documented project-validation contract. Feature-document checks validate only the approved feature index, unchanged
exported design, and SUMMARY link; repository tooling owns whole-book builds and broader documentation policy. Worktree
checks derive `feat/<slug>` from the feature root and verify its branch, path, repository, and base ancestry. Commit
subjects use `feat(<slug>): <task title>`; implementation bodies contain one unwrapped bullet per ordered
`Implementation:` fragment. Each fragment must be verb-led, one line, and no more than 96 characters; formatting strips
surrounding whitespace and punctuation before adding a dash-and-space prefix. Each new commit contains exactly one
`Task: <task>` trailer. Repository-changing tasks require at least one implementation note. The task must be
`in_progress`. When a reopened task already has one unpublished commit, the same command creates a fixup and immediately
autosquashes it from the feature base. Ambiguous evidence, unrelated dirt, conflicts, or published history stop safely.
`docs commit` accepts only the feature directory and its SUMMARY entry, validates them, and creates the one final
`docs(<slug>): <feature title>` commit with no body and one internal-close-step `Task:` trailer. With one unpublished
close-owned commit and a clean worktree, rerunning the command safely rewords stale canonical metadata. Ambiguous or
published evidence stops without rewriting. `audit --require-docs` distinguishes feature-document checks from the target
repository's external validation contract and rejects a noncanonical close commit.

## Audit

```text
dstack audit <feature> \
  [--include-plan] \
  [--include-task ID] \
  [--include-decision ID] \
  [--history-for ID] \
  [--include-commit-paths] \
  [--require-docs]
```

Repeat `--include-task`, `--include-decision`, and `--history-for` when needed. Default task, decision, gate, commit,
and error collections are bounded to 100 items and report truncation. Commit paths are omitted unless
`--include-commit-paths` is explicit. Multi-issue reads are batched through native Beads commands.
