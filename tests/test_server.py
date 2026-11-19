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



def test_ollama_status_lists_installed_local_models(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "ollama_request",
        lambda path, payload=None, timeout=5.0: {
            "models": [{"name": "qwen3.5:9b"}, {"name": "llama3.2:3b"}]
        },
    )
    response = client.get("/api/ollama/status")
    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "models": ["qwen3.5:9b", "llama3.2:3b"],
        "selected_model": "qwen3.5:9b",
    }


def test_ollama_status_reports_missing_local_runtime(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("connection refused")
    monkeypatch.setattr(server, "ollama_request", unavailable)
    response = client.get("/api/ollama/status")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["models"] == []


def test_ollama_chat_uses_only_an_installed_model_and_returns_local_reply(client, monkeypatch):
    calls = []

    def fake_ollama(path, payload=None, timeout=5.0):
        calls.append((path, payload, timeout))
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b"}]}
        return {"message": {"content": "Revise Fundamental Rights and solve your pending PYQs."}}

    monkeypatch.setattr(server, "ollama_request", fake_ollama)
    response = client.post(
        "/api/ollama/chat",
        json={
            "model": "qwen3.5:9b",
            "message": "What should I study next?",
            "context": {"completed_topics": 12, "pending_topics": 20},
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "response": "Revise Fundamental Rights and solve your pending PYQs.",
        "model": "qwen3.5:9b",
    }
    assert calls[0][0] == "/api/tags"
    assert calls[1][0] == "/api/chat"
    assert calls[1][1]["stream"] is False
    assert calls[1][1]["messages"][1]["content"].find('"pending_topics": 20') >= 0


def test_ollama_chat_rejects_uninstalled_model(client, monkeypatch):
    monkeypatch.setattr(server, "ollama_request", lambda *args, **kwargs: {"models": []})
    response = client.post(
        "/api/ollama/chat",
        json={"model": "missing:model", "message": "Help me plan."},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "That model is not installed in Ollama."


def test_ollama_planner_returns_valid_schedule_from_pending_tracker_topics(client, monkeypatch):
    schedule = {
        "schedule": [
            {
                "date": f"2026-11-{day:02d}",
                "blocks": [
                    {
                        "start": "07:00",
                        "end": "08:30",
                        "subject": "Polity",
                        "topic": "Fundamental Rights",
                        "task": "Read and make concise notes.",
                        "type": "study",
                    },
                    {
                        "start": "08:30",
                        "end": "08:45",
                        "subject": "",
                        "topic": "",
                        "task": "Take a short break.",
                        "type": "break",
                    },
                ],
            }
            for day in (20, 21, 22)
        ]
    }
    calls = []

    def fake_ollama(path, payload=None, timeout=5.0):
        calls.append((path, payload))
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b"}]}
        return {"message": {"content": json.dumps(schedule)}}

    monkeypatch.setattr(server, "ollama_request", fake_ollama)
    response = client.post(
        "/api/ollama/plan",
        json={
            "model": "qwen3.5:9b",
            "days": 3,
            "context": {
                "today": "2026-11-20",
                "daily_goal_hours": 4,
                "subjects": [
                    {"subject": "Polity", "pending": ["Fundamental Rights"]}
                ],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["schedule"] == schedule["schedule"]
    assert calls[1][1]["format"] == "json"
    assert calls[1][1]["stream"] is False


def test_ollama_planner_rejects_topics_outside_tracker_pending_syllabus(client, monkeypatch):
    schedule = {
        "schedule": [
            {
                "date": f"2026-11-{day:02d}",
                "blocks": [
                    {
                        "start": "07:00",
                        "end": "08:00",
                        "subject": "Polity",
                        "topic": "Invented Topic",
                        "task": "Study this.",
                        "type": "study",
                    }
                ],
            }
            for day in (20, 21, 22)
        ]
    }

    def fake_ollama(path, payload=None, timeout=5.0):
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b"}]}
        return {"message": {"content": json.dumps(schedule)}}

    monkeypatch.setattr(server, "ollama_request", fake_ollama)
    response = client.post(
        "/api/ollama/plan",
        json={
            "model": "qwen3.5:9b",
            "days": 3,
            "context": {
                "subjects": [
                    {"subject": "Polity", "pending": ["Fundamental Rights"]}
                ]
            },
        },
    )
    assert response.status_code == 503
    assert "valid schedule" in response.json()["detail"]


def test_ollama_planner_rejects_overlapping_schedule_blocks(client, monkeypatch):
    schedule = {
        "schedule": [
            {
                "date": f"2026-11-{day:02d}",
                "blocks": [
                    {"start": "07:00", "end": "09:00", "subject": "Polity", "topic": "Fundamental Rights", "task": "Study.", "type": "study"},
                    {"start": "08:30", "end": "09:30", "subject": "Polity", "topic": "Fundamental Rights", "task": "Continue.", "type": "study"},
                ],
            }
            for day in (20, 21, 22)
        ]
    }

    def fake_ollama(path, payload=None, timeout=5.0):
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b"}]}
        return {"message": {"content": json.dumps(schedule)}}

    monkeypatch.setattr(server, "ollama_request", fake_ollama)
    response = client.post(
        "/api/ollama/plan",
        json={
            "model": "qwen3.5:9b",
            "days": 3,
            "context": {"subjects": [{"subject": "Polity", "pending": ["Fundamental Rights"]}]},
        },
    )
    assert response.status_code == 503
    assert "valid schedule" in response.json()["detail"]



def test_teacher_settings_and_context_are_persisted(client):
    settings = client.put(
        "/api/teacher/settings",
        json={
            "enabled": True,
            "interval_minutes": 60,
            "quiet_start": "21:30",
            "quiet_end": "07:30",
            "model": "qwen3.5:9b",
        },
    )
    assert settings.status_code == 200
    assert settings.json()["interval_minutes"] == 60
    assert client.get("/api/teacher/settings").json()["model"] == "qwen3.5:9b"

    context = {
        "today": "2026-11-20",
        "subjects": [{"subject": "Polity", "pending": ["Basic Structure"]}],
        "daily_goal_hours": 4,
    }
    assert client.put("/api/teacher/context", json={"context": context}).json() == {"status": "saved"}
    assert server.read_teacher_config()["context"] == context


def test_teacher_cycle_creates_one_syllabus_grounded_question(client, monkeypatch):
    calls = []

    def fake_ollama(path, payload=None, timeout=5.0):
        calls.append((path, payload))
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b"}]}
        return {
            "message": {
                "content": json.dumps(
                    {
                        "kind": "concept_check",
                        "prompt": "Explain the basic structure doctrine in your own words.",
                        "subject": "Polity",
                        "topic": "Basic Structure",
                        "reason": "Check conceptual understanding.",
                    }
                )
            }
        }

    monkeypatch.setattr(server, "ollama_request", fake_ollama)
    client.put(
        "/api/teacher/settings",
        json={
            "enabled": True,
            "interval_minutes": 120,
            "quiet_start": "00:00",
            "quiet_end": "00:00",
            "model": "qwen3.5:9b",
        },
    )
    client.put(
        "/api/teacher/context",
        json={
            "context": {
                "today": "2026-11-20",
                "subjects": [{"subject": "Polity", "pending": ["Basic Structure"]}],
                "daily_goal_hours": 4,
            }
        },
    )

    server.run_teacher_cycle()
    events = client.get("/api/teacher/events").json()["events"]
    assert len(events) == 1
    assert events[0]["kind"] == "concept_check"
    assert events[0]["topic"] == "Basic Structure"
    assert calls[0][0] == "/api/tags"
    assert calls[1][0] == "/api/chat"


def test_teacher_cycle_does_not_duplicate_an_unanswered_question(client, monkeypatch):
    client.put(
        "/api/teacher/settings",
        json={
            "enabled": True,
            "interval_minutes": 120,
            "quiet_start": "00:00",
            "quiet_end": "00:00",
            "model": "qwen3.5:9b",
        },
    )
    with server.database_session() as connection:
        connection.execute(
            """
            INSERT INTO teacher_events (created_at, kind, prompt)
            VALUES (?, ?, ?)
            """,
            ("2026-11-20T09:00:00+05:30", "daily_check_in", "Did you complete yesterday's work?"),
        )

    def should_not_call(*args, **kwargs):
        raise AssertionError("Ollama must not be called while a question is unanswered.")

    monkeypatch.setattr(server, "ollama_request", should_not_call)
    server.run_teacher_cycle()



def test_teacher_answer_is_evaluated_and_saved(client, monkeypatch):
    client.put(
        "/api/teacher/settings",
        json={"enabled": True, "interval_minutes": 120, "quiet_start": "22:00", "quiet_end": "07:00", "model": "qwen3.5:9b"},
    )
    with server.database_session() as connection:
        cursor = connection.execute(
            """
            INSERT INTO teacher_events (created_at, kind, prompt, subject, topic)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "2026-11-20T09:00:00+05:30",
                "concept_check",
                "Explain the basic structure doctrine.",
                "Polity",
                "Basic Structure",
            ),
        )
        event_id = cursor.lastrowid

    monkeypatch.setattr(
        server,
        "ollama_request",
        lambda *args, **kwargs: {
            "message": {"content": "Good start. Add the role of judicial review and constitutional identity."}
        },
    )
    response = client.post(
        "/api/teacher/respond",
        json={"event_id": event_id, "answer": "It limits Parliament's amending power."},
    )
    assert response.status_code == 200
    assert "judicial review" in response.json()["feedback"]
    event = client.get("/api/teacher/events").json()["events"][0]
    assert event["answer"] == "It limits Parliament's amending power."
    assert event["feedback"] == response.json()["feedback"]



def test_teacher_question_cannot_be_answered_twice(client, monkeypatch):
    client.put(
        "/api/teacher/settings",
        json={"enabled": True, "interval_minutes": 120, "quiet_start": "22:00", "quiet_end": "07:00", "model": "qwen3.5:9b"},
    )
    with server.database_session() as connection:
        cursor = connection.execute(
            """
            INSERT INTO teacher_events (created_at, kind, prompt)
            VALUES (?, ?, ?)
            """,
            ("2026-11-20T09:00:00+05:30", "daily_check_in", "Did you complete yesterday's work?"),
        )
        event_id = cursor.lastrowid

    calls = []
    monkeypatch.setattr(
        server,
        "ollama_request",
        lambda *args, **kwargs: calls.append(args) or {"message": {"content": "Answer reviewed."}},
    )
    first = client.post(
        "/api/teacher/respond",
        json={"event_id": event_id, "answer": "Yes, I completed the topic."},
    )
    second = client.post(
        "/api/teacher/respond",
        json={"event_id": event_id, "answer": "Changing my answer."},
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert len(calls) == 1
