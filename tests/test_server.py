from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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
