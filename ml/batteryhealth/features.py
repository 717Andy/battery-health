"""Per-cycle time-series feature engineering for charge/discharge sensor streams."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from batteryhealth.config import SOH_FEATURE_COLUMNS


def trapz(y, x):
    """numpy 1.x used trapz; 2.x renamed it trapezoid."""
    fn = getattr(np, "trapezoid", None) or np.trapz
    return fn(y, x)


def _as_1d(values) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    return arr[np.isfinite(arr)]


def _safe_std(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.std(x))


def _time_to_voltage(time_s: np.ndarray, voltage: np.ndarray, threshold: float) -> float:
    """First time (s) the discharge voltage crosses `threshold` from above. 0 if never."""
    if time_s.size == 0 or voltage.size == 0:
        return 0.0
    n = min(time_s.size, voltage.size)
    t = time_s[:n]
    v = voltage[:n]
    below = np.where(v <= threshold)[0]
    if below.size == 0:
        return float(t[-1])
    i = int(below[0])
    if i == 0:
        return float(t[0])
    v0, v1 = float(v[i - 1]), float(v[i])
    t0, t1 = float(t[i - 1]), float(t[i])
    if abs(v1 - v0) < 1e-12:
        return t1
    frac = (threshold - v0) / (v1 - v0)
    return float(t0 + frac * (t1 - t0))


def _linear_slope(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 2 or y.size < 2:
        return 0.0
    n = min(x.size, y.size)
    x = x[:n]
    y = y[:n]
    if np.allclose(x, x[0]):
        return 0.0
    coef = np.polyfit(x, y, 1)
    return float(coef[0])


def extract_cycle_features(
    *,
    cycle_index: int,
    time_s,
    voltage_v,
    current_a,
    temperature_c,
    ambient_temp_c: float = 24.0,
    soh: float | None = None,
) -> dict[str, float]:
    """Compute the fixed feature vector used by SoH / RUL models.

    Capacity is intentionally not a feature. `soh` is attached only for the RUL
    model (measured in the lab, or predicted SoH at inference).
    """
    t = _as_1d(time_s)
    v = _as_1d(voltage_v)
    i = _as_1d(current_a)
    temp = _as_1d(temperature_c)
    n = min(t.size, v.size, i.size if i.size else t.size, temp.size if temp.size else t.size)
    t, v = t[:n], v[:n]
    i = i[:n] if i.size else np.zeros(n)
    temp = temp[:n] if temp.size else np.full(n, ambient_temp_c)

    duration = float(t[-1] - t[0]) if n >= 2 else 0.0
    power_w = v * np.abs(i)
    if n >= 2:
        energy_wh = float(trapz(power_w, t) / 3600.0)
    else:
        energy_wh = 0.0

    features = {
        "cycle_index": float(cycle_index),
        "voltage_mean": float(np.mean(v)) if n else 0.0,
        "voltage_std": _safe_std(v),
        "voltage_min": float(np.min(v)) if n else 0.0,
        "voltage_max": float(np.max(v)) if n else 0.0,
        "voltage_start": float(v[0]) if n else 0.0,
        "voltage_end": float(v[-1]) if n else 0.0,
        "voltage_slope": _linear_slope(t, v),
        "current_mean": float(np.mean(i)) if n else 0.0,
        "current_std": _safe_std(i),
        "temp_mean": float(np.mean(temp)) if n else float(ambient_temp_c),
        "temp_std": _safe_std(temp),
        "temp_max": float(np.max(temp)) if n else float(ambient_temp_c),
        "temp_rise": float(np.max(temp) - np.min(temp)) if n else 0.0,
        "duration_s": duration,
        "energy_wh": energy_wh,
        "time_to_3v5": _time_to_voltage(t, v, 3.5),
        "time_to_3v0": _time_to_voltage(t, v, 3.0),
        "ambient_temp_c": float(ambient_temp_c),
    }
    if soh is not None:
        features["soh"] = float(soh)
    return features


def feature_vector(features: Mapping[str, float], columns: tuple[str, ...] = SOH_FEATURE_COLUMNS) -> np.ndarray:
    return np.array([float(features.get(col, 0.0)) for col in columns], dtype=np.float32)


def downsample_trace(time_s, voltage_v, current_a, temperature_c, max_points: int = 256):
    t = _as_1d(time_s)
    v = _as_1d(voltage_v)
    i = _as_1d(current_a)
    temp = _as_1d(temperature_c)
    n = min(len(t), len(v), len(i) if len(i) else len(t), len(temp) if len(temp) else len(t))
    if n == 0:
        return [], [], [], []
    t, v = t[:n], v[:n]
    i = i[:n] if len(i) else np.zeros(n)
    temp = temp[:n] if len(temp) else np.zeros(n)
    if n <= max_points:
        idx = np.arange(n)
    else:
        idx = np.linspace(0, n - 1, max_points).astype(int)
    return (
        t[idx].tolist(),
        v[idx].tolist(),
        i[idx].tolist(),
        temp[idx].tolist(),
    )


def add_sensor_noise(
    time_s,
    voltage_v,
    current_a,
    temperature_c,
    sigma_frac: float,
    rng: np.random.Generator | None = None,
):
    """Add i.i.d. Gaussian noise at `sigma_frac` × each channel's own std."""
    rng = rng or np.random.default_rng(0)
    t = _as_1d(time_s)
    v = _as_1d(voltage_v)
    i = _as_1d(current_a)
    temp = _as_1d(temperature_c)

    def _noise(x: np.ndarray) -> np.ndarray:
        if x.size == 0 or sigma_frac <= 0:
            return x
        scale = _safe_std(x) * sigma_frac
        if scale <= 0:
            scale = 1e-6
        return x + rng.normal(0.0, scale, size=x.shape)

    return t, _noise(v), _noise(i), _noise(temp)
