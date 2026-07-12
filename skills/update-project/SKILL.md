---
name: update-project
description: Update a Copier-managed dstack project to the newest published template tag. Use when asked to inherit template changes while preserving project-owned files, validating the result, and resolving real update conflicts.
metadata:
  version: "0.0.0"
allowed-tools: Read Glob Grep Edit Write Bash AskUserQuestion
---

# Purpose

Use this skill to inherit newer workflow, formula, script, and scaffold changes from the published dstack Copier
template. Copier uses `.copier-answers.yml` and a three-way update so project-owned changes remain local while template
changes are applied.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

Update-specific authority:

- Invocation authorizes a local Copier update and its dedicated reconciliation commit. It does not authorize push,
  merge, force-push, branch deletion, or unrelated project changes.
- The default command queries the Git source recorded in `.copier-answers.yml` for tags and selects the newest stable
  PEP 440-compatible `vX.Y.Z` release. Projects created by `/setup-project` record `gh:RobertDeRose/dstack`.
- The installed skill's `metadata.version` is not the update target. Updating skills and updating a generated project
  are independent operations.
- Explicit development revisions must be reported before mutation and never result from an implicit fallback to `HEAD`.

## Preconditions

- `.copier-answers.yml` exists at the Git root and records a Git-backed `_src_path` plus `_commit`;
- the initial scaffold has been committed;
- the worktree is clean unless the user explicitly accepts a dirty update;
- the recorded Git source contains at least one eligible release tag.

## Execution

Update to the newest stable published release:

```bash
uv run <skill-dir>/scripts/update-project.py
```

Preview, include prereleases, or explicitly select another revision:

```bash
uv run <skill-dir>/scripts/update-project.py --pretend
uv run <skill-dir>/scripts/update-project.py --prereleases --pretend
uv run <skill-dir>/scripts/update-project.py --vcs-ref <release-tag>
uv run <skill-dir>/scripts/update-project.py --vcs-ref HEAD
```

An explicit branch, commit, or `HEAD` is allowed for development, but the default command requires a published release
tag and refuses to fall back silently.

## Helper contract

The helper:

1. resolves the Git root and reads the Copier source and previous revision from `.copier-answers.yml`;
2. runs `git ls-remote --tags` against that source and selects the greatest eligible tag using PEP 440 version ordering
   unless `--vcs-ref` is supplied;
3. excludes prereleases by default and includes them only with `--prereleases`;
4. verifies that a selected release tag exists before modifying the project;
5. requires a clean worktree by default;
6. applies the Copier update;
7. checks only Git-visible modified and untracked project files for coherent conflict markers, Git unmerged paths, and
   newly produced `.rej` files;
8. ignores dependency environments and other Git-ignored content such as `.venv`;
9. runs `scripts/check-docs.py` when present;
10. runs storage-mode-neutral Beads smoke checks with `bd info --json` and `bd ready --json --limit 1`;
11. validates the project feature formula when present;
12. reports the requested release, resolved Copier commit, changed files, validation, warnings, and conflicts.

`bd doctor` is not used because it is not supported by every Beads storage mode.

## Reconciliation

Build a path-accounting ledger from the helper's changed-file output plus `git status --short` and
`git diff --name-status`. Every changed path must appear exactly once with one classification:

- `template change accepted`;
- `project change preserved`;
- `conflict resolved`.

For each path, record the upstream change, local behavior that must remain, resolution taken, and validation evidence.
Use a table such as:

| Path | Classification           | Upstream/local intent | Resolution | Validation |
|------|--------------------------|-----------------------|------------|------------|
| `…`  | template change accepted | …                     | …          | …          |

Preserve project-owned architecture, operations, development, reference, roadmap, and feature history. Stop when a path
is ambiguous; do not infer acceptance from the absence of a textual conflict. Reconciliation is incomplete while any
changed path is missing from the ledger or classified only as `unknown`.

After every path is accounted for, rerun project-specific validation against the final files and commit the template
update as a dedicated boundary before resuming feature work.

## Return

Report:

1. destination and Copier source;
2. previous Copier revision;
3. discovered or explicitly requested release tag and resolved revision;
4. changed files and the complete path-accounting ledger;
5. real update conflicts and their resolutions, if any;
6. documentation validation;
7. Beads smoke-check results;
8. warnings and any unclassified path;
9. readiness to resume feature work, which must be false while a path is unclassified.
