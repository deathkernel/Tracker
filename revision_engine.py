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



def update_mastery_progress(
    previous: dict[str, Any] | None,
    today: str,
    quality: int,
) -> dict[str, Any]:
    """Update deterministic recall mastery metrics for one study topic."""
    if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 5:
        raise ValueError("Revision quality must be an integer between 0 and 5.")
    try:
        reviewed_date = datetime.strptime(today, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("Review date must use YYYY-MM-DD.") from exc

    prior = previous if isinstance(previous, dict) else {}
    try:
        reviews = max(0, int(prior.get("reviews", 0)))
    except (TypeError, ValueError, OverflowError):
        reviews = 0
    try:
        quality_total = float(prior.get("quality_total", prior.get("qualityTotal", 0)))
    except (TypeError, ValueError, OverflowError):
        quality_total = 0.0
    if quality_total < 0 or quality_total != quality_total:
        quality_total = 0.0
    if quality_total == 0 and reviews:
        try:
            quality_total = max(0.0, float(prior.get("average_quality", prior.get("averageQuality", 0)))) * reviews
        except (TypeError, ValueError, OverflowError):
            quality_total = 0.0

    try:
        mastery_level = int(prior.get("mastery_level", prior.get("masteryLevel", 0)))
    except (TypeError, ValueError, OverflowError):
        mastery_level = 0
    mastery_level = max(0, min(5, mastery_level))
    try:
        consecutive_strong = max(0, int(prior.get("consecutive_strong", prior.get("consecutiveStrong", 0))))
    except (TypeError, ValueError, OverflowError):
        consecutive_strong = 0

    reviews += 1
    quality_total += quality
    mastery_level = max(0, min(5, mastery_level + (1 if quality >= 4 else -1 if quality < 3 else 0)))
    consecutive_strong = consecutive_strong + 1 if quality >= 4 else 0
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
    try:
        reviewed_date = datetime.strptime(today, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("Review date must use YYYY-MM-DD.") from exc

    prior = previous if isinstance(previous, dict) else {}
    try:
        attempts = max(0, int(prior.get("attempts", 0)))
    except (TypeError, ValueError, OverflowError):
        attempts = 0
    if is_retest:
        attempts += 1

    interval_days = 1 if quality < 3 else 3 if quality < 4 else 7
    return {
        "due_date": (reviewed_date + timedelta(days=interval_days)).isoformat(),
        "attempts": attempts,
        "last_quality": quality,
        "status": "scheduled",
        "interval_days": interval_days,
    }
