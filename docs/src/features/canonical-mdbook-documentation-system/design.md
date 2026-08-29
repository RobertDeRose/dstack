# Canonical mdBook documentation system

> **Historical record:** setup/migration behavior described below reflects the workflow at the time this feature was
> delivered. It is superseded by the current
> [compatibility and formula-audit contract](../../reference/compatibility.md): formulas are templates, historical
> graphs are not migrated, and normal commands do not run setup or migration.

## Feature summary

Make mdBook the canonical documentation system for dStack-managed projects and treat durable documentation as part of
implementation. dStack will establish a small common book foundation, define semantic boundaries and feature-record
lifecycle, validate deterministic documentation properties, and migrate only legacy content whose destination is
unambiguous.

The organizing principle is:

> Put documentation where a reader would look based on the question they are trying to answer.

The same durable book serves end users and operators, developers and reviewers, and future agents and auditors. There is
no agent-only documentation tree.

## User intent

A managed project should be understandable from its mdBook, source, tests, Git history, and durable Beads intent without
a previous conversation. Readers should find current behavior in current-product documentation and change history in
feature records. Projects should share minimum guarantees without being forced into identical optional directory trees.

## Goals

- Make `docs/book.toml` and `docs/src/SUMMARY.md` the canonical book and navigation sources for every managed project.
- Initialize a useful minimum foundation without overwriting authored content.
- Define durable semantic roles while allowing project-specific physical sections.
- Make documentation part of specification, implementation, validation, and closeout.
- Preserve accepted feature intent in `design.md` and delivered reconciliation in `index.md`.
- Keep current shipped behavior discoverable outside feature history.
- Automate only deterministic foundation, scaffold, navigation, local-link, build, orphan, leakage, and migration
  mechanics.
- Preserve existing project-specific content and report ambiguous migration choices instead of guessing.

## Non-goals

- An allowlist of optional documentation directories or one complete taxonomy for every project.
- Empty optional sections, source-tree mirrors, or speculative pages.
- A second documentation manifest, documentation database, semantic classifier, workflow ledger, or cached validation
  state.
- A separate documentation set for agents.
- Roadmap, unknowns, readiness, ownership, review, branch, commit, pull-request, or next-command mirrors of Beads and
  Git.
- Automatic decisions about architecture decomposition, module meaning, normative specifications, operational needs, or
  substantive prose.
- Network-dependent validation of external URLs.
- Reproducing dStack command or lifecycle instructions in managed projects.

## User-visible behavior

### Minimum foundation

`/review-feature-spec` creates these files only when missing:

```text
docs/
├── book.toml
└── src/
    ├── SUMMARY.md
    ├── index.md
    ├── architecture/
    │   └── index.md
    ├── development/
    │   ├── index.md
    │   └── documentation.md
    └── features/
        └── index.md
```

The created pages contain concise orientation for their required semantic role, not empty placeholders. Existing files
remain byte-for-byte unchanged. Setup creates no optional section and does not reject an unfamiliar directory.

`SUMMARY.md` remains the only navigation manifest. Optional project sections are authored directly in it. dStack does
not maintain parallel metadata that lists documentation structure.

### Documentation validation

A stateless documentation validator checks the current worktree. It:

- requires the minimum files;
- invokes the installed `mdbook` binary against `docs/book.toml` with build output directed to a temporary directory;
- verifies every local Markdown link resolves within the book source after removing query and fragment components;
- verifies every durable Markdown page under `docs/src`, except `SUMMARY.md`, is a book chapter listed in `SUMMARY.md`
  or is a source included by a listed chapter;
- rejects absolute, traversing, or symlink-escaping local targets; and
- reports all deterministic failures without writing a manifest or cache.

HTTP, HTTPS, and mail links are preserved but are not fetched. External reachability is not deterministic enough for
setup or closeout authority. Anchor correctness remains mdBook/author responsibility; dStack validates the local target
file rather than reimplementing mdBook heading rules.

The supported runtime contract is an `mdbook` executable on `PATH`. dStack does not install tools into managed projects
or parse a minimum version when the required build behavior succeeds. dStack's own repository pins the tested mdBook
release through its existing mise tool configuration and CI uses that pin.

Missing tooling or any validation failure returns nonzero before lifecycle completion. Temporary build output is removed
and no generated book is added to the repository.

### Semantic roles

The required and optional sections answer reader questions rather than mirror source layout:

- **Orientation** answers what the project is, who it serves, what it does, and its major boundaries.
  `docs/src/index.md` is the entry point.
- **Architecture** describes the current system, components, relationships, invariants, and runtime, trust, networking,
  persistence, or deployment boundaries. It is not chronological history.
- **User/operator guidance** explains current installation, configuration, use, deployment, operation, troubleshooting,
  backup, recovery, upgrades, and maintenance where those concerns exist.
- **Development** explains repository structure, build, tests, changes, validation, documentation, contribution, and
  releases. `development/documentation.md` records how the generic principles apply to the project.
- **Reference** states exact current configuration, defaults, commands, APIs, protocols, schemas, formats, interfaces,
  contracts, and compatibility.
- **Feature records** preserve accepted change-specific intent and reconcile it with delivered reality. They are not the
  primary source for current shipped behavior.

Optional semantic sections remain project decisions:

- Specifications state what must be true; architecture states what currently exists. Content is not duplicated merely to
  populate both.
- Cross-cutting decision records exist only when their rationale remains useful independently of the feature that
  introduced them.
- Module documentation describes semantic responsibility, boundaries, interfaces, relationships, and invariants rather
  than every package or file.
- Operations, provisioning, tutorials, examples, hardware, security, deployment, networking, integrations, and other
  sections exist only when concrete durable facts answer real reader questions.

### Feature records

Every feature retains:

```text
docs/src/features/<slug>/
├── design.md
└── index.md
```

`design.md` is accepted intent before implementation. It covers feature summary, user intent, goals, non-goals,
user-visible behavior, requirements, existing patterns and reuse, proposed design, architecture consistency, interfaces
and data flow, happy path, invalid input, failure and recovery, security, compatibility, migration, validation,
documentation impact, risks and tradeoffs, rejected alternatives, and deferred decisions. Its documentation impact
addresses all three audiences; `N/A` requires a reason. It never becomes workflow or delivery history.

`index.md` is created at closeout, not as an empty planning page. It links to the design and records delivered
capability, resulting user-visible behavior, authoritative current-product documentation, architecture integration,
delivered-as-designed scope, intentional differences, deferred scope, removed or rejected scope, and durable validation,
compatibility boundaries, limitations, and risks. It contains no task list, Beads identity, branch, pull request,
commit, merge identity, status dashboard, or audit trail.

`features/index.md` is the reader-facing catalog. Before delivery it may link a planned feature to `design.md`; once
reconciliation exists it links to `index.md`, which links back to the design.

mdBook only renders Markdown chapters listed in `SUMMARY.md`. To keep every record in the built book without adding a
preprocessor, dStack keeps one **top-level** `Feature Records` entry and nests each feature `index.md` and `design.md`
beneath it. The catalog remains the intentional discovery page; the nested chapter entries satisfy native mdBook
inclusion and may be folded by a project's normal mdBook presentation. A custom preprocessor or an unrendered feature
tree is rejected because either adds machinery or violates the navigable-book requirement.

### Current product versus feature history

The durable distinction is:

- `features/`: why the system changed this way;
- `architecture/`: what the system is now;
- user/operator sections: how to use and operate it now;
- reference sections: the exact current contract; and
- `development/`: how to work on it now.

A feature that changes architecture, operations, reference behavior, or another current-product surface updates that
authoritative page in the same candidate. The feature record links to it. A reader need not know the introducing feature
to learn current behavior.

Feature designs declare affected documentation surfaces as local Markdown links under `Documentation impact`. Those
links may name pages created by implementation. Closeout runs the local-link validator after implementation, so every
declared surface must exist and be navigable before delivery. This reuses normal Markdown rather than adding manifest
fields.

### Durable truth

Documentation may describe durable product states such as `planned`, `implemented`, and `deprecated`. It must not mirror
actionable or transient Beads/Git state, including readiness, blockers, assignees, active review, delivery readiness,
task/gate/Beads IDs, branches, worktrees, commits, pull requests, or next dStack commands.

Beads remains authoritative for actionable plans, dependencies, unknowns, findings, and execution. No required
`planned-features.md` or `unknowns.md` is introduced. A roadmap is optional only when it expresses durable product
direction.

## Requirements

1. Setup and doctor share one stateless documentation validator and foundation contract; no normal command invokes
   compatibility repair implicitly.
2. Foundation creation uses exclusive create-if-missing writes and performs preflight checks before mutation where
   possible.
3. Existing authored core files are never normalized, merged, or overwritten.
4. `SUMMARY.md` is the only documentation navigation authority.
5. Optional directories are neither created nor classified by an allowlist.
6. All durable reader-facing Markdown under `docs/src` is included in the mdBook chapter graph or explicitly included as
   source by a chapter.
7. Feature specification scaffolding creates only `design.md`; feature closeout scaffolding creates only a missing
   `index.md` and never overwrites it.
8. Navigation updates are idempotent, preserve unrelated project entries, and point to files that exist or are created
   in the same operation.
9. The documentation policy guard retains its narrow structured-workflow leakage checks and allows normal domain prose
   and durable product status.
10. Closeout validates the complete current book and all local documentation links, including documentation-impact links
    from the accepted design.
11. Validation and migration operate from current Git/filesystem/Beads truth and persist no result.
12. Existing project-specific sections and meaningful feature designs survive migration.
13. dStack's own documentation and tests conform to the same contract delivered to managed projects.

## Existing patterns and reuse

The implementation reuses:

- the current `docs/book.toml` and `docs/src` layout;
- canonical `docs/src/features/<slug>/design.md` identity and path-safety checks;
- idempotent `feature scaffold-design` behavior;
- `features/index.md` and `SUMMARY.md` navigation updates;
- the narrow documentation leakage patterns and `docs check` delivery guard;
- setup/doctor and explicit legacy adoption boundaries;
- the single `dstackctl.py` argparse entry point and standard-library Python controller modules;
- temporary directories, `pathlib`, `urllib.parse`, subprocess argument arrays, and existing Git helpers; and
- fast protocol tests plus the existing two real-Beads acceptance scenarios.

A stateless documentation validator is necessary because mdBook build, foundation, local-link, and orphan checks are
repeatable mechanics shared by setup and closeout. It is not a service, plugin system, or persistence layer. No
third-party Python Markdown parser or link checker is added; the required local target forms are intentionally narrow
and behavior-tested.

## Proposed design

### Foundation initialization

Setup first verifies that `mdbook` is executable. It then creates missing core files using fixed, concise templates and
exclusive file creation. Templates explain only the required semantic purpose and invite project-specific content; they
do not create optional pages.

If a write fails, already-created files remain visible as ordinary unstaged Git changes and a retry safely completes the
missing subset. dStack records no rollback journal. It never deletes or overwrites existing content to simulate a
transaction.

Setup validates the completed book after foundation creation. Doctor validates without creating content. Their JSON
output reports created files and current validation results without storing them.

### Stateless validation

Add a mechanical current-worktree documentation validation operation and reuse its function from setup/doctor. The
validator:

1. resolves the Git root and canonical `docs`/`docs/src` paths without following an escape outside the repository;
2. checks required files and regular-file types;
3. parses chapter and include targets needed for local path validation;
4. reports missing, escaping, or orphan Markdown paths in sorted order;
5. runs `mdbook build` with a temporary destination; and
6. removes temporary output on success or failure.

The parser recognizes Markdown links/images and mdBook include directives only for extracting local filesystem targets.
It ignores URL schemes and strips query/fragment suffixes. It does not render Markdown or infer semantics.

`docs check --base --head` continues to inspect added lines for transient workflow leakage. Closeout runs both leakage
comparison and current-worktree validation. Delivery requires both results to be successful.

### Feature lifecycle mechanics

Expand the design scaffold headings to this accepted design contract while retaining create-if-missing/non-overwrite
behavior. Navigation creation ensures the top-level feature catalog and the design chapter entry exist.

Add an idempotent closeout scaffold operation. It resolves the same safe feature directory, creates `index.md` with the
reconciliation headings only when absent, changes the catalog target from `design.md` to `index.md`, and ensures both
pages are nested chapters under the single top-level feature section. It does not write reconciliation prose.

The closeout skill invokes this scaffold after claiming closeout, then the agent writes actual reconciliation and
affected current-product docs. Full validation fails until those local targets exist and the book builds.

Navigation helpers match targets rather than exact generated titles, so authored titles and unrelated optional sections
remain intact. They do not reorder the project's other sections.

### Existing-project migration

Normal setup creates missing foundation files but does not relocate legacy content. Explicit compatibility handling owns
mechanically safe moves.

The initially supported automatic move is the existing known feature design layout:

```text
docs/features/<slug>/design.md
    -> docs/src/features/<slug>/design.md
```

The move is allowed only when the source is a regular file within the repository, the destination is absent, the slug
matches the selected feature, and all affected known navigation references can be rewritten. The filesystem move and
navigation update occur before Beads metadata is changed. If any precondition fails, metadata remains unchanged and
repair reports the conflict. A successful retry observes the destination and canonical metadata and makes no additional
change.

Missing reconciliation records for older delivered features are reported for agent/user reconciliation rather than
created as empty pages. Other legacy layouts, ambiguous semantic destinations, and obsolete prose are reported and left
untouched. Agents may author durable reconciliation or move content in a normal reviewed Git change; automation does not
guess.

### dStack repository reconciliation

The feature candidate applies the foundation to dStack itself:

- add `development/documentation.md` with the generic contract and dStack's project-specific conventions;
- update orientation, architecture, lifecycle, testing, compatibility, README, skills, and command help where current
  behavior changes;
- reconcile existing delivered feature designs with substantive `index.md` records rather than empty scaffolds;
- update `SUMMARY.md` and `features/index.md` to the feature-record model;
- pin the tested mdBook release in mise and run documentation validation in CI; and
- keep release validation within the existing fast and two real-Beads scenario structure.

## Interfaces and data flow

### Setup and doctor

```text
/review-feature-spec
    -> setup install
    -> preflight mdbook
    -> create missing core docs
    -> validate current book
    -> report visible Git changes and validation

documentation validation
    -> validate formulas/tooling
    -> validate current book
    -> report only
```

### Specification and closeout

```text
/review-feature-spec
    -> scaffold design if absent
    -> add design/catalog/SUMMARY navigation
    -> agent authors accepted intent

/close-feature
    -> claim closeout
    -> scaffold reconciliation if absent
    -> agent reconciles implementation and current-product docs
    -> validate required files, navigation, local links, orphans, mdBook build
    -> run existing leakage comparison
    -> finish closeout only after success
```

### Migration

```text
explicit repair
    -> inspect source, destination, navigation, and metadata
    -> refuse ambiguity/conflict
    -> move known file and update references
    -> update canonical metadata last
    -> validate resulting book
```

No step writes a custom state record. Each retry derives the next action from files, Git, and Beads.

## Architecture consistency

The design preserves the documented authority split:

- Git owns documentation and its history.
- Beads owns planned work, dependencies, gates, readiness, and completion.
- `dstackctl` and setup perform only stateless deterministic mechanics.
- Agents own semantic writing, section choice, architecture judgment, and reconciliation.

No formula step, lifecycle state, persistent manifest, scheduler, cache, reviewer topology, or Git-to-Beads mapping is
added. Compatibility migration remains explicit and isolated from normal feature commands.

## Happy path and observable success

1. Setup in a repository with Beads and mdBook creates only missing required pages, preserves authored files, validates
   the book, and reports the exact visible changes.
2. Repeating setup changes no documentation and returns successful validation.
3. A feature design is scaffolded and authored, appears in the feature catalog, and is built as a nested chapter.
4. Implementation updates behavior, tests, and authoritative current-product pages.
5. Closeout creates a reconciliation scaffold, the agent records delivered reality, navigation changes to the
   implementation record, and complete documentation validation passes.
6. A reader can reach orientation, current-product guidance, feature reconciliation, and accepted design through the
   built mdBook.
7. A future agent can compare design, reconciliation, source, tests, and current docs without workflow bookkeeping or
   prior conversation.

## Failure, recovery, and state behavior

- Missing `mdbook`, invalid `book.toml`, build failure, missing core files, broken local links, orphan Markdown, missing
  feature records, unsafe paths, or declared-but-absent documentation surfaces produce actionable nonzero output.
- Setup preflights mdBook before writing documentation. A later filesystem failure may leave a visible subset of new
  files; retry completes it without overwrite. No hidden transaction state or automatic destructive rollback is added.
- Scaffold retries never overwrite authored design or reconciliation content.
- Navigation is updated only with a corresponding existing or newly created page.
- Closeout remains open when validation fails, times out, is interrupted, runs the wrong scope, or is replaced with
  weaker checks.
- Migration conflict or ambiguity leaves source content and Beads metadata unchanged. A partially interrupted move is
  recoverable from visible source, destination, navigation, and metadata truth on retry.
- Validation reads current files each invocation; stale prior success cannot authorize closeout.

## Security implications

- Resolve all local paths beneath the repository and book source; reject absolute paths, parent traversal, and symlink
  escapes.
- Invoke mdBook and Git with argument arrays. Documentation content, link text, paths, and validation output are never
  shell syntax.
- Do not fetch external links, execute snippets, or persist validation output that may contain repository details.
- Preserve existing narrow workflow-leakage rejection and avoid broad semantic matching that could reject legitimate
  domain documentation.
- Create files without overwrite to prevent authored-content loss.

## Compatibility and migration implications

- Existing optional sections and project-specific structures remain valid when represented in `SUMMARY.md`.
- Existing core content is never rewritten to a new template.
- Existing `docs/src/features/<slug>/design.md` records remain valid and gain reconciliation records through reviewed
  content, not destructive conversion.
- Existing narrow documentation leakage behavior remains compatible.
- Current consumers of `feature scaffold-design` retain idempotent creation; navigation changes from individual
  top-level behavior to one grouped feature section.
- Closeout gains required current-book validation and can now fail for missing mdBook tooling or invalid documentation.
- Managed projects choose how to install mdBook; dStack requires it on `PATH` and documents the tested version rather
  than silently downloading software.
- Only the known legacy `docs/features/<slug>/design.md` move is automated initially. Additional layouts require
  evidence and a later bounded change.

## Validation strategy

Write behavior-first tests before implementation. Focused fast tests prove:

- foundation initialization creates exactly the minimum missing files, preserves existing bytes, creates no optional
  sections, and is idempotent;
- missing mdBook fails before foundation mutation, while build failure leaves lifecycle completion unauthorized;
- current-worktree validation accepts project-specific sections and rejects missing core files, invalid navigation,
  broken local targets, escaping paths, orphans, and mdBook failure;
- external URLs are not fetched and local query/fragment suffixes resolve to the correct file;
- design and reconciliation scaffolds create once, preserve authored content, maintain one top-level feature section,
  and catalog/nest both mdBook chapters;
- closeout validation catches a documentation-impact link whose target was not delivered;
- the leakage guard still accepts ordinary blocked/completed/implemented domain prose and rejects structured dStack
  workflow bookkeeping;
- explicit repair moves the known legacy design and rewrites navigation before metadata, is idempotent, and refuses
  conflicts or ambiguous layouts without content loss; and
- package/docs contracts establish the semantic roles, three audiences, current-product/history boundary, no allowlist,
  and no second manifest.

Extend the existing real-Beads feature smoke scenario only where needed to prove the supported scaffold/closeout command
boundary with the real binary. Do not add another acceptance scenario or teach the fast protocol stub mdBook or Beads
lifecycle semantics.

Final validation follows the repository release contract: metadata parsing, Python compilation, the complete fast suite,
both required real-Beads acceptance scenarios, the pinned mdBook build and documentation validator, `git diff --check`,
`git fsck`, bundle verification, and clean-clone checks. Required checks must execute rather than skip.

## Documentation impact

| Perspective | Required durable outcome |
| --- | --- |
| End user/operator | Update the [project orientation](../../index.md), README, and the new [documentation conventions](../../development/documentation.md) so managed-project users can initialize, navigate, build, validate, and troubleshoot the canonical book. Current product behavior remains in the project's actual user/operator/reference sections rather than feature history. |
| Developer/reviewer | Update [architecture](../../architecture/index.md), [core principles](../../development/index.md), [feature lifecycle](../../development/feature-lifecycle.md), [testing](../../development/tooling.md), setup/closeout skills, command help, and compatibility guidance with the foundation, semantic boundaries, validation contract, feature reconciliation, and migration rules. |
| Future agent/auditor | This design, delivered feature `index.md`, the same current-product docs, behavior-first tests, and source establish accepted intent and drift boundaries. No prior conversation, agent-only tree, or documentation manifest is required. |

## Risks and tradeoffs

- Native mdBook requires every rendered record in `SUMMARY.md`; nesting feature pages preserves one top-level section
  but the source summary still grows with feature count. This is preferred over a custom preprocessor or unbuilt pages.
- A small standard-library local-link extractor will not implement all Markdown grammar. Its supported forms must be
  documented and tested; mdBook remains the rendering authority.
- Requiring mdBook on `PATH` adds a setup prerequisite. Silent installation would be more convenient but unsafe and
  project-tooling-specific.
- Strict orphan detection may expose existing hidden Markdown. Reporting it is intentional; ambiguous semantic placement
  remains an agent/user decision.
- Conservative migration leaves some manual work. That is preferable to moving durable content into the wrong semantic
  section.

## Rejected alternatives

- **Fixed comprehensive directory taxonomy:** rejected because it creates empty sections and erases domain differences.
- **Optional-section allowlist or configuration:** rejected because `SUMMARY.md` already expresses project structure.
- **Second dStack docs manifest:** rejected as duplicate authority and state.
- **Separate agent documentation:** rejected because it drifts from human-facing durable truth.
- **Feature history as current-product documentation:** rejected because readers should not need historical knowledge to
  use current behavior.
- **One mutable feature page:** rejected because accepted intent and delivered reconciliation answer different durable
  questions.
- **Unlisted feature Markdown:** rejected because mdBook does not render pages absent from `SUMMARY.md`.
- **Custom mdBook preprocessor to generate feature navigation:** rejected as unnecessary machinery and a hidden second
  navigation source.
- **Third-party Markdown/link checker:** rejected because deterministic local path checks and mdBook build need only
  small standard-library mechanics.
- **External URL probing:** rejected as slow, flaky, and non-deterministic.
- **Automatic semantic migration:** rejected because incorrect moves are data loss even when the original file survives.

## Open or intentionally deferred decisions

- No consequential product or architecture decision remains open.
- Support for additional mechanically unambiguous legacy layouts is deferred until a real repository demonstrates one.
- More complete Markdown grammar, anchor validation, or external link checking is deferred until the supported local
  forms produce a concrete false result.
- A custom feature-navigation preprocessor is deferred unless native nested chapters become a measured usability
  problem.
