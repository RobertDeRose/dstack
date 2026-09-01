# Documentation

Put documentation where a reader would look based on the question they are trying to answer.

The accepted design is prepared before implementation; current-product documentation ships from the final closeout or
alignment landing. Tests prove outcomes; documentation explains those outcomes, constraints, contracts, and intended
use.

## Audiences

One durable mdBook serves:

- **End users and operators** installing, configuring, using, operating, troubleshooting, recovering, upgrading, or
  maintaining the product.
- **Developers and reviewers** understanding architecture, invariants, interfaces, design constraints, tests, repository
  conventions, and maintenance boundaries.
- **Future agents and auditors** reconstructing accepted intent, explaining the current codebase shape, and detecting
  drift from documentation, source, tests, Git, and durable Beads intent.

No separate agent documentation tree exists. Humans and agents consume the same durable sources.

When a feature is materialized, its planned Beads description and acceptance criteria are copied once into the design
scaffold. Specification review then refines that content into the accepted repository design; dStack does not keep Beads
prose and Git documentation in live two-way synchronization.

## Canonical foundation

Every managed project uses `docs/book.toml` and `docs/src/SUMMARY.md` as its canonical book and navigation. The required
source foundation is:

```text
docs/src/
├── SUMMARY.md
├── index.md
├── architecture/index.md
├── development/index.md
├── development/documentation.md
└── features/index.md
```

This is a minimum, not an allowlist. Projects add only sections that answer real reader questions. Operations,
provisioning, specifications, reference, modules, tutorials, examples, hardware, security, deployment, networking, and
integration sections are optional. Empty taxonomy is not useful documentation.

`SUMMARY.md` is the sole navigation manifest. Durable reader-facing Markdown belongs in the book rather than hidden
elsewhere in `docs/src`.

## Semantic boundaries

- Orientation explains what the project is, who it serves, its capabilities, and its important boundaries.
- Architecture describes the current system, relationships, and durable invariants—not chronological change history.
- User and operator guidance explains current installation, use, operation, troubleshooting, maintenance, and recovery.
- Development explains how to build, test, change, validate, document, and release the project.
- Reference states exact current configuration, commands, APIs, schemas, interfaces, contracts, and compatibility.
- Specifications state normative requirements when a project has them.
- Feature records preserve accepted change intent and reconcile it with delivered reality.

Current behavior belongs in current-product documentation. A reader should not need to know which feature introduced a
capability to understand or use it.

Feature documentation impact explicitly considers operator usage and configuration, deployment/upgrade/rollback,
operations and recovery, developer architecture and contracts, and future audit evidence. Concrete affected pages use
inline local Markdown links; an inapplicable subject is `Not applicable — <specific reason>`.

Feature design/reconciliation and alignment reconciliation records use one fixed ATX-heading contract shared by their
scaffolds and validators. Every required section contains substantive authored content or the explicit applicability
form. Code examples do not create headings or satisfy prose. Duplicate/missing headings, untouched scaffolds,
TODOs/placeholders, reference-style local links, missing targets, and repository escapes fail with section-specific
diagnostics before the corresponding authorization or terminal mutation.

Alignment review authority is Beads-native. Accepted corrections, acceptance criteria, priorities, and dependencies live
in the native correction workstream. Tier 1 writes only a concise temporary Markdown review summary outside the
repository and finalizes it with `alignment finish-plan --summary-file`. The analysis, human gate, approval step, and
current correction graph remain the complete live authorization surface. The controller does not create an external
plan packet, alignment review digest, or duplicate correction state. The final landing retains its separate temporary
Markdown reconciliation scaffold. Documentation is deferred to the final closeout or landing, and there is never a
per-task documentation manifest or reconciliation task. Human review remains responsible for truth and content quality.

## Feature records

Each feature keeps accepted intent in `features/<slug>/design.md` and delivered reconciliation in
`features/<slug>/index.md`. The implementation record explains what exists, where current behavior is documented, how
the design was delivered or intentionally changed, and which durable limitations remain. It does not copy task, branch,
commit, pull-request, or delivery history.

`features/index.md` catalogs records. `SUMMARY.md` has one top-level Feature Records entry and nests each implementation
record and design because native mdBook renders only listed chapters.

## Durable truth

Documentation may describe durable product classifications such as `planned`, `implemented`, and `deprecated`. It does
not mirror Beads readiness, blockers, assignees, active review, delivery readiness, task or gate identities, branches,
worktrees, commits, pull requests, or next dStack commands.

Beads owns actionable work and dependencies. Git owns documentation and its history. `dstack ctl` validates
deterministic mechanics without a second manifest, cache, or documentation state store.

## Validation

The repository and installed controller require mdBook 0.5.3. Validate the current book with:

```bash
dstack ctl docs validate
```

Validation requires the core foundation, canonical `[book].src = "src"`, local link targets, chapter navigation, and
mdBook build to succeed. It rejects orphan Markdown and paths that escape `docs/src`. External URLs are not fetched.

The deterministic link checker intentionally recognizes inline Markdown links/images and mdBook include directives.
Reference-style links, HTML links, autolinks, and other Markdown extensions remain mdBook content but are outside
dStack's mechanical target extraction. Use inline local Markdown links for concrete documentation surfaces that feature
closeout must prove exist.
