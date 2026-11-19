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
