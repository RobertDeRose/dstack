# Design — Universal project tooling

## Metadata

- Beads feature root: `dstack-mol-lg3`
- Feature slug: `universal-project-tooling`
- Design path: `docs/src/features/universal-project-tooling/design.md`
- Implemented record: `docs/src/features/universal-project-tooling/index.md`
- Base branch: `main`
- Status: reviewed

## Feature Summary

Every generated project receives one mise-managed developer interface, one hk policy, concrete tooling documentation,
and a resolved project-owned `mise.lock`.

## User Intent

Contributors and CI use the same discoverable commands without globally installed project tools.

## Goals

- Render the exact universal mise/hk baseline and required config.
- Expose `check`, `fix`, `docs:check`, `docs:build`, and `docs:serve`.
- Stash unstaged work during pre-commit fixes, not explicit `fix` runs.
- Lock Linux/macOS x64/ARM64 aliases and provision after setup and conflict-free Copier updates.
- Preserve the scaffold and report exact recovery when provisioning degrades.

## Non-Goals

- Application source, manifests, releases, language checks, CI, or dstack's full root inventory.
- Windows support; this feature's task contract uses POSIX shell.
- Global hk installation.

## User-Facing Behavior

New setup and conflict-free updates invoke a generated provisioner after rendering. It resolves `mise.lock`, installs
with the lock enforced, then installs hk hooks separately when Git exists. Failure never rolls back the scaffold;
structured output identifies the stage and recovery command. The lock targets `linux-x64`, `linux-arm64`, `macos-x64`,
and `macos-arm64`.

## Requirements

### Functional Requirements

#### Tool and version authority

| Tool                           | Version  | Purpose/config                                            |
|--------------------------------|----------|-----------------------------------------------------------|
| `hk`                           | `1.49.0` | Runner; both `hk.pkl` package URIs must also use `1.49.0` |
| `node`                         | `lts`    | Runtime for the declared npm formatter                    |
| `mdbook`                       | `latest` | Documentation via `docs/book.toml`                        |
| `uv`                           | `latest` | Inline-metadata Python scripts                            |
| `rumdl`                        | `latest` | Markdown via `.config/rumdl.toml`                         |
| `typos`                        | `latest` | Typo detection                                            |
| `npm:markdown-table-formatter` | `latest` | Markdown table check/fix                                  |

`hk` is the pin exception because its binary and Pkl imports are one version-coupled interface. No other root, language,
release, CI, YAML, shell, Python, or scanner tool is copied.

#### Tasks and checks

`mise.toml` sets `HK_MISE=1`; it does not use a post-install hook because provisioning must report install and hook
outcomes separately.

| mise task    | Command                                               |
|--------------|-------------------------------------------------------|
| `check`      | `hk check -a`                                         |
| `fix`        | `hk fix -a`                                           |
| `docs:check` | build dependency, then `uv run scripts/check-docs.py` |
| `docs:build` | `mdbook build docs`                                   |
| `docs:serve` | `mdbook serve docs --port <port>`, default `3000`     |

One hk step map feeds `check`, `fix`, and `pre-commit`. It contains only docs, markdown-table-formatter, rumdl, typos,
mise config, byte-order-marker, case-conflict, executable-shebang, merge-conflict, private-key, smart-quote, newline,
and trailing-whitespace checks. `pre-commit` sets `fix = true` and `stash = "git"`; `fix` sets only `fix = true`.
Universal ignores cover generated/build/cache/local-secret artifacts, never `mise.lock`.

#### Provisioning and lock lifecycle

The template renders stdlib-only `scripts/setup-tooling.py`; setup and update call it with their current Python and
users can rerun `python3 scripts/setup-tooling.py --json`. Its fixed order is:

1. find `mise`;
2. run `mise lock --yes --platform linux-x64,linux-arm64,macos-x64,macos-arm64`;
3. require a nonempty `mise.lock` and run `mise install --locked`;
4. if `.git` exists, run `mise x -- hk install --mise` separately.

`mise.lock` is generated/project-owned rather than a Copier template file. A conflict-free update reruns the provisioner
after Copier; a conflicted update skips it, sets update readiness false, and reports the recovery command. Update and
setup skills document this network side effect. `--skip-post-setup` skips all stages; `--no-git-init` still locks and
installs but skips hooks.

#### Result contract

Setup and update include this `tooling` object:

```json
{
  "status": "succeeded | degraded | skipped",
  "mise": "available | unavailable | skipped",
  "lock": {"status": "succeeded | failed | skipped", "path": "mise.lock", "error": null},
  "install": {"status": "succeeded | failed | skipped", "error": null},
  "hooks": {"status": "succeeded | failed | skipped | skipped-no-git", "error": null},
  "platforms": ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"],
  "recovery": []
}
```

Errors are bounded captured command text or `null`; recovery contains exact commands and is also reflected in existing
`outstanding`. Missing mise makes it `unavailable` and later stages `skipped`. Lock failure skips install/hooks; install
failure skips hooks; hook failure leaves successful lock/install intact. No-Git is `degraded` with `skipped-no-git`.
Explicit workflow skipping is `skipped`; all completed stages are `succeeded`. An update is ready for feature work only
when Copier is conflict-free and tooling succeeds.

### Quality Requirements

- Copier rendering remains local and safe; only post-render provisioning performs downloads.
- Configs load and every referenced executable is declared.
- Repeated provisioning is idempotent and never overwrites user code/config beyond generated tooling artifacts.
- Failure tests simulate subprocess outcomes; one marked live test proves real resolution/install/hooks.

### Documentation Impact

| Reader question                                            | Exact destination                                           | Owner              |
|------------------------------------------------------------|-------------------------------------------------------------|--------------------|
| How do generated-project contributors use/recover tooling? | template `docs/src/development/tooling.md.jinja`            | `dstack-mol-b69.1` |
| What files, tools, tasks, states, and platforms exist?     | template `docs/src/reference/tooling.md.jinja`              | `dstack-mol-b69.1` |
| Where are generated pages linked?                          | template `docs/src/SUMMARY.md.jinja` and conditional README | `dstack-mol-b69.1` |
| Where is tooling authority/flow documented in dstack?      | `docs/src/architecture/index.md`                            | `dstack-mol-b69.4` |
| How are setup/update failures recovered?                   | `docs/src/operations/index.md`                              | `dstack-mol-b69.4` |
| Which commands/hooks do dstack developers use?             | `docs/src/development/index.md`                             | `dstack-mol-b69.4` |
| What are exact files/tasks/status fields?                  | `docs/src/reference/index.md`                               | `dstack-mol-b69.4` |

Generated `README.md` uses named mise tasks, not raw `uv`/`mdbook` commands. Generated navigation links both tooling
pages. Root pages already exist in `docs/src/SUMMARY.md`; no root navigation change or new root page is needed. Language
quality profiles extends these same generated pages rather than inventing profile-specific documentation.

## Existing Context

Purposeful project scaffold now renders factual docs and local metadata scripts, while generated projects still
advertise raw global commands. dstack's root mise/hk files prove the task shape but include language, CI, and release
concerns that are not universal. Current setup owns post-render side effects; current update owns conflict-aware Copier
application.

## Proposed Design

Render the literal nine-tool baseline, one hk mapping, a project-local provisioner, and two concrete tooling pages.
Setup and update call the same provisioner while retaining their existing orchestration and reporting ownership.

## Architecture Consistency

Copier remains a local renderer. The generated provisioner owns network and repository-local tooling state. Setup/update
only decide when to invoke it and merge its result. Language quality profiles extends the same files/pages; GitHub
validation and docs deployment consumes the named tasks.

## Boundaries

Owned artifacts are the universal config/templates, generated provisioner/docs, setup/update integrations and skills,
focused tests, and the four root reader pages. Language quality profiles owns language profiles; GitHub validation and
docs deployment owns GitHub workflows; Monorepo tooling layout owns monorepo layout. Setup/update orchestrate side
effects; Copier only renders files.

## Operational Considerations

Resolution/downloads require network access and supported upstream artifacts. Degraded setup/update preserves rendered
files and returns a rerunnable command. The lock covers supported Linux/macOS targets; the live test records external
limitations rather than treating subprocess mocks as download proof.

## Compatibility and Migration

Pre-v1 compatibility aliases are unnecessary. Existing Copier-managed projects receive templates through
`/update-project`; after conflict resolution, rerunning update or the project-local provisioner reconciles the lock.
Local customizations remain subject to Copier conflict handling.

## Validation Strategy

- Structural matrix: every project kind, both Copier entrypoints, README kept/deleted.
- Config assertions: exact nine tools, synchronized hk versions, exact tasks/checks/hooks/ignores, loadable mise/hk
  config.
- Setup/update simulations: success, missing mise, skip, lock/install/hook failure, no Git, Copier conflict, stale lock.
- One representative marked live project: create lock, install locked tools, list tasks, build/check docs, run
  check/fix, prove pre-commit stashing and hooks, and finish without unexpected changes.
- Run repository tests, docs checker, mdBook build, and `mise run check`.

## Dependencies and Parallelism

Templates precede setup; setup precedes update; all three precede end-to-end validation; final root docs follow every
behavior task. This serializes shared scripts and gives every documentation path one implementation owner. Language
quality profiles and GitHub validation and docs deployment remain blocked on Universal project tooling at their feature
roots.

## Risks and Tradeoffs

Fuzzy aliases require initial network resolution, while the committed lock restores repeatability. A fixed hk pin needs
occasional template maintenance but prevents binary/Pkl drift. Four-platform resolution costs more than host-only lock
creation but avoids committing a lock unusable by common local/CI hosts.

## Implementation Decomposition

1. `dstack-mol-b69.1`: exact templates, generated tooling docs/navigation/README, render/config tests.
2. `dstack-mol-b69.2`: generated provisioner, setup integration/skill, status and failure tests.
3. `dstack-mol-b69.5`: update integration/skill and conflict/stale-lock tests; blocked by setup.
4. `dstack-mol-b69.3`: structural and representative live end-to-end validation; blocked by template, setup, update.
5. `dstack-mol-b69.4`: exclusive root reader documentation; blocked by all behavior/validation tasks.

Each task is one reviewed commit and owns only the documentation named in its Beads description.

## Resolved Decisions

- Universal baseline is one nine-tool mise/hk policy, not a copy of dstack's root config.
- Aliases are resolved per project; hk stays pinned to synchronize its versioned Pkl interface.
- Lock resolution is explicit before locked installation and owned by both setup and update paths.
- Hook installation is separate from tool installation; no implicit mise post-install hook.
- Generated development/reference pages are the Language quality profiles extension point.
- Live external proof runs once; matrix/failure coverage stays deterministic.

## Rejected Alternatives

- Copy root config: rejected because it imports language/release policy.
- Host-only lock: rejected because local and CI hosts commonly differ.
- Implicit mise post-install hook: rejected because it merges install and hook failure.
- Optional baseline: rejected because the feature requires one universal interface.

## Open Questions

None.
