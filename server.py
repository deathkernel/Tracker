from __future__ import annotations

import hmac
import ipaddress
import json
import os
import secrets
import socket
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager, contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from revision_engine import next_revision_schedule, next_retest_schedule, update_mastery_progress
from pydantic import BaseModel, ConfigDict, Field


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("TRACKER_DB_PATH", str(BASE_DIR / "tracker.db")))
INDEX_PATH = BASE_DIR / "index.html"
FAVICON_PATH = BASE_DIR / "favicon.svg"
THEME_PATH = BASE_DIR / "theme.css"
# Injected into the dashboard <head>. The stylesheet is the monochrome light
# theme; the small script keeps the legacy "dark" class off <body> because the
# interface is light-only.
THEME_SNIPPET = (
    '<link rel="stylesheet" href="/theme.css">'
    '<script>new MutationObserver(function(){var b=document.body;'
    'if(b&&b.classList.contains("dark"))b.classList.remove("dark")})'
    '.observe(document.documentElement,{attributes:true,subtree:true,attributeFilter:["class"]})</script>'
)
LAN_ACCESS_TOKEN = os.environ.get("TRACKER_ACCESS_TOKEN") or secrets.token_urlsafe(32)
STUDY_CYCLE_START_DATE = date(2026, 11, 20)
# Must stay in sync with BASE_STUDY_PLAN length in index.html (client uses
# Math.ceil(STUDY_PLAN_TOPICS.length / 2) for the same capacity rule).
PLANNED_STUDY_UNITS = 189
MIN_STUDY_WINDOW_DAYS = (PLANNED_STUDY_UNITS + 1) // 2  # at most two new topics per day

def validate_target_date_settings(settings: dict[str, Any]) -> None:
    target = settings.get("targetDate")
    if target is None:
        return
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="UPSC 2027 Tracker", version="1.1.0", lifespan=lifespan)


def is_loopback_request(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    try:
        address = ipaddress.ip_address(client.host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


@app.middleware("http")
async def protect_lan_api(request: Request, call_next):
    public_local_network_endpoints = {"/api/network-info", "/api/qr-code"}
    if (
        request.url.path.startswith("/api/")
        and request.url.path not in public_local_network_endpoints
        and not is_loopback_request(request)
    ):
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {LAN_ACCESS_TOKEN}"
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Tracker data is protected on the local network. "
                        "Scan the phone-access QR code from the host PC."
                    )
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


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


def strip_retired_study_time_tracking(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)

    settings = cleaned.get("settings")
    if isinstance(settings, dict):
        settings = dict(settings)
        settings.pop("studyGoal", None)
        cleaned["settings"] = settings

    logs = cleaned.get("logs")
    if isinstance(logs, dict):
        cleaned_logs: dict[str, dict[str, Any]] = {}
        for day, entry in logs.items():
            if not isinstance(entry, dict):
                continue
            record: dict[str, Any] = {}
            if "mcqs" in entry:
                record["mcqs"] = entry["mcqs"]
            if "notes" in entry:
                record["notes"] = entry["notes"]
            if record:
                cleaned_logs[day] = record
        cleaned["logs"] = cleaned_logs

    return cleaned


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
        row = connection.execute(
            "SELECT payload FROM app_state WHERE id = 1"
        ).fetchone()
        if row is not None:
            try:
                current = json.loads(row[0])
                if isinstance(current, dict):
                    cleaned = strip_retired_study_time_tracking(current)
                    if cleaned != current:
                        connection.execute(
                            "UPDATE app_state SET payload = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                            (json.dumps(cleaned, ensure_ascii=False),),
                        )
            except (json.JSONDecodeError, TypeError):
                pass



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
def qr_code(request: Request) -> Response:
    if not is_loopback_request(request):
        raise HTTPException(
            status_code=403,
            detail="Generate the phone-access QR code from the Tracker host PC.",
        )
    destination = network_info()["url"]
    destination += f"#access_token={LAN_ACCESS_TOKEN}"
    from io import BytesIO
    import qrcode
    from qrcode.image.svg import SvgPathImage

    image = qrcode.make(destination, image_factory=SvgPathImage, box_size=8, border=4)
    output = BytesIO()
    image.save(output)
    return Response(
        content=output.getvalue(),
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
        },
    )



@app.get("/api/pyq")
def get_public_pyq(request: Request) -> dict[str, Any]:
    """Safely proxy the documented public UPSC Prelims Test question API."""
    allowed = {"page", "limit", "q", "subject", "year"}
    supplied = dict(request.query_params)
    if set(supplied) - allowed or len(request.query_params.multi_items()) != len(supplied):
        raise HTTPException(status_code=400, detail="Unsupported or repeated PYQ filter.")
    try:
        page = int(supplied.get("page", "1"))
        limit = int(supplied.get("limit", "25"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Page and limit must be integers.") from exc
    if page < 1 or not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="Page must be positive and limit must be between 1 and 100.")
    params: dict[str, str] = {"page": str(page), "limit": str(limit)}
    query = supplied.get("q", "").strip()
    subject = supplied.get("subject", "").strip()
    year = supplied.get("year", "").strip()
    if len(query) > 200:
        raise HTTPException(status_code=400, detail="Search text must be 200 characters or fewer.")
    if query:
        params["q"] = query
    subjects = {"Polity", "History", "Economy", "Geography", "Environment", "Science", "Current Affairs"}
    if subject:
        if subject not in subjects:
            raise HTTPException(status_code=400, detail="Unknown PYQ subject.")
        params["subject"] = subject
    if year:
        if not year.isdigit() or not 2014 <= int(year) <= 2026:
            raise HTTPException(status_code=400, detail="Year must be between 2014 and 2026.")
        params["year"] = year
    url = "https://upscprelimstest.com/api/pyq/database?" + urllib.parse.urlencode(params)
    outbound = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "UPSC-Tracker/1.0"},
    )
    try:
        with urllib.request.urlopen(outbound, timeout=15) as response:
            payload = json.loads(response.read(5_000_001))
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail="The PYQ provider rejected the request.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=502, detail="The PYQ provider is unavailable or returned invalid JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise HTTPException(status_code=502, detail="The PYQ provider returned an unexpected response.")
    return payload


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
    quality: int = Field(strict=True, ge=0, le=5)


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


class StudyReviewBatchItem(BaseModel):
    key: str = Field(min_length=1, max_length=256)
    previous_revision: dict[str, Any] | None = None
    previous_mastery: dict[str, Any] | None = None
    previous_retest: dict[str, Any] | None = None
    quality: int = Field(strict=True, ge=0, le=5)
    is_retest: bool = False
    update_revision: bool = False


class StudyReviewBatchRequest(BaseModel):
    today: str
    reviews: list[StudyReviewBatchItem] = Field(min_length=1, max_length=50)


@app.post("/api/study/review-batch")
def update_study_review_batch(request: StudyReviewBatchRequest) -> dict[str, Any]:
    keys = [item.key for item in request.reviews]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=422, detail="Review batch keys must be unique.")

    try:
        updates = []
        for item in request.reviews:
            revision = (
                next_revision_schedule(request.today, item.previous_revision, item.quality)
                if item.update_revision
                else None
            )
            mastery = update_mastery_progress(
                item.previous_mastery,
                request.today,
                item.quality,
            )
            retest = next_retest_schedule(
                item.previous_retest,
                request.today,
                item.quality,
                is_retest=item.is_retest,
            )
            updates.append({
                "key": item.key,
                "revision_schedule": revision,
                "mastery": mastery,
                "retest": retest,
            })
        return {"updates": updates}
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
        return TrackerState.model_validate(strip_retired_study_time_tracking(data)).model_dump()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Saved tracker data is invalid.") from exc


@app.put("/api/state")
def save_state(state: TrackerState) -> dict[str, Any]:
    try:
        validate_target_date_settings(state.settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
            strip_retired_study_time_tracking({**state.model_dump(), "version": next_version}),
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


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg() -> FileResponse:
    if not FAVICON_PATH.exists():
        raise HTTPException(status_code=404, detail="favicon.svg not found")
    return FileResponse(FAVICON_PATH, media_type="image/svg+xml")


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico_compatibility() -> RedirectResponse:
    return RedirectResponse(url="/favicon.svg", status_code=307)


@app.get("/theme.css")
def theme_stylesheet() -> FileResponse:
    if not THEME_PATH.exists():
        raise HTTPException(status_code=404, detail="theme.css not found")
    return FileResponse(THEME_PATH, media_type="text/css", headers={"Cache-Control": "no-cache"})


@app.get("/")
def dashboard() -> Response:
    if not INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    if not THEME_PATH.exists():
        return FileResponse(INDEX_PATH)
    html = INDEX_PATH.read_text(encoding="utf-8")
    if THEME_SNIPPET not in html and "</head>" in html:
        html = html.replace("</head>", THEME_SNIPPET + "</head>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
