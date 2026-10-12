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
    uncensored_true: list[np.ndarray] = []
    uncensored_pred: list[np.ndarray] = []
    for holdout in batteries:
        train = frame[frame["battery_id"] != holdout]
        test = frame[frame["battery_id"] == holdout]
        model = fit(train[list(feature_cols)].to_numpy(dtype=np.float32), train[target].to_numpy(dtype=float))
        pred = np.asarray(predict(model, test[list(feature_cols)].to_numpy(dtype=np.float32)), dtype=float).reshape(-1)
        y = test[target].to_numpy(dtype=float)
        per[str(holdout)] = regression_metrics(y, pred)
        all_true.append(y)
        all_pred.append(pred)
        if not _battery_censored(test):
            uncensored_true.append(y)
            uncensored_pred.append(pred)
    pooled = regression_metrics(np.concatenate(all_true), np.concatenate(all_pred))
    report: dict[str, Any] = {"perBattery": per, "pooled": pooled, "batteries": batteries}
    if uncensored_true and len(uncensored_true) < len(all_true):
        report["pooledExcludingCensored"] = regression_metrics(
            np.concatenate(uncensored_true),
            np.concatenate(uncensored_pred),
        )
    return report


def _battery_censored(frame: pd.DataFrame) -> bool:
    if "eol_censored" not in frame.columns or frame.empty:
        return False
    return bool(frame["eol_censored"].iloc[0])


def censoring_report(frame: pd.DataFrame) -> dict[str, Any]:
    """Per-cell flag for right-censored 70% EOL labels.

    Censored cells never reached the capacity threshold, so a zero RUL on the last
    cycle is not an observed failure. Pooled scores that treat those labels as exact
    are reported separately from `pooledExcludingCensored`.
    """
    batteries: dict[str, Any] = {}
    for battery_id, sub in frame.groupby("battery_id", sort=True):
        censored = _battery_censored(sub)
        batteries[str(battery_id)] = {
            "censored": censored,
            "eolCycle": float(sub["eol_cycle"].iloc[0]) if "eol_cycle" in sub.columns else None,
            "n": int(len(sub)),
            "minCapacityAh": float(sub["capacity_ah"].min()) if "capacity_ah" in sub.columns else None,
        }
    censored_ids = [name for name, body in batteries.items() if body["censored"]]
    return {
        "definition": (
            "censored is true when discharge capacity never reaches eolCapacityFraction of rated capacity. "
            "Those cells are omitted from pooledExcludingCensored."
        ),
        "batteries": batteries,
        "censoredBatteries": censored_ids,
    }


def nested_soh_to_rul(
    frame: pd.DataFrame,
    *,
    soh_cols: tuple[str, ...] = SOH_FEATURE_COLUMNS,
    rul_cols: tuple[str, ...] = RUL_FEATURE_COLUMNS,
    fit: Callable[[np.ndarray, np.ndarray], Any],
    predict: Callable[[Any, np.ndarray], np.ndarray],
) -> dict[str, Any]:
    """Leave-one-battery-out RUL using predicted SoH on the held-out cell.

    RUL is still trained on measured SoH. Scoring replaces that column with the SoH
    model, which is the graph used when a log has no coulomb-counted capacity.
    """
    batteries = sorted(frame["battery_id"].unique())
    per: dict[str, Any] = {}
    all_true: list[np.ndarray] = []
    all_pred: list[np.ndarray] = []
    uncensored_true: list[np.ndarray] = []
    uncensored_pred: list[np.ndarray] = []
    for holdout in batteries:
        train = frame[frame["battery_id"] != holdout]
        test = frame[frame["battery_id"] == holdout].copy()
        soh_model = fit(
            train[list(soh_cols)].to_numpy(dtype=np.float32),
            train["soh"].to_numpy(dtype=float),
        )
        pred_soh = np.asarray(
            predict(soh_model, test[list(soh_cols)].to_numpy(dtype=np.float32)),
            dtype=float,
        ).reshape(-1)
        rul_model = fit(
            train[list(rul_cols)].to_numpy(dtype=np.float32),
            train["rul"].to_numpy(dtype=float),
        )
        scored = test.copy()
        scored["soh"] = pred_soh
        pred_rul = np.asarray(
            predict(rul_model, scored[list(rul_cols)].to_numpy(dtype=np.float32)),
            dtype=float,
        ).reshape(-1)
        y = test["rul"].to_numpy(dtype=float)
        metrics = regression_metrics(y, pred_rul)
        metrics["sohRmse"] = regression_metrics(test["soh"].to_numpy(dtype=float), pred_soh)["rmse"]
        metrics["censored"] = _battery_censored(test)
        per[str(holdout)] = metrics
        all_true.append(y)
        all_pred.append(pred_rul)
        if not metrics["censored"]:
            uncensored_true.append(y)
            uncensored_pred.append(pred_rul)
    report: dict[str, Any] = {
        "description": (
            "RUL leave-one-battery-out scored with SoH predicted from the other cells. "
            "Teacher-forced RUL metrics, which use measured SoH, stay in rul.*.leaveOneBatteryOut."
        ),
        "family": "sklearn Pipeline(StandardScaler + GradientBoostingRegressor)",
        "fitScope": "holdout-excluded",
        "perBattery": per,
        "pooled": regression_metrics(np.concatenate(all_true), np.concatenate(all_pred)),
        "batteries": [str(b) for b in batteries],
    }
    if uncensored_true:
        report["pooledExcludingCensored"] = regression_metrics(
            np.concatenate(uncensored_true),
            np.concatenate(uncensored_pred),
        )
    return report


def feature_ablations(
    frame: pd.DataFrame,
    *,
    feature_cols: tuple[str, ...],
    target: str,
    fit: Callable[[np.ndarray, np.ndarray], Any],
    predict: Callable[[Any, np.ndarray], np.ndarray],
    holdout: str | None = None,
) -> dict[str, Any]:
    """Same leave-one-battery-out split after dropping protocol-proxy columns."""
    drops = {
        "dropEnergyAndDuration": ("energy_wh", "duration_s"),
        "dropCycleIndex": ("cycle_index",),
    }
    if holdout is None:
        holdout = "B0018" if "B0018" in set(frame["battery_id"]) else str(frame["battery_id"].iloc[-1])
    report: dict[str, Any] = {
        "holdoutBattery": holdout,
        "target": target,
        "family": "sklearn Pipeline(StandardScaler + GradientBoostingRegressor)",
    }
    for name, dropped in drops.items():
        cols = tuple(col for col in feature_cols if col not in dropped)
        train = frame[frame["battery_id"] != holdout]
        test = frame[frame["battery_id"] == holdout]
        model = fit(train[list(cols)].to_numpy(dtype=np.float32), train[target].to_numpy(dtype=float))
        pred = np.asarray(predict(model, test[list(cols)].to_numpy(dtype=np.float32)), dtype=float).reshape(-1)
        lobo = leave_one_battery_out(
            frame,
            feature_cols=cols,
            target=target,
            fit=fit,
            predict=predict,
        )
        report[name] = {
            "dropped": list(dropped),
            "columns": list(cols),
            "holdout": regression_metrics(test[target].to_numpy(dtype=float), pred),
            "leaveOneBatteryOut": lobo,
        }
    return report


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
        scope = "in-sample" if level == 0.0 else "in-sample-perturbed"
        block: dict[str, Any] = {
            "sigmaFrac": level,
            "scope": scope,
            "soh": regression_metrics(soh_true, soh_pred),
            "rul": regression_metrics(rul_true, rul_pred),
        }
        if level == 0.0:
            block["note"] = (
                "Production model scored on the same cycles it was fit on. This is not a hold-out number."
            )
        results[str(level)] = block
    return results
