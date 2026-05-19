from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class FePredictRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    # 운영용 최소 식별자
    x_session_ticket: str = Field(
        ...,
        alias="X-Session-Ticket",
        description="Ticketing session token from ticketing service",
    )
    show_schedule_id: int = Field(
        ...,
        alias="showScheduleId",
        description="showScheduleId from ticketing service",
    )

    # 모델 feature
    duration_ms: float = Field(..., ge=0, description="Stage/session duration in ms")
    mousemove_teleport_count: float = Field(..., ge=0, description="Mousemove teleport count")
    mousemove_count: float = Field(..., ge=0, description="Mousemove count")

    @field_validator("x_session_ticket")
    @classmethod
    def validate_non_empty_str(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class BePredictRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    # 운영용 최소 식별자
    x_user_id: str = Field(
        ...,
        alias="X-User-Id",
        description="User id used for accumulation/penalty",
    )
    order_id: str = Field(
        ...,
        alias="orderId",
        description="Payment order id for current case",
    )

    # 모델 feature
    ts_payment_ready: float = Field(..., ge=0, description="Payment-ready to terminal time")
    ts_whole_session: float = Field(..., ge=0, description="Whole session time from login to confirm")
    req_interval_cv_pre_hold: float = Field(..., ge=0, description="Request interval CV before first hold")
    req_interval_cv_hold_gap: float = Field(..., ge=0, description="Absolute CV gap between post-hold and pre-hold")

    @field_validator("x_user_id", "order_id")
    @classmethod
    def validate_non_empty_str(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class PredictResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    model_type: Literal["fe", "be"]
    label: Literal["human", "bot"]
    bot_score: float = Field(..., ge=0.0, le=1.0)
    threshold: float = Field(..., ge=0.0, le=1.0)
    model_name: Optional[str] = None

    # 운영용 식별자 그대로 반환
    x_session_ticket: Optional[str] = Field(default=None, alias="X-Session-Ticket")
    show_schedule_id: Optional[int] = Field(default=None, alias="showScheduleId")
    x_user_id: Optional[str] = Field(default=None, alias="X-User-Id")
    order_id: Optional[str] = Field(default=None, alias="orderId")


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    fe_loaded: bool
    be_loaded: bool
    fe_model_path: str
    be_model_path: str