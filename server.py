from __future__ import annotations

import json
import os
import socket
from contextlib import asynccontextmanager, contextmanager
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

from revision_engine import next_revision_schedule, next_retest_schedule, update_mastery_progress
from pydantic import BaseModel, ConfigDict, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "tracker.db"
INDEX_PATH = BASE_DIR / "index.html"
STUDY_CYCLE_START_DATE = date(2026, 11, 20)
MIN_STUDY_WINDOW_DAYS = 95  # 189 planned units, with at most two new topics per day.

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="UPSC 2027 Tracker", version="1.1.0", lifespan=lifespan)


def connect_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


@contextmanager
def database_session():
    connection = connect_database()
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    with database_session() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO app_state (id, payload) VALUES (1, '{}')"
        )



class TrackerState(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = Field(default=0, ge=0)
    topics: dict[str, Any] = Field(default_factory=dict)
    daily: dict[str, Any] = Field(default_factory=dict)
    weekly: dict[str, Any] = Field(default_factory=dict)
    logs: dict[str, Any] = Field(default_factory=dict)
    studyPlanDone: dict[str, Any] = Field(default_factory=dict)
    studyPlanProgress: dict[str, Any] = Field(default_factory=dict)
    revisionDone: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    customSubjects: list[dict[str, Any]] = Field(default_factory=list)
    customDaily: list[list[Any]] = Field(default_factory=list)
    topicEvidence: dict[str, Any] = Field(default_factory=dict)
    revisionSchedule: dict[str, Any] = Field(default_factory=dict)
    testResults: list[dict[str, Any]] = Field(default_factory=list)
    errorNotebook: list[dict[str, Any]] = Field(default_factory=list)
    strictRules: dict[str, Any] = Field(default_factory=dict)
    questionBank: list[dict[str, Any]] = Field(default_factory=list)
    masteryProgress: dict[str, Any] = Field(default_factory=dict)
    retestSchedule: dict[str, Any] = Field(default_factory=dict)
    recoveryQueue: list[dict[str, Any]] = Field(default_factory=list)
    examSession: dict[str, Any] | None = None
    pendingTopicEvidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("settings")
    @classmethod
    def validate_target_date(cls, value: dict[str, Any]) -> dict[str, Any]:
        target = value.get("targetDate")
        if target is None:
            return value
        if not isinstance(target, str):
            raise ValueError("The target date must use YYYY-MM-DD.")
        try:
            target_date = date.fromisoformat(target)
        except ValueError as exc:
            raise ValueError("The target date must use YYYY-MM-DD.") from exc
        if target_date.isoformat() != target:
            raise ValueError("The target date must use YYYY-MM-DD.")
        minimum_date = STUDY_CYCLE_START_DATE + timedelta(days=MIN_STUDY_WINDOW_DAYS)
        if target_date < minimum_date:
            raise ValueError(
                f"The target date must be on or after {minimum_date.isoformat()} "
                "to fit the complete two-day study plan."
            )
        return value


def get_lan_ip() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


@app.get("/api/network-info")
def network_info() -> dict[str, Any]:
    host = os.environ.get("TRACKER_HOST", "127.0.0.1")
    return {
        "url": f"http://{get_lan_ip()}:8000",
        "network_access_enabled": host in {"0.0.0.0", "::"},
    }


@app.get("/api/qr-code")
def qr_code(url: str) -> Response:
    from io import BytesIO
    import qrcode
    from qrcode.image.svg import SvgPathImage

    image = qrcode.make(url, image_factory=SvgPathImage, box_size=8, border=4)
    output = BytesIO()
    image.save(output)
    return Response(content=output.getvalue(), media_type="image/svg+xml")


@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        with database_session() as connection:
            connection.execute("SELECT 1 FROM app_state WHERE id = 1").fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Tracker database is unavailable.") from exc
    return {"status": "ok", "database": "sqlite"}


class RevisionScheduleRequest(BaseModel):
    today: str
    previous: dict[str, Any] | None = None
    quality: int = Field(ge=0, le=5)


@app.post("/api/revision/next")
def calculate_revision_schedule(request: RevisionScheduleRequest) -> dict[str, Any]:
    try:
        return next_revision_schedule(request.today, request.previous, request.quality)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



class StudyReviewRequest(BaseModel):
    today: str
    previous_mastery: dict[str, Any] | None = None
    previous_retest: dict[str, Any] | None = None
    quality: int = Field(strict=True, ge=0, le=5)
    is_retest: bool = False


@app.post("/api/study/review")
def update_study_review(request: StudyReviewRequest) -> dict[str, Any]:
    try:
        mastery = update_mastery_progress(
            request.previous_mastery,
            request.today,
            request.quality,
        )
        retest = next_retest_schedule(
            request.previous_retest,
            request.today,
            request.quality,
            is_retest=request.is_retest,
        )
        return {"mastery": mastery, "retest": retest}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    initialize_database()
    with database_session() as connection:
        row = connection.execute(
            "SELECT payload FROM app_state WHERE id = 1"
        ).fetchone()
    if row is None:
        return TrackerState().model_dump()
    try:
        data = json.loads(row[0])
        return TrackerState.model_validate(data).model_dump()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Saved tracker data is invalid.") from exc


@app.put("/api/state")
def save_state(state: TrackerState) -> dict[str, Any]:
    initialize_database()
    with database_session() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT payload FROM app_state WHERE id = 1"
        ).fetchone()
        try:
            current = json.loads(row[0]) if row else {}
            if not isinstance(current, dict):
                raise ValueError("Saved tracker state must be a JSON object.")
            raw_version = current.get("version", 0)
            if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version < 0:
                raise ValueError("Saved tracker version must be a non-negative integer.")
            current_version = raw_version
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            connection.rollback()
            raise HTTPException(
                status_code=500, detail="Saved tracker data is invalid."
            ) from exc

        if state.version != current_version:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Tracker state changed since it was loaded.",
                    "current_version": current_version,
                    "submitted_version": state.version,
                },
            )

        next_version = current_version + 1
        payload = json.dumps(
            {**state.model_dump(), "version": next_version},
            ensure_ascii=False,
        )
        connection.execute(
            """
            INSERT INTO app_state (id, payload, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (payload,),
        )
        connection.commit()
    return {"status": "saved", "version": next_version}




@app.get("/strict_engine.js")
def strict_engine_asset() -> Response:
    raise HTTPException(status_code=404, detail="Strict engine asset is not included in this build.")


@app.get("/strict_rules.js")
def strict_rules_asset() -> Response:
    raise HTTPException(status_code=404, detail="Strict rules asset is not included in this build.")


@app.get("/")
def dashboard() -> FileResponse:
    if not INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(INDEX_PATH)
