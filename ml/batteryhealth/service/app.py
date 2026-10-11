"""Local FastAPI service for work ONNX in the desktop app does not cover.

The WinUI app can run SoH/RUL fully offline via ONNX Runtime. This service adds
NASA/CALCE parsing, feature extraction, noise studies, and the same stress math.
On Linux (and any browser) it also serves a three-page demo UI that mirrors
the desktop Lifecycle / Forecast / Simulator screens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from batteryhealth.config import (
    DEFAULT_MODEL_DIR,
    DEFAULT_PROCESSED_DIR,
    EOL_CAPACITY_FRACTION,
    REPO_ROOT,
    RUL_FEATURE_COLUMNS,
    SOH_FEATURE_COLUMNS,
)
from batteryhealth.features import extract_cycle_features, feature_vector
from batteryhealth.parsers.calce import parse_calce
from batteryhealth.parsers.canonical import dict_to_summary
from batteryhealth.parsers.nasa import parse_nasa_mat
from batteryhealth.service.workspace import (
    battery_summary,
    cycle_at,
    predict_cycle,
    predict_trajectory,
)
from batteryhealth.simulate import simulate_stress

STATIC_DIR = Path(__file__).resolve().parent / "static"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

app = FastAPI(
    title="BatteryHealth ML Service",
    version="0.1.0",
    description="Local Python sidecar for parsing, features, and stress simulation.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_SESSIONS: dict[str, Any] = {}


def _metrics_path() -> Path:
    return DEFAULT_MODEL_DIR.parent / "metrics.json"


def _load_ort(name: str):
    if name in _SESSIONS:
        return _SESSIONS[name]
    import onnxruntime as ort

    path = DEFAULT_MODEL_DIR / f"{name}.onnx"
    if not path.exists():
        raise FileNotFoundError(path)
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    _SESSIONS[name] = session
    return session


def _ort_predict(name: str, x: np.ndarray) -> float:
    session = _load_ort(name)
    input_name = session.get_inputs()[0].name
    pred = session.run(None, {input_name: x.astype(np.float32)})[0]
    return float(np.asarray(pred).reshape(-1)[0])


class CyclePayload(BaseModel):
    cycle_index: int = Field(ge=1)
    time_s: list[float]
    voltage_v: list[float]
    current_a: list[float]
    temperature_c: list[float] = Field(default_factory=list)
    ambient_temp_c: float = 24.0
    soh: float | None = None


class PredictRequest(BaseModel):
    cycle: CyclePayload


class StressRequest(BaseModel):
    battery: dict[str, Any]
    ambient_temperature_c: float = 24.0
    discharge_c_rate: float = 1.0
    current_cycle: int | None = None
    eol_fraction: float = EOL_CAPACITY_FRACTION


class WorkspaceRequest(BaseModel):
    battery: dict[str, Any]
    cycle_index: int | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    models = {
        "soh": (DEFAULT_MODEL_DIR / "soh.onnx").exists(),
        "rul": (DEFAULT_MODEL_DIR / "rul.onnx").exists(),
    }
    return {"status": "ok", "models": models}


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    path = _metrics_path()
    if not path.exists():
        raise HTTPException(404, "metrics.json not found; train models first")
    return json.loads(path.read_text())


@app.post("/features")
def features(req: PredictRequest) -> dict[str, Any]:
    c = req.cycle
    feats = extract_cycle_features(
        cycle_index=c.cycle_index,
        time_s=c.time_s,
        voltage_v=c.voltage_v,
        current_a=c.current_a,
        temperature_c=c.temperature_c or [c.ambient_temp_c] * len(c.time_s),
        ambient_temp_c=c.ambient_temp_c,
        soh=c.soh,
    )
    return {"features": feats}


@app.post("/predict/soh")
def predict_soh(req: PredictRequest) -> dict[str, Any]:
    c = req.cycle
    feats = extract_cycle_features(
        cycle_index=c.cycle_index,
        time_s=c.time_s,
        voltage_v=c.voltage_v,
        current_a=c.current_a,
        temperature_c=c.temperature_c or [c.ambient_temp_c] * len(c.time_s),
        ambient_temp_c=c.ambient_temp_c,
        soh=c.soh,
    )
    x = feature_vector(feats, SOH_FEATURE_COLUMNS).reshape(1, -1)
    soh = _ort_predict("soh", x)
    return {"soh": soh, "sohPercent": soh * 100.0, "features": feats}


@app.post("/predict/rul")
def predict_rul(req: PredictRequest) -> dict[str, Any]:
    c = req.cycle
    feats = extract_cycle_features(
        cycle_index=c.cycle_index,
        time_s=c.time_s,
        voltage_v=c.voltage_v,
        current_a=c.current_a,
        temperature_c=c.temperature_c or [c.ambient_temp_c] * len(c.time_s),
        ambient_temp_c=c.ambient_temp_c,
        soh=c.soh,
    )
    if "soh" not in feats:
        x_soh = feature_vector(feats, SOH_FEATURE_COLUMNS).reshape(1, -1)
        feats["soh"] = _ort_predict("soh", x_soh)
    x = feature_vector(feats, RUL_FEATURE_COLUMNS).reshape(1, -1)
    rul = max(0.0, _ort_predict("rul", x))
    return {
        "rulCycles": rul,
        "soh": feats["soh"],
        "eolFraction": EOL_CAPACITY_FRACTION,
        "features": feats,
    }


@app.post("/simulate/stress")
def stress(req: StressRequest) -> dict[str, Any]:
    try:
        return simulate_stress(
            req.battery,
            ambient_c=req.ambient_temperature_c,
            c_rate=req.discharge_c_rate,
            current_cycle=req.current_cycle,
            eol_fraction=req.eol_fraction,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/parse/nasa")
async def parse_nasa(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "upload.mat").suffix.lower()
    if suffix != ".mat":
        raise HTTPException(400, "Upload a NASA .mat file")
    tmp = Path("/tmp") / (file.filename or "upload.mat")
    tmp.write_bytes(await file.read())
    try:
        return parse_nasa_mat(tmp)
    finally:
        tmp.unlink(missing_ok=True)


@app.post("/parse/calce")
async def parse_calce_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    name = file.filename or "upload.csv"
    tmp = Path("/tmp") / name
    tmp.write_bytes(await file.read())
    try:
        return parse_calce(tmp)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        tmp.unlink(missing_ok=True)


def _demo_catalog() -> dict[str, Path]:
    return {
        "B0005": FIXTURES_DIR / "B0005.sample.json",
        "tiny": FIXTURES_DIR / "tiny_battery.json",
        "calce": FIXTURES_DIR / "calce_sample.csv",
    }


def _load_demo(battery_id: str) -> dict[str, Any]:
    catalog = _demo_catalog()
    key = battery_id.strip()
    path = catalog.get(key) or catalog.get(key.upper())
    if path is None or not path.exists():
        processed = DEFAULT_PROCESSED_DIR / f"{key.upper()}.json"
        if processed.exists():
            return json.loads(processed.read_text())
        raise HTTPException(404, f"Unknown demo battery {battery_id!r}")
    if path.suffix.lower() in {".csv", ".xlsx", ".xls"}:
        return parse_calce(path)
    return json.loads(path.read_text())


@app.get("/")
def index() -> FileResponse:
    html = STATIC_DIR / "index.html"
    if not html.exists():
        raise HTTPException(404, "Demo UI is missing")
    return FileResponse(html)


@app.get("/demo")
def list_demos() -> dict[str, Any]:
    items = []
    for demo_id, path in _demo_catalog().items():
        if not path.exists():
            continue
        record = _load_demo(demo_id)
        items.append({"id": demo_id, "file": path.name, **dict_to_summary(record)})
    return {"demos": items}


@app.get("/demo/{battery_id}")
def demo_battery(battery_id: str) -> dict[str, Any]:
    record = _load_demo(battery_id)
    return {"summary": battery_summary(record), "battery": record}


@app.post("/workspace/forecast")
def workspace_forecast(req: WorkspaceRequest) -> dict[str, Any]:
    try:
        cycle = cycle_at(req.battery, req.cycle_index)
        return predict_cycle(_ort_predict, req.battery, cycle)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/workspace/trajectory")
def workspace_trajectory(req: WorkspaceRequest) -> dict[str, Any]:
    try:
        return {"points": predict_trajectory(_ort_predict, req.battery)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/sample/{battery_id}")
def sample_battery(battery_id: str) -> dict[str, Any]:
    path = DEFAULT_PROCESSED_DIR / f"{battery_id.upper()}.json"
    if path.exists():
        return json.loads(path.read_text())
    try:
        return _load_demo(battery_id)
    except HTTPException:
        raise HTTPException(404, f"{battery_id} not processed yet") from None


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main(argv: list[str] | None = None) -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    uvicorn.run("batteryhealth.service.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
