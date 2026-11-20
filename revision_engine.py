"""Deterministic spaced-revision helpers for Tracker."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from typing import Any


MAX_STUDY_REVIEW_COUNT = 1_000_000
MAX_REVISION_INTERVAL_DAYS = 3_650


def _parse_iso_date(value: Any, label: str = "Review date") -> date:
    """Parse a canonical YYYY-MM-DD date and reject permissive alternatives."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must use YYYY-MM-DD.")
    return parsed


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
        if isinstance(value, float) and not value.is_integer():
            return default
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, number))


def _bounded_float(
    value: Any,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return max(minimum, min(maximum, number))


def next_revision_schedule(
    today: str,
    previous: dict[str, Any] | None,
    quality: int,
) -> dict[str, Any]:
    """Return a deterministic SM-2-style next review date for a 0–5 recall score."""
    if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 5:
        raise ValueError("Revision quality must be an integer between 0 and 5.")
    review_date = _parse_iso_date(today)
    prior = previous if isinstance(previous, dict) else {}
    repetitions = _bounded_int(
        prior.get("repetitions", 0),
        0,
        0,
        MAX_STUDY_REVIEW_COUNT,
    )
    interval_days = _bounded_int(
        prior.get("interval_days", 1),
        1,
        1,
        MAX_REVISION_INTERVAL_DAYS,
    )
    ease_factor = _bounded_float(
        prior.get("ease_factor", 2.5),
        2.5,
        1.3,
        3.0,
    )

    difficulty = 5 - quality
    ease_factor = max(
        1.3,
        ease_factor + (0.1 - difficulty * (0.08 + difficulty * 0.02)),
    )

    if quality < 3:
        repetitions = 0
        interval_days = 1
    else:
        repetitions = min(MAX_STUDY_REVIEW_COUNT, repetitions + 1)
        if repetitions == 1:
            interval_days = 1
        elif repetitions == 2:
            interval_days = 6
        else:
            interval_days = min(
                MAX_REVISION_INTERVAL_DAYS,
                max(1, round(interval_days * ease_factor)),
            )

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
        current_date = _parse_iso_date(today, "Current date")
    except ValueError:
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
                due_date = _parse_iso_date(schedule.get("due_date"), "Revision due date")
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



def update_mastery_progress(
    previous: dict[str, Any] | None,
    today: str,
    quality: int,
) -> dict[str, Any]:
    """Update deterministic recall mastery metrics for one study topic."""
    if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 5:
        raise ValueError("Revision quality must be an integer between 0 and 5.")
    reviewed_date = _parse_iso_date(today)

    prior = previous if isinstance(previous, dict) else {}
    reviews = _bounded_int(
        prior.get("reviews", 0),
        0,
        0,
        MAX_STUDY_REVIEW_COUNT,
    )
    quality_total = _bounded_float(
        prior.get("quality_total", prior.get("qualityTotal", 0)),
        0.0,
        0.0,
        MAX_STUDY_REVIEW_COUNT * 5.0,
    )
    if quality_total == 0 and reviews:
        average_quality = _bounded_float(
            prior.get("average_quality", prior.get("averageQuality", 0)),
            0.0,
            0.0,
            5.0,
        )
        quality_total = average_quality * reviews

    mastery_level = _bounded_int(
        prior.get("mastery_level", prior.get("masteryLevel", 0)),
        0,
        0,
        5,
    )
    consecutive_strong = _bounded_int(
        prior.get("consecutive_strong", prior.get("consecutiveStrong", 0)),
        0,
        0,
        MAX_STUDY_REVIEW_COUNT,
    )

    reviews = min(MAX_STUDY_REVIEW_COUNT, reviews + 1)
    quality_total = min(MAX_STUDY_REVIEW_COUNT * 5.0, quality_total + quality)
    mastery_level = max(0, min(5, mastery_level + (1 if quality >= 4 else -1 if quality < 3 else 0)))
    consecutive_strong = (
        min(MAX_STUDY_REVIEW_COUNT, consecutive_strong + 1)
        if quality >= 4
        else 0
    )
    return {
        "reviews": reviews,
        "quality_total": quality_total,
        "average_quality": round(quality_total / reviews, 2),
        "mastery_level": mastery_level,
        "consecutive_strong": consecutive_strong,
        "last_quality": quality,
        "last_reviewed_at": reviewed_date.isoformat(),
    }


def next_retest_schedule(
    previous: dict[str, Any] | None,
    today: str,
    quality: int,
    *,
    is_retest: bool = False,
) -> dict[str, Any]:
    """Schedule a follow-up recall check based on the latest 0–5 quality score."""
    if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 5:
        raise ValueError("Revision quality must be an integer between 0 and 5.")
    reviewed_date = _parse_iso_date(today)

    prior = previous if isinstance(previous, dict) else {}
    attempts = _bounded_int(
        prior.get("attempts", 0),
        0,
        0,
        MAX_STUDY_REVIEW_COUNT,
    )
    if is_retest:
        attempts = min(MAX_STUDY_REVIEW_COUNT, attempts + 1)

    interval_days = 1 if quality < 3 else 3 if quality < 4 else 7
    return {
        "due_date": (reviewed_date + timedelta(days=interval_days)).isoformat(),
        "attempts": attempts,
        "last_quality": quality,
        "status": "scheduled",
        "interval_days": interval_days,
    }
