from __future__ import annotations

from pathlib import Path


ASSETS = Path(__file__).parents[2] / "dstack" / "assets"
SKILLS = ASSETS / "skills"


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def test_prime_owns_only_common_dstack_contract() -> None:
    prime = (ASSETS / "PRIME.md").read_text(encoding="utf-8")

    assert "dstack <command> [arguments]" in prime
    assert "explicitly activated dStack workflow" in prime
    assert "recovery_required" in prime
    assert "Git owns repository content" in prime
    assert "Beads owns plans" in prime

    for stage_specific_command in (
        "dstack commit --bead",
        "dstack audit --bead",
        "dstack docs commit --bead",
        "dstack check plan --bead",
    ):
        assert stage_specific_command not in prime


def test_each_skill_documents_only_its_required_dstack_surface() -> None:
    expected = {
        "dstack-plan-feature": ("dstack init", "dstack check formula", "dstack check plan --bead <plan>"),
        "dstack-review-plan": ("dstack check plan --bead <plan>", "dstack check review --bead <root>"),
        "dstack-implement": (
            "dstack worktree --bead <feature-or-descendant>",
            "dstack commit --bead <task>",
            "dstack check task --bead <task>",
        ),
        "dstack-close-feature": (
            "dstack worktree --bead <feature-or-descendant>",
            "dstack audit --bead <root> --include-plan",
            "dstack docs export-design --bead <root> --scaffold",
            "dstack check docs --slug <slug>",
            "dstack docs commit --bead <root>",
            "dstack audit --bead <root> --include-plan --require-docs",
        ),
        "dstack-audit-project": ("dstack init", "dstack check formula", "dstack check plan --bead <plan>"),
    }

    for name, commands in expected.items():
        skill = _skill(name)
        assert "## dStack operations" in skill
        for command in commands:
            assert command in skill


def test_implementation_skill_does_not_explain_commit_rewrite_internals() -> None:
    skill = _skill("dstack-implement")
    for implementation_detail in ("GIT_SEQUENCE_EDITOR", "sequence editor", "autosquash", "replay descendants"):
        assert implementation_detail not in skill


def test_review_and_close_skills_preserve_persistent_native_close_blockers() -> None:
    review = _skill("dstack-review-plan")
    close = _skill("dstack-close-feature")

    command = "bd dep add <audit> <task> --type blocks"
    assert command in review
    assert command in close
    assert "later reopen blocks close again" in review
    assert "interrupted task-creation sequence" in close
