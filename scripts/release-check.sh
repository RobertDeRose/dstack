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

if [[ -n $(git status --porcelain=v1 --untracked-files=all) ]]; then
  echo 'release check modified the source worktree' >&2
  git status --short >&2
  exit 1
fi
