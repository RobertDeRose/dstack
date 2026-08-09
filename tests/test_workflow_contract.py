from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def read_skill(name: str) -> str:
    return (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_mutating_lifecycles_use_the_repository_interaction_lease() -> None:
    for name in ("implement-feature", "implement-task", "close-feature"):
        text = read_skill(name)
        assert "beads-workflow-lock.py" in text
        assert "shared native beads authority" in text.lower()


def test_close_feature_has_fail_closed_delivery_ordering() -> None:
    text = read_skill("close-feature")

    assert "reconcile-beads-interactions.py preflight" in text
    assert "finalize-feature-delivery.py" in text
    assert "leave delivery/root open" in text
    assert "Do not close delivery/root" in text


def test_lifecycle_docs_describe_shared_interaction_authority() -> None:
    text = (ROOT / "docs/src/development/feature-lifecycle.md").read_text(encoding="utf-8")

    assert "repository-scoped interaction lease" in text
    assert "foreign interaction" in text
    assert "and root closures happen after the merge" in text.casefold()
