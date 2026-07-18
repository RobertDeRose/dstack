---
name: update-project
description: Update a Copier-managed dstack project through its stable or unstable template channel, explicitly bootstrap dstack self-adoption, or route a legacy Markdown workflow through migration.
metadata:
  version: "0.4.0"
allowed-tools: Read Glob Grep Edit Write Bash AskUserQuestion
---

# Purpose

Use this skill for an existing repository. It first decides whether the repository is ready for a Copier update, needs
legacy-workflow migration, or is the dstack template source eligible for explicit self-adoption. A normal update
resolves the recorded stable or unstable channel from the Git source in `.copier-answers.yml`, then applies Copier's
three-way update so project-owned changes remain local.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

Update-specific authority:

- Invocation authorizes preflight inspection. It authorizes a local Copier update and dedicated reconciliation commit
  only after the repository passes migration routing. It does not authorize push, merge, force-push, branch deletion, or
  unrelated project changes.
- The default channel is `stable`, which selects the newest stable PEP 440-compatible `vX.Y.Z` release. `unstable`
  selects the recorded source's default-branch HEAD. Existing projects preserve their recorded channel.
- Every selected tag, branch, or explicit revision is resolved to a reachable commit and that exact SHA is persisted in
  `_commit`; installed skill metadata is never template provenance.
- Explicit development revisions must be reported before mutation. Template-source self-adoption is never implicit.

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

For Copier-managed projects whose answers do not yet contain `language_profiles`, use the preflight's root-only
`suggested_language_profiles`. It maps `pyproject.toml` to Python, `tsconfig.json` or `package.json` to TypeScript,
`Cargo.toml` to Rust, `go.mod` to Go, `mix.exs` to Elixir, and `flake.nix` to Nix. Ask the user to confirm the
suggestions; never apply them automatically. If none are found or accepted, offer the exclusive `other` profile.
Recursive package discovery is outside this workflow.

Older answer files default to `single-package` with no packages. Preserve that state unless the user explicitly requests
conversion. Convert only with `--repository-layout monorepo` and one `--monorepo-package '<JSON object>'` per complete
package; never infer packages. The preflight lists exact destinations and occupied paths and rejects invalid, reserved,
overlapping, case-colliding, or symlinked paths before revision lookup or rendering. Package objects contain exactly
`display_name`, `slug`, `path`, and `language_profiles`; preserve display names and acronyms exactly.

## 2. Update preconditions

Continue with a normal update only when preflight recommends `update-project` and:

- `.copier-answers.yml` records a Git-backed `_src_path` plus `_commit`;
- the initial scaffold or completed migration checkpoint is committed;
- the worktree is clean unless the user explicitly accepts a dirty update;
- the recorded Git source can resolve the selected channel or explicit revision.

## 3. Apply the template update

Update through the recorded channel, or override it explicitly:

```bash
uv run <skill-dir>/scripts/update-project.py
uv run <skill-dir>/scripts/update-project.py --stable
uv run <skill-dir>/scripts/update-project.py --unstable
```

Preview, include prereleases, or explicitly select another revision:

```bash
uv run <skill-dir>/scripts/update-project.py --pretend
uv run <skill-dir>/scripts/update-project.py --prereleases --pretend
uv run <skill-dir>/scripts/update-project.py --vcs-ref <release-tag>
uv run <skill-dir>/scripts/update-project.py --vcs-ref <reviewed-tag-branch-or-commit>
uv run <skill-dir>/scripts/update-project.py --add-profile typescript
uv run <skill-dir>/scripts/update-project.py --remove-profile python --add-profile other
```

Omitting profile flags preserves the recorded selection. Add/remove flags are repeatable, idempotent set operations; the
same profile cannot appear in both sets. `other` is exclusive, and removing the final recognized profile requires adding
`other` in the same invocation.

Updates reuse structured project-brief values already recorded by Copier. For an older project missing any of purpose,
users, scope, boundaries, or project kind, ask one question at a time and pass the corresponding `--purpose`, `--users`,
`--scope`, `--boundaries`, and `--project-kind` flags. Never derive missing values from a legacy description.

An explicit branch, commit, or `HEAD` is a one-shot override. The helper persists the exact resolved commit while
leaving the selected stable/unstable channel as the default for the next update.

### dstack self-adoption

When preflight reports `update-project-adopt`, run only after explicit user approval and a clean worktree:

```bash
uv run <skill-dir>/scripts/update-project.py --adopt --unstable \
  --project-name dstack --project-slug dstack \
  --purpose "<purpose>" --users "<users>" --scope "<scope>" --boundaries "<boundaries>" \
  --project-kind other --language-profile python --json
```

Self-adoption renders the reachable remote default-branch commit in isolation, copies missing generated paths, preserves
existing dstack-owned paths, writes differing generated versions under `migration/copier-adoption-candidates/`, and
records exact unstable Copier state. Reconcile every candidate and remove the directory before validation or commit. It
never adopts a local-only commit or runs generated code before reconciliation.

## Helper contract

The helper:

1. resolves the Git root and performs migration/self-adoption routing before any revision lookup or mutation;
2. reads the Copier source and previous revision from `.copier-answers.yml`;
3. resolves the preserved or explicit channel: stable uses the greatest eligible tag by PEP 440 ordering; unstable uses
   the source default-branch HEAD;
4. excludes prereleases by default and includes them only with `--prereleases`;
5. verifies every selected revision is reachable and persists its exact commit SHA before reporting success;
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
15. preserves or explicitly adds/removes canonical language profiles, with legacy root-manifest suggestions reported by
    preflight but never silently applied;
16. defaults older layout answers to single-package and validates explicit package conversion before rendering;
17. reports the selected release, resolved Copier commit, changed files, tooling stages, validation, warnings,
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
3. previous Copier revision and channel;
4. selected channel, friendly tag/branch/ref, and exact resolved revision;
5. previous, suggested, and resulting language profiles;
6. repository layout, exact package preflight, rendered package paths, and every unresolved candidate;
7. changed files and the complete path-accounting ledger;
8. real update conflicts and resolutions;
9. separate tooling availability, lock, install, and hook states plus exact recovery commands;
10. documentation and Beads validation;
11. warnings and any unclassified path;
12. readiness to resume feature work, which must be false while migration is required, conflicts or degraded tooling
    remain, candidates remain unresolved, the lock is stale or missing, or a changed path is unclassified.
