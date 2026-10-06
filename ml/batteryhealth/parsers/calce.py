"""CALCE (University of Maryland) CSV / Excel cycle-log parser.

Accepts Arbin-style exports with columns such as Cycle_Index, Current(A),
Voltage(V), Discharge_Capacity(Ah), Charge_Capacity(Ah), and optional
Temperature. Also accepts a simplified canonical CSV used in tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from batteryhealth.config import EOL_CAPACITY_FRACTION, MAX_TRACE_POINTS, RATED_CAPACITY_AH
from batteryhealth.features import downsample_trace, extract_cycle_features, trapz

_COLUMN_ALIASES = {
    "cycle_index": (
        "cycle_index",
        "cycleindex",
        "cycle",
        "cycle_number",
        "cyc",
    ),
    "voltage": ("voltage_v", "voltagev", "voltage", "volt", "v"),
    "current": ("current_a", "currenta", "current", "curr", "i"),
    "time": (
        "test_times",
        "test_time_s",
        "testtime",
        "step_times",
        "step_time_s",
        "time_s",
        "time",
        "t",
    ),
    "charge_capacity": (
        "charge_capacity_ah",
        "chargecapacityah",
        "charge_capacity",
        "q_charge",
    ),
    "discharge_capacity": (
        "discharge_capacity_ah",
        "dischargecapacityah",
        "discharge_capacity",
        "capacity_ah",
        "capacity",
        "q_discharge",
    ),
    "temperature": (
        "temperature_c",
        "temperaturec",
        "temperature_c_1",
        "temperature",
        "temp",
    ),
}


def _normalize_name(name: str) -> str:
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "")
        .replace(".", "")
        .replace("-", "_")
        .replace("[", "")
        .replace("]", "")
    )


def _resolve_columns(columns: list[str]) -> dict[str, str]:
    normalized = {_normalize_name(c): c for c in columns}
    resolved: dict[str, str] = {}
    for key, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                resolved[key] = normalized[alias]
                break
    return resolved


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def parse_calce(
    path: str | Path,
    *,
    battery_id: str | None = None,
    rated_capacity_ah: float = 1.1,
    eol_fraction: float = EOL_CAPACITY_FRACTION,
    ambient_temp_c: float = 25.0,
    max_trace_points: int = MAX_TRACE_POINTS,
) -> dict[str, Any]:
    """Parse a CALCE CSV/Excel file into the BatteryHealth canonical record.

    CS2 pouch cells are typically ~1.1 Ah; pass `rated_capacity_ah` if known.
    Discharge rows are inferred from negative current, or from a rising
    discharge-capacity column.
    """
    path = Path(path)
    frame = _read_table(path)
    if frame.empty:
        raise ValueError(f"{path} is empty")
    mapping = _resolve_columns(list(frame.columns))
    if "voltage" not in mapping or "current" not in mapping:
        raise ValueError(
            f"{path} needs Voltage and Current columns; found {list(frame.columns)}"
        )

    voltage = pd.to_numeric(frame[mapping["voltage"]], errors="coerce").to_numpy(dtype=float)
    current = pd.to_numeric(frame[mapping["current"]], errors="coerce").to_numpy(dtype=float)
    if "time" in mapping:
        time_s = pd.to_numeric(frame[mapping["time"]], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(time_s).any():
            time_s = np.arange(len(frame), dtype=float)
    else:
        time_s = np.arange(len(frame), dtype=float)

    if "temperature" in mapping:
        temperature = pd.to_numeric(frame[mapping["temperature"]], errors="coerce").to_numpy(
            dtype=float
        )
    else:
        temperature = np.full(len(frame), ambient_temp_c, dtype=float)

    if "cycle_index" in mapping:
        cycle_ids = pd.to_numeric(frame[mapping["cycle_index"]], errors="coerce").to_numpy()
    else:
        cycle_ids = np.ones(len(frame))

    discharge_cap = None
    if "discharge_capacity" in mapping:
        discharge_cap = pd.to_numeric(
            frame[mapping["discharge_capacity"]], errors="coerce"
        ).to_numpy(dtype=float)

    cycles: list[dict[str, Any]] = []
    unique_cycles = [int(c) for c in pd.unique(cycle_ids) if np.isfinite(c)]
    discharge_ordinal = 0
    for cycle_id in unique_cycles:
        mask = cycle_ids == cycle_id
        c_current = current[mask]
        c_voltage = voltage[mask]
        c_time = time_s[mask]
        c_temp = temperature[mask]
        # Discharge: negative current (Arbin sign) or falling voltage with |I| > 0.
        discharge_mask = c_current < -0.02
        if discharge_mask.sum() < 5:
            discharge_mask = (np.abs(c_current) > 0.02) & (c_voltage < 4.15)
        if discharge_mask.sum() < 5:
            continue
        d_t = c_time[discharge_mask]
        d_v = c_voltage[discharge_mask]
        d_i = c_current[discharge_mask]
        d_temp = c_temp[discharge_mask]
        if d_t.size >= 2 and d_t[-1] < d_t[0]:
            order = np.argsort(d_t)
            d_t, d_v, d_i, d_temp = d_t[order], d_v[order], d_i[order], d_temp[order]
        # Rebase time to the start of this discharge.
        d_t = d_t - d_t[0]

        capacity_ah = None
        if discharge_cap is not None:
            seg = discharge_cap[mask][discharge_mask]
            seg = seg[np.isfinite(seg)]
            if seg.size:
                capacity_ah = float(np.nanmax(seg))
        if capacity_ah is None or capacity_ah <= 0:
            capacity_ah = float(trapz(np.abs(d_i), d_t) / 3600.0)

        discharge_ordinal += 1
        soh = capacity_ah / rated_capacity_ah if rated_capacity_ah else None
        features = extract_cycle_features(
            cycle_index=discharge_ordinal,
            time_s=d_t,
            voltage_v=d_v,
            current_a=d_i,
            temperature_c=d_temp,
            ambient_temp_c=ambient_temp_c,
            soh=soh,
        )
        t, v, i, temp = downsample_trace(d_t, d_v, d_i, d_temp, max_points=max_trace_points)
        cycles.append(
            {
                "cycleIndex": discharge_ordinal,
                "type": "discharge",
                "ambientTemperatureC": ambient_temp_c,
                "capacityAh": capacity_ah,
                "timeS": t,
                "voltageV": v,
                "currentA": i,
                "temperatureC": temp,
                "features": features,
            }
        )

    if not cycles:
        raise ValueError(f"No discharge cycles found in {path}")

    return {
        "batteryId": battery_id or path.stem,
        "source": "calce",
        "ratedCapacityAh": rated_capacity_ah or RATED_CAPACITY_AH,
        "eolCapacityFraction": eol_fraction,
        "chemistry": "Li-ion (CALCE)",
        "ambientTemperatureC": ambient_temp_c,
        "cycles": cycles,
        "sourceFile": path.name,
    }
