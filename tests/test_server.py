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
    with TestClient(server.app, client=("127.0.0.1", 50123)) as test_client:
        yield test_client


def test_health_and_dashboard_assets(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "sqlite"}
    assert client.get("/").status_code == 200
    assert client.get("/strict_engine.js").status_code == 404
    assert client.get("/strict_rules.js").status_code == 404


def test_favicon_assets_serve_and_redirect_without_404(client):
    svg = client.get("/favicon.svg")
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in svg.text

    legacy_icon = client.get("/favicon.ico", follow_redirects=False)
    assert legacy_icon.status_code == 307
    assert legacy_icon.headers["location"] == "/favicon.svg"

    followed_icon = client.get("/favicon.ico")
    assert followed_icon.status_code == 200
    assert followed_icon.headers["content-type"].startswith("image/svg+xml")


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


@pytest.mark.parametrize("target_date", ["2026-02-30", "20-11-2026", "2027-02-22"])
def test_state_rejects_invalid_or_too_early_target_dates(client, target_date):
    payload = client.get("/api/state").json()
    payload["settings"] = {"targetDate": target_date}
    response = client.put("/api/state", json=payload)
    assert response.status_code == 422


def test_state_accepts_minimum_target_date_that_fits_the_two_day_plan(client):
    payload = client.get("/api/state").json()
    payload["settings"] = {"targetDate": "2027-02-23"}
    response = client.put("/api/state", json=payload)
    assert response.status_code == 200


def test_state_keeps_legacy_target_dates_readable(client):
    legacy_state = {
        "version": 0,
        "settings": {"targetDate": "2026-12-01"},
    }
    with sqlite3.connect(server.DB_PATH) as db:
        db.execute(
            "UPDATE app_state SET payload = ? WHERE id = 1",
            (json.dumps(legacy_state),),
        )

    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.json()["settings"]["targetDate"] == "2026-12-01"


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


def test_study_review_batch_returns_complete_multi_topic_updates(client):
    response = client.post("/api/study/review-batch", json={
        "today": "2026-11-20",
        "reviews": [
            {
                "key": "Polity::Fundamental Rights",
                "previous_revision": {"interval_days": 1, "repetitions": 1, "ease_factor": 2.5},
                "previous_mastery": None,
                "previous_retest": None,
                "quality": 5,
                "update_revision": True,
            },
            {
                "key": "Polity::Basic Structure",
                "previous_revision": {},
                "previous_mastery": None,
                "previous_retest": {"attempts": 2},
                "quality": 2,
                "update_revision": True,
            },
        ],
    })
    assert response.status_code == 200
    updates = response.json()["updates"]
    assert [item["key"] for item in updates] == [
        "Polity::Fundamental Rights",
        "Polity::Basic Structure",
    ]
    assert all(item["revision_schedule"]["due_date"] for item in updates)
    assert updates[0]["mastery"]["mastery_level"] == 1
    assert updates[1]["retest"]["due_date"] == "2026-11-21"
    assert updates[1]["retest"]["attempts"] == 2


def test_study_review_batch_rejects_any_invalid_item_without_partial_result(client):
    response = client.post("/api/study/review-batch", json={
        "today": "2026-11-20",
        "reviews": [
            {"key": "Polity::Rights", "quality": 5, "update_revision": True},
            {"key": "Polity::Basic Structure", "quality": 6, "update_revision": True},
        ],
    })
    assert response.status_code == 422


def test_study_review_batch_rejects_duplicate_topic_keys(client):
    response = client.post("/api/study/review-batch", json={
        "today": "2026-11-20",
        "reviews": [
            {"key": "Polity::Rights", "quality": 4},
            {"key": "Polity::Rights", "quality": 4},
        ],
    })
    assert response.status_code == 422


def test_health_reports_database_query_failure(client, monkeypatch):
    def broken_connect():
        raise sqlite3.OperationalError("database unavailable")
    monkeypatch.setattr(server, "connect_database", broken_connect)
    response = client.get("/api/health")
    assert response.status_code == 503


def test_state_rejects_stale_writes_without_overwriting_newer_data(client):
    first = client.get("/api/state").json()
    payload = {
        **first,
        "settings": {**first["settings"], "studyGoal": 5},
        "logs": {
            "2026-11-18": {
                "hours": 4,
                "csat": 30,
                "mcqs": 20,
                "notes": "attempted set",
            }
        },
    }
    assert client.put("/api/state", json=payload).status_code == 200

    restored = client.get("/api/state").json()
    assert restored["logs"]["2026-11-18"] == {
        "mcqs": 20,
        "notes": "attempted set",
    }
    assert "studyGoal" not in restored["settings"]

    stale_payload = {**first, "logs": {"2026-11-18": {"hours": 1, "mcqs": 1}}}
    response = client.put("/api/state", json=stale_payload)
    assert response.status_code == 409
    assert client.get("/api/state").json()["logs"]["2026-11-18"] == {
        "mcqs": 20,
        "notes": "attempted set",
    }


def test_database_startup_migrates_existing_study_duration_records(client):
    legacy = client.get("/api/state").json()
    legacy["settings"]["studyGoal"] = 5
    legacy["logs"] = {
        "2026-11-18": {
            "hours": 3.5,
            "mcqs": 25,
            "csat": 20,
            "notes": "saved notes",
        },
        "2026-11-19": {"hours": 2, "csat": 15},
    }
    with sqlite3.connect(server.DB_PATH) as database:
        database.execute(
            "UPDATE app_state SET payload = ? WHERE id = 1",
            (json.dumps(legacy),),
        )

    server.initialize_database()
    with sqlite3.connect(server.DB_PATH) as database:
        stored = json.loads(
            database.execute(
                "SELECT payload FROM app_state WHERE id = 1"
            ).fetchone()[0]
        )

    assert "studyGoal" not in stored["settings"]
    assert stored["logs"] == {
        "2026-11-18": {
            "mcqs": 25,
            "notes": "saved notes",
        }
    }


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



@pytest.mark.parametrize("quality", [True, 3.0, "3"])
def test_legacy_revision_endpoint_rejects_non_integer_quality(client, quality):
    response = client.post("/api/revision/next", json={
        "today": "2026-11-20",
        "quality": quality,
    })
    assert response.status_code == 422


def test_legacy_revision_endpoint_accepts_strict_integer_quality(client):
    response = client.post("/api/revision/next", json={
        "today": "2026-11-20",
        "quality": 3,
    })
    assert response.status_code == 200



@pytest.fixture
def lan_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "tracker-lan.db")
    monkeypatch.setattr(server, "LAN_ACCESS_TOKEN", "test-lan-access-token")
    with TestClient(server.app, client=("192.168.1.45", 50124)) as test_client:
        yield test_client


def test_remote_lan_api_rejects_missing_and_invalid_bearer_tokens(lan_client):
    unauthenticated = lan_client.get("/api/state")
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"

    invalid = lan_client.get(
        "/api/state",
        headers={"Authorization": "Bearer incorrect-token"},
    )
    assert invalid.status_code == 401

    authorized = lan_client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-lan-access-token"},
    )
    assert authorized.status_code == 200


def test_remote_lan_api_protects_revision_and_state_endpoints(lan_client):
    revision = lan_client.post(
        "/api/revision/next",
        json={"today": "2026-11-20", "quality": 4},
    )
    batch = lan_client.post(
        "/api/study/review-batch",
        json={
            "today": "2026-11-20",
            "reviews": [{"key": "Polity::Rights", "quality": 4}],
        },
    )
    assert revision.status_code == 401
    assert batch.status_code == 401


def test_qr_endpoint_uses_server_generated_lan_url_and_disables_caching(
    client, monkeypatch
):
    import qrcode

    monkeypatch.setattr(server, "LAN_ACCESS_TOKEN", "qr-secret-test-token")
    monkeypatch.setattr(server, "get_lan_ip", lambda: "192.168.1.45")
    captured = {}

    class FakeQrCode:
        def save(self, output):
            output.write(b"<svg></svg>")

    def capture_qr_payload(value, **_kwargs):
        captured["value"] = value
        return FakeQrCode()

    monkeypatch.setattr(qrcode, "make", capture_qr_payload)
    response = client.get(
        "/api/qr-code",
        params={"url": "https://attacker.example/collect"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert captured["value"] == (
        "http://192.168.1.45:8000#access_token=qr-secret-test-token"
    )
    assert "attacker.example" not in captured["value"]
    assert "qr-secret-test-token" not in str(response.request.url)


def test_remote_clients_cannot_generate_phone_access_qr_codes(lan_client):
    response = lan_client.get("/api/qr-code")
    assert response.status_code == 403
