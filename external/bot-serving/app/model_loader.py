from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple

import joblib
from sklearn.pipeline import Pipeline

from app.config import (
    FE_MODEL_PATH,
    BE_MODEL_PATH,
    FE_FEATURE_COLUMNS,
    BE_FEATURE_COLUMNS,
)


def _assert_file_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Model path is not a file: {path}")


def _load_pickle(path: Path) -> Any:
    return joblib.load(path)


def _assert_pipeline(model: Any, model_name: str) -> None:
    if not isinstance(model, Pipeline):
        raise TypeError(
            f"{model_name} is not a sklearn Pipeline. "
            "Serving code expects a Pipeline including preprocessing."
        )

    if "preprocessor" not in model.named_steps:
        raise ValueError(f"{model_name} pipeline does not contain 'preprocessor' step.")

    if "model" not in model.named_steps:
        raise ValueError(f"{model_name} pipeline does not contain 'model' step.")


def _extract_expected_columns_from_pipeline(model: Pipeline) -> list[str]:
    preprocessor = model.named_steps["preprocessor"]

    if not hasattr(preprocessor, "transformers"):
        raise ValueError("Preprocessor does not have 'transformers' attribute.")

    columns: list[str] = []
    for _name, _transformer, cols in preprocessor.transformers:
        if cols is None:
            continue
        if isinstance(cols, (list, tuple)):
            columns.extend(list(cols))

    return columns


def _assert_expected_columns(
    model: Pipeline,
    expected_columns: list[str],
    model_name: str,
) -> None:
    actual_columns = _extract_expected_columns_from_pipeline(model)
    if actual_columns != expected_columns:
        raise ValueError(
            f"{model_name} feature columns mismatch.\n"
            f"Expected: {expected_columns}\n"
            f"Actual: {actual_columns}"
        )


def _assert_predict_proba_supported(model: Pipeline, model_name: str) -> None:
    if not hasattr(model, "predict_proba"):
        raise ValueError(
            f"{model_name} does not support predict_proba(). "
            "Current serving design requires probability output."
        )


def _validate_model(path: Path, expected_columns: list[str], model_name: str) -> Pipeline:
    _assert_file_exists(path)
    loaded = _load_pickle(path)
    _assert_pipeline(loaded, model_name)
    _assert_expected_columns(loaded, expected_columns, model_name)
    _assert_predict_proba_supported(loaded, model_name)
    return loaded


def load_fe_model() -> Pipeline:
    return _validate_model(
        path=FE_MODEL_PATH,
        expected_columns=FE_FEATURE_COLUMNS,
        model_name="FE model",
    )


def load_be_model() -> Pipeline:
    return _validate_model(
        path=BE_MODEL_PATH,
        expected_columns=BE_FEATURE_COLUMNS,
        model_name="BE model",
    )


def load_all_models() -> Tuple[Pipeline, Pipeline]:
    fe_model = load_fe_model()
    be_model = load_be_model()
    return fe_model, be_model


def summarize_loaded_model(model: Pipeline) -> dict:
    estimator = model.named_steps["model"]
    columns = _extract_expected_columns_from_pipeline(model)
    return {
        "pipeline_type": model.__class__.__name__,
        "estimator_type": estimator.__class__.__name__,
        "feature_count": len(columns),
        "feature_columns": columns,
        "has_predict_proba": hasattr(model, "predict_proba"),
    }