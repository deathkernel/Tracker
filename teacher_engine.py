"""Deterministic policy helpers for Tracker's local Strict AI Teacher."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

TEACHER_PROMPT_KINDS = {
    "daily_check_in",
    "completion_follow_up",
    "recall_question",
    "concept_check",
    "revision_check",
}


def parse_clock(value: str, fallback: time) -> time:
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def is_quiet_time(now: datetime, quiet_start: str, quiet_end: str) -> bool:
    start = parse_clock(quiet_start, time(22, 0))
    end = parse_clock(quiet_end, time(7, 0))
    current = now.timetz().replace(tzinfo=None)
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def prompt_is_due(
    now: datetime,
    last_prompt_at: str | None,
    interval_minutes: int,
    quiet_start: str,
    quiet_end: str,
) -> bool:
    if is_quiet_time(now, quiet_start, quiet_end):
        return False
    if last_prompt_at:
        try:
            previous = datetime.fromisoformat(last_prompt_at)
            if previous.tzinfo is None and now.tzinfo is not None:
                previous = previous.replace(tzinfo=now.tzinfo)
            if now - previous < timedelta(minutes=max(15, min(interval_minutes, 1440))):
                return False
        except (TypeError, ValueError):
            pass
    return True


def validate_teacher_event(
    payload: Any,
    allowed_topics: set[tuple[str, str]],
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Teacher response must be a JSON object.")

    kind = payload.get("kind")
    prompt = payload.get("prompt")
    subject = payload.get("subject", "")
    topic = payload.get("topic", "")
    reason = payload.get("reason", "")

    if kind not in TEACHER_PROMPT_KINDS:
        raise ValueError("Teacher returned an unsupported prompt type.")
    if not isinstance(prompt, str) or not 10 <= len(prompt.strip()) <= 1200:
        raise ValueError("Teacher returned an invalid question.")
    if not isinstance(subject, str) or not isinstance(topic, str):
        raise ValueError("Teacher returned invalid topic metadata.")
    if subject and topic and (subject, topic) not in allowed_topics:
        raise ValueError("Teacher referenced a topic outside the Tracker syllabus.")
    if not isinstance(reason, str):
        reason = ""

    return {
        "kind": kind,
        "prompt": prompt.strip(),
        "subject": subject[:100],
        "topic": topic[:200],
        "reason": reason.strip()[:500],
    }


def build_teacher_context(state: dict[str, Any]) -> dict[str, Any]:
    topics = state.get("topics", {})
    logs = state.get("logs", {})
    if not isinstance(topics, dict):
        topics = {}
    if not isinstance(logs, dict):
        logs = {}

    pending: list[dict[str, str]] = []
    completed_count = 0
    for subject in state.get("subjects", []):
        if not isinstance(subject, dict):
            continue
        subject_name = str(subject.get("name", ""))
        for topic in subject.get("topics", []):
            if not isinstance(topic, (list, tuple)) or not topic:
                continue
            topic_name = str(topic[0])
            if topics.get(f"{subject_name}::{topic_name}"):
                completed_count += 1
            else:
                pending.append({"subject": subject_name, "topic": topic_name})

    return {
        "completed_topic_count": completed_count,
        "pending_topics": pending[:100],
        "recent_study_logs": dict(list(logs.items())[-7:]),
        "daily_goal_hours": state.get("settings", {}).get("studyGoal", 4)
        if isinstance(state.get("settings"), dict)
        else 4,
        "two_day_cycle": "Day 1 study; Day 2 MCQ attempt count and revision for the same topic. Track counts only; do not create MCQ questions.",
    }
