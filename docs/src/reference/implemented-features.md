# Implemented Features

These records preserve the accepted design for features that materially shaped dStack's current behavior. They use the
same publication structure that `/close-feature` produces for new feature documentation:

- **Overview** explains the feature in the context of the current product.
- **User Impact** describes what changed for users, operators, or contributors.
- **Implemented Design** includes `design.md` without rewriting it.

The design file follows the six-section planning template used by `/plan-feature`:

```text
Goals
User-facing behavior
Implemented design
Compatibility and constraints
Validation
Non-goals
```

For current features, `dstack docs export-design` copies that design verbatim from the Beads plan into `design.md`.
The surrounding index remains reader-facing documentation, while exact command syntax, environment behavior, and
compatibility contracts stay in their dedicated reference pages.

## Current records

- [Beads-native control plane](../features/beads-native-control-plane/index.md)
- [Lean workflow and documentation lifecycle](../features/lean-workflow-refinement/index.md)
