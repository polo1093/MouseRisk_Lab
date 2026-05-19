from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"

FE_MODEL_PATH = Path(os.getenv("FE_MODEL_PATH", MODEL_DIR / "fe_model.pkl"))
BE_MODEL_PATH = Path(os.getenv("BE_MODEL_PATH", MODEL_DIR / "be_model.pkl"))

API_TITLE = os.getenv("API_TITLE", "Bot Detection Inference API")
API_VERSION = os.getenv("API_VERSION", "1.0.0")

FE_THRESHOLD = float(os.getenv("FE_THRESHOLD", "0.5"))
BE_THRESHOLD = float(os.getenv("BE_THRESHOLD", "0.5"))
BOT_CLASS_INDEX = int(os.getenv("BOT_CLASS_INDEX", "1"))

# FE 최신 feature 컬럼
FE_FEATURE_COLUMNS = [
    "duration_ms",
    "mouse_teleport_rate",
    "mousemove_count",
]

# BE 최신 feature 컬럼
BE_FEATURE_COLUMNS = [
    "ts_payment_ready",
    "ts_whole_session",
    "req_interval_cv_pre_hold",
    "req_interval_cv_hold_gap",
]


def validate_config() -> None:
    if not (0.0 <= FE_THRESHOLD <= 1.0):
        raise ValueError(f"FE_THRESHOLD must be between 0 and 1. Got: {FE_THRESHOLD}")

    if not (0.0 <= BE_THRESHOLD <= 1.0):
        raise ValueError(f"BE_THRESHOLD must be between 0 and 1. Got: {BE_THRESHOLD}")

    if BOT_CLASS_INDEX < 0:
        raise ValueError(f"BOT_CLASS_INDEX must be >= 0. Got: {BOT_CLASS_INDEX}")
