from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH, HTML_PATH, OUT = ROOT / "tracker.db", ROOT / "index.html", ROOT / "powerbi_data"


def extract_array(source: str, declaration: str) -> list[Any]:
    pos = source.find(declaration)
    if pos < 0:
        raise RuntimeError(f"Missing {declaration} in index.html")
    start = source.find("[", pos + len(declaration))
    if start < 0:
        raise RuntimeError(f"Missing array for {declaration}")
    depth = 0
    in_string = escaped = False
    quote = ""
    for i in range(start, len(source)):
        ch = source[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_string = False
        elif ch in ("'", '"', "`"):
            in_string, quote = True, ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(source[start : i + 1])
    raise RuntimeError(f"Could not parse {declaration}")


def merge_subjects(base: list[dict[str, Any]], custom: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = [{"name": item["name"], "topics": list(item.get("topics", []))} for item in base]
    for item in custom:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"].strip()
        if not name:
            continue
        group = next((s for s in merged if s["name"].casefold() == name.casefold()), None)
        if group is None:
            group = {"name": name, "topics": []}
            merged.append(group)
        known = {str(t[0]).casefold() for t in group["topics"] if isinstance(t, (list, tuple)) and t}
        for topic in item.get("topics", []):
            if not isinstance(topic, (list, tuple)) or not topic or not isinstance(topic[0], str):
                continue
            topic_name = topic[0].strip()
            if not topic_name or topic_name.casefold() in known:
                continue
            pyq = topic[1] if len(topic) > 1 and isinstance(topic[1], (int, float)) else None
            priority = topic[2] if len(topic) > 2 and isinstance(topic[2], str) else "P2"
            group["topics"].append([topic_name, pyq, priority])
            known.add(topic_name.casefold())
    return merged


CSV_COLUMNS = {
    "Topics": ["TopicKey", "Subject", "Topic", "Priority", "PYQCount"],
    "TopicProgress": ["TopicKey", "Subject", "Topic", "Priority", "IsCompleted", "IsRevised"],
    "StudyLogs": ["Date", "StudyHours", "MCQs", "CSAT", "Notes"],
    "DailyChecklist": ["Date", "TaskID", "Task", "IsCompleted"],
    "StudyPlan": ["PlanKey", "Date", "Week", "Subject", "PlannedTopic", "Phase", "MCQAttempts", "IsCompleted"],
    "PlanTopics": ["PlanKey", "Subject", "PlannedTopic"],
    "Calendar": ["Date", "Year", "MonthNumber", "Month", "Weekday", "WeekdayNumber"],
    "Mastery": ["TopicKey", "PlanKey", "Subject", "Topic", "Reviews", "MasteryLevel", "AverageQuality", "LastQuality"],
    "RetestSchedule": ["TopicKey", "PlanKey", "Subject", "Topic", "DueDate", "Attempts", "Status", "LastQuality"],
    "RecoveryQueue": ["PlanKey", "Subject", "Topic", "Phase", "DueDate", "Status"],
}


def write_csv(name: str, rows: list[dict[str, Any]]) -> None:
    if name not in CSV_COLUMNS:
        raise ValueError(f"Unknown Power BI table: {name}")
    path = OUT / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS[name], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{path.name}: {len(rows)} rows")


def valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def safe_number(value: Any, *, integer: bool = False) -> int | float | str:
    try:
        number = float(value)
        if not (number >= 0 and number < float("inf")):
            return ""
        if integer:
            return int(number) if number.is_integer() else ""
        return number
    except (TypeError, ValueError, OverflowError):
        return ""


def build_study_plan_rows(html: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    plan_start = html.find("const BASE_STUDY_PLAN=")
    if plan_start < 0:
        raise RuntimeError("Could not locate BASE_STUDY_PLAN")
    plan_end = html.find("];", plan_start)
    if plan_end < 0:
        raise RuntimeError("Could not locate the end of BASE_STUDY_PLAN")
    plan_source = html[plan_start:plan_end + 1]
    groups = re.findall(r'\{subject:"([^"]+)",days:\[(.*?)\]\}', plan_source, re.S)
    if not groups:
        raise RuntimeError("Could not parse BASE_STUDY_PLAN topics")

    topics: list[tuple[str, str]] = []
    for subject, raw_topics in groups:
        topic_names = re.findall(r'"((?:\\.|[^"\\])*)"', raw_topics)
        topics.extend((subject, topic) for topic in topic_names)

    if not topics:
        return []

    progress_state = state.get("studyPlanProgress", {})
    if not isinstance(progress_state, dict):
        progress_state = {}
    legacy_done = state.get("studyPlanDone", {})
    if not isinstance(legacy_done, dict):
        legacy_done = {}
    settings = state.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}

    start = date(2026, 11, 20)
    target_text = settings.get("targetDate", "2027-05-23")
    try:
        target = date.fromisoformat(target_text) if isinstance(target_text, str) else date(2027, 5, 23)
    except ValueError:
        target = date(2027, 5, 23)
    final_study_offset = max(0, (target - start).days - 1)

    rows: list[dict[str, Any]] = []
    for plan_index, (subject, topic) in enumerate(topics):
        if len(topics) > 1:
            study_offset = round(plan_index * final_study_offset / (len(topics) - 1))
        else:
            study_offset = 0
        study_date = start + timedelta(days=study_offset)
        revision_date = study_date + timedelta(days=1)

        progress_key = f"plan:{plan_index}"
        has_new_progress = progress_key in progress_state
        progress = progress_state.get(progress_key, {})
        if not isinstance(progress, dict):
            progress = {}

        study_done = bool(progress.get("studyDone"))
        mcq_done = bool(progress.get("mcqDone"))
        revision_done = bool(progress.get("revisionDone"))
        mcq_count = progress.get("mcqCount", 0)

        # Read legacy date-keyed records only when the new per-topic key is absent.
        if not has_new_progress:
            legacy_study_date = date(2026, 11, 17) + timedelta(days=plan_index * 2)
            legacy_revision_date = legacy_study_date + timedelta(days=1)
            old_study = progress_state.get(legacy_study_date.isoformat(), {})
            old_revision = progress_state.get(legacy_revision_date.isoformat(), {})
            if not isinstance(old_study, dict):
                old_study = {}
            if not isinstance(old_revision, dict):
                old_revision = {}
            legacy_study_done = bool(old_study.get("studyDone") or legacy_done.get(legacy_study_date.isoformat()))
            legacy_day_two_done = bool(legacy_done.get(legacy_revision_date.isoformat()))
            study_done = legacy_study_done and not bool(old_study.get("studyReset"))
            mcq_done = bool(old_study.get("mcqDone") or old_revision.get("mcqDone") or (study_done and legacy_day_two_done))
            revision_done = bool(old_study.get("revisionDone") or old_revision.get("revisionDone") or (study_done and legacy_day_two_done))
            mcq_count = old_revision.get("mcqCount", old_study.get("mcqCount", 0))

        rows.append({
            "PlanKey": f"plan:{plan_index}",
            "Date": study_date.isoformat(),
            "Week": (study_offset // 7) + 1,
            "Subject": subject,
            "PlannedTopic": topic,
            "Phase": "Day 1 · Study",
            "MCQAttempts": "",
            "IsCompleted": study_done,
        })
        rows.append({
            "PlanKey": f"plan:{plan_index}",
            "Date": revision_date.isoformat(),
            "Week": (study_offset // 7) + 1,
            "Subject": subject,
            "PlannedTopic": topic,
            "Phase": "Day 2 · MCQ + Revision",
            "MCQAttempts": safe_number(mcq_count, integer=True),
            "IsCompleted": study_done and mcq_done and revision_done,
        })
    return rows


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError("tracker.db not found")
    with sqlite3.connect(DB_PATH) as db:
        record = db.execute("SELECT payload FROM app_state WHERE id=1").fetchone()
    if not record:
        raise RuntimeError("No saved Tracker state")
    state = json.loads(record[0])
    if not isinstance(state, dict):
        raise RuntimeError("Saved Tracker state must be a JSON object")

    html = HTML_PATH.read_text(encoding="utf-8")
    subjects = merge_subjects(
        extract_array(html, "const SUBJECTS="),
        state.get("customSubjects", []) if isinstance(state.get("customSubjects", []), list) else [],
    )
    daily = extract_array(html, "const DAILY=")
    custom_daily = state.get("customDaily", []) if isinstance(state.get("customDaily", []), list) else []
    daily_items = daily + [
        item for item in custom_daily
        if isinstance(item, (list, tuple)) and len(item) >= 2
        and isinstance(item[0], str) and isinstance(item[1], str)
    ]

    topic_rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    topic_state = state.get("topics", {}) if isinstance(state.get("topics", {}), dict) else {}
    revision_state = state.get("revisionDone", {}) if isinstance(state.get("revisionDone", {}), dict) else {}
    for subject in subjects:
        for topic in subject["topics"]:
            name, pyq, priority = topic
            key = f'{subject["name"]}::{name}'
            completed = bool(topic_state.get(key, False))
            topic_rows.append({"TopicKey": key, "Subject": subject["name"], "Topic": name, "Priority": priority, "PYQCount": pyq if pyq is not None else ""})
            progress_rows.append({"TopicKey": key, "Subject": subject["name"], "Topic": name, "Priority": priority, "IsCompleted": completed, "IsRevised": completed and bool(revision_state.get(key, False))})

    logs_state = state.get("logs", {}) if isinstance(state.get("logs", {}), dict) else {}
    logs = []
    for day, value in sorted(logs_state.items()):
        if not isinstance(value, dict) or not valid_iso_date(day):
            continue
        logs.append({"Date": day, "StudyHours": safe_number(value.get("hours")), "MCQs": safe_number(value.get("mcqs"), integer=True), "CSAT": safe_number(value.get("csat"), integer=True), "Notes": str(value.get("notes") or "")})

    checklist = []
    daily_state = state.get("daily", {}) if isinstance(state.get("daily", {}), dict) else {}
    for day, checks in sorted(daily_state.items()):
        if not isinstance(checks, dict) or not valid_iso_date(day):
            continue
        for item in daily_items:
            checklist.append({"Date": day, "TaskID": item[0], "Task": item[1], "IsCompleted": bool(checks.get(item[0], False))})

    plan_rows = build_study_plan_rows(html, state)

    dates = sorted({row["Date"] for row in logs + checklist + plan_rows if valid_iso_date(row.get("Date"))})
    calendar = []
    for value in dates:
        day = date.fromisoformat(value)
        calendar.append({"Date": value, "Year": day.year, "MonthNumber": day.month, "Month": day.strftime("%B"), "Weekday": day.strftime("%A"), "WeekdayNumber": day.isoweekday()})

    known_topics = {row["TopicKey"]: row for row in topic_rows}
    plan_topics = {row["PlanKey"]: {"Subject": row["Subject"], "Topic": row["PlannedTopic"]} for row in plan_rows}
    mastery_rows: list[dict[str, Any]] = []
    mastery_state = state.get("masteryProgress", {})
    if isinstance(mastery_state, dict):
        for key, value in mastery_state.items():
            topic = known_topics.get(key) or plan_topics.get(key)
            if not topic or not isinstance(value, dict):
                continue
            is_plan_key = key.startswith("plan:")
            mastery_rows.append({
                "TopicKey": "" if is_plan_key else key,
                "PlanKey": key if is_plan_key else "",
                "Subject": topic["Subject"],
                "Topic": topic["Topic"],
                "Reviews": safe_number(value.get("reviews"), integer=True),
                "MasteryLevel": safe_number(value.get("masteryLevel"), integer=True),
                "AverageQuality": safe_number(value.get("averageQuality")),
                "LastQuality": safe_number(value.get("lastQuality"), integer=True),
            })

    retest_rows: list[dict[str, Any]] = []
    retest_state = state.get("retestSchedule", {})
    if isinstance(retest_state, dict):
        for key, value in retest_state.items():
            topic = known_topics.get(key) or plan_topics.get(key)
            if not topic or not isinstance(value, dict):
                continue
            due_date = value.get("due_date", "")
            is_plan_key = key.startswith("plan:")
            retest_rows.append({
                "TopicKey": "" if is_plan_key else key,
                "PlanKey": key if is_plan_key else "",
                "Subject": topic["Subject"],
                "Topic": topic["Topic"],
                "DueDate": due_date if valid_iso_date(due_date) else "",
                "Attempts": safe_number(value.get("attempts"), integer=True),
                "Status": str(value.get("status") or ""),
                "LastQuality": safe_number(value.get("last_quality"), integer=True),
            })

    recovery_rows: list[dict[str, Any]] = []
    recovery_state = state.get("recoveryQueue", [])
    if isinstance(recovery_state, list):
        for item in recovery_state:
            if not isinstance(item, dict):
                continue
            due_date = item.get("due_date", "")
            recovery_rows.append({
                "PlanKey": str(item.get("plan_key") or f"plan:{item.get('planIndex')}"),
                "Subject": str(item.get("subject") or ""),
                "Topic": str(item.get("topic") or ""),
                "Phase": str(item.get("phase") or ""),
                "DueDate": due_date if valid_iso_date(due_date) else "",
                "Status": str(item.get("status") or "pending"),
            })

    OUT.mkdir(exist_ok=True)
    for name, rows in [
        ("Topics", topic_rows),
        ("TopicProgress", progress_rows),
        ("StudyLogs", logs),
        ("DailyChecklist", checklist),
        ("StudyPlan", plan_rows),
        ("PlanTopics", [
            {
                "PlanKey": key,
                "Subject": value["Subject"],
                "PlannedTopic": value["Topic"],
            }
            for key, value in sorted(plan_topics.items())
        ]),
        ("Calendar", calendar),
        ("Mastery", mastery_rows),
        ("RetestSchedule", retest_rows),
        ("RecoveryQueue", recovery_rows),
    ]:
        write_csv(name, rows)
    print(f"Power BI data exported to {OUT}")


if __name__ == "__main__":
    main()
