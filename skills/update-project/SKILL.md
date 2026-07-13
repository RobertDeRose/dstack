---
name: update-project
description: Update an existing Copier-managed dstack project to the latest eligible tagged template release, or route a legacy Markdown workflow through migration before updating.
metadata:
  version: "0.2.1"
allowed-tools: Read Glob Grep Edit Write Bash AskUserQuestion
---

# Purpose

Use this skill for an existing repository. It first decides whether the repository is ready for a Copier update or still
needs legacy-workflow migration. A normal update discovers the latest eligible tagged release from the Git source
recorded in `.copier-answers.yml`, then applies Copier's three-way update so project-owned changes remain local.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

Update-specific authority:

- Invocation authorizes preflight inspection. It authorizes a local Copier update and dedicated reconciliation commit
  only after the repository passes migration routing. It does not authorize push, merge, force-push, branch deletion, or
  unrelated project changes.
- The default update queries the Git source recorded in `.copier-answers.yml` for tags and selects the newest stable PEP
  440-compatible `vX.Y.Z` release.
- The installed skill's `metadata.version` is not the update target. Skill installation and generated-project updates
  are independent operations.
- Explicit development revisions must be reported before mutation and never result from an implicit fallback to `HEAD`.

## 1. Route legacy repositories before update

Run the non-mutating preflight first:

```bash
uv run <skill-dir>/scripts/update-project.py --preflight --json
```

The helper inspects:

- whether `.copier-answers.yml` exists;
- active `tasks.md` files anywhere in the project, excluding tool, template, archive, migration, and vendored
  directories;
- initialized Beads state, without treating a copied formula as an initialized database.

When `recommended_workflow` is `migrate-workflow`, do not run Copier update. Explain the detected task files and missing
Beads state, then ask exactly one question with `AskUserQuestion`: `Run /migrate-workflow now?`

- If the user agrees, execute `/migrate-workflow` and let that workflow adopt the current tagged template, manually
  reconcile the rendered new-project structure, initialize Beads, and import the legacy task state.
- If the user declines, stop without running Copier or changing files.
- After migration completes and commits its checkpoints, rerun this preflight before considering an update.

This routing applies whether Copier state is already present or absent. A repository with legacy `tasks.md` files and no
Beads state must migrate before template update.

## 2. Update preconditions

Continue only when preflight recommends `update-project` and:

- `.copier-answers.yml` records a Git-backed `_src_path` plus `_commit`;
- the initial scaffold or completed migration checkpoint is committed;
- the worktree is clean unless the user explicitly accepts a dirty update;
- the recorded Git source contains at least one eligible release tag.

## 3. Apply the tagged update

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

1. resolves the Git root and performs migration routing before any tag lookup or mutation;
2. reads the Copier source and previous revision from `.copier-answers.yml`;
3. runs `git ls-remote --tags` against that source and selects the greatest eligible tag using PEP 440 ordering unless
   `--vcs-ref` is supplied;
4. excludes prereleases by default and includes them only with `--prereleases`;
5. verifies that a selected release tag exists before modifying the project;
6. requires a clean worktree by default;
7. applies the Copier update;
8. checks only Git-visible modified and untracked files for coherent conflict markers, Git unmerged paths, and newly
   produced `.rej` files;
9. ignores dependency environments and other Git-ignored content such as `.venv`;
10. when conflict-free, runs `python3 scripts/setup-tooling.py --json` to refresh `mise.lock`, install with `--locked`,
    and reconcile hooks before documentation or Beads checks;
11. when conflicted, skips all generated project code, reports tooling as skipped, and names the recovery command;
12. runs `scripts/check-docs.py` when present;
13. runs storage-mode-neutral Beads smoke checks with `bd info --json` and `bd ready --json --limit 1`;
14. validates the project feature formula when present;
15. reports the selected release, resolved Copier commit, changed files, tooling stages, validation, warnings,
    conflicts, and readiness.

`bd doctor` is not used because it is not supported by every Beads storage mode.

## 4. Reconcile every changed path

Build a path-accounting ledger from the helper's changed-file output plus `git status --short` and
`git diff --name-status`. Every changed path must appear exactly once with one classification:

- `template change accepted`;
- `project change preserved`;
- `conflict resolved`.

For each path, record the upstream change, local behavior that must remain, resolution, and validation evidence:

| Path | Classification           | Upstream/local intent | Resolution | Validation |
|------|--------------------------|-----------------------|------------|------------|
| `…`  | template change accepted | …                     | …          | …          |

Preserve project-owned architecture, operations, development, reference, roadmap, and feature history. Stop when a path
is ambiguous; absence of a textual conflict is not acceptance. Reconciliation is incomplete while any changed path is
missing from the ledger or classified only as `unknown`.

After every path is accounted for, rerun project-specific validation against the final files and commit the template
update as a dedicated boundary before resuming feature work. A degraded tooling result is unresolved: run each reported
recovery command and verify a current nonempty `mise.lock` before classifying the update ready.

## Return

Report:

1. preflight route, legacy task files, Beads-state result, and user consent decision when migration was offered;
2. destination and Copier source;
3. previous Copier revision;
4. discovered or explicitly requested release tag and resolved revision;
5. changed files and the complete path-accounting ledger;
6. real update conflicts and resolutions;
7. separate tooling availability, lock, install, and hook states plus exact recovery commands;
8. documentation and Beads validation;
9. warnings and any unclassified path;
10. readiness to resume feature work, which must be false while migration is required, conflicts or degraded tooling
    remain, the lock is stale or missing, or a changed path is unclassified.
