# ruff: noqa: S603, S607

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "skills/dstack-core/scripts/guarded-beads-push.py"
LOCK_SCRIPT = Path(__file__).parents[1] / "skills/dstack-core/scripts/beads-workflow-lock.py"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def guarded_repository(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repository, check=True)
    (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
    beads = repository / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text("{}\n", encoding="utf-8")
    (beads / "config.yaml").write_text("database: issues\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt", ".beads"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repository, check=True, capture_output=True)

    data_dir = tmp_path / "dolt-data"
    data_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    remote_count = tmp_path / "remote-count"
    write_executable(
        bin_dir / "bd",
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
root = Path(args[1])
args = args[2:]
log = Path(os.environ['FAKE_CALLS'])
with log.open('a', encoding='utf-8') as handle:
    handle.write('bd ' + ' '.join(args) + '\\n')
if args == ['dolt', 'show', '--json']:
    print(json.dumps({'data_dir': os.environ['FAKE_DATA_DIR'], 'database': 'issues', 'embedded': True}))
elif args == ['dolt', 'remote', 'list', '--json']:
    count_path = Path(os.environ['FAKE_REMOTE_COUNT'])
    count = int(count_path.read_text() or '0') if count_path.exists() else 0
    count_path.write_text(str(count + 1), encoding='utf-8')
    replaced = (os.environ.get('FAKE_REPLACE_REMOTE') and count) or Path(os.environ['FAKE_REPLACED']).exists()
    url = 'git+ssh://example.invalid/replaced.git' if replaced else 'git+ssh://example.invalid/issues.git'
    remotes = [{'name': 'origin', 'url': url, 'sql_url': url, 'status': 'ok'}]
    aliases_path = Path(os.environ['FAKE_ALIASES'])
    aliases = json.loads(aliases_path.read_text()) if aliases_path.exists() else {}
    remotes.extend({'name': name, 'url': value, 'sql_url': value, 'status': 'ok'} for name, value in aliases.items())
    print(json.dumps(remotes))
else:
    print(f'unexpected bd args: {args}', file=sys.stderr)
    raise SystemExit(2)
""",
    )
    write_executable(
        bin_dir / "dolt",
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
operation = args[4]
with Path(os.environ['FAKE_CALLS']).open('a', encoding='utf-8') as handle:
    handle.write('dolt ' + ' '.join(args[4:]) + '\\n')
if operation == 'fetch':
    Path(os.environ['FAKE_FETCHED']).write_text('fetched\\n', encoding='utf-8')
elif operation == 'sql':
    query = args[args.index('-q') + 1]
    if 'dolt_status' in query:
        print('{}')
    elif 'dolt_remote_branches' in query:
        remote_head = os.environ['FAKE_REMOTE_HEAD']
        rows = [{'name': 'remotes/origin/main', 'hash': remote_head}] if remote_head else []
        print(json.dumps({'rows': rows}))
    else:
        print(json.dumps({'rows': [{
            'branch': 'main',
            'local_head': os.environ['FAKE_LOCAL_HEAD'],
        }]}))
elif operation == 'merge-base':
    merge_base = os.environ.get('FAKE_MERGE_BASE')
    if not merge_base:
        print('no common ancestor', file=sys.stderr)
        raise SystemExit(1)
    print(merge_base)
elif operation == 'remote':
    aliases_path = Path(os.environ['FAKE_ALIASES'])
    aliases = json.loads(aliases_path.read_text()) if aliases_path.exists() else {}
    if args[5] == 'add':
        aliases[args[6]] = args[7]
        if os.environ.get('FAKE_REPLACE_AFTER_BIND'):
            Path(os.environ['FAKE_REPLACED']).write_text('replaced\\n', encoding='utf-8')
    elif args[5] == 'remove':
        aliases.pop(args[6])
    else:
        raise SystemExit(2)
    aliases_path.write_text(json.dumps(aliases), encoding='utf-8')
elif operation == 'push':
    aliases_path = Path(os.environ['FAKE_ALIASES'])
    aliases = json.loads(aliases_path.read_text())
    Path(os.environ['FAKE_PUSHED']).write_text(aliases[args[5]] + '\\n', encoding='utf-8')
else:
    print(f'unexpected dolt args: {args}', file=sys.stderr)
    raise SystemExit(2)
""",
    )
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "DSTACK_WORKFLOW_LOCK_DIR": str(tmp_path / "locks"),
        "FAKE_ALIASES": str(tmp_path / "aliases.json"),
        "FAKE_CALLS": str(calls),
        "FAKE_DATA_DIR": str(data_dir),
        "FAKE_FETCHED": str(tmp_path / "fetched"),
        "FAKE_LOCAL_HEAD": "local-head",
        "FAKE_MERGE_BASE": "remote-head",
        "FAKE_PUSHED": str(tmp_path / "pushed"),
        "FAKE_REMOTE_COUNT": str(remote_count),
        "FAKE_REMOTE_HEAD": "remote-head",
        "FAKE_REPLACED": str(tmp_path / "replaced"),
    }
    return repository, environment


def run_guard(repository: Path, environment: dict[str, str], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--worktree", str(repository), "--run-id", "test-run", *extra],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("remote_head", ["remote-head", ""])
def test_guard_fetches_and_pushes_only_fast_forward_or_new_history(
    guarded_repository: tuple[Path, dict[str, str]],
    remote_head: str,
) -> None:
    repository, environment = guarded_repository
    environment["FAKE_REMOTE_HEAD"] = remote_head

    result = run_guard(repository, environment)

    assert result.returncode == 0, result.stderr
    assert Path(environment["FAKE_PUSHED"]).read_text(encoding="utf-8") == ("git+ssh://example.invalid/issues.git\n")
    assert json.loads(result.stdout)["status"] == "pushed"
    assert "git+ssh://example.invalid/issues.git" not in result.stdout
    calls = Path(environment["FAKE_CALLS"]).read_text(encoding="utf-8")
    assert calls.index("dolt fetch origin") < calls.index("dolt push dstack-publication-")
    if not remote_head:
        assert "dolt merge-base" not in calls


@pytest.mark.parametrize(
    ("local_head", "remote_head", "merge_base", "expected"),
    [
        ("local-head", "remote-head", "other-head", "divergent"),
        ("local-head", "remote-head", "local-head", "behind"),
        ("local-head", "remote-head", "", "no-common-ancestor"),
    ],
)
def test_guard_rejects_unsafe_history_without_pushing(
    guarded_repository: tuple[Path, dict[str, str]],
    local_head: str,
    remote_head: str,
    merge_base: str,
    expected: str,
) -> None:
    repository, environment = guarded_repository
    environment.update(
        FAKE_LOCAL_HEAD=local_head,
        FAKE_REMOTE_HEAD=remote_head,
        FAKE_MERGE_BASE=merge_base,
    )

    result = run_guard(repository, environment)

    assert result.returncode == 1
    assert expected in result.stderr
    assert "recovery" in result.stderr
    assert not Path(environment["FAKE_PUSHED"]).exists()


def test_guard_rejects_dirty_or_foreign_interaction_state(
    guarded_repository: tuple[Path, dict[str, str]],
) -> None:
    repository, environment = guarded_repository
    interactions = repository / ".beads/interactions.jsonl"
    interactions.parent.mkdir(exist_ok=True)
    interactions.write_text('{"id":"foreign","issue_id":"other"}\n', encoding="utf-8")

    result = run_guard(repository, environment)

    assert result.returncode == 1
    assert "clean canonical worktree" in result.stderr
    assert not Path(environment["FAKE_FETCHED"]).exists()
    assert not Path(environment["FAKE_PUSHED"]).exists()


@pytest.mark.parametrize("replacement", ["FAKE_REPLACE_REMOTE", "FAKE_REPLACE_AFTER_BIND"])
def test_guard_rejects_remote_replacement_without_pushing(
    guarded_repository: tuple[Path, dict[str, str]],
    replacement: str,
) -> None:
    repository, environment = guarded_repository
    environment[replacement] = "1"

    result = run_guard(repository, environment)

    assert result.returncode == 1
    assert "remote configuration changed" in result.stderr
    assert not Path(environment["FAKE_PUSHED"]).exists()


def test_guard_rejects_force_and_concurrent_publication(
    guarded_repository: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, environment = guarded_repository
    forced = run_guard(repository, environment, "--force")
    assert forced.returncode != 0
    assert not Path(environment["FAKE_PUSHED"]).exists()

    marker = tmp_path / "locked"
    holder = subprocess.Popen(
        [
            sys.executable,
            str(LOCK_SCRIPT),
            "exec",
            "--repository-root",
            str(repository),
            "--lock-dir",
            environment["DSTACK_WORKFLOW_LOCK_DIR"],
            "--timeout",
            "1",
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(0.5)",
        ],
        env=environment,
    )
    try:
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        blocked = run_guard(repository, environment)
        assert blocked.returncode == 1
        assert "workflow lock is busy" in blocked.stderr
        assert not Path(environment["FAKE_PUSHED"]).exists()
    finally:
        holder.wait(timeout=3)
