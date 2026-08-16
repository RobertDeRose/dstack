from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def skill(name: str) -> str:
    return (ROOT / "skills" / f"dstack-beads-{name}" / "SKILL.md").read_text()


def test_feature_skills_use_native_beads_workflow_primitives() -> None:
    assert "bd mol pour dstack-feature" in skill("start-feature")
    assert "--waits-for-gate" in skill("start-feature")
    assert "resolve the unique human gate" in skill("review-feature-spec").lower()
    assert "bd ready --mol" in skill("implement-feature")
    assert "bd mol current" in skill("implement-feature")
    assert "bd mol progress" in skill("implement-feature")
    assert "git merge --ff-only" in skill("close-feature")
    assert "gh:pr" in skill("close-feature")


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
