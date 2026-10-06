"""Metrics, leave-one-battery-out evaluation, and sensor-noise robustness."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from batteryhealth.config import RUL_FEATURE_COLUMNS, SOH_FEATURE_COLUMNS
from batteryhealth.dataset import records_to_frame
from batteryhealth.features import add_sensor_noise, extract_cycle_features, feature_vector
from batteryhealth.parsers.canonical import discharge_cycles


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred)) if y_true.size > 1 else float("nan")
    return {"rmse": rmse, "mae": mae, "r2": r2, "n": int(y_true.size)}


def leave_one_battery_out(
    frame: pd.DataFrame,
    *,
    feature_cols: tuple[str, ...],
    target: str,
    fit: Callable[[np.ndarray, np.ndarray], Any],
    predict: Callable[[Any, np.ndarray], np.ndarray],
) -> dict[str, Any]:
    batteries = sorted(frame["battery_id"].unique())
    per: dict[str, dict[str, float]] = {}
    all_true: list[np.ndarray] = []
    all_pred: list[np.ndarray] = []
    for holdout in batteries:
        train = frame[frame["battery_id"] != holdout]
        test = frame[frame["battery_id"] == holdout]
        model = fit(train[list(feature_cols)].to_numpy(dtype=np.float32), train[target].to_numpy(dtype=float))
        pred = np.asarray(predict(model, test[list(feature_cols)].to_numpy(dtype=np.float32)), dtype=float).reshape(-1)
        y = test[target].to_numpy(dtype=float)
        per[str(holdout)] = regression_metrics(y, pred)
        all_true.append(y)
        all_pred.append(pred)
    pooled = regression_metrics(np.concatenate(all_true), np.concatenate(all_pred))
    return {"perBattery": per, "pooled": pooled, "batteries": batteries}


def noise_robustness(
    records: list[dict[str, Any]],
    *,
    soh_predict: Callable[[np.ndarray], np.ndarray],
    rul_predict: Callable[[np.ndarray], np.ndarray],
    levels: tuple[float, ...] = (0.0, 0.01, 0.02, 0.05),
    seed: int = 0,
) -> dict[str, Any]:
    """Re-extract features after adding Gaussian sensor noise; report SoH/RUL RMSE."""
    frame = records_to_frame(records)
    results: dict[str, Any] = {}
    rng = np.random.default_rng(seed)
    for level in levels:
        soh_true: list[float] = []
        soh_pred: list[float] = []
        rul_true: list[float] = []
        rul_pred: list[float] = []
        for record in records:
            rated = float(record["ratedCapacityAh"])
            discharges = [c for c in discharge_cycles(record) if c.get("capacityAh")]
            sub = frame[frame["battery_id"] == record["batteryId"]]
            rul_by_cycle = {int(row["cycle_index"]): float(row["rul"]) for _, row in sub.iterrows()}
            for cycle in discharges:
                t, v, i, temp = add_sensor_noise(
                    cycle["timeS"],
                    cycle["voltageV"],
                    cycle["currentA"],
                    cycle["temperatureC"],
                    sigma_frac=level,
                    rng=rng,
                )
                soh = float(cycle["capacityAh"]) / rated
                feats = extract_cycle_features(
                    cycle_index=int(cycle["cycleIndex"]),
                    time_s=t,
                    voltage_v=v,
                    current_a=i,
                    temperature_c=temp,
                    ambient_temp_c=float(cycle.get("ambientTemperatureC") or 24.0),
                    soh=soh,
                )
                x_soh = feature_vector(feats, SOH_FEATURE_COLUMNS).reshape(1, -1)
                pred_soh = float(np.asarray(soh_predict(x_soh)).reshape(-1)[0])
                feats_rul = dict(feats)
                feats_rul["soh"] = pred_soh
                x_rul = feature_vector(feats_rul, RUL_FEATURE_COLUMNS).reshape(1, -1)
                pred_rul = float(np.asarray(rul_predict(x_rul)).reshape(-1)[0])
                soh_true.append(soh)
                soh_pred.append(pred_soh)
                rul_true.append(rul_by_cycle.get(int(cycle["cycleIndex"]), 0.0))
                rul_pred.append(pred_rul)
        results[str(level)] = {
            "sigmaFrac": level,
            "soh": regression_metrics(soh_true, soh_pred),
            "rul": regression_metrics(rul_true, rul_pred),
        }
    return results
