# Install and use dstack

## Install the skills

```bash
npx skills@latest add RobertDeRose/dstack --all
```

## Create a project

Run `/setup-project` in a new project directory. The skill asks one question at a time for the project's purpose,
intended users, current scope, key boundaries, and kind. Supported kinds are library, CLI, service, application,
infrastructure, documentation, and other. It does not infer or fabricate missing project facts.

The skill renders its bundled Copier template, initializes Git and Beads when available, and validates the generated
documentation. Existing repositories are routed to `/migrate-workflow`; already managed repositories are routed to
`/update-project` with explicit consent.

## Deliver features

```text
/plan-features
/start-feature 010-feature-name
/implement-feature 010-feature-name
/close-feature 010-feature-name
/audit-project
```

Use `bd prime` at session start. Beads owns live readiness and dependencies; `docs/src/planned-features.md` is only the
human roadmap.

## Update

- `npx skills update` refreshes installed skills and bundled assets.
- `/update-project` applies a newer published Copier template to a managed repository.
- `/migrate-workflow` adopts an existing legacy Markdown workflow before normal updates.

## Failure boundaries

Setup refuses non-empty unmanaged destinations. For a new destination, direct helper invocation also rejects missing,
blank, multiline, or NUL-containing brief values and names the required flags. This is an intentionally breaking pre-v1
setup contract; F010 does not support updating or adopting older answer sets.

Update refuses missing or invalid Copier state and does not silently select untagged template code. If Beads is
unavailable, setup reports initialization and verification as outstanding rather than claiming a complete workflow
installation.

## Tool provisioning and recovery

Setup and conflict-free updates run the generated project provisioner after rendering. It executes, in order:

```bash
mise lock --yes --platform linux-x64,linux-arm64,macos-x64,macos-arm64
mise install --locked
mise x -- hk install --mise
```

The lock/install commands ignore user-global mise tools. Hook installation runs only when Git exists and is reported
separately. Setup with `--no-git-init` can therefore finish lock/install work while reporting hooks as `skipped-no-git`;
`--skip-post-setup` performs no generated code and reports all tooling stages as skipped.

A missing mise executable, failed lock resolution/download, failed locked install, or failed hook does not roll back the
scaffold. Inspect the returned `tooling` stages and run each listed recovery command. The general rerun command is:

```bash
python3 scripts/setup-tooling.py --json
```

Do not commit an empty or stale `mise.lock`. A Copier conflict skips provisioning entirely: resolve every conflict,
account for every changed path, then rerun the project provisioner. `/update-project` keeps readiness false while
conflicts, degraded tooling, a missing/stale lock, or unclassified changed paths remain.
