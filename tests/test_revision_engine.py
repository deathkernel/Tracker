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


def test_mastery_progress_increases_on_strong_recall_and_tracks_average():
    from revision_engine import update_mastery_progress

    first = update_mastery_progress(None, "2026-11-20", 5)
    assert first["reviews"] == 1
    assert first["average_quality"] == 5
    assert first["mastery_level"] == 1
    assert first["consecutive_strong"] == 1

    second = update_mastery_progress(first, "2026-11-21", 4)
    assert second["reviews"] == 2
    assert second["average_quality"] == 4.5
    assert second["mastery_level"] == 2
    assert second["consecutive_strong"] == 2


def test_mastery_progress_weak_recall_reduces_level_and_resets_streak():
    from revision_engine import update_mastery_progress

    previous = {
        "reviews": 3,
        "quality_total": 12,
        "mastery_level": 4,
        "consecutive_strong": 3,
    }
    result = update_mastery_progress(previous, "2026-11-20", 1)
    assert result["mastery_level"] == 3
    assert result["consecutive_strong"] == 0
    assert result["average_quality"] == 3.25


def test_retest_schedule_uses_quality_based_intervals_and_counts_attempts():
    from revision_engine import next_retest_schedule

    weak = next_retest_schedule({"attempts": 2}, "2026-11-20", 1, is_retest=True)
    normal = next_retest_schedule(weak, "2026-11-21", 3)
    strong = next_retest_schedule(normal, "2026-11-24", 5)

    assert weak["due_date"] == "2026-11-21"
    assert weak["attempts"] == 3
    assert weak["interval_days"] == 1
    assert normal["due_date"] == "2026-11-24"
    assert normal["attempts"] == 3
    assert normal["interval_days"] == 3
    assert strong["due_date"] == "2026-12-01"
    assert strong["interval_days"] == 7


def test_mastery_and_retest_reject_invalid_quality_and_dates():
    from revision_engine import next_retest_schedule, update_mastery_progress

    with pytest.raises(ValueError, match="between 0 and 5"):
        update_mastery_progress(None, "2026-11-20", True)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        update_mastery_progress(None, "20-11-2026", 3)
    with pytest.raises(ValueError, match="between 0 and 5"):
        next_retest_schedule(None, "2026-11-20", 6)
