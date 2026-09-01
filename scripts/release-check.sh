#!/usr/bin/env bash
set -euo pipefail

root=$(git rev-parse --show-toplevel)
cd "$root"

before=$(git status --porcelain=v1 --untracked-files=all)
if [[ -n "$before" ]]; then
  printf 'release check requires a clean worktree:\n%s\n' "$before" >&2
  exit 1
fi

tmp=$(mktemp -d "${TMPDIR:-/tmp}/dstack-release-check.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

uv build --out-dir "$tmp/dist"
git diff --check
git fsck --full

git bundle create "$tmp/dstack.bundle" HEAD
git bundle verify "$tmp/dstack.bundle"
git clone --quiet "$tmp/dstack.bundle" "$tmp/clone"
git -C "$tmp/clone" fsck --full
uv run --project "$tmp/clone" pytest -q "$tmp/clone/tests/fast/test_package_contract.py"

wheel=$(find "$tmp/dist" -maxdepth 1 -type f -name '*.whl' -print -quit)
if [[ -z "$wheel" ]]; then
  echo 'release check did not produce a wheel' >&2
  exit 1
fi

python -m venv "$tmp/venv"
"$tmp/venv/bin/python" -m pip install --quiet "$wheel"
"$tmp/venv/bin/dstack" --version >/dev/null
"$tmp/venv/bin/dstack" ctl --help >/dev/null

agent_dir="$tmp/pi-agent"
"$tmp/venv/bin/dstack" install_skills --agent-dir "$agent_dir" >"$tmp/install-skills.json"
for skill in \
  dstack-beads-close-feature \
  dstack-beads-implement-feature \
  dstack-beads-plan-feature \
  dstack-beads-project-alignment-execute \
  dstack-beads-project-alignment-land \
  dstack-beads-project-alignment-review \
  dstack-beads-review-feature-spec; do
  test -f "$agent_dir/skills/$skill/SKILL.md"
done
for prompt in \
  close-feature.md \
  implement-feature.md \
  plan-feature.md \
  plan-features.md \
  project-alignment-execute.md \
  project-alignment-land.md \
  project-alignment-review.md \
  review-feature-spec.md; do
  test -f "$agent_dir/prompts/$prompt"
done
test -f "$agent_dir/APPEND_SYSTEM.md"
"$tmp/venv/bin/python" - <<'PYFORMULA'
from dstack.formula import load_formula

for name in ("dstack-feature", "dstack-project-alignment"):
    formula = load_formula(name)
    assert formula["formula"] == name
    assert isinstance(formula["version"], int) and formula["version"] > 0
PYFORMULA

if [[ -n $(git status --porcelain=v1 --untracked-files=all) ]]; then
  echo 'release check modified the source worktree' >&2
  git status --short >&2
  exit 1
fi
