# Install and use dstack

## Install the skills

```bash
npx skills@latest add RobertDeRose/dstack --all
```

## Create a project

Run `/setup-project` in a new project directory. The skill asks one question at a time for the project's purpose,
intended users, current scope, key boundaries, kind, and language profiles. Supported kinds are library, CLI, service,
application, infrastructure, documentation, and other. Select one or more recognized language profiles for a polyglot
root policy, or select exclusive `other` for only the universal baseline. Setup does not infer or fabricate missing
facts.

The skill resolves the stable channel by default or `--unstable` explicitly, verifies its installed template matches the
exact selected commit, renders the bundle, initializes Git and Beads when available, and validates the documentation.
Existing repositories are routed to `/migrate-workflow`; already managed repositories are routed to `/update-project`
with explicit consent.

## Deliver features

```text
/plan-features
/start-feature feature-name
/implement-feature feature-name
/close-feature feature-name
/audit-project
```

Use `bd prime` at session start. Beads owns live readiness and dependencies; `docs/src/planned-features.md` is only the
human roadmap.

## Update

- `npx skills update` refreshes installed skill definitions and scripts.
- `/update-project` applies the newest revision from the recorded stable or unstable channel to a managed repository.
  Pass `--stable` or `--unstable` to change the preserved channel. Repeat `--add-profile` and `--remove-profile` for
  explicit idempotent profile changes; their sets must be disjoint and the result nonempty.
- `/update-project --adopt --unstable` explicitly bootstraps dstack itself as an unstable template consumer; reconcile
  every generated candidate before validation or commit.
- `/migrate-workflow` adopts an existing legacy Markdown workflow before normal updates.

Migration captures the legacy hk hook/step inventory before adoption. Candidate reconciliation is additive: a removed
step or changed same-key definition blocks verification until restored or explicitly approved with both behaviors and a
reason. If the legacy config cannot be evaluated, migration stops for manual inventory confirmation rather than treating
the generated policy as equivalent. Durable manifests, reports, baselines, and legacy-task archives must be committed;
temporary candidates must be removed. Conditional adoption backups require an explicit retain/remove disposition.
Repeated unchanged scans do not churn committed migration evidence. Migration asks one question at a time with a concise
decision title, why it is needed, current evidence/uncertainty, controlled behavior, a concrete example, choices/safe
default, and the consequence of deferral. After reconciliation, the rendered project provisioner must install the locked
tools and Git hooks before an ordinary checkpoint commit. Failures stop with exact reproduction/recovery. A
user-approved intermediate exception may skip only the strict docs step after migration-mode docs pass and the decision,
equivalent evidence, and risk are recorded; whole-hook bypass is never allowed.

Beads import dry-run is a separate nonmutating command. Apply begins with an explicit `APPLY STARTED` notice and reports
existing, recovered, pending, conflicting, completed, remaining, and total features. Per-feature import phases persist
in the manifest, so retries skip completed state rather than replaying it. A later `scan --write` preserves import start
and completion timestamps, phase state, identities, and the last progress summary. Legacy checkbox states map `[ ]` to
open, `[-]` to in progress, and `[x]` to closed unless a nonempty explicit status overrides the checkbox.

Legacy managed projects keep their recorded profiles. When none are recorded, update preflight inspects only root
`pyproject.toml`, `tsconfig.json`/`package.json`, `Cargo.toml`, `go.mod`, `mix.exs`, and `flake.nix`, then presents
recognized profile suggestions for confirmation. It never applies suggestions automatically.

## Enable generated GitHub Pages

Generated projects include a default-disabled Documentation workflow. From the generated project, install and
authenticate external GitHub CLI with repository administration access, then run:

```bash
mise run docs:deployment:enable
```

The helper resolves the current GitHub repository, creates or updates Pages with `build_type=workflow`, sets
`DOCS_DEPLOYMENT_ENABLED=true` only after Pages configuration succeeds, and prints the Pages URL. Repeating the command
updates the existing configuration. A failure names the operation and never reports success.

For manual recovery, install `gh` from <https://cli.github.com/> if needed, then run:

```bash
gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow
gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO
gh api repos/OWNER/REPO/pages --jq .html_url
```

Use POST instead of PUT when Pages does not exist. If the final URL query failed, verify state before retrying because
the variable may already be set.

## Failure boundaries

Setup refuses non-empty unmanaged destinations. For a new destination, direct helper invocation also rejects missing,
blank, multiline, or NUL-containing brief values and names the required flags. This is an intentionally breaking pre-v1
setup contract; Purposeful project scaffold does not support updating or adopting older answer sets.

Update refuses missing or invalid Copier state and unreachable revisions. Stable never falls back to untagged code;
unstable explicitly resolves the source default-branch HEAD. If Beads is unavailable, setup reports initialization and
verification as outstanding rather than claiming a complete workflow installation.

## Tool provisioning and recovery

Setup and conflict-free updates run the generated project provisioner after rendering. It executes, in order:

```bash
mise lock --yes --platform linux-x64,linux-arm64,macos-x64,macos-arm64
mise install --locked
mise x -- hk install --mise
```

The lock/install commands ignore user-global mise tools. For the Nix profile, the provisioner validates the three
supported nixfmt-rs lock entries and removes only its macOS x64 entry before locked installation; all other tools retain
the four-platform lock. Hook installation runs only when Git exists and is reported separately. Setup with
`--no-git-init` can therefore finish lock/install work while reporting hooks as `skipped-no-git`; `--skip-post-setup`
performs no generated code and reports all tooling stages as skipped.

Profile source checks skip when no matching files exist. Package checks skip without their root manifest. A selected
manifest with missing project-owned pytest, Vitest, or Credo fails with the named prerequisite; flake checks similarly
require system Nix. Matching Nix inputs fail clearly on unsupported macOS x64.

A missing mise executable, failed lock resolution/download, failed locked install, or failed hook does not roll back the
scaffold. Inspect the returned `tooling` stages and run each listed recovery command. The general rerun command is:

```bash
python3 scripts/setup-tooling.py --json
```

Do not commit an empty or stale `mise.lock`. A Copier conflict skips provisioning entirely: resolve every conflict,
account for every changed path, then rerun the project provisioner. `/update-project` keeps readiness false while
conflicts, degraded tooling, a missing/stale lock, or unclassified changed paths remain.
