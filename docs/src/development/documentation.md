# Documentation

Documentation is part of the product and changes with the behavior it describes.

## Audiences

- **End users:** installation, configuration, usage, operations, and troubleshooting.
- **Developers:** architecture, interfaces, data flow, invariants, tests, and extension points.
- **Future agents:** current boundaries and durable rationale.

## Current truth

The mdBook under `docs/` is the canonical repository documentation. Architecture describes the running system;
operations explain how to use it; reference pages state exact contracts; development pages explain how to change and
validate it.

Use Beads for live plans, tasks, decisions, blockers, claims, and readiness only inside an explicitly activated dStack
workflow. Do not copy those facts into Markdown.

## Validation

Run:

```bash
dstack ctl docs validate
```

The validator checks required files, navigation, local links, decision records, and the mdBook build without writing a
manifest or cache.
