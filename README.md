<!-- rumdl-disable-file MD041 -->

<p align="center">
  <img src="docs/src/assets/img/dstack_logo.png" alt="dStack logo">
</p>

`dStack` is a small deterministic control plane for software-engineering agents. It does not own a workflow state
machine.

- **Beads** owns plans, questions, decisions, tasks, dependencies, gates, claims, readiness, and completion.
- **Git** owns repository history and branches.
- **Git worktrees** isolate implementation work.
- **hk** runs repeatable repository checks and chains Beads lifecycle hooks.
- **dStack skills** guide planning, review, implementation, and drift analysis.
- **`dstack ctl`** performs only deterministic repository mechanics and structural validation.

The core invariant is simple: an agent finds its next unit of work through the native Beads ready queue, never through a
Markdown task list or dStack-owned lifecycle state.

## Workflow

One persistent Beads molecule represents a feature:

```text
plan -> review -> human approval -> implementation tasks -> audit
```

The formula creates five fixed steps. The implementation epic is only a structural container: Beads does not permit a
task-shaped approval milestone to block an epic. Review therefore creates every implementation child atomically with a
native dependency on approval. The audit uses one native `children-of(implementation)` waits-for edge as its sole fan-in.

The four installed skills are:

```text
/plan-feature   Ask material questions and record the plan in Beads
/review-plan    Review the plan against code/docs and create native tasks
/implement      Claim and complete the next native ready task
/audit-feature  Detect implementation/documentation/intent drift
```

Planning records questions, answers, decisions, rationale, repository evidence, non-goals, compatibility concerns,
acceptance criteria, and documentation impact in native Beads fields. Current repository documentation describes how the
system works. Decision Beads preserve why material choices were made. Git records what changed.

The plan validator requires paired `Question:`/`Answer:` entries or an evidence-based `No material questions: <reason>`
declaration; an agent cannot silently omit the ambiguity pass and still close planning.

## Install

Requirements:

- Git
- Pi or another shell-capable coding agent
- `uv`
- Python 3.14
- Beads 1.2.2
- hk for project validation
- mdBook 0.5.4 when documentation validation is enabled

Install the CLI:

```bash
uv tool install --python 3.14 /path/to/dstack
```

Install the four targeted Pi skills and prompts:

```bash
dstack install_skills
```

Initialize Beads directly. dStack never initializes Beads and never uses stealth mode:

```bash
bd init --quiet --non-interactive
```

Install the project-local dStack formula:

```bash
dstack ctl formula install
dstack ctl formula check
```

The formula is copied to `.beads/formulas/dstack-feature.formula.toml` as versioned project configuration. dStack does
not use a formula swap journal, formula cache, or recovery ledger. Commit intentional formula updates as normal project
configuration outside implementation-task commits.

## Deterministic commands

```text
dstack ctl formula install [--update]
dstack ctl formula check
dstack ctl plan check <plan-bead>
dstack ctl worktree ensure <feature-or-descendant>
dstack ctl git commit --bead <task> [--body-file <path>]
dstack ctl git amend --bead <task> [--body-file <path>]
dstack ctl evidence commits --bead <task> --ref <range>
dstack ctl task check <task>
dstack ctl audit evidence <feature> [targeted detail flags]
dstack ctl docs validate
```

These commands do not decide which workflow step is ready and do not advance Beads state. Skills perform native `bd`
mutations after deterministic checks succeed. Task and audit checks always run the repository's `hk check -a` contract;
agent-facing flags cannot replace it with a weaker command or alternate Git refs.

## Commit contract

Implementation task labels define the commit prefix:

```text
dstack:commit:<type>
dstack:scope:<optional-scope>
```

`dstack ctl git commit` derives the subject from the task title and adds exactly one one-way evidence footer:

```text
feat(parser): preserve source locations

Beads: project-abc.3
```

No commit SHA is stored in Beads. dStack reconstructs evidence from reachable Git history, so amend, rebase, and
cherry-pick do not require a mapping update.

## Documentation contract

Each implementation task classifies its effect on all three audiences:

```markdown
## Documentation impact

- End-user: required - <behavior, configuration, operations, or migration docs>
- Developer: required - <architecture, interfaces, tests, or extension docs>
- Future-agent: required - <current invariant or decision record>
```

`not affected` is valid only with a specific reason. Documentation that explains changed behavior belongs in the same
task as code and tests. The final audit compares approved intent, tasks, commits, observable behavior, current
documentation, and decision history. When authority is ambiguous, it creates a native human gate and asks the user
rather than silently choosing code or docs.

## Development

```bash
uv run pytest
uv run pytest tests/acceptance
hk check -a
```

Real-Beads acceptance tests require Beads 1.2.2 on `PATH`.
