"""NASA Ames PCoE Li-ion aging `.mat` parser (B0005 / B0006 / B0007 / B0018, …)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

from batteryhealth.config import (
    EOL_CAPACITY_FRACTION,
    MAX_TRACE_POINTS,
    RATED_CAPACITY_AH,
)
from batteryhealth.features import downsample_trace, extract_cycle_features


def _field(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _array(value) -> np.ndarray:
    if value is None:
        return np.array([], dtype=float)
    arr = np.asarray(value, dtype=float).reshape(-1)
    return arr


def parse_nasa_mat(
    path: str | Path,
    *,
    rated_capacity_ah: float = RATED_CAPACITY_AH,
    eol_fraction: float = EOL_CAPACITY_FRACTION,
    max_trace_points: int = MAX_TRACE_POINTS,
) -> dict[str, Any]:
    path = Path(path)
    raw = loadmat(str(path), struct_as_record=False, squeeze_me=True)
    keys = [k for k in raw if not k.startswith("__")]
    if not keys:
        raise ValueError(f"No battery struct in {path}")
    battery_id = keys[0]
    battery = raw[battery_id]
    cycles_raw = _field(battery, "cycle")
    if cycles_raw is None:
        raise ValueError(f"{path} has no cycle field")
    if not isinstance(cycles_raw, (list, np.ndarray, tuple)):
        cycles_raw = [cycles_raw]

    cycles: list[dict[str, Any]] = []
    discharge_index = 0
    last_ambient = 24.0
    for raw_cycle in cycles_raw:
        ctype = str(_field(raw_cycle, "type", "")).lower().strip()
        if ctype not in {"charge", "discharge"}:
            continue
        ambient = float(_field(raw_cycle, "ambient_temperature", last_ambient) or last_ambient)
        last_ambient = ambient
        data = _field(raw_cycle, "data")
        voltage = _array(_field(data, "Voltage_measured"))
        current = _array(_field(data, "Current_measured"))
        temperature = _array(_field(data, "Temperature_measured"))
        time_s = _array(_field(data, "Time"))
        if voltage.size == 0 or time_s.size == 0:
            continue

        capacity = _field(data, "Capacity")
        capacity_ah = None
        if capacity is not None:
            cap_arr = np.asarray(capacity, dtype=float).reshape(-1)
            if cap_arr.size and np.isfinite(cap_arr[0]) and cap_arr[0] > 0:
                capacity_ah = float(cap_arr[0])

        if ctype == "discharge":
            discharge_index += 1
            cycle_index = discharge_index
            soh = (capacity_ah / rated_capacity_ah) if capacity_ah else None
            features = extract_cycle_features(
                cycle_index=cycle_index,
                time_s=time_s,
                voltage_v=voltage,
                current_a=current,
                temperature_c=temperature,
                ambient_temp_c=ambient,
                soh=soh,
            )
        else:
            cycle_index = max(discharge_index, 1)
            features = None

        t, v, i, temp = downsample_trace(
            time_s, voltage, current, temperature, max_points=max_trace_points
        )
        cycles.append(
            {
                "cycleIndex": cycle_index,
                "type": ctype,
                "ambientTemperatureC": ambient,
                "capacityAh": capacity_ah,
                "timeS": t,
                "voltageV": v,
                "currentA": i,
                "temperatureC": temp,
                "features": features,
            }
        )

    return {
        "batteryId": battery_id,
        "source": "nasa",
        "ratedCapacityAh": rated_capacity_ah,
        "eolCapacityFraction": eol_fraction,
        "chemistry": "Li-ion 18650",
        "ambientTemperatureC": last_ambient,
        "cycles": cycles,
        "sourceFile": path.name,
    }
