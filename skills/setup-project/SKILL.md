---
name: setup-project
description: Create and initialize a new Copier-managed dstack project from the latest stable template release or the explicitly selected unstable channel. Use only for a new project, with an explicit project name or basename($PWD) by default.
metadata:
  version: "0.2.1"
allowed-tools: Read Glob Bash AskUserQuestion
---

# Purpose

Use this skill only for a new repository. It resolves the selected channel from the official Git source, verifies the
installed bundled template matches that exact commit, renders the bundle, records the commit for future three-way
updates, initializes the new-project workflow, and validates the generated documentation. It does not migrate legacy
project state.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

Setup-specific authority:

- The default source is `gh:RobertDeRose/dstack`; `stable` selects its newest stable PEP 440 tag and `unstable` selects
  its default-branch HEAD. Stable is the default.
- The helper dereferences the selected tag, branch, or explicit revision, verifies the bundled `copier.yml` and
  `template/` match that commit, and records the exact reachable 40-character SHA in `.copier-answers.yml`; skill
  metadata is never used as template provenance.
- `--template-source` and `--vcs-ref` are explicit development/testing overrides. A requested revision must be
  retrievable from the recorded source.
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

## Project brief

Before invoking the helper, collect missing facts with `AskUserQuestion`, one question at a time, in this order:

1. `--purpose`: one sentence describing the problem and intended outcome;
2. `--users`: one sentence describing intended users;
3. `--scope`: one sentence describing current supported scope;
4. `--boundaries`: one sentence describing key exclusions and ownership boundaries;
5. `--project-kind`: select `library`, `cli`, `service`, `application`, `infrastructure`, `documentation`, or `other`;
6. `--language-profile`: select one or more of `python`, `typescript`, `rust`, `go`, `elixir`, `nix`, or `other`.

Selecting the kind and profiles is confirmation; do not ask a second confirmation question. `other` is exclusive and
means no recognized language tooling. Values must be non-empty single lines. Do not infer missing facts from the project
name or fabricate defaults.

## Defaults

- Project name: supplied value, otherwise `basename "$PWD"`.
- Destination: current working directory.
- Template channel: `stable`; pass `--unstable` to select the source default-branch HEAD.
- Render source: the installed bundle after exact revision verification; explicit `--template-source` overrides it.
- Recorded update source: `gh:RobertDeRose/dstack` unless `--template-source` is explicit.
- Recorded baseline revision: the exact resolved commit SHA; stable results also report the selected release tag.
- Default branch: `main`.
- Beads: initialize with `bd init --stealth --skip-agents` when `bd` is available; otherwise complete documentation
  setup and report Beads initialization as outstanding.
- Tooling: after rendering and optional Git initialization, resolve `mise.lock` for Linux/macOS x64/ARM64, install with
  `mise install --locked`, then install repository-local hk hooks separately. These steps require mise and network
  access.

## Execution

```bash
uv run <skill-dir>/scripts/setup-project.py [project-name] \
  --purpose "<problem and outcome>" \
  --users "<intended users>" \
  --scope "<current supported scope>" \
  --boundaries "<key exclusions and ownership boundaries>" \
  --project-kind <kind> \
  --language-profile <profile> [...]
```

The project name remains optional and defaults to `basename "$PWD"`. Add `--destination <path>` to target another new
directory, `--delete-readme` to omit the starter README, or `--unstable` to use the latest default-branch commit.

Development-only template overrides retain the same required brief flags:

```bash
uv run <skill-dir>/scripts/setup-project.py "Reader Control Plane" \
  --purpose "Coordinate reader devices from one control plane." \
  --users "Operators responsible for reader fleets." \
  --scope "Provisioning and health workflows for supported readers." \
  --boundaries "Reader firmware and identity-provider administration remain external." \
  --project-kind service \
  --language-profile python \
  --language-profile typescript \
  --template-source gh:example/dstack-fork \
  --vcs-ref <reviewed-tag-or-commit>
```

The setup helper performs post-render initialization itself. It does not generate `scripts/bootstrap.py`,
`scripts/migrate-legacy-workflow.py`, or a migration guide in the new project. Use `--skip-post-setup` to skip tooling,
Beads, and documentation setup while preserving exact recovery commands. `--no-git-init` still resolves and installs
tools but reports hook installation as `skipped-no-git`.

## Verification

Confirm at least:

```text
.copier-answers.yml
AGENTS.md
.beads/formulas/dstack-feature.formula.toml
docs/book.toml
docs/src/SUMMARY.md
docs/src/planned-features.md
docs/src/features/_template/design.md
docs/src/features/_template/index.md
scripts/check-docs.py
scripts/setup-tooling.py
mise.toml
hk.pkl
.config/rumdl.toml
```

Confirm these new-project-inappropriate paths do not exist:

```text
MIGRATION.md
scripts/bootstrap.py
scripts/migrate-legacy-workflow.py
```

Verify `.copier-answers.yml` records the selected source, exact resolved commit SHA, and `dstack_template_channel`.
Verify generated `AGENTS.md` requires real multiline commit messages via `git commit -F <file>` (never multiple `-m`
flags or escaped `\n`) and permits only `git merge --ff-only` into `main`. The helper runs
`uv run scripts/check-docs.py` as part of setup. A successful tooling run creates a nonempty `mise.lock`, installs with
`--locked`, and runs `mise x -- hk install --mise`. If mise, resolution, installation, or hook setup fails, the scaffold
remains intact and the JSON `tooling` object reports separate `mise`, `lock`, `install`, and `hooks` states, supported
platforms, bounded error text, and exact recovery commands. Rerun recovery with:

```bash
python3 scripts/setup-tooling.py --json
```

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
- Stable setup and updates select the newest stable tag; unstable setup and updates select the source default-branch
  HEAD. Both persist the exact commit used.
- `npx skills update` updates installed skill definitions and scripts.
- `/update-project` preserves the recorded channel unless explicitly overridden.
- Do not edit `.copier-answers.yml` manually.

## Return

Report project name, slug, purpose, users, scope, boundaries, kind, language profiles, destination, template channel,
selected ref, exact recorded commit, skill version, Git result, Beads result, documentation validation, the complete
`tooling` status, outstanding recovery commands, and the next `/plan-features` action. If setup was routed to
`/update-project`, report the user's consent decision and do not claim setup ran.
