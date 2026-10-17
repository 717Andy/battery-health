"""Export sklearn / XGBoost models to ONNX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from batteryhealth.config import (
    APPLICABILITY,
    EOL_CAPACITY_FRACTION,
    HOLDOUT_METRICS_FIT_SCOPE,
    PRODUCTION_FAMILY,
    PRODUCTION_FIT_SCOPE,
    RUL_FEATURE_COLUMNS,
    SOH_FEATURE_COLUMNS,
    STRESS_CLAIM,
)


def _write(path: Path, model_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(model_bytes)


def export_sklearn(model, n_features: int, path: Path, input_name: str = "features") -> Path:
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    onx = convert_sklearn(
        model,
        initial_types=[(input_name, FloatTensorType([None, n_features]))],
        target_opset=15,
    )
    _write(path, onx.SerializeToString())
    return path


def export_xgboost(model, n_features: int, path: Path, input_name: str = "features") -> Path:
    from onnxmltools.convert import convert_xgboost
    from onnxmltools.convert.common.data_types import FloatTensorType

    booster = model.get_booster() if hasattr(model, "get_booster") else model
    onx = convert_xgboost(
        booster,
        initial_types=[(input_name, FloatTensorType([None, n_features]))],
        target_opset=15,
    )
    _write(path, onx.SerializeToString())
    return path


def verify_onnx(path: Path, x: np.ndarray, expected: np.ndarray, atol: float = 1e-3) -> dict[str, Any]:
    import onnxruntime as ort

    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    pred = session.run(None, {input_name: x.astype(np.float32)})[0].reshape(-1)
    expected = np.asarray(expected, dtype=float).reshape(-1)
    max_abs = float(np.max(np.abs(pred - expected)))
    return {
        "path": str(path),
        "inputName": input_name,
        "outputName": session.get_outputs()[0].name,
        "maxAbsError": max_abs,
        "ok": max_abs <= atol,
        "n": int(pred.size),
    }


def feature_spec(
    *,
    soh_input: str,
    rul_input: str,
    soh_output: str,
    rul_output: str,
    n_rows: int | None = None,
    batteries: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "soh": {
            "model": "soh.onnx",
            "inputName": soh_input,
            "outputName": soh_output,
            "columns": list(SOH_FEATURE_COLUMNS),
        },
        "rul": {
            "model": "rul.onnx",
            "inputName": rul_input,
            "outputName": rul_output,
            "columns": list(RUL_FEATURE_COLUMNS),
        },
        "eolCapacityFraction": EOL_CAPACITY_FRACTION,
        "eolCapacityFractionOem": 0.80,
        "ratedCapacityAh": 2.0,
        "notes": (
            "NASA PCoE official end-of-life is 70% of rated capacity (2.0 Ah → 1.4 Ah). "
            "The 80% threshold is the common EV warranty / replacement line."
        ),
        "modelCard": {
            "family": PRODUCTION_FAMILY,
            "fitScope": PRODUCTION_FIT_SCOPE,
            "holdoutMetricsFitScope": HOLDOUT_METRICS_FIT_SCOPE,
            "eolCapacityFraction": EOL_CAPACITY_FRACTION,
            "eolDefinition": (
                "Remaining useful life is cycles until discharge capacity falls to "
                "70% of rated capacity (NASA PCoE official stop criterion: 2.0 Ah → 1.4 Ah)."
            ),
            "nRows": n_rows,
            "batteries": batteries or [],
            "applicability": APPLICABILITY,
            "stressModel": {
                "kind": "scenario",
                "identifiedOnDataset": False,
                "claim": STRESS_CLAIM,
            },
        },
    }
