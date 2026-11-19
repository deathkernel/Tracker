from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import powerbi_export as exporter


def test_empty_power_bi_tables_keep_importable_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "OUT", tmp_path)
    exporter.write_csv("StudyLogs", [])
    with (tmp_path / "StudyLogs.csv").open(encoding="utf-8-sig", newline="") as file:
        assert next(csv.reader(file)) == ["Date", "StudyHours", "MCQs", "CSAT", "Notes"]


def test_power_bi_date_validation_rejects_invalid_dates():
    assert exporter.valid_iso_date("2026-11-18")
    assert not exporter.valid_iso_date("2026-02-30")
    assert not exporter.valid_iso_date("18-11-2026")
    assert not exporter.valid_iso_date(None)


def test_power_bi_numeric_conversion_handles_malformed_values():
    assert exporter.safe_number("4.5") == 4.5
    assert exporter.safe_number("50", integer=True) == 50
    assert exporter.safe_number("2.5", integer=True) == ""
    assert exporter.safe_number("not-a-number") == ""
    assert exporter.safe_number(float("nan")) == ""
    assert exporter.safe_number(-1) == ""



def test_study_plan_export_contains_both_phases_and_attempt_counts():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution","Parliament"]},
{subject:"History",days:["Modern India"]}
];
'''
    state = {
        "studyPlanProgress": {
            "2026-11-17": {"studyDone": True, "mcqDone": True, "revisionDone": True, "mcqCount": 18},
        }
    }
    rows = exporter.build_study_plan_rows(html, state)
    assert len(rows) == 6
    assert rows[0]["Date"] == "2026-11-17"
    assert rows[0]["Phase"] == "Day 1 · Study"
    assert rows[0]["IsCompleted"] is True
    assert rows[1]["Date"] == "2026-11-18"
    assert rows[1]["Phase"] == "Day 2 · MCQ + Revision"
    assert rows[1]["MCQAttempts"] == 18
    assert rows[1]["IsCompleted"] is True
    assert rows[2]["Date"] == "2026-11-19"
    assert rows[2]["Subject"] == "Polity"
    assert rows[4]["Subject"] == "History"


def test_real_dashboard_plan_expands_to_two_phases_per_topic():
    html = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
    rows = exporter.build_study_plan_rows(html, {})
    assert len(rows) == 378
    assert rows[0]["Date"] == "2026-11-17"
    assert rows[0]["Phase"] == "Day 1 · Study"
    assert rows[1]["Date"] == "2026-11-18"
    assert rows[1]["Phase"] == "Day 2 · MCQ + Revision"
    assert rows[-1]["Date"] == "2027-11-29"


def test_day_two_export_reads_progress_from_previous_study_date():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    state = {
        "studyPlanProgress": {
            "2026-11-17": {"studyDone": True, "mcqDone": True, "revisionDone": False, "mcqCount": 12},
        }
    }
    rows = exporter.build_study_plan_rows(html, state)
    assert rows[0]["IsCompleted"] is True
    assert rows[1]["Date"] == "2026-11-18"
    assert rows[1]["MCQAttempts"] == 12
    assert rows[1]["IsCompleted"] is False


def test_day_two_export_keeps_legacy_same_date_progress_compatible():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    state = {
        "studyPlanProgress": {
            "2026-11-17": {"studyDone": True},
            "2026-11-18": {"mcqDone": True, "revisionDone": True, "mcqCount": 7},
        }
    }
    rows = exporter.build_study_plan_rows(html, state)
    assert rows[1]["MCQAttempts"] == 7
    assert rows[1]["IsCompleted"] is True


def test_day_two_export_merges_split_legacy_and_linked_progress():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    state = {
        "studyPlanProgress": {
            "2026-11-17": {"studyDone": True},
            "2026-11-18": {"mcqDone": True, "revisionDone": True, "mcqCount": 13},
        }
    }
    rows = exporter.build_study_plan_rows(html, state)
    assert rows[0]["IsCompleted"] is True
    assert rows[1]["MCQAttempts"] == 13
    assert rows[1]["IsCompleted"] is True
