"""Shipped ONNX must match the committed golden vector, not a vacuous tolerance."""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

from batteryhealth.config import DEFAULT_MODEL_DIR, RUL_FEATURE_COLUMNS, SOH_FEATURE_COLUMNS
from batteryhealth.features import extract_cycle_features, feature_vector

ROOT = Path(__file__).resolve().parents[2]
CYCLE_PATH = ROOT / "tests" / "fixtures" / "golden_cycle.json"
EXPECTED_PATH = ROOT / "tests" / "fixtures" / "golden_expected.json"


def _run(model_name: str, columns: tuple[str, ...], features: dict) -> float:
    session = ort.InferenceSession(
        str(DEFAULT_MODEL_DIR / f"{model_name}.onnx"),
        providers=["CPUExecutionProvider"],
    )
    x = feature_vector(features, columns).reshape(1, -1)
    input_name = session.get_inputs()[0].name
    pred = session.run(None, {input_name: x.astype(np.float32)})[0]
    return float(np.asarray(pred).reshape(-1)[0])


def test_golden_features_and_onnx_match_committed_vector():
    cycle = json.loads(CYCLE_PATH.read_text())
    expected = json.loads(EXPECTED_PATH.read_text())
    feats = extract_cycle_features(
        cycle_index=cycle["cycleIndex"],
        time_s=cycle["timeS"],
        voltage_v=cycle["voltageV"],
        current_a=cycle["currentA"],
        temperature_c=cycle["temperatureC"],
        ambient_temp_c=cycle["ambientTemperatureC"],
        soh=cycle["soh"],
    )
    atol_features = float(expected["atolFeatures"])
    atol_onnx = float(expected["atolOnnx"])
    assert expected["sohColumns"] == list(SOH_FEATURE_COLUMNS)
    assert expected["rulColumns"] == list(RUL_FEATURE_COLUMNS)
    for column in RUL_FEATURE_COLUMNS:
        assert abs(float(feats[column]) - float(expected["features"][column])) <= atol_features, column
    assert abs(_run("soh", SOH_FEATURE_COLUMNS, feats) - float(expected["sohOnnx"])) <= atol_onnx
    assert abs(_run("rul", RUL_FEATURE_COLUMNS, feats) - float(expected["rulOnnx"])) <= atol_onnx
