from __future__ import annotations

import json
from datetime import date as date_type, timedelta
import os
import socket
import urllib.error
import urllib.request
from contextlib import asynccontextmanager, contextmanager
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "tracker.db"
INDEX_PATH = BASE_DIR / "index.html"

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
    version: int = Field(default=0, ge=0)
    topics: dict[str, Any] = Field(default_factory=dict)
    daily: dict[str, Any] = Field(default_factory=dict)
    weekly: dict[str, Any] = Field(default_factory=dict)
    logs: dict[str, Any] = Field(default_factory=dict)
    studyPlanDone: dict[str, Any] = Field(default_factory=dict)
    studyPlanProgress: dict[str, Any] = Field(default_factory=dict)
    aiSchedule: list[dict[str, Any]] = Field(default_factory=list)
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


class OllamaChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        if not value.strip() or any(char in value for char in "\r\n"):
            raise ValueError("Choose a valid local Ollama model.")
        return value.strip()

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a message for the study assistant.")
        return value.strip()



class OllamaPlannerRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    context: dict[str, Any] = Field(default_factory=dict)
    days: int = Field(default=7, ge=3, le=14)

    @field_validator("model")
    @classmethod
    def validate_planner_model(cls, value: str) -> str:
        if not value.strip() or any(char in value for char in "\r\n"):
            raise ValueError("Choose a valid local Ollama model.")
        return value.strip()


OLLAMA_URL = "http://127.0.0.1:11434"


def ollama_request(path: str, payload: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{OLLAMA_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Ollama returned an invalid response.")
    return result


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


@app.get("/api/ollama/status")
def ollama_status() -> dict[str, Any]:
    try:
        result = ollama_request("/api/tags", timeout=3.0)
        models = result.get("models", [])
        if not isinstance(models, list):
            models = []
        names = [
            item.get("name")
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        preferred = os.environ.get("TRACKER_OLLAMA_MODEL", "").strip()
        selected = preferred if preferred in names else (names[0] if names else "")
        return {"available": True, "models": names, "selected_model": selected}
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return {"available": False, "models": [], "selected_model": "", "message": "Ollama is not running on this PC."}


@app.post("/api/ollama/chat")
def ollama_chat(request: OllamaChatRequest) -> dict[str, str]:
    try:
        available = ollama_request("/api/tags", timeout=3.0)
        models = available.get("models", [])
        names = {
            item.get("name")
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if request.model not in names:
            raise HTTPException(status_code=400, detail="That model is not installed in Ollama.")
        context = json.dumps(request.context, ensure_ascii=False)[:12000]
        result = ollama_request(
            "/api/chat",
            {
                "model": request.model,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are the local UPSC study assistant inside Tracker. "
                            "Help the student reduce manual planning and review work. "
                            "Use only the supplied tracker context; never invent completed work, "
                            "dates, scores or official facts. Suggest actions, but never claim that "
                            "you changed Tracker records. The student must confirm any progress update. "
                            "Do not generate or store MCQ question banks; MCQ attempt counts only are tracked. "
                            "Keep responses practical, concise and organized."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Tracker context (JSON): {context}\\n\\nUser request: {request.message}",
                    },
                ],
                "options": {"temperature": 0.2},
            },
            timeout=120.0,
        )
        message = result.get("message", {})
        response_text = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(response_text, str) or not response_text.strip():
            raise ValueError("Ollama returned an empty response.")
        return {"response": response_text.strip(), "model": request.model}
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {detail}") from exc
    except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Ollama is unavailable or did not respond in time.") from exc


@app.post("/api/ollama/plan")
def ollama_plan(request: OllamaPlannerRequest) -> dict[str, Any]:
    try:
        available = ollama_request("/api/tags", timeout=3.0)
        models = available.get("models", [])
        names = {
            item.get("name")
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if request.model not in names:
            raise HTTPException(status_code=400, detail="That model is not installed in Ollama.")

        context = json.dumps(request.context, ensure_ascii=False)[:20000]
        prompt = (
            "Create a practical UPSC study schedule for the next "
            f"{request.days} days using ONLY this Tracker data: {context}. "
            "Return JSON only with exactly this shape: "
            '{"schedule":[{"date":"YYYY-MM-DD","blocks":[{"start":"HH:MM","end":"HH:MM",'
            '"subject":"...","topic":"...","task":"...","type":"study|revision|practice|break"}]}]}. '
            "Include every date, use 24-hour local time, keep within the daily study-hours goal, "
            "include breaks, revision and realistic study blocks. Prioritize pending high-priority "
            "topics and overdue work; do not schedule completed topics as new study. "
            "Respect the existing two-day topic cycle when it is represented in the context. "
            "Never create MCQ questions or a question bank; practice blocks may say attempt MCQs "
            "and record only the count. Do not invent topics: every subject/topic must come from "
            "the supplied pending topics. Keep the schedule actionable and avoid overlapping blocks."
        )
        result = ollama_request(
            "/api/chat",
            {
                "model": request.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": "You are an autonomous UPSC timetable planner. Return valid JSON only. Never fabricate Tracker data."},
                    {"role": "user", "content": prompt},
                ],
                "options": {"temperature": 0.1},
            },
            timeout=180.0,
        )
        message = result.get("message", {})
        raw = message.get("content", "") if isinstance(message, dict) else ""
        plan = json.loads(raw)
        days = plan.get("schedule") if isinstance(plan, dict) else None
        if not isinstance(days, list) or len(days) != request.days:
            raise ValueError("Ollama returned an incomplete schedule.")
        normalized = []
        seen_dates = set()
        start_date = date_type.fromisoformat(str(request.context.get("today", "")))
        allowed_topics = {
            (str(subject), str(topic))
            for item in request.context.get("subjects", [])
            if isinstance(item, dict)
            for topic in item.get("pending", [])
            for subject in [item.get("subject", "")]
        }
        for day in days:
            if not isinstance(day, dict) or not isinstance(day.get("date"), str):
                raise ValueError("Ollama returned an invalid schedule date.")
            date = day["date"]
            expected_date = (start_date + timedelta(days=len(normalized))).isoformat()
            if date != expected_date or date in seen_dates:
                raise ValueError("Ollama dates must cover the requested days in order.")
            seen_dates.add(date)
            blocks = day.get("blocks")
            if not isinstance(blocks, list) or not 1 <= len(blocks) <= 12:
                raise ValueError("Ollama returned an invalid number of daily blocks.")
            clean_blocks = []
            previous_end = ""
            planned_minutes = 0
            for block in blocks:
                if not isinstance(block, dict):
                    raise ValueError("Ollama returned an invalid schedule block.")
                start, end = block.get("start"), block.get("end")
                if not isinstance(start, str) or not isinstance(end, str):
                    raise ValueError("Schedule blocks need start and end times.")
                if not all(len(value) == 5 and value[2] == ":" and value[:2].isdigit() and value[3:].isdigit() for value in (start, end)):
                    raise ValueError("Schedule times must use HH:MM.")
                if not ("00:00" <= start < "24:00" and "00:00" < end <= "24:00" and start < end):
                    raise ValueError("Schedule block times are out of range.")
                if previous_end and start < previous_end:
                    raise ValueError("Schedule blocks cannot overlap.")
                previous_end = end
                kind = block.get("type", "study")
                if kind != "break":
                    planned_minutes += (int(end[:2]) * 60 + int(end[3:])) - (int(start[:2]) * 60 + int(start[3:]))
                subject = str(block.get("subject", ""))[:100]
                topic = str(block.get("topic", ""))[:200]
                kind = block.get("type", "study")
                if kind not in {"study", "revision", "practice", "break"}:
                    raise ValueError("Schedule block type is invalid.")
                if kind != "break" and subject and topic and allowed_topics and (subject, topic) not in allowed_topics:
                    raise ValueError("Ollama suggested a topic outside the pending Tracker syllabus.")
                clean_blocks.append({
                    "start": start, "end": end, "subject": subject,
                    "topic": topic, "task": str(block.get("task", ""))[:300],
                    "type": kind,
                })
            daily_goal = request.context.get("daily_goal_hours", 4)
            try:
                daily_goal_minutes = int(float(daily_goal) * 60)
            except (TypeError, ValueError):
                daily_goal_minutes = 240
            if planned_minutes > daily_goal_minutes:
                raise ValueError("Ollama scheduled more study time than the daily goal.")
            normalized.append({"date": date, "blocks": clean_blocks})
        normalized.sort(key=lambda item: item["date"])
        return {"schedule": normalized, "model": request.model}
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=502, detail=f"Ollama planner failed: {detail}") from exc
    except (OSError, TimeoutError, ValueError, TypeError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Ollama could not build a valid schedule. Retry or choose another local model.") from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database": "sqlite"}


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
