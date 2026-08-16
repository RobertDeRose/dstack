---
name: dstack-beads-setup-project
description: "Initialize Beads when authorized, install dstack's formulas, cook persistent protos, and validate the workflow foundation."
---

# Setup project

Use the user's input only to determine whether `--force` was explicitly
requested. Invoking this command authorizes Beads initialization when the target
repository has not been initialized.

## Procedure

1. Verify the current directory is inside the intended Git repository.
2. Run the bundled installer:

   ```bash
   python3 "{baseDir}/../dstack-beads-core/scripts/setup.py" \
     install --root . --init
   ```

3. Add `--force` only when the user explicitly supplied it. This replaces
   differing installed formula source files and recooks their protos; it does
   not rewrite existing poured molecules.
4. Read the JSON result and report:
   - target Git root;
   - Beads version;
   - whether each formula was installed, updated, or unchanged;
   - persisted proto names;
   - validation result.
5. Run the doctor once after installation:

   ```bash
   python3 "{baseDir}/../dstack-beads-core/scripts/setup.py" doctor --root .
   ```

6. Stop on a formula conflict without `--force`, invalid parser result, failed
   cook, or unavailable proto. Do not manually patch `.beads` state to bypass a
   failure.

## Installed workflows

- `dstack-feature`
- `dstack-project-alignment`

No feature or audit molecule is poured by setup.
