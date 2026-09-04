# Getting started

dStack is opt-in. Normal requests do not create Beads work; invoke one of the installed commands when you want the
native feature workflow.

Install dStack and its five hidden agent skills plus public prompt commands:

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install skills
```

Initialize and validate the Beads workspace plus scoped `bd prime` instructions:

```bash
dstack init
```

`dstack init` is idempotent, preflights the supported Beads version, and uses
`bd init --init-if-missing --skip-agents --skip-hooks` for new workspaces. It does not create workflow issues or replace
an unhealthy existing `.beads` workspace. It never removes generic integrations from an existing workspace; clean those
up explicitly before relying on dStack's opt-in boundary. Review and commit the installed formula policy, then run
`dstack check formula`; `/plan-feature` and `/audit-project` do not pour new work until that committed-policy check
passes.

Start a feature with `/plan-feature`, then use `/review-plan`, `/implement`, and `/close-feature`. Use `/audit-project`
to inspect current project drift and prepare a normal remediation plan. Only explicit prompt invocation activates the
workflow; hidden skills are not model-selected.
