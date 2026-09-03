#!/usr/bin/env bash
set -euo pipefail

root=$(git rev-parse --show-toplevel)
cd "$root"

before=$(git status --porcelain=v1 --untracked-files=all)
if [[ -n "$before" ]]; then
  printf 'release check requires a clean worktree:\n%s\n' "$before" >&2
  exit 1
fi

tmp=$(realpath "$(mktemp -d "${TMPDIR:-/tmp}/dstack-release-check.XXXXXX")")
trap 'rm -rf "$tmp"' EXIT

uv build --out-dir "$tmp/dist"
git diff --check
git fsck --full

git bundle create "$tmp/dstack.bundle" HEAD
git bundle verify "$tmp/dstack.bundle"
git clone --quiet "$tmp/dstack.bundle" "$tmp/clone"
git -C "$tmp/clone" fsck --full
uv run --project "$tmp/clone" pytest

wheel=$(find "$tmp/dist" -maxdepth 1 -type f -name '*.whl' -print -quit)
if [[ -z "$wheel" ]]; then
  echo 'release check did not produce a wheel' >&2
  exit 1
fi

uv venv --python 3.14 "$tmp/venv"
uv pip install --python "$tmp/venv/bin/python" "$wheel"
"$tmp/venv/bin/dstack" --version >/dev/null
"$tmp/venv/bin/dstack" ctl --help >/dev/null

agent_dir="$tmp/pi-agent"
"$tmp/venv/bin/dstack" install_skills --agent-dir "$agent_dir" >"$tmp/install-skills.json"
for skill in \
  dstack-beads-audit-feature \
  dstack-beads-implement \
  dstack-beads-plan-feature \
  dstack-beads-review-plan; do
  test -f "$agent_dir/skills/$skill/SKILL.md"
done
for prompt in audit-feature.md implement.md plan-feature.md review-plan.md; do
  test -f "$agent_dir/prompts/$prompt"
done

"$tmp/venv/bin/python" - <<'PYFORMULA'
from dstack.formula import EXPECTED_STEPS, load_formula

formula = load_formula()
assert formula["formula"] == "dstack-feature"
assert tuple(step["id"] for step in formula["steps"]) == EXPECTED_STEPS
PYFORMULA

if [[ -n $(git status --porcelain=v1 --untracked-files=all) ]]; then
  echo 'release check modified the source worktree' >&2
  git status --short >&2
  exit 1
fi
