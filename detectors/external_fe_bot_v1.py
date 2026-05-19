from __future__ import annotations

import os
from typing import Any, Dict

import requests

from .base import Detector


DEFAULT_EXTERNAL_FE_BOT_URL = "http://127.0.0.1:8001/predict/fe"


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


class ExternalFeBotV1(Detector):
    name = "external_fe_bot_v1"

    def __init__(self, url: str | None = None, timeout: float = 1.5) -> None:
        self.url = url or os.getenv("EXTERNAL_FE_BOT_URL", DEFAULT_EXTERNAL_FE_BOT_URL)
        self.timeout = timeout

    def score(self, payload: Any) -> Dict[str, Any]:
        request_payload = {
            "X-Session-Ticket": getattr(payload, "session_id", None) or "default-session",
            "showScheduleId": 101,
            "duration_ms": getattr(payload, "duration_ms", None),
            "mousemove_teleport_count": getattr(payload, "mousemove_teleport_count", None),
            "mousemove_count": getattr(payload, "mousemove_count", None),
        }

        try:
            response = requests.post(self.url, json=request_payload, timeout=self.timeout)
            response.raise_for_status()
            remote = response.json()
            bot_score = clamp01(float(remote.get("bot_score", 0.0)))
            return {
                "score": bot_score,
                "raw": {
                    "status": "ok",
                    "label": remote.get("label"),
                    "model_name": remote.get("model_name"),
                    "remote": remote,
                },
            }
        except Exception as exc:
            return {
                "score": 0.0,
                "raw": {
                    "status": "external_error",
                    "error": str(exc),
                },
            }
