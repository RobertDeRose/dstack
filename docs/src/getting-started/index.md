# Getting Started

## Prerequisites

Before installing dStack, make sure you have:

- Git
- [uv](https://docs.astral.sh/uv/)
- Beads 1.2.2
- Pi, if you want to use the packaged workflow commands and skills

The dStack package requires Python 3.14. `uv` can manage that interpreter for the installed tool.

## Install

Install the CLI directly from GitHub:

```bash
uv tool install git+https://github.com/RobertDeRose/dstack
```

Then install the Pi workflow commands and their skills:

```bash
dstack install
```

By default, those resources are installed under `~/.pi/agent`. If Pi uses another directory, set
`PI_CODING_AGENT_DIR` or pass `--agent-dir` to `dstack install`.

## Initialize a repository

From the Git repository you want to use with dStack, run:

```bash
cd /path/to/repository
dstack init
```

Initialization creates the repository-local Beads workspace when needed and installs the dStack workflow policy under
`.beads/`. Review the generated changes and commit them with the repository.

Then verify that the committed formula matches the installed dStack version:

```bash
dstack check formula
```

You can run `dstack init` again safely. If an existing Beads workspace or policy needs attention, the command reports
what must be fixed instead of replacing it silently.

## The workflow

dStack is centered on feature work. A feature is planned, checked against the repository, approved, implemented as one
or more tasks, and then reviewed and closed.

```text
/plan-feature <request>
        |
        v
/review-plan <feature>
        |
        v
review and approve the proposed scope
        |
        v
/implement <feature>
        |
        v
/close-feature <feature>
```

### Plan

Start with a description of the change you want:

```text
/plan-feature <what you want to change>
```

Planning asks any questions needed to clarify the request and returns the feature ID used by the remaining workflow
commands.

### Review and approval

Review the plan against the current repository:

```text
/review-plan <feature>
```

Review turns the approved intent into bounded implementation tasks and presents the resulting scope, risks, and
material decisions. Read that result and explicitly approve the proposed scope before implementation begins.

### Implement

By default, `/implement` works on one task at a time:

```text
/implement <feature>
```

It resumes an in-progress task when one already belongs to the current agent; otherwise it claims the next ready task.
To work on a specific task, pass that task ID instead:

```text
/implement <task>
```

When you want the workflow to continue sequentially through every ready implementation task, use `--all`:

```text
/implement <feature> --all
```

`--all` still processes tasks one at a time. It stops when no implementation task is ready and reports the remaining
blockers or directs you to close the feature.

### Close

After the implementation tasks are complete, run:

```text
/close-feature <feature>
```

Close reviews the delivered repository against the approved plan. If it finds a clear implementation problem, the work
returns to implementation. When the review is clean, close updates or confirms the feature documentation and completes
the feature workflow.

## Project Auditing

### What it is

`/audit-project` reviews the current repository as a whole instead of reviewing one feature. It compares the current
code, tests, documentation, security and operational guidance, accepted decisions, and the repository's own validation
results.

### Why it exists

Feature close answers whether one feature matches its approved plan. Project auditing answers a different question:
whether the current project is internally consistent and whether documented expectations still match what is actually
implemented.

### When to use it

Use `/audit-project` when you want a repository-wide health and drift review that is not tied to a specific feature. If
there is nothing actionable, it reports the evidence and stops. If remediation is needed, it creates a normal feature
plan and returns that feature for the usual review, approval, implementation, and close workflow.

## Where to go next

- If work stopped partway through a workflow command, see [Interrupted Skill Recovery](../recovery.md).
- To understand how Beads, Git, skills, and the CLI divide responsibilities, see [Architecture](../architecture/index.md).
- For exact command syntax and options, see the [CLI reference](../reference/cli.md).
