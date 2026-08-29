# Canonical mdBook Documentation System

> **Historical record:** setup/migration behavior described below reflects the workflow at the time this feature was
> delivered. It is superseded by the current
> [compatibility and formula-audit contract](../../reference/compatibility.md): formulas are templates, historical
> graphs are not migrated, and normal commands do not run setup or migration.

[Design record](design.md)

## Delivered capability

dStack-managed projects now use one canonical mdBook for durable product, architecture, development, and feature
documentation. Setup creates only a small missing foundation, while a stateless validator checks required pages, chapter
navigation, local targets, includes, orphan Markdown, path safety, and the mdBook build.

Feature records now keep accepted intent in `design.md` and delivered reconciliation in `index.md`. The feature catalog
remains the discovery page, and native nested mdBook chapters keep both records rendered without another manifest or
preprocessor.

Explicit compatibility repair can canonicalize a non-`src` mdBook source tree and move other mechanically placed book
content under `docs/` into `docs/src`. It rewrites known local navigation/references with each move, refuses conflicts
and unsafe paths, leaves semantically ambiguous Markdown for judgment, and reports missing historical reconciliations
for human or agent authorship.

## User-visible behavior

The specification-review boundary creates missing core book files lazily without overwriting authored content or
creating optional sections. Projects remain free to organize real operator, reference, module, deployment, security, or
other documentation through `SUMMARY.md`.

The current book can be checked with the repository's documented validation command. Missing mdBook tooling, invalid
navigation, broken or escaping local links, orphan Markdown, unsafe required files, and build failures stop setup or
closeout with actionable errors. External URLs are retained but are not fetched.

Current conventions and usage are documented in [Documentation](../../development/documentation.md).

## Architecture integration

The implementation preserves the existing authority split described in [Architecture](../../architecture/index.md): Git
owns durable documentation, Beads owns actionable work, and `dstackctl` performs stateless deterministic mechanics.
`SUMMARY.md` is the sole navigation authority; no documentation manifest, cache, semantic classifier, or lifecycle store
was added.

The validator is a small standard-library controller module shared by setup, doctor, closeout, and delivery guards.
Feature scaffolding reuses existing safe feature identity and create-if-missing behavior. Compatibility migration
remains an explicit repair operation rather than an implicit part of normal setup or feature execution.

## Design reconciliation

### Delivered as designed

- The minimum foundation and semantic roles serve end users/operators, developers/reviewers, and future agents/auditors
  from one durable book.
- Existing content and project-specific sections are preserved; optional directory names are neither generated nor
  allowlisted.
- Feature specification and closeout create distinct, non-overwriting design and reconciliation records and maintain one
  top-level Feature Records section.
- Validation derives all results from the current worktree, uses temporary build output, and persists no state.
- Local targets reject absolute paths, traversal, required-file symlinks, and symlink escapes. Deterministic link and
  orphan failures are reported together.
- Documentation migration is conservative and retryable from visible state: a configured noncanonical source tree is
  preserved structurally, while other outside-source content moves only when navigation/includes establish a
  deterministic destination; ambiguous Markdown is reported rather than guessed.
- dStack pins its tested mdBook release through mise while managed projects only require a working `mdbook` executable
  on `PATH`.

### Intentional differences

Closeout review tightened two specified boundaries before initial delivery: required foundation paths are verified as
regular files, and authored feature navigation labels survive reconciliation updates. A later compatibility correction
broadened the originally single-layout migration rule without changing its safety principle: dStack now canonicalizes
any mechanically identified mdBook source/content placement under `docs/`, while still refusing to infer semantic
chapter placement for ambiguous Markdown.

### Deferred scope

- Semantically ambiguous legacy Markdown remains manual when no existing mdBook source, chapter, include, or asset
  reference determines its placement.
- Full Markdown grammar, anchor validation, and external-link reachability remain outside the deterministic validator.
- Native nested feature chapters remain in use unless measured book usability justifies a preprocessor later.

### Removed or rejected scope

A fixed optional taxonomy, second manifest, agent-only documentation tree, persistent validation state, third-party
Markdown parser, external URL probing, and automatic semantic migration were not added. Current-product guidance was not
moved into feature history.

## Documentation

Authoritative current behavior is documented in:

- [project orientation](../../index.md) and the repository README;
- [documentation conventions](../../development/documentation.md);
- [architecture](../../architecture/index.md);
- [feature lifecycle](../../development/feature-lifecycle.md);
- [testing and tooling](../../development/tooling.md); and
- [compatibility and explicit repair](../../reference/compatibility.md).

The [feature catalog](../index.md) links delivered records while each record retains its accepted design for future
comparison.

## Validation and limitations

Behavior-first fast tests cover foundation creation and preservation, mdBook preflight/build failure, local target and
orphan failures, project-specific sections, query/fragment links, includes, path and symlink safety, feature navigation
and non-overwrite behavior, closeout documentation-impact failures, workflow leakage, and conservative migration.
Real-Beads acceptance covers the shipped setup, feature-record, closeout, and fast-forward delivery boundaries.

The local Markdown extractor intentionally supports documented inline links, images, and mdBook includes rather than
implementing a renderer. mdBook remains the rendering authority. Reference-style/HTML/autolink target extraction,
external reachability, and anchor correctness are not validated. Automatic migration is limited by deterministic
placement rather than a directory allowlist: unresolved Markdown stays visible for semantic judgment.
