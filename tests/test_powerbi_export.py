from __future__ import annotations

import csv
import json
import sqlite3
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
            "plan:0": {"studyDone": True, "mcqDone": True, "revisionDone": True, "mcqCount": 18},
        }
    }
    rows = exporter.build_study_plan_rows(html, state)
    assert len(rows) == 6
    assert rows[0]["Date"] == "2026-11-20"
    assert rows[0]["Phase"] == "Day 1 · Study"
    assert rows[0]["IsCompleted"] is True
    assert rows[1]["Date"] == "2026-11-21"
    assert rows[1]["Phase"] == "Day 2 · MCQ + Revision"
    assert rows[1]["MCQAttempts"] == 18
    assert rows[1]["IsCompleted"] is True
    assert rows[2]["Date"] == "2027-02-20"
    assert rows[2]["Subject"] == "Polity"
    assert rows[4]["Subject"] == "History"


def test_real_dashboard_plan_expands_to_two_phases_per_topic():
    html = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
    rows = exporter.build_study_plan_rows(html, {})
    assert len(rows) == 378
    assert rows[0]["Date"] == "2026-11-20"
    assert rows[0]["Phase"] == "Day 1 · Study"
    assert rows[1]["Date"] == "2026-11-21"
    assert rows[1]["Phase"] == "Day 2 · MCQ + Revision"
    assert rows[-1]["Date"] == "2027-05-23"


def test_day_two_export_reads_progress_from_previous_study_date():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    state = {
        "studyPlanProgress": {
            "plan:0": {"studyDone": True, "mcqDone": True, "revisionDone": False, "mcqCount": 12},
        }
    }
    rows = exporter.build_study_plan_rows(html, state)
    assert rows[0]["IsCompleted"] is True
    assert rows[1]["Date"] == "2026-11-21"
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



def test_study_plan_export_places_two_phase_cycle_inside_exam_window():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution","Parliament","Judiciary"]}
];
'''
    rows = exporter.build_study_plan_rows(html, {"settings": {"targetDate": "2026-11-25"}})
    assert len(rows) == 6
    assert rows[0]["Date"] == "2026-11-20"
    assert rows[-1]["Date"] == "2026-11-25"
    assert rows[0]["Phase"] == "Day 1 · Study"
    assert rows[-1]["Phase"] == "Day 2 · MCQ + Revision"


def test_study_plan_export_prefers_new_per_topic_progress_keys():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    rows = exporter.build_study_plan_rows(html, {
        "studyPlanProgress": {
            "plan:0": {
                "studyDone": True,
                "mcqDone": True,
                "revisionDone": True,
                "mcqCount": 21,
            }
        }
    })
    assert rows[0]["IsCompleted"] is True
    assert rows[1]["IsCompleted"] is True
    assert rows[1]["MCQAttempts"] == 21



def test_explicit_plan_progress_reset_wins_over_stale_legacy_done_flags():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    rows = exporter.build_study_plan_rows(html, {
        "studyPlanProgress": {
            "plan:0": {
                "studyDone": False,
                "mcqDone": False,
                "revisionDone": False,
                "mcqCount": 18,
                "studyReset": True,
            },
            "2026-11-17": {"studyDone": True},
            "2026-11-18": {"mcqDone": True, "revisionDone": True},
        },
        "studyPlanDone": {
            "2026-11-17": True,
            "2026-11-18": True,
        },
    })
    assert rows[0]["IsCompleted"] is False
    assert rows[1]["IsCompleted"] is False
    assert rows[1]["MCQAttempts"] == 18


def test_power_bi_schema_includes_mastery_retest_and_recovery_tables():
    assert "Mastery" in exporter.CSV_COLUMNS
    assert "RetestSchedule" in exporter.CSV_COLUMNS
    assert "RecoveryQueue" in exporter.CSV_COLUMNS
    assert "PlanTopics" in exporter.CSV_COLUMNS
    assert "PlanKey" in exporter.CSV_COLUMNS["StudyPlan"]
    assert "PlanKey" in exporter.CSV_COLUMNS["RecoveryQueue"]


def test_recovery_queue_rows_keep_topic_level_plan_keys():
    html = '''
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    rows = exporter.build_study_plan_rows(html, {})
    assert rows[0]["PlanKey"] == "plan:0"
    assert rows[1]["PlanKey"] == "plan:0"


def test_full_export_writes_consistent_plan_mastery_retest_and_recovery_keys(tmp_path, monkeypatch):
    html = '''
const SUBJECTS=[{"name":"Polity","topics":[["Constitution",1,"P1"]]}];
const DAILY=[["reading","Main topic study","7:00–8:15 AM","Read concepts"]];
const BASE_STUDY_PLAN=[
{subject:"Polity",days:["Constitution"]}
];
'''
    database = tmp_path / "tracker.db"
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TABLE app_state (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        state = {
            "version": 1,
            "topics": {"Polity::Constitution": True},
            "daily": {},
            "logs": {},
            "studyPlanProgress": {
                "plan:0": {
                    "studyDone": True,
                    "mcqDone": True,
                    "revisionDone": True,
                    "mcqCount": 14,
                }
            },
            "masteryProgress": {
                "plan:0": {
                    "reviews": 1,
                    "masteryLevel": 2,
                    "averageQuality": 4,
                    "lastQuality": 4,
                }
            },
            "retestSchedule": {
                "plan:0": {
                    "due_date": "2026-11-24",
                    "attempts": 1,
                    "status": "scheduled",
                    "last_quality": 4,
                }
            },
            "recoveryQueue": [{
                "key": "plan:0:study",
                "plan_key": "plan:0",
                "planIndex": 0,
                "subject": "Polity",
                "topic": "Constitution",
                "phase": "study",
                "due_date": "2026-11-19",
                "status": "pending",
            }],
            "settings": {"targetDate": "2026-11-25"},
            "customSubjects": [],
            "customDaily": [],
        }
        db.execute(
            "INSERT INTO app_state (id, payload) VALUES (1, ?)",
            (json.dumps(state),),
        )

    html_path = tmp_path / "index.html"
    html_path.write_text(html, encoding="utf-8")
    output = tmp_path / "powerbi_data"
    monkeypatch.setattr(exporter, "DB_PATH", database)
    monkeypatch.setattr(exporter, "HTML_PATH", html_path)
    monkeypatch.setattr(exporter, "OUT", output)

    exporter.main()

    with (output / "PlanTopics.csv").open(encoding="utf-8-sig", newline="") as file:
        plan_topics = list(csv.DictReader(file))
    with (output / "Mastery.csv").open(encoding="utf-8-sig", newline="") as file:
        mastery = list(csv.DictReader(file))
    with (output / "RetestSchedule.csv").open(encoding="utf-8-sig", newline="") as file:
        retests = list(csv.DictReader(file))
    with (output / "RecoveryQueue.csv").open(encoding="utf-8-sig", newline="") as file:
        recovery = list(csv.DictReader(file))

    assert plan_topics == [{"PlanKey": "plan:0", "Subject": "Polity", "PlannedTopic": "Constitution"}]
    assert mastery[0]["PlanKey"] == "plan:0"
    assert retests[0]["PlanKey"] == "plan:0"
    assert recovery[0]["PlanKey"] == "plan:0"
    assert recovery[0]["Phase"] == "study"
