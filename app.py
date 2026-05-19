from __future__ import annotations

from collections import deque
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Deque, Dict, Optional

from fastapi import FastAPI
from fastapi import Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from detectors.aggregator import Aggregator
from detectors.botd_v2 import BotdV2
from detectors.external_fe_bot_v1 import ExternalFeBotV1
from detectors.heuristic_mouse_v1 import HeuristicMouseV1

APP_DIR = Path(__file__).resolve().parent
MOUSE_PROGRAM_DIR = APP_DIR / "mouse_programs"
MAX_MOUSE_PROGRAM_SECONDS = 15.0
DEFAULT_MOUSE_CLICK_RATE_HZ = 0.7
app = FastAPI(title="MouseRisk Lab — heuristic bot-risk scoring")

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


class FeaturePayload(BaseModel):
    # movement/click features
    n: int = Field(..., ge=1)
    mean_dt: float
    std_dt: float
    p90_dt: float
    mean_speed: float
    std_speed: float
    max_speed: float
    straightness: float = Field(..., ge=0.0, le=1.0)
    mean_abs_turn: float
    trusted_ratio: float = Field(..., ge=0.0, le=1.0)
    pointer_type: Optional[str] = None
    duration_ms: Optional[float] = None
    mousemove_count: Optional[float] = None
    mousemove_teleport_count: Optional[float] = None

    # minimal “automation / environment” signals (no training, just heuristics)
    webdriver: Optional[bool] = None
    plugins_len: Optional[int] = None
    languages_len: Optional[int] = None
    hardware_concurrency: Optional[int] = None
    max_touch_points: Optional[int] = None
    ua_len: Optional[int] = None

    botd_bot: Optional[bool] = None
    botd_kind: Optional[str] = None

    session_id: Optional[str] = None
    reason: Optional[str] = None


class MouseProgramRunPayload(BaseModel):
    filename: str = Field(..., min_length=1, max_length=120)
    region: str = Field(..., pattern=r"^-?\d+,-?\d+,-?\d+,-?\d+$")
    count: int = Field(20, ge=1, le=100)
    focus_wait: float = Field(3.0, ge=0.0, le=30.0)
    timeout: float = Field(MAX_MOUSE_PROGRAM_SECONDS, ge=1.0, le=600.0)
    base_url: str = Field("http://127.0.0.1:8000", min_length=1, max_length=200)

    @field_validator("region", mode="before")
    @classmethod
    def normalize_region(cls, value: Any) -> Any:
        if isinstance(value, str):
            return ",".join(part.strip() for part in value.split(","))
        return value


aggregator = Aggregator([HeuristicMouseV1(), BotdV2(), ExternalFeBotV1()])
telemetry_events: Deque[Dict[str, Any]] = deque(maxlen=200)
telemetry_lock = threading.Lock()
mouse_program_lock = threading.Lock()


def resolve_mouse_program(filename: str) -> Path:
    if filename != Path(filename).name or not filename.endswith(".py"):
        raise ValueError("Invalid mouse program filename")
    path = (MOUSE_PROGRAM_DIR / filename).resolve()
    root = MOUSE_PROGRAM_DIR.resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError(filename)
    return path


def fit_click_count(count: int, focus_wait: float) -> int:
    runnable_seconds = max(1.0, MAX_MOUSE_PROGRAM_SECONDS - focus_wait - 0.5)
    max_count = max(1, int(runnable_seconds * DEFAULT_MOUSE_CLICK_RATE_HZ))
    return min(count, max_count)


@app.get("/", response_class=HTMLResponse)
def index() -> Any:
    html = (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/api/mouse-programs")
def list_mouse_programs() -> list[Dict[str, Any]]:
    MOUSE_PROGRAM_DIR.mkdir(exist_ok=True)
    programs = []
    for path in sorted(MOUSE_PROGRAM_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        stat = path.stat()
        programs.append(
            {
                "filename": path.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return programs


@app.post("/api/mouse-programs/run")
def run_mouse_program(payload: MouseProgramRunPayload) -> Dict[str, Any]:
    try:
        program_path = resolve_mouse_program(payload.filename)
    except FileNotFoundError:
        return {"ok": False, "error": "program_not_found"}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    acquired = mouse_program_lock.acquire(blocking=False)
    if not acquired:
        return {"ok": False, "error": "program_already_running"}

    started_at = time.time()
    timeout_seconds = min(payload.timeout, MAX_MOUSE_PROGRAM_SECONDS)
    click_count = fit_click_count(payload.count, payload.focus_wait)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(program_path),
                "--base-url",
                payload.base_url,
                "--region",
                payload.region,
                "--count",
                str(click_count),
                "--focus-wait",
                str(payload.focus_wait),
            ],
            cwd=str(APP_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": "timeout",
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + f"\nStopped after {timeout_seconds:.0f}s max runtime.",
            "duration": time.time() - started_at,
        }
    finally:
        mouse_program_lock.release()

    return {
        "ok": completed.returncode == 0,
        "filename": payload.filename,
        "requested_count": payload.count,
        "run_count": click_count,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration": time.time() - started_at,
    }


@app.post("/api/score")
def score(payload: FeaturePayload) -> Dict[str, Any]:
    result = aggregator.score(payload)
    session_id = payload.session_id or "default"
    event = {
        "ts": time.time(),
        "session_id": session_id,
        "reason": payload.reason,
        "n": payload.n,
        "bot_probability": result["bot_probability"],
        "model": result["model"],
        "raw_score": result["raw_score"],
        "signals": result.get("signals"),
    }
    with telemetry_lock:
        telemetry_events.append(event)
    return result


@app.get("/api/telemetry")
def telemetry(
    session_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[Dict[str, Any]]:
    with telemetry_lock:
        events = list(telemetry_events)
    if session_id:
        events = [event for event in events if event.get("session_id") == session_id]
    return events[-limit:]
