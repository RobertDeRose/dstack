# CHANGELOG

- - -

## v0.4.0 — 2026-07-17

### Added

- **workflow:** Integrate safe migration recovery (`23f0a55`)
- **workflow:** Automate migration record reconciliation (`ff92dfb`)

### Fixed

- **workflow:** Reconcile migration delivery (`047bc5b`)
- **workflow:** Batch large migration imports (`b863d13`)
- **workflow:** Preserve migration repository identity (`d872cc2`)
- **workflow:** Preserve migration import progress (`e56ffc5`)
- **workflow:** Require verified migration commits (`7f5ba3a`)
- **workflow:** Enforce migration artifact handling (`9aeb28a`)
- **workflow:** Preserve legacy hook behavior (`0de2faf`)
- **toolchain:** Reduce repository test time (`a34574c`)
- **toolchain:** Prevent recursive policy tests (`668a3a4`)
- **toolchain:** Restore module update ordering (`82642bc`)
- **toolchain:** Restore native Harper linting (`13baa63`)
- **template:** Add editor and typo policy (`9510a21`)

### Changed

- **toolchain:** Simplify validation step policy (`3e6239b`)

- - -

## v0.3.0 — 2026-07-16

### Breaking changes

- **BREAKING** **workflow:** Use slug-only features (`da9ae19`)

### Added

- **workflow:** Collect migration adoption briefs (`a0a616b`)
- **template:** Self-host dstack template updates (`119674a`)
- **skill:** Add stable and unstable template channels (`73df430`)
- **template:** Generate commit policy (`23b5a7a`)
- **workflow:** Refine project conventions (`df7a4e5`)
- **github:** Enable Pages safely via gh (`ebbfe14`)
- **github:** Add gated Pages deployment (`685f61f`)
- **github:** Add locked validation (`e8dd79a`)
- **profiles:** Add Elixir and Nix profiles (`4980c9d`)
- **profiles:** Add Rust and Go profiles (`c204910`)
- **profiles:** Add Python and TypeScript profiles (`01f7507`)
- **profiles:** Compose language profiles (`f662172`)
- **skill:** Reconcile locked tooling in update-project (`429f009`)
- **toolchain:** Provision locked project tools (`63fd3c6`)
- **template:** Add universal toolchain files (`78c9558`)
- **docs:** Render factual project books (`1497515`)
- **skill:** Require structured project brief in setup-project (`1ba4324`)

### Fixed

- **github:** Install locked tools in external CI (`15b2d7b`)
- **profiles:** Provision external validation tools (`bb466e3`)
- **github:** Isolate integration test prerequisites (`87dd3ef`)
- **github:** Configure Git identity in hook test (`0ca9624`)
- **github:** Make commit-hook test hermetic (`d3ca20c`)
- **toolchain:** Configure Contextlint validation (`802a844`)
- **skill:** Collect briefs during legacy updates (`ab264cc`)
- **toolchain:** Ignore hashes in typo checks (`429714b`)
- **repo:** Align automated release subjects (`b48424a`)
- **github:** Restore root Pages workflow (`32c5aaa`)
- **workflow:** Normalize lifecycle task metadata (`51e9a94`)
- **github:** Install locked tools before CI tests (`f3cd450`)
- **github:** Pin root workflow actions (`2cdb563`)
- **skill:** Keep no-op updates clean (`c849469`)
- **skill:** Complete update-project dogfooding (`511fc71`)
- **toolchain:** Require visible commit scopes (`7b59ce8`)
- **repo:** Normalize semantic commits (`78f4b88`)
- **toolchain:** Standardize Beads footers (`eba8871`)
- **repo:** Require fast-forward merges (`b2cd934`)
- **toolchain:** Enforce commit message formatting (`63e078c`)
- **docs:** Publish feature design records (`4b1b807`)
- **docs:** Remove broken design links (`19e2cd1`)
- **profiles:** Reconcile delivery (`5c2ecf2`)
- **toolchain:** Harden delivery (`5644ad7`)
- **workflow:** Focus iterative validation (`75f6ce5`)
- **workflow:** Streamline review orchestration (`44a14ac`)
- **workflow:** Harden feature workflow continuity (`0a7d921`)
- **template:** Reconcile delivery (`8a7e015`)
- **docs:** Allow variable documentation structures (`c026963`)

### Changed

- **repo:** Use Cocogitto for releases (`14c96b0`)

- - -

## v0.2.1 (2026-07-13)

### Bug Fixes

- Reject recursive Beads relationships
  ([`927f126`](https://github.com/RobertDeRose/dstack/commit/927f126b722505a1bcfd14a27c1383272f33a28c))

## v0.2.0 (2026-07-12)

### Features

- Make feature selection and migration explicit
  ([`9abce37`](https://github.com/RobertDeRose/dstack/commit/9abce37151dfd5114fc1882321ed56d09215b232))

## v0.1.0 (2026-07-12)

- Initial Release
