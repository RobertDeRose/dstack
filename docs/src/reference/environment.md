# Environment and defaults

| Setting | Default | Purpose |
| --- | --- | --- |
| `PI_CODING_AGENT_DIR` | `~/.pi/agent` | Target for installed prompts and skills |
| `DSTACK_COMMAND_TIMEOUT_SECONDS` | command-specific | Positive finite timeout override |
| `BD_JSON_ENVELOPE` | set to `1` by dStack | Stable Beads JSON envelope |

Project validation is fixed to `hk check -a` for agent-facing task and audit commands. There is no environment variable or
CLI option that can weaken validation or substitute alternate evidence refs.

The default base branch is recorded on each feature root during planning. The skills choose `dev` when it exists,
otherwise `main`; dStack does not maintain a project branch registry.

The conventional feature branch is `feat/<slug>`. Its worktree is a sibling of the primary checkout named
`<repository>.feat-<slug>`.
