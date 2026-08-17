---
name: dstack-beads-adopt-feature
description: "Adopt one active legacy dStack feature through a narrow stateless compatibility transition."
---

# Adopt feature

This authorizes Beads adoption mutations only—no source, Git-history, branch, or worktree changes.

1. Inspect and classify obvious legacy nodes:

   ```bash
   python3 "{baseDir}/../dstack-beads-core/scripts/dstackctl.py" \
     adopt inspect <legacy-feature>
   ```

2. Decide only the ambiguous cases:
   - which open items are real remaining implementation outcomes;
   - which are specification ceremony;
   - which are implementation coordinators;
   - which are closeout/validation ceremony;
   - which unresolved decisions must stay on specification review.
3. Apply the explicit classification:

   ```bash
   dstackctl.py adopt apply <legacy-feature> \
     [--remaining <id>] \
     [--spec-ceremony <id>] \
     [--implementation-coordinator <id>] \
     [--closeout-ceremony <id>]
   ```

The controller pours one current molecule, copies only selected remaining work,
uses native supersession, and leaves specification approval open. It creates no
migration packet, SHA mapping, or dStack migration database.

Return the new root/steps, selected remaining work, ambiguous decisions, and `/review-feature-spec <slug>`.
