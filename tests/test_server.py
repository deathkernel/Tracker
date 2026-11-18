from __future__ import annotations

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
    assert "TrackerStrictEngine" in client.get("/strict_engine.js").text
    assert "renderStrictPreparation" in client.get("/strict_rules.js").text


def test_state_round_trip_preserves_strict_exam_data(client):
    initial = client.get("/api/state")
    assert initial.status_code == 200
    assert initial.json()["version"] == 0

    payload = {
        **initial.json(),
        "topics": {"Polity::Fundamental Rights": True},
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
    }
    saved = client.put("/api/state", json=payload)
    assert saved.status_code == 200
    assert saved.json() == {"status": "saved", "version": 1}

    restored = client.get("/api/state").json()
    assert restored["version"] == 1
    assert restored["topics"] == payload["topics"]
    assert restored["questionBank"] == payload["questionBank"]
    assert restored["masteryProgress"] == payload["masteryProgress"]
    assert restored["examSession"] == payload["examSession"]
    assert restored["pendingTopicEvidence"] == payload["pendingTopicEvidence"]


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
