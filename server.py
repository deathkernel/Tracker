from __future__ import annotations

import json
import socket
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "tracker.db"
INDEX_PATH = BASE_DIR / "index.html"

app = FastAPI(title="UPSC 2027 Tracker", version="1.0.0")


def initialize_database() -> None:
    with sqlite3.connect(DB_PATH) as connection:
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
    topics: dict[str, Any] = {}
    daily: dict[str, Any] = {}
    weekly: dict[str, Any] = {}
    logs: dict[str, Any] = {}
    studyPlanDone: dict[str, Any] = {}
    revisionDone: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    customSubjects: list[dict[str, Any]] = []
    customDaily: list[list[Any]] = []


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()


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
def network_info() -> dict[str, str]:
    return {"url": f"http://{get_lan_ip()}:8000"}


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
    return {"status": "ok", "database": "sqlite"}


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    initialize_database()
    with sqlite3.connect(DB_PATH) as connection:
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
def save_state(state: TrackerState) -> dict[str, str]:
    initialize_database()
    payload = json.dumps(state.model_dump(), ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as connection:
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
    return {"status": "saved"}


@app.get("/")
def dashboard() -> FileResponse:
    if not INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(INDEX_PATH)

