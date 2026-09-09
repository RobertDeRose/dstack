# Getting started

dStack is an opt-in feature workflow for software-engineering agents. It uses Beads for workflow state and Git for
repository state, while dStack handles deterministic checks and repository mechanics.

## Requirements

Install these tools first:

- Git
- Python 3.14
- Beads 1.2.2

The dStack repository itself uses additional development tools, but target repositories do not need hk or mdBook unless
they choose them for their own validation.

## 1. Install dStack once

Install the CLI and then install dStack's Pi workflow commands and skills:

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install
```

By default, agent resources are installed under `~/.pi/agent`. Set `PI_CODING_AGENT_DIR` or pass `--agent-dir` when Pi
uses a different directory.

## 2. Set up a repository

Run initialization from the Git repository that will use dStack:

```bash
cd /path/to/repository
dstack init
```

`dstack init` prepares the repository-local Beads workspace when needed and installs two reviewed policy files:

- `.beads/formulas/dstack-feature.formula.toml`
- `.beads/PRIME.md`

Initialization is idempotent and does not create feature work. It reports an unhealthy existing Beads workspace instead
of replacing it.

Review the installed formula, commit it with the repository, and verify that the committed policy matches the installed
dStack version:

```bash
dstack check formula
```

Feature planning will refuse to create new work until this check passes.

## 3. Plan your first feature

Start the workflow explicitly:

```text
/plan-feature <what you want to change>
```

Planning records the request, asks material questions, and produces a feature root. Keep that root ID; later workflow
commands can also accept an issue inside the same feature when documented.

## 4. Review and approve the plan

Review the plan against the current repository:

```text
/review-plan <feature>
```

Review creates bounded implementation tasks and presents the proposed scope, risks, and decisions. Review does **not**
grant approval. Read the result and explicitly approve the proposed scope before implementation begins.

## 5. Implement the approved work

Run:

```text
/implement <feature>
```

Implementation resumes work already owned by the current agent before claiming another ready task. dStack locates the
feature worktree, creates or corrects the task's canonical Git commit, and validates task evidence. The target
repository
still owns its test, lint, build, and other project-specific validation commands.

## 6. Review and close the feature

When implementation tasks are complete, run:

```text
/close-feature <feature>
```

Close reviews the delivered repository against the approved plan before writing feature documentation. Findings return
to implementation when necessary. Once review is clean, close publishes or confirms the feature documentation and
closes the workflow.

## Project-wide review

`/audit-project` is not a lifecycle stage. Use it when you want to compare the current repository with its
documentation,
decisions, tests, security guidance, and operational expectations. It creates a normal remediation plan only when it
finds actionable drift.

## When something is interrupted

Do not create replacement workflow state. Beads and Git remain authoritative after a restart. Start with
[Recovery](../operations/recovery.md), especially when `dstack worktree` reports `recovery_required`.

For exact CLI syntax, see the [CLI reference](../reference/cli.md). For the ownership model, see
[Architecture](../architecture/index.md).
