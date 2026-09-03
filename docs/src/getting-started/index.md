# Getting started

dStack is opt-in. Normal requests do not create Beads work; invoke one of the installed commands when you want the
native feature workflow.

Install dStack and its four agent skills:

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install_skills
```

Initialize and validate the Beads workspace plus scoped `bd prime` instructions:

```bash
dstack init
```

`dstack init` is idempotent, uses `bd init --skip-agents` for new workspaces, and does not create workflow issues. It
never removes generic integrations from an existing workspace; clean those up explicitly before relying on dStack's
opt-in boundary.

Start a feature with `/plan-feature`. Use `/review-plan`, `/implement`, and `/audit-feature` as the native molecule
steps become ready.
