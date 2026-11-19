from __future__ import annotations

import pytest

from revision_engine import build_due_revision_queue, next_revision_schedule


def test_next_revision_schedule_uses_spaced_intervals_for_successful_recall():
    first = next_revision_schedule("2026-11-19", None, 4)
    assert first["due_date"] == "2026-11-20"
    assert first["interval_days"] == 1
    second = next_revision_schedule("2026-11-20", first, 4)
    assert second["due_date"] == "2026-11-26"
    assert second["interval_days"] == 6
    third = next_revision_schedule("2026-11-26", second, 4)
    assert third["interval_days"] >= 6


def test_next_revision_schedule_resets_after_weak_recall():
    previous = {"interval_days": 14, "repetitions": 4, "ease_factor": 2.5}
    result = next_revision_schedule("2026-11-19", previous, 1)
    assert result["interval_days"] == 1
    assert result["repetitions"] == 0
    assert result["due_date"] == "2026-11-20"
    assert result["ease_factor"] < 2.5


def test_next_revision_schedule_rejects_invalid_quality():
    with pytest.raises(ValueError, match="between 0 and 5"):
        next_revision_schedule("2026-11-19", None, 6)


def test_due_revision_queue_includes_only_completed_topics_due_today_or_earlier():
    completed = [
        {"subject": "Polity", "topic": "Fundamental Rights"},
        {"subject": "History", "topic": "Modern India"},
        {"subject": "Economy", "topic": "Inflation"},
        {"subject": "Polity", "topic": "Fundamental Rights"},
    ]
    schedule = {
        "Polity::Fundamental Rights": {"due_date": "2026-11-19"},
        "History::Modern India": {"due_date": "2026-11-20"},
        "Economy::Inflation": {"due_date": "invalid"},
    }
    result = build_due_revision_queue(completed, schedule, "2026-11-19")
    assert result == [{
        "subject": "Polity",
        "topic": "Fundamental Rights",
        "due_date": "2026-11-19",
    }]
