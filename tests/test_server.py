from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "tracker.db")
    with TestClient(server.app) as test_client:
        yield test_client


def test_health_and_dashboard_assets(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "sqlite"}
    assert client.get("/").status_code == 200
    assert client.get("/strict_engine.js").status_code == 404
    assert client.get("/strict_rules.js").status_code == 404


def test_state_round_trip_preserves_strict_exam_data(client):
    initial = client.get("/api/state")
    assert initial.status_code == 200
    assert initial.json()["version"] == 0

    payload = {
        **initial.json(),
        "topics": {"Polity::Fundamental Rights": True},
        "studyPlanProgress": {"2026-11-17": {"studyDone": True}, "2026-11-18": {"mcqDone": True, "revisionDone": True, "mcqCount": 18}},
        "questionBank": [{
            "id": "q-1",
            "subject": "Polity",
            "topic": "Fundamental Rights",
            "question": "Which part contains Fundamental Rights?",
            "options": ["Part I", "Part II", "Part III", "Part IV"],
            "correctIndex": 2,
        }],
        "masteryProgress": {"Polity::Fundamental Rights": {"streak": 2}},
        "examSession": {"id": "exam-1", "answers": {"q-1": 2}},
        "pendingTopicEvidence": {"Polity::Fundamental Rights": {"pyqs": 15}},
        "aiSchedule": [{"date": "2026-11-20", "topic": "Legacy timetable"}],
    }
    saved = client.put("/api/state", json=payload)
    assert saved.status_code == 200
    assert saved.json() == {"status": "saved", "version": 1}

    restored = client.get("/api/state").json()
    assert restored["version"] == 1
    assert restored["topics"] == payload["topics"]
    assert restored["studyPlanProgress"] == payload["studyPlanProgress"]
    assert restored["questionBank"] == payload["questionBank"]
    assert restored["masteryProgress"] == payload["masteryProgress"]
    assert restored["examSession"] == payload["examSession"]
    assert restored["pendingTopicEvidence"] == payload["pendingTopicEvidence"]
    assert restored["aiSchedule"] == payload["aiSchedule"]


def test_revision_schedule_endpoint_uses_shared_sm2_policy(client):
    response = client.post("/api/revision/next", json={
        "today": "2026-11-19",
        "previous": {"interval_days": 14, "repetitions": 4, "ease_factor": 2.5},
        "quality": 1,
    })
    assert response.status_code == 200
    assert response.json()["interval_days"] == 1
    assert response.json()["repetitions"] == 0
    assert response.json()["ease_factor"] < 2.5
    invalid = client.post("/api/revision/next", json={"today": "2026-11-19", "quality": 6})
    assert invalid.status_code == 422


def test_health_reports_database_query_failure(client, monkeypatch):
    def broken_connect():
        raise sqlite3.OperationalError("database unavailable")
    monkeypatch.setattr(server, "connect_database", broken_connect)
    response = client.get("/api/health")
    assert response.status_code == 503


def test_state_rejects_stale_writes_without_overwriting_newer_data(client):
    first = client.get("/api/state").json()
    payload = {**first, "logs": {"2026-11-18": {"hours": 4}}}
    assert client.put("/api/state", json=payload).status_code == 200

    stale_payload = {**first, "logs": {"2026-11-18": {"hours": 1}}}
    response = client.put("/api/state", json=stale_payload)
    assert response.status_code == 409
    assert client.get("/api/state").json()["logs"]["2026-11-18"]["hours"] == 4


def test_state_rejects_negative_version(client):
    payload = client.get("/api/state").json()
    payload["version"] = -1
    response = client.put("/api/state", json=payload)
    assert response.status_code == 422


def test_state_rejects_non_object_saved_json(client):
    with sqlite3.connect(server.DB_PATH) as db:
        db.execute("UPDATE app_state SET payload = ? WHERE id = 1", ('["not", "an", "object"]',))
    response = client.put("/api/state", json={"version": 0})
    assert response.status_code == 500


def test_database_sessions_close_connections(client, monkeypatch):
    connections = []
    original_connect = server.connect_database
    def tracked_connect():
        connection = original_connect()
        connections.append(connection)
        return connection
    monkeypatch.setattr(server, "connect_database", tracked_connect)
    assert client.get("/api/state").status_code == 200
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


@pytest.mark.parametrize("invalid_version", [True, 1.5, "1", -1])
def test_state_rejects_invalid_saved_version_types(client, invalid_version):
    with sqlite3.connect(server.DB_PATH) as db:
        db.execute(
            "UPDATE app_state SET payload = ? WHERE id = 1",
            (json.dumps({"version": invalid_version}),),
        )
    response = client.put("/api/state", json={"version": 0})
    assert response.status_code == 500
    assert response.json()["detail"] == "Saved tracker data is invalid."


def test_study_review_endpoint_updates_mastery_and_retest(client):
    response = client.post("/api/study/review", json={
        "today": "2026-11-20",
        "quality": 5,
        "previous_mastery": None,
        "previous_retest": None,
        "is_retest": False,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["mastery"]["mastery_level"] == 1
    assert payload["mastery"]["average_quality"] == 5
    assert payload["retest"]["due_date"] == "2026-11-27"
    assert payload["retest"]["attempts"] == 0


def test_study_review_endpoint_validates_recall_quality_and_date(client):
    invalid_quality = client.post("/api/study/review", json={
        "today": "2026-11-20",
        "quality": True,
    })
    assert invalid_quality.status_code == 422

    invalid_date = client.post("/api/study/review", json={
        "today": "20-11-2026",
        "quality": 3,
    })
    assert invalid_date.status_code == 422


def test_study_retest_endpoint_counts_attempts_without_resetting_mastery(client):
    response = client.post("/api/study/review", json={
        "today": "2026-11-20",
        "quality": 1,
        "previous_mastery": {
            "reviews": 1,
            "qualityTotal": 5,
            "masteryLevel": 2,
            "consecutiveStrong": 1,
        },
        "previous_retest": {"attempts": 2},
        "is_retest": True,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["mastery"]["reviews"] == 2
    assert payload["mastery"]["mastery_level"] == 1
    assert payload["retest"]["attempts"] == 3
    assert payload["retest"]["due_date"] == "2026-11-21"
