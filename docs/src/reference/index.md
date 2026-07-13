# Repository and command reference

## Primary commands

| Command               | Purpose                                                               |
|-----------------------|-----------------------------------------------------------------------|
| `mise run check`      | Run the shared read-only hk validation policy.                        |
| `mise run fix`        | Apply deterministic fixes from the shared hk policy.                  |
| `mise run docs:check` | Validate documentation structure and build the mdBook.                |
| `mise run docs:serve` | Serve the documentation locally.                                      |
| `mise run release`    | Run semantic-release with signed commits and tags; pushing is opt-in. |
| `uv run pytest`       | Run all repository tests.                                             |

## Workflow paths

| Path                                             | Contract                                               |
|--------------------------------------------------|--------------------------------------------------------|
| `skills/<name>/SKILL.md`                         | Canonical installed workflow instructions and version. |
| `skills/setup-project/template/`                 | Bundled generated-project scaffold.                    |
| `.beads/formulas/feature-lifecycle.formula.toml` | Project-local feature lifecycle graph.                 |
| `docs/src/features/<num>-<slug>/design.md`       | Intended behavior and design decisions.                |
| `docs/src/features/<num>-<slug>/index.md`        | Delivered feature reconciliation and evidence.         |
| `docs/src/planned-features.md`                   | Human roadmap; not executable state.                   |
| `.copier-answers.yml`                            | Copier-managed template source, revision, and answers. |

## Release contract

Releases use `vX.Y.Z` tags. Python Semantic Release synchronizes the project version, lockfile, and skill metadata
versions. Git configuration injected by the mise task requires both the release commit and annotated tag to be signed.
The task does not create a remote VCS release and does not push unless requested.
