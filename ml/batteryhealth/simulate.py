"""Thermal and C-rate degradation stress model (mirrored in BatteryHealth.Core)."""

from __future__ import annotations

import math
from typing import Any

from batteryhealth.config import (
    ARRHENIUS_EA_EV,
    BOLTZMANN_EV_PER_K,
    C_RATE_EXPONENT,
    EOL_CAPACITY_FRACTION,
    RATED_CAPACITY_AH,
    REF_C_RATE,
    REF_TEMPERATURE_C,
    STRESS_CLAIM,
)
from batteryhealth.parsers.canonical import discharge_cycles


def kelvin(temp_c: float) -> float:
    return float(temp_c) + 273.15


def temperature_acceleration(
    ambient_c: float,
    *,
    ref_c: float = REF_TEMPERATURE_C,
    ea_ev: float = ARRHENIUS_EA_EV,
) -> float:
    """Arrhenius acceleration vs the NASA 24 °C reference: exp(Ea/k · (1/Tref − 1/T))."""
    t = kelvin(ambient_c)
    t_ref = kelvin(ref_c)
    if t <= 0 or t_ref <= 0:
        return 1.0
    return math.exp(ea_ev / BOLTZMANN_EV_PER_K * (1.0 / t_ref - 1.0 / t))


def crate_acceleration(
    c_rate: float,
    *,
    ref_c_rate: float = REF_C_RATE,
    exponent: float = C_RATE_EXPONENT,
) -> float:
    """Power-law load acceleration (Wöhler-style): (C / Cref)^β."""
    c_rate = max(float(c_rate), 1e-3)
    ref_c_rate = max(float(ref_c_rate), 1e-3)
    return (c_rate / ref_c_rate) ** exponent


def combined_acceleration(ambient_c: float, c_rate: float) -> float:
    return temperature_acceleration(ambient_c) * crate_acceleration(c_rate)


def simulate_stress(
    record: dict[str, Any],
    *,
    ambient_c: float,
    c_rate: float,
    current_cycle: int | None = None,
    eol_fraction: float | None = None,
) -> dict[str, Any]:
    """Rescale remaining fade by the combined acceleration factor.

    Capacity already lost is kept; future fade is multiplied by AF so the
    dashboard can overlay baseline vs stressed fade and a new RUL.
    """
    rated = float(record.get("ratedCapacityAh") or RATED_CAPACITY_AH)
    frac = float(eol_fraction if eol_fraction is not None else record.get("eolCapacityFraction") or EOL_CAPACITY_FRACTION)
    threshold = rated * frac
    discharges = [c for c in discharge_cycles(record) if c.get("capacityAh")]
    if not discharges:
        raise ValueError("Battery record has no discharge capacities")

    cycles = [int(c["cycleIndex"]) for c in discharges]
    capacities = [float(c["capacityAh"]) for c in discharges]
    af = combined_acceleration(ambient_c, c_rate)

    if current_cycle is None:
        current_cycle = cycles[0]
    # Snap to the nearest available discharge at or before current_cycle.
    cursor = 0
    for i, idx in enumerate(cycles):
        if idx <= current_cycle:
            cursor = i
    c0 = capacities[cursor]
    n0 = cycles[cursor]

    baseline = [{"cycleIndex": n, "capacityAh": c, "soh": c / rated} for n, c in zip(cycles, capacities)]
    stressed: list[dict[str, float]] = []
    for n, c in zip(cycles, capacities):
        if n <= n0:
            stressed_c = c
        else:
            lost = c0 - c
            stressed_c = max(0.0, c0 - af * lost)
        stressed.append({"cycleIndex": n, "capacityAh": stressed_c, "soh": stressed_c / rated})

    def _eol(points: list[dict[str, float]]) -> int | None:
        for p in points:
            if p["cycleIndex"] >= n0 and p["capacityAh"] <= threshold:
                return int(p["cycleIndex"])
        return None

    # If the discrete curve never hits EOL, linearly extrapolate remaining fade.
    def _extrapolate_eol(points: list[dict[str, float]]) -> tuple[int, bool]:
        hit = _eol(points)
        if hit is not None:
            return hit, False
        if len(points) < 2:
            return int(points[-1]["cycleIndex"]), True
        # Use fade rate from the last two points after n0, else overall.
        tail = [p for p in points if p["cycleIndex"] >= n0]
        if len(tail) < 2:
            tail = points
        dn = tail[-1]["cycleIndex"] - tail[0]["cycleIndex"]
        dc = tail[0]["capacityAh"] - tail[-1]["capacityAh"]
        if dn <= 0 or dc <= 1e-9:
            return int(points[-1]["cycleIndex"]), True
        rate = dc / dn
        remaining = tail[-1]["capacityAh"] - threshold
        extra = max(0.0, remaining / rate)
        return int(round(tail[-1]["cycleIndex"] + extra)), True

    base_eol, base_ex = _extrapolate_eol(baseline)
    stress_eol, stress_ex = _extrapolate_eol(stressed)
    base_rul = max(0, base_eol - n0)
    stress_rul = max(0, stress_eol - n0)

    return {
        "claim": STRESS_CLAIM,
        "identifiedOnDataset": False,
        "accelerationFactor": af,
        "temperatureAcceleration": temperature_acceleration(ambient_c),
        "cRateAcceleration": crate_acceleration(c_rate),
        "ambientTemperatureC": ambient_c,
        "dischargeCRate": c_rate,
        "currentCycle": n0,
        "currentCapacityAh": c0,
        "eolCapacityAh": threshold,
        "eolFraction": frac,
        "baselineEolCycle": base_eol,
        "stressedEolCycle": stress_eol,
        "baselineRulCycles": base_rul,
        "stressedRulCycles": stress_rul,
        "baselineExtrapolated": base_ex,
        "stressedExtrapolated": stress_ex,
        "baseline": baseline,
        "stressed": stressed,
    }
