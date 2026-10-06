import json
from pathlib import Path

import numpy as np

from batteryhealth.config import DEFAULT_MODEL_DIR, SOH_FEATURE_COLUMNS
from batteryhealth.export_onnx import verify_onnx


def test_exported_onnx_exists_and_runs():
    soh = DEFAULT_MODEL_DIR / "soh.onnx"
    spec = DEFAULT_MODEL_DIR / "feature_spec.json"
    if not soh.exists():
        return
    spec_data = json.loads(spec.read_text())
    assert spec_data["soh"]["columns"] == list(SOH_FEATURE_COLUMNS)
    x = np.zeros((2, len(SOH_FEATURE_COLUMNS)), dtype=np.float32)
    x[0, 0] = 10
    x[1, 0] = 50
    check = verify_onnx(soh, x, np.array([0.0, 0.0]), atol=1e9)
    assert check["ok"]
    assert check["n"] == 2
