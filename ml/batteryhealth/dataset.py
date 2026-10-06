"""Build tabular SoH / RUL datasets from parsed battery records."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from batteryhealth.config import EOL_CAPACITY_FRACTION, RATED_CAPACITY_AH, RUL_FEATURE_COLUMNS
from batteryhealth.parsers.canonical import discharge_cycles


def eol_cycle_index(
    capacities: list[float],
    *,
    rated_capacity_ah: float = RATED_CAPACITY_AH,
    eol_fraction: float = EOL_CAPACITY_FRACTION,
) -> int:
    """1-based discharge index of first cycle at or below the EOL threshold.

    If the cell never reaches the threshold, returns the last cycle (right-censored).
    """
    threshold = rated_capacity_ah * eol_fraction
    for i, cap in enumerate(capacities, start=1):
        if cap <= threshold:
            return i
    return max(len(capacities), 1)


def records_to_frame(
    records: Iterable[dict[str, Any]],
    *,
    eol_fraction: float | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        rated = float(record.get("ratedCapacityAh") or RATED_CAPACITY_AH)
        frac = float(eol_fraction if eol_fraction is not None else record.get("eolCapacityFraction") or EOL_CAPACITY_FRACTION)
        discharges = discharge_cycles(record)
        capacities = [float(c["capacityAh"]) for c in discharges if c.get("capacityAh")]
        if not capacities:
            continue
        eol = eol_cycle_index(capacities, rated_capacity_ah=rated, eol_fraction=frac)
        for cycle in discharges:
            feats = cycle.get("features") or {}
            cap = cycle.get("capacityAh")
            if cap is None:
                continue
            soh = float(cap) / rated
            row = {col: float(feats.get(col, 0.0)) for col in RUL_FEATURE_COLUMNS if col != "soh"}
            row["soh"] = soh
            row["capacity_ah"] = float(cap)
            row["rul"] = float(max(0, eol - int(cycle["cycleIndex"])))
            row["battery_id"] = record.get("batteryId")
            row["eol_cycle"] = float(eol)
            row["eol_fraction"] = frac
            row["rated_capacity_ah"] = rated
            rows.append(row)
    if not rows:
        raise ValueError("No discharge cycles with capacity found")
    return pd.DataFrame(rows)


def split_leave_one_battery_out(frame: pd.DataFrame, holdout: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame[frame["battery_id"] != holdout].copy()
    test = frame[frame["battery_id"] == holdout].copy()
    if train.empty or test.empty:
        raise ValueError(f"Hold-out '{holdout}' does not produce a valid split")
    return train, test


def matrix(frame: pd.DataFrame, columns: tuple[str, ...]) -> np.ndarray:
    return frame.loc[:, list(columns)].to_numpy(dtype=np.float32)
