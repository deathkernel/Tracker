from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from teacher_engine import is_quiet_time, prompt_is_due, validate_teacher_event


def test_quiet_hours_cover_overnight_window():
    zone = ZoneInfo("Asia/Kolkata")
    assert is_quiet_time(datetime(2026, 11, 19, 23, 0, tzinfo=zone), "22:00", "07:00")
    assert is_quiet_time(datetime(2026, 11, 20, 6, 59, tzinfo=zone), "22:00", "07:00")
    assert not is_quiet_time(datetime(2026, 11, 20, 7, 0, tzinfo=zone), "22:00", "07:00")
    assert not is_quiet_time(datetime(2026, 11, 20, 12, 0, tzinfo=zone), "22:00", "07:00")


def test_quiet_hours_support_same_day_window():
    zone = ZoneInfo("Asia/Kolkata")
    assert is_quiet_time(datetime(2026, 11, 20, 13, 0, tzinfo=zone), "12:00", "14:00")
    assert not is_quiet_time(datetime(2026, 11, 20, 15, 0, tzinfo=zone), "12:00", "14:00")


def test_teacher_prompt_cadence_respects_interval_and_quiet_hours():
    zone = ZoneInfo("Asia/Kolkata")
    now = datetime(2026, 11, 20, 12, 0, tzinfo=zone)
    assert prompt_is_due(now, None, 120, "22:00", "07:00")
    assert not prompt_is_due(now, "2026-11-20T11:00:00+05:30", 120, "22:00", "07:00")
    assert not prompt_is_due(now, None, 120, "11:00", "13:00")


def test_teacher_event_requires_one_supported_question_and_pending_topic():
    event = validate_teacher_event(
        {
            "kind": "concept_check",
            "prompt": "Explain the basic structure doctrine in your own words.",
            "subject": "Polity",
            "topic": "Basic Structure",
            "reason": "Check conceptual understanding.",
        },
        {("Polity", "Basic Structure")},
    )
    assert event["kind"] == "concept_check"
    assert event["topic"] == "Basic Structure"


def test_teacher_event_rejects_out_of_syllabus_topic():
    with pytest.raises(ValueError, match="outside the Tracker syllabus"):
        validate_teacher_event(
            {
                "kind": "recall_question",
                "prompt": "Explain this topic in your own words.",
                "subject": "Polity",
                "topic": "Invented Topic",
            },
            {("Polity", "Basic Structure")},
        )


@pytest.mark.parametrize("payload", [None, [], {}, {"kind": "unknown", "prompt": "This is a sufficiently long question."}])
def test_teacher_event_rejects_invalid_payload(payload):
    with pytest.raises(ValueError):
        validate_teacher_event(payload, set())



def test_next_revision_schedule_uses_spaced_intervals_for_successful_recall():
    from teacher_engine import next_revision_schedule

    first = next_revision_schedule("2026-11-19", None, 4)
    assert first["due_date"] == "2026-11-20"
    assert first["interval_days"] == 1
    second = next_revision_schedule("2026-11-20", first, 4)
    assert second["due_date"] == "2026-11-26"
    assert second["interval_days"] == 6
    third = next_revision_schedule("2026-11-26", second, 4)
    assert third["interval_days"] >= 6


def test_next_revision_schedule_resets_after_weak_recall():
    from teacher_engine import next_revision_schedule

    previous = {"interval_days": 14, "repetitions": 4, "ease_factor": 2.5}
    result = next_revision_schedule("2026-11-19", previous, 1)
    assert result["interval_days"] == 1
    assert result["repetitions"] == 0
    assert result["due_date"] == "2026-11-20"


def test_next_revision_schedule_rejects_invalid_quality():
    from teacher_engine import next_revision_schedule

    with pytest.raises(ValueError, match="between 0 and 5"):
        next_revision_schedule("2026-11-19", None, 6)


def test_due_revision_queue_includes_only_completed_topics_due_today_or_earlier():
    from teacher_engine import build_due_revision_queue

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


def test_teacher_can_test_due_completed_topics_without_opening_pending_topics():
    from teacher_engine import build_due_revision_queue

    context = {
        "completed_topics": [{"subject": "Polity", "topic": "Basic Structure"}],
        "revision_schedule": {"Polity::Basic Structure": {"due_date": "2026-11-18"}},
    }
    context["due_revision_topics"] = build_due_revision_queue(
        context["completed_topics"], context["revision_schedule"], "2026-11-19"
    )
    from server import teacher_allowed_topics

    assert ("Polity", "Basic Structure") in teacher_allowed_topics(context)



def test_due_revision_queue_treats_legacy_completed_topics_as_due():
    from teacher_engine import build_due_revision_queue

    result = build_due_revision_queue(
        [{"subject": "Polity", "topic": "Fundamental Rights"}],
        {},
        "2026-11-19",
    )
    assert result == [{
        "subject": "Polity",
        "topic": "Fundamental Rights",
        "due_date": "2026-11-19",
    }]
