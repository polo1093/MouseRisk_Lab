from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.config import (
    API_TITLE,
    API_VERSION,
    FE_THRESHOLD,
    BE_THRESHOLD,
    BOT_CLASS_INDEX,
    FE_MODEL_PATH,
    BE_MODEL_PATH,
    validate_config,
)
from app.model_loader import load_all_models, summarize_loaded_model
from app.predictor import predict_score_and_label
from app.schemas import (
    FePredictRequest,
    BePredictRequest,
    PredictResponse,
    HealthResponse,
)

fe_model = None
be_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global fe_model, be_model
    validate_config()
    fe_model, be_model = load_all_models()
    print("[BOOT] FE model loaded:", summarize_loaded_model(fe_model))
    print("[BOOT] BE model loaded:", summarize_loaded_model(be_model))
    yield


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        fe_loaded=fe_model is not None,
        be_loaded=be_model is not None,
        fe_model_path=str(FE_MODEL_PATH),
        be_model_path=str(BE_MODEL_PATH),
    )


@app.post("/predict/fe", response_model=PredictResponse)
def predict_fe(payload: FePredictRequest):
    if fe_model is None:
        raise HTTPException(status_code=500, detail="FE model not loaded")

    # 모델에는 feature만 넣음
    mouse_teleport_rate = (
        payload.mousemove_teleport_count / payload.mousemove_count
        if payload.mousemove_count > 0
        else 0.0
    )
    feature_dict = {
        "duration_ms": payload.duration_ms,
        "mouse_teleport_rate": mouse_teleport_rate,
        "mousemove_count": payload.mousemove_count,
    }

    bot_score, label, model_name = predict_score_and_label(
        model=fe_model,
        feature_dict=feature_dict,
        threshold=FE_THRESHOLD,
        bot_class_index=BOT_CLASS_INDEX,
    )

    return PredictResponse(
        model_type="fe",
        label=label,
        bot_score=round(bot_score, 6),
        threshold=FE_THRESHOLD,
        model_name=model_name,
        x_session_ticket=payload.x_session_ticket,
        show_schedule_id=payload.show_schedule_id,
    )


@app.post("/predict/be", response_model=PredictResponse)
def predict_be(payload: BePredictRequest):
    if be_model is None:
        raise HTTPException(status_code=500, detail="BE model not loaded")

    # 모델에는 feature만 넣음
    feature_dict = {
        "ts_payment_ready": payload.ts_payment_ready,
        "ts_whole_session": payload.ts_whole_session,
        "req_interval_cv_pre_hold": payload.req_interval_cv_pre_hold,
        "req_interval_cv_hold_gap": payload.req_interval_cv_hold_gap,
    }

    bot_score, label, model_name = predict_score_and_label(
        model=be_model,
        feature_dict=feature_dict,
        threshold=BE_THRESHOLD,
        bot_class_index=BOT_CLASS_INDEX,
    )

    return PredictResponse(
        model_type="be",
        label=label,
        bot_score=round(bot_score, 6),
        threshold=BE_THRESHOLD,
        model_name=model_name,
        x_user_id=payload.x_user_id,
        order_id=payload.order_id,
    )
