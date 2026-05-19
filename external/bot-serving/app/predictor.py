from __future__ import annotations

import pandas as pd


def predict_score_and_label(model, feature_dict: dict, threshold: float, bot_class_index: int = 1):
    x = pd.DataFrame([feature_dict])

    if not hasattr(model, "predict_proba"):
        raise RuntimeError("Loaded model does not support predict_proba().")

    proba = model.predict_proba(x)[0]
    bot_score = float(proba[bot_class_index])
    label = "bot" if bot_score >= threshold else "human"

    model_name = None
    if hasattr(model, "named_steps") and "model" in model.named_steps:
        model_name = model.named_steps["model"].__class__.__name__

    return bot_score, label, model_name