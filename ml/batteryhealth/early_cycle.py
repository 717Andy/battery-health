"""Early-cycle lifetime prediction: first K cycles → EOL cycle.

Baselines: persist (train-mean EOL), linear fade extrapolation, Ridge on
summary features, Severson-style log-variance of early capacity.

NASA 18650s reach 80% of initial capacity around cycles 60–125, so K=100 is
not an early window on that set. CALCE CS2 pouch cells last ~500–600 cycles
to the same 80%-of-initial line, so K=100 is actually early there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from batteryhealth.calce_fade import CALCE_CITATION, CALCE_RATED_AH
from batteryhealth.config import NASA_CITATION, REPO_ROOT
from batteryhealth.evaluate import regression_metrics
from batteryhealth.parsers.canonical import discharge_cycles

K_NASA = 40
K_CALCE = 100
ROLL = 11


def fade_from_record(record: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for cycle in discharge_cycles(record):
        cap = cycle.get("capacityAh")
        if cap is None:
            continue
        rows.append(
            {
                "battery_id": record.get("batteryId"),
                "source": record.get("source") or "unknown",
                "cycle": int(cycle["cycleIndex"]),
                "capacity_ah": float(cap),
                "rated_capacity_ah": float(record.get("ratedCapacityAh") or np.nan),
            }
        )
    return pd.DataFrame(rows)


def load_nasa_fade(processed_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(processed_dir.glob("B*.json")):
        if path.name.endswith(".summary.json"):
            continue
        frames.append(fade_from_record(json.loads(path.read_text())))
    if not frames:
        raise FileNotFoundError(processed_dir)
    return pd.concat(frames, ignore_index=True)


def smooth_capacity(capacity: np.ndarray, window: int = ROLL) -> np.ndarray:
    return pd.Series(capacity).rolling(window, center=True, min_periods=max(3, window // 3)).median().to_numpy()


def initial_capacity(capacity: np.ndarray) -> float:
    return float(np.median(capacity[: min(8, len(capacity))]))


def eol_cycle(
    cycles: np.ndarray,
    capacity: np.ndarray,
    *,
    fraction: float = 0.80,
    threshold_ah: float | None = None,
) -> tuple[float, bool]:
    """First smoothed crossing of `fraction` of initial capacity, or `threshold_ah`."""
    smooth = smooth_capacity(capacity)
    q0 = initial_capacity(capacity)
    thr = float(threshold_ah) if threshold_ah is not None else fraction * q0
    hit = np.where(np.isfinite(smooth) & (smooth <= thr))[0]
    if hit.size:
        return float(cycles[int(hit[0])]), False
    return float(cycles[-1]), True


def cell_table(fade: pd.DataFrame, *, fraction: float = 0.80, threshold_ah: float | None = None) -> pd.DataFrame:
    rows = []
    for battery_id, sub in fade.groupby("battery_id", sort=True):
        sub = sub.sort_values("cycle")
        cycles = sub["cycle"].to_numpy(dtype=float)
        cap = sub["capacity_ah"].to_numpy(dtype=float)
        eol, censored = eol_cycle(cycles, cap, fraction=fraction, threshold_ah=threshold_ah)
        rows.append(
            {
                "battery_id": str(battery_id),
                "source": sub["source"].iloc[0],
                "n": int(len(sub)),
                "q0": initial_capacity(cap),
                "eol_cycle": eol,
                "eol_censored": censored,
                "last_capacity_ah": float(cap[-1]),
            }
        )
    return pd.DataFrame(rows)


def early_features(cycles: np.ndarray, capacity: np.ndarray, k: int) -> dict[str, float]:
    mask = cycles <= k
    cyc = cycles[mask]
    cap = capacity[mask]
    if cap.size < 8:
        raise ValueError("not enough early cycles")
    slope = float(np.polyfit(cyc, cap, 1)[0])
    delta = np.diff(cap)
    log_var = float(np.log(np.var(cap[max(0, cap.size - k + 10) :]) + 1e-12))
    log_var_delta = float(np.log(np.var(delta) + 1e-12))
    return {
        "q0": initial_capacity(cap),
        "q_at_k": float(cap[-1]),
        "drop": float(initial_capacity(cap) - cap[-1]),
        "slope": slope,
        "mean": float(np.mean(cap)),
        "std": float(np.std(cap)),
        "log_var": log_var,
        "log_var_delta": log_var_delta,
        "k": float(k),
    }


FEATURE_COLS = ("q0", "q_at_k", "drop", "slope", "mean", "std", "log_var", "log_var_delta")


def build_xy(fade: pd.DataFrame, cells: pd.DataFrame, k: int) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    rows = []
    y = []
    ids = []
    for row in cells.itertuples():
        if row.eol_censored or row.eol_cycle <= k:
            continue
        sub = fade[fade["battery_id"] == row.battery_id].sort_values("cycle")
        feats = early_features(sub["cycle"].to_numpy(dtype=float), sub["capacity_ah"].to_numpy(dtype=float), k)
        feats["battery_id"] = row.battery_id
        rows.append(feats)
        y.append(float(row.eol_cycle))
        ids.append(str(row.battery_id))
    if not rows:
        raise ValueError(f"No cells with EOL > {k}")
    return pd.DataFrame(rows), np.asarray(y, dtype=float), ids


def _ridge() -> Pipeline:
    return Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])


def clip_eol(hat: float, k: int) -> float:
    """Cycle index cannot be before the observation window. No upper physics cap."""
    return float(max(k, hat))


def persist_predict(y_train: np.ndarray, n: int) -> np.ndarray:
    return np.full(n, float(np.mean(y_train)))


def linear_eol(cycles: np.ndarray, capacity: np.ndarray, k: int, threshold: float) -> float:
    mask = cycles <= k
    cyc = cycles[mask]
    cap = capacity[mask]
    slope, intercept = np.polyfit(cyc, cap, 1)
    if slope >= -1e-9:
        return float(cyc[-1] + 1000.0)
    pred = (threshold - intercept) / slope
    return float(max(k, pred))


def severson_logvar_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    model = LinearRegression()
    model.fit(x_train.reshape(-1, 1), y_train)
    return model.predict(x_test.reshape(-1, 1))


def leave_one_cell_out(fade: pd.DataFrame, *, k: int, fraction: float = 0.80) -> dict[str, Any]:
    cells = cell_table(fade, fraction=fraction)
    x_frame, y, ids = build_xy(fade, cells, k)
    per: dict[str, Any] = {}
    methods = ("persist", "linear", "ridge", "severson_logvar")
    preds: dict[str, list[float]] = {m: [] for m in methods}
    truths: list[float] = []
    for holdout in ids:
        train_mask = x_frame["battery_id"] != holdout
        test_mask = x_frame["battery_id"] == holdout
        x_train = x_frame.loc[train_mask, list(FEATURE_COLS)].to_numpy(dtype=float)
        y_train = y[train_mask.to_numpy()]
        x_test = x_frame.loc[test_mask, list(FEATURE_COLS)].to_numpy(dtype=float)
        y_test = float(y[test_mask.to_numpy()][0])
        sub = fade[fade["battery_id"] == holdout].sort_values("cycle")
        cycles = sub["cycle"].to_numpy(dtype=float)
        cap = sub["capacity_ah"].to_numpy(dtype=float)
        q0 = initial_capacity(cap)
        thr = fraction * q0

        persist = clip_eol(float(persist_predict(y_train, 1)[0]), k)
        lin = clip_eol(linear_eol(cycles, cap, k, thr), k)
        ridge = _ridge()
        ridge.fit(x_train, y_train)
        ridge_hat = clip_eol(float(ridge.predict(x_test)[0]), k)
        sev = clip_eol(
            float(
                severson_logvar_predict(
                    x_frame.loc[train_mask, "log_var"].to_numpy(dtype=float),
                    y_train,
                    x_frame.loc[test_mask, "log_var"].to_numpy(dtype=float),
                )[0]
            ),
            k,
        )
        per[holdout] = {
            "y": y_test,
            "persist": persist,
            "linear": lin,
            "ridge": ridge_hat,
            "severson_logvar": sev,
            "q0": q0,
        }
        for name, hat in zip(methods, (persist, lin, ridge_hat, sev)):
            preds[name].append(hat)
        truths.append(y_test)

    y_true = np.asarray(truths)
    summary = {
        name: regression_metrics(y_true, np.asarray(preds[name])) for name in methods
    }
    return {
        "k": k,
        "target": f"{int(fraction * 100)}% of initial (smoothed) capacity",
        "nCells": len(ids),
        "cells": ids,
        "perCell": per,
        "pooled": summary,
        "cellTable": cells.to_dict(orient="records"),
    }


def domain_shift(
    train_fade: pd.DataFrame,
    test_fade: pd.DataFrame,
    *,
    k: int,
    fraction: float = 0.80,
) -> dict[str, Any]:
    train_cells = cell_table(train_fade, fraction=fraction)
    test_cells = cell_table(test_fade, fraction=fraction)
    x_train, y_train, train_ids = build_xy(train_fade, train_cells, k)
    x_test, y_test, test_ids = build_xy(test_fade, test_cells, k)
    methods: dict[str, np.ndarray] = {}
    methods["persist"] = np.asarray([clip_eol(v, k) for v in persist_predict(y_train, len(y_test))])
    lin = []
    for battery_id in test_ids:
        sub = test_fade[test_fade["battery_id"] == battery_id].sort_values("cycle")
        cap = sub["capacity_ah"].to_numpy(dtype=float)
        lin.append(
            clip_eol(
                linear_eol(
                    sub["cycle"].to_numpy(dtype=float),
                    cap,
                    k,
                    fraction * initial_capacity(cap),
                ),
                k,
            )
        )
    methods["linear"] = np.asarray(lin)
    ridge = _ridge()
    ridge.fit(x_train[list(FEATURE_COLS)].to_numpy(dtype=float), y_train)
    methods["ridge"] = np.asarray(
        [clip_eol(v, k) for v in ridge.predict(x_test[list(FEATURE_COLS)].to_numpy(dtype=float))]
    )
    methods["severson_logvar"] = np.asarray(
        [
            clip_eol(v, k)
            for v in severson_logvar_predict(
                x_train["log_var"].to_numpy(dtype=float),
                y_train,
                x_test["log_var"].to_numpy(dtype=float),
            )
        ]
    )
    pooled = {name: regression_metrics(y_test, pred) for name, pred in methods.items()}
    per = {}
    for i, battery_id in enumerate(test_ids):
        per[battery_id] = {
            "y": float(y_test[i]),
            **{name: float(methods[name][i]) for name in methods},
        }
    return {
        "k": k,
        "trainCells": train_ids,
        "testCells": test_ids,
        "target": f"{int(fraction * 100)}% of initial (smoothed) capacity",
        "note": (
            "Train on NASA, test on CALCE CS2. Different chemistry (18650 vs pouch), "
            "nameplate (2.0 Ah vs 1.1 Ah), and lifetime scale. Poor transfer is expected."
        ),
        "perCell": per,
        "pooled": pooled,
    }


def run_study(
    *,
    nasa_fade: pd.DataFrame,
    calce_fade: pd.DataFrame,
) -> dict[str, Any]:
    nasa_k40 = leave_one_cell_out(nasa_fade, k=K_NASA)
    calce_k100 = leave_one_cell_out(calce_fade, k=K_CALCE)
    shift = domain_shift(nasa_fade, calce_fade, k=K_NASA)
    return {
        "citation": {
            "nasa": NASA_CITATION,
            "calce": CALCE_CITATION,
        },
        "honesty": (
            "Target is the cycle where a rolling-median capacity first drops to 80% of "
            "that cell's own initial capacity. NASA cells hit that line around 60–125 cycles, "
            f"so K={K_NASA} is used there. CALCE CS2 1C cells last ~500–600 cycles, so K={K_CALCE}. "
            "The Severson-style feature is log variance of early capacity, not ΔQ(V); "
            "we do not have interpolated voltage-capacity curves for the CALCE zip extract."
        ),
        "nasaK40": nasa_k40,
        "calceK100": calce_k100,
        "nasaToCalceK40": shift,
        "calceRatedAh": CALCE_RATED_AH,
    }


def load_or_read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "battery_id" not in frame.columns and "batteryId" in frame.columns:
        frame = frame.rename(columns={"batteryId": "battery_id"})
    return frame


def default_artifact_dir() -> Path:
    return REPO_ROOT / "artifacts" / "early_cycle"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nasa-fade", type=Path, default=default_artifact_dir() / "nasa_fade.csv")
    parser.add_argument("--calce-fade", type=Path, default=default_artifact_dir() / "calce_fade.csv")
    parser.add_argument("--out", type=Path, default=default_artifact_dir() / "metrics.json")
    args = parser.parse_args(argv)
    nasa = load_or_read_csv(args.nasa_fade)
    calce = load_or_read_csv(args.calce_fade)
    report = run_study(nasa_fade=nasa, calce_fade=calce)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(
        {
            "nasaK40": report["nasaK40"]["pooled"],
            "calceK100": report["calceK100"]["pooled"],
            "nasaToCalceK40": report["nasaToCalceK40"]["pooled"],
        },
        indent=2,
    ))
    print("Wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
