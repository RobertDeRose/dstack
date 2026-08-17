---
name: dstack-beads-setup-project
description: "Initialize Beads when authorized, install dstack formula source, validate it with an isolated pour, and remove verified legacy template artifacts."
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

3. The installer first copies both bundled formulas into an isolated temporary
   Beads repository, verifies them with `bd mol seed`, and pours one temporary
   molecule from each formula. This exercises real gate and dependency creation
   before the target repository is modified.
4. Add `--force` only when the user explicitly supplied it. This replaces
   differing formula source and removes only verified legacy template artifacts
   in the reserved `dstack-feature` and `dstack-project-alignment` namespaces.
   This includes orphaned steps or gates left when an earlier cleanup removed
   only the proto roots.
5. Read the JSON result and report:
   - target Git root;
   - Beads version;
   - whether each formula was installed, updated, or unchanged;
   - isolated-pour validation result;
   - any legacy persisted template graphs removed.
6. Run the dstack doctor once after installation:

   ```bash
   python3 "{baseDir}/../dstack-beads-core/scripts/setup.py" doctor --root .
   ```

7. Check whether `.beads/interactions.jsonl` is tracked:

   ```bash
   git ls-files --error-unmatch .beads/interactions.jsonl >/dev/null 2>&1
   ```

   If it is tracked, it is legacy repository configuration. Without `--force`,
   report that migration is required and leave it untouched. With explicit
   `--force`, preserve the file on disk, add `.beads/interactions.jsonl` to the
   repository `.gitignore` when needed, and run:

   ```bash
   git rm --cached -- .beads/interactions.jsonl
   ```

   Report the staged untracking change. Never delete or restore the runtime log.
8. Stop on a formula conflict without `--force`, invalid parser result, failed
   isolated pour, unavailable formula, unrecognized same-named Bead, or unsafe
   legacy-template cleanup. Do not manually patch `.beads` state to bypass a
   failure.

## Installed workflows

- `dstack-feature`
- `dstack-project-alignment`

Setup installs formula source only. It does not persist protos or pour a feature
or audit molecule in the target repository.
