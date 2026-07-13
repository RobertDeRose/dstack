# dstack overview

## Purpose

dstack gives coding agents and maintainers a shared, auditable workflow in which product intent, executable work, reader
documentation, implementation evidence, and delivery records remain aligned.

## Intended users

- Maintainers planning and delivering software with coding agents.
- Coding agents that need explicit authority, lifecycle, and validation contracts.
- Teams adopting the bundled Copier scaffold in new or existing repositories.
- dstack contributors maintaining the skills, template, and migration behavior.

## Current scope

dstack ships installable agent skills, a versioned Copier template, Beads lifecycle formulas, safe
setup/update/migration helpers, documentation validation, and GitHub review workflows. It supports new projects, legacy
workflow migration, planned feature delivery, close-out, and drift audits.

Future behavior belongs in [Planned Features](../planned-features.md) until delivered.

## Boundaries

- Beads owns live work state; dstack does not replace the issue database with Markdown task lists.
- Copier owns generated scaffold updates; Skills CLI owns installed skill files.
- dstack defines workflow and documentation contracts, not an application framework or universal build system.
- Setup never adopts an existing repository implicitly; migration and updates are separate explicit workflows.

## Current status

dstack is versioned and usable, but remains an evolving personal workflow toolkit. Published tags are the supported
update boundary. Repository tests cover template rendering, workflow helpers, migration behavior, and external skill
installation.
