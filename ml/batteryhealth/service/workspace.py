"""Workspace helpers for the browser demo — same SoH/RUL/stress math as the WinUI app."""

from __future__ import annotations

from typing import Any

from batteryhealth.config import (
    EOL_CAPACITY_FRACTION,
    EOL_CAPACITY_FRACTION_OEM,
    RUL_FEATURE_COLUMNS,
    SOH_FEATURE_COLUMNS,
)
from batteryhealth.features import extract_cycle_features, feature_vector
from batteryhealth.parsers.canonical import discharge_cycles


def has_trace(cycle: dict[str, Any]) -> bool:
    time_s = cycle.get("timeS") or cycle.get("time_s") or []
    voltage = cycle.get("voltageV") or cycle.get("voltage_v") or []
    return len(time_s) > 1 and len(voltage) > 1


def cycle_at(battery: dict[str, Any], cycle_index: int | None) -> dict[str, Any]:
    discharges = discharge_cycles(battery)
    if not discharges:
        raise ValueError("No discharge cycles")
    if cycle_index is None:
        traced = [c for c in discharges if has_trace(c)]
        return traced[-1] if traced else discharges[-1]
    matches = [c for c in discharges if int(c["cycleIndex"]) <= int(cycle_index)]
    return matches[-1] if matches else discharges[0]


def observed_soh(cycle: dict[str, Any], rated: float) -> float | None:
    cap = cycle.get("capacityAh")
    if cap is None or rated <= 0:
        return None
    return float(cap) / float(rated)


def features_for_cycle(cycle: dict[str, Any], rated: float) -> tuple[dict[str, float], float | None]:
    observed = observed_soh(cycle, rated)
    ambient = float(cycle.get("ambientTemperatureC") or cycle.get("ambient_temp_c") or 24.0)
    if has_trace(cycle):
        feats = extract_cycle_features(
            cycle_index=int(cycle["cycleIndex"]),
            time_s=cycle.get("timeS") or cycle.get("time_s") or [],
            voltage_v=cycle.get("voltageV") or cycle.get("voltage_v") or [],
            current_a=cycle.get("currentA") or cycle.get("current_a") or [],
            temperature_c=cycle.get("temperatureC") or cycle.get("temperature_c") or [],
            ambient_temp_c=ambient,
            soh=observed,
        )
        return feats, observed
    feats = cycle.get("features")
    if feats:
        feats = {str(k): float(v) for k, v in dict(feats).items() if v is not None}
        if observed is not None:
            feats["soh"] = observed
        return feats, observed
    raise ValueError(f"Cycle {cycle.get('cycleIndex')} has neither a sensor trace nor precomputed features.")


def estimate_rul_from_fade(
    battery: dict[str, Any],
    fraction: float,
    current_cycle: int,
) -> float:
    """Linear fade-curve RUL to `fraction` of rated capacity (OEM 80% line)."""
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    threshold = rated * fraction
    points = [
        (int(c["cycleIndex"]), float(c["capacityAh"]))
        for c in discharge_cycles(battery)
        if c.get("capacityAh") is not None
    ]
    for idx, cap in points:
        if idx >= current_cycle and cap <= threshold:
            return float(max(0, idx - current_cycle))
    if len(points) < 2:
        return 0.0
    later = [p for p in points if p[0] >= current_cycle]
    if len(later) < 2:
        later = points
    first, last = later[0], later[-1]
    dn = last[0] - first[0]
    dc = first[1] - last[1]
    if dn <= 0 or dc <= 1e-9:
        return 0.0
    extra = max(0.0, (last[1] - threshold) / (dc / dn))
    return float(max(0.0, last[0] + extra - current_cycle))


def predict_cycle(ort_predict, battery: dict[str, Any], cycle: dict[str, Any]) -> dict[str, Any]:
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    eol_frac = float(battery.get("eolCapacityFraction") or EOL_CAPACITY_FRACTION)
    feats, observed = features_for_cycle(cycle, rated)
    soh = float(ort_predict("soh", feature_vector(feats, SOH_FEATURE_COLUMNS).reshape(1, -1)))
    soh = max(0.0, min(1.5, soh))
    feats = dict(feats)
    feats["soh"] = observed if observed is not None else soh
    rul = max(0.0, float(ort_predict("rul", feature_vector(feats, RUL_FEATURE_COLUMNS).reshape(1, -1))))
    cycle_index = int(cycle["cycleIndex"])
    return {
        "batteryId": battery.get("batteryId"),
        "cycleIndex": cycle_index,
        "predictedSoh": soh,
        "predictedSohPercent": soh * 100.0,
        "observedSoh": observed,
        "predictedRulCycles": rul,
        "oemRulCycles": estimate_rul_from_fade(battery, EOL_CAPACITY_FRACTION_OEM, cycle_index),
        "eolCapacityFraction": eol_frac,
        "eolCapacityAh": rated * eol_frac,
        "features": feats,
    }


def predict_trajectory(ort_predict, battery: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    for cycle in discharge_cycles(battery):
        try:
            feats, observed = features_for_cycle(cycle, rated)
        except ValueError:
            continue
        soh = float(ort_predict("soh", feature_vector(feats, SOH_FEATURE_COLUMNS).reshape(1, -1)))
        soh = max(0.0, min(1.5, soh))
        points.append(
            {
                "cycleIndex": int(cycle["cycleIndex"]),
                "predictedSoh": soh,
                "observedSoh": observed,
            }
        )
    return points


def battery_summary(battery: dict[str, Any]) -> dict[str, Any]:
    discharges = discharge_cycles(battery)
    caps = [float(c["capacityAh"]) for c in discharges if c.get("capacityAh") is not None]
    traced = [int(c["cycleIndex"]) for c in discharges if has_trace(c)]
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    eol = float(battery.get("eolCapacityFraction") or EOL_CAPACITY_FRACTION)
    return {
        "batteryId": battery.get("batteryId"),
        "source": battery.get("source"),
        "chemistry": battery.get("chemistry"),
        "notes": battery.get("notes"),
        "nCycles": len(discharges),
        "ratedCapacityAh": rated,
        "eolCapacityFraction": eol,
        "eolCapacityAh": rated * eol,
        "firstCapacityAh": caps[0] if caps else None,
        "lastCapacityAh": caps[-1] if caps else None,
        "cycleMin": int(discharges[0]["cycleIndex"]) if discharges else 1,
        "cycleMax": int(discharges[-1]["cycleIndex"]) if discharges else 1,
        "tracedCycles": traced,
        "defaultCycle": traced[-1] if traced else (int(discharges[-1]["cycleIndex"]) if discharges else 1),
    }
