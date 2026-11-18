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
    "StudyPlan": ["Date", "Week", "Subject", "PlannedTopic", "IsCompleted"],
    "Calendar": ["Date", "Year", "MonthNumber", "Month", "Weekday", "WeekdayNumber"],
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

    plan: list[dict[str, Any]] = []
    plan_start = html.find("const DAILY_STUDY_PLAN=")
    plan_end = html.find("];", plan_start) + 1
    if plan_start < 0 or plan_end <= plan_start:
        raise RuntimeError("Could not locate DAILY_STUDY_PLAN")
    plan_source = html[plan_start:plan_end]
    for match in re.finditer(r'\{subject:"([^"]+)",days:\[(.*?)\]\}', plan_source, re.S):
        topics = json.loads("[" + match.group(2) + "]")
        plan.append({"subject": match.group(1), "days": topics})

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

    plan_rows = []
    plan_state = state.get("studyPlanDone", {}) if isinstance(state.get("studyPlanDone", {}), dict) else {}
    first = date(2026, 11, 17)
    for wi, week in enumerate(plan):
        for di, topic in enumerate(week["days"]):
            day = first + timedelta(days=wi * 7 + di)
            day_key = day.isoformat()
            plan_rows.append({"Date": day_key, "Week": wi + 1, "Subject": week.get("subject", ""), "PlannedTopic": topic, "IsCompleted": bool(plan_state.get(day_key, False))})

    dates = sorted({row["Date"] for row in logs + checklist + plan_rows if valid_iso_date(row.get("Date"))})
    calendar = []
    for value in dates:
        day = date.fromisoformat(value)
        calendar.append({"Date": value, "Year": day.year, "MonthNumber": day.month, "Month": day.strftime("%B"), "Weekday": day.strftime("%A"), "WeekdayNumber": day.isoweekday()})

    OUT.mkdir(exist_ok=True)
    for name, rows in [("Topics", topic_rows), ("TopicProgress", progress_rows), ("StudyLogs", logs), ("DailyChecklist", checklist), ("StudyPlan", plan_rows), ("Calendar", calendar)]:
        write_csv(name, rows)
    print(f"Power BI data exported to {OUT}")


if __name__ == "__main__":
    main()
