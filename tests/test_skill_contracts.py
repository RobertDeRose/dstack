from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def skill(name: str) -> str:
    return (ROOT / "skills" / f"dstack-beads-{name}" / "SKILL.md").read_text()


def test_feature_skills_use_native_beads_workflow_primitives() -> None:
    assert "bd mol pour dstack-feature" in skill("start-feature")
    start = skill("start-feature")
    assert "depend on the implementation-approval milestone" in start
    assert "Do not pass the human gate ID through `--waits-for-gate`" in start
    assert "approval milestone" in skill("review-feature-spec").lower()
    assert "resolve the unique human gate" in skill("review-feature-spec").lower()
    assert "bd ready --mol" in skill("implement-feature")
    assert "bd mol current" in skill("implement-feature")
    assert "bd mol progress" in skill("implement-feature")
    assert "git merge --ff-only" in skill("close-feature")
    assert "gh:pr" in skill("close-feature")
    close = skill("close-feature")
    assert "whole feature branch" in close
    assert "log --oneline --no-merges <target>..HEAD" in close
    assert "diff --stat <target>...HEAD" in close
    assert "origin/<target>" in close
    assert "docs-only" in close


def test_start_feature_accepts_slug_bead_id_or_exact_title() -> None:
    start = skill("start-feature")
    assert "feature slug, a Bead ID, or an exact" in start
    assert "exact Bead ID" in start
    assert "Title matching is case-insensitive" in start
    assert "ignores a leading `Feature: ` prefix" in start
    assert "/adopt-feature <bead-id>" in start
    assert "Do not use fuzzy matching" in start


def test_alignment_skills_preserve_three_authority_tiers() -> None:
    review = skill("project-alignment-review")
    execute = skill("project-alignment-execute")
    land = skill("project-alignment-land")
    assert "do not modify source" in review.lower()
    assert "leave the human gate open" in review
    assert "explicit approval" in execute
    assert "resolve that gate" in execute.lower()
    assert "does not authorize final delivery" in execute
    assert "git merge --ff-only" in land
    assert "gh:pr" in land


def test_discovery_and_review_policies_are_shared() -> None:
    discoveries = (ROOT / "skills" / "dstack-beads-core" / "references" / "discoveries.md").read_text()
    reviews = (ROOT / "skills" / "dstack-beads-core" / "references" / "review-loop.md").read_text()
    assert "bd todo add" in discoveries
    assert "discovered-from" in discoveries
    assert "There is no maximum pass count" in reviews
    assert "review unavailable" in reviews
    assert "changes requested" in reviews


def test_human_gate_ids_are_not_misused_as_waits_for_gate_modes() -> None:
    all_text = "\n".join(
        path.read_text()
        for path in (ROOT / "skills").glob("*/SKILL.md")
    )
    assert "--waits-for-gate <human-gate-id>" not in all_text
    assert "--waits-for-gate <gate-id>" not in all_text


def test_adopt_feature_is_the_only_legacy_migration_path() -> None:
    adopt = skill("adopt-feature")
    assert "one-time compatibility path" in adopt
    assert "bd mol pour dstack-feature" in adopt
    assert "Never delete the legacy graph" in adopt
    assert "Do not recreate reviewer/coordinator tasks" in adopt
    assert "supersede the legacy feature root with the new root **last**" in adopt
    assert "/review-feature-spec <slug>" in adopt


def test_review_and_implement_default_to_active_session_feature() -> None:
    start = skill("start-feature")
    review = skill("review-feature-spec")
    implement = skill("implement-feature")

    assert "active feature for the current Pi session" in start
    assert "most recently resolved by `/start-feature`" in review
    assert "most recently resolved by `/start-feature`" in implement
    assert "most recently resolved by" in implement
    assert "`/review-feature-spec` in the current Pi session" in implement
    assert "An explicit selector always overrides the session default" in review
    assert "An explicit feature selector always overrides these defaults" in implement
    assert 'Do not persist an\n"active feature" label or custom state file' in review
    assert 'Do not persist an\n"active feature" label or custom state file' in implement


def test_beads_interaction_log_is_runtime_state() -> None:
    core = skill("core")
    close = skill("close-feature")
    setup = skill("setup-project")
    assert ".beads/interactions.jsonl" in core
    assert "Never recommend `git restore`" in core
    assert "/setup-project --force" in close
    assert "git rm --cached -- .beads/interactions.jsonl" in setup


def test_feature_skills_do_not_duplicate_git_history_or_workflow_state() -> None:
    root = Path(__file__).parents[1]
    feature_skills = [
        root / "skills" / "dstack-beads-start-feature" / "SKILL.md",
        root / "skills" / "dstack-beads-review-feature-spec" / "SKILL.md",
        root / "skills" / "dstack-beads-implement-feature" / "SKILL.md",
        root / "skills" / "dstack-beads-close-feature" / "SKILL.md",
    ]
    text = "\n".join(path.read_text() for path in feature_skills)
    assert "external reference `git:" not in text
    assert "set the specification step's external reference" not in text
    assert "Update the roadmap entry" not in text
    assert "update the roadmap" not in text
    assert "committed specification SHA" not in text


def test_commit_footer_is_the_only_git_beads_evidence_contract() -> None:
    root = Path(__file__).parents[1]
    core = (root / "skills" / "dstack-beads-core" / "SKILL.md").read_text()
    review = (root / "skills" / "dstack-beads-review-feature-spec" / "SKILL.md").read_text()
    implement = (root / "skills" / "dstack-beads-implement-feature" / "SKILL.md").read_text()
    close = (root / "skills" / "dstack-beads-close-feature" / "SKILL.md").read_text()
    assert "Beads: <work-item-id>" in core
    assert "Beads: <specification-step-id>" in review
    assert "Beads: <task-id>" in implement
    assert "Beads: <closeout-step-id>" in close
