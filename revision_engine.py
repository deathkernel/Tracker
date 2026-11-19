"""Deterministic spaced-revision helpers for Tracker."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def next_revision_schedule(
    today: str,
    previous: dict[str, Any] | None,
    quality: int,
) -> dict[str, Any]:
    """Return a deterministic SM-2-style next review date for a 0–5 recall score."""
    if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 5:
        raise ValueError("Revision quality must be an integer between 0 and 5.")
    review_date = datetime.strptime(today, "%Y-%m-%d").date()
    prior = previous if isinstance(previous, dict) else {}
    try:
        repetitions = max(0, int(prior.get("repetitions", 0)))
        interval_days = max(1, int(prior.get("interval_days", 1)))
    except (TypeError, ValueError, OverflowError):
        repetitions = 0
        interval_days = 1
    try:
        ease_factor = float(prior.get("ease_factor", 2.5))
    except (TypeError, ValueError):
        ease_factor = 2.5
    ease_factor = max(1.3, min(3.0, ease_factor))

    difficulty = 5 - quality
    ease_factor = max(
        1.3,
        ease_factor + (0.1 - difficulty * (0.08 + difficulty * 0.02)),
    )

    if quality < 3:
        repetitions = 0
        interval_days = 1
    else:
        repetitions += 1
        if repetitions == 1:
            interval_days = 1
        elif repetitions == 2:
            interval_days = 6
        else:
            interval_days = max(1, round(interval_days * ease_factor))

    due_date = review_date + timedelta(days=interval_days)
    return {
        "due_date": due_date.isoformat(),
        "interval_days": interval_days,
        "repetitions": repetitions,
        "ease_factor": round(ease_factor, 2),
        "last_reviewed_at": today,
        "last_quality": quality,
    }


def build_due_revision_queue(
    completed_topics: Any,
    revision_schedule: Any,
    today: str,
) -> list[dict[str, str]]:
    """Select only completed syllabus topics whose persisted review date is due."""
    try:
        current_date = datetime.strptime(today, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return []
    if not isinstance(completed_topics, list) or not isinstance(revision_schedule, dict):
        return []

    due: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in completed_topics:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        topic = item.get("topic")
        if not isinstance(subject, str) or not subject.strip():
            continue
        if not isinstance(topic, str) or not topic.strip():
            continue
        key = f"{subject}::{topic}"
        if key in seen:
            continue
        schedule = revision_schedule.get(key)
        if schedule is None:
            due_date = current_date
        elif isinstance(schedule, dict):
            try:
                due_date = datetime.strptime(str(schedule.get("due_date", "")), "%Y-%m-%d").date()
            except ValueError:
                continue
        else:
            continue
        if due_date <= current_date:
            seen.add(key)
            due.append({
                "subject": subject.strip(),
                "topic": topic.strip(),
                "due_date": due_date.isoformat(),
            })
    due.sort(key=lambda item: (item["due_date"], item["subject"], item["topic"]))
    return due[:30]
