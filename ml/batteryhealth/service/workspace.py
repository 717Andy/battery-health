"""Workspace helpers for the browser demo — same SoH/RUL/stress math as the WinUI app."""

from __future__ import annotations

import json
from typing import Any

from batteryhealth.config import (
    APPLICABILITY,
    EOL_CAPACITY_FRACTION,
    EOL_CAPACITY_FRACTION_OEM,
    RATED_CAPACITY_AH,
    RUL_FEATURE_COLUMNS,
    SOH_FEATURE_COLUMNS,
    STRESS_CLAIM,
)
from batteryhealth.features import extract_cycle_features, feature_vector
from batteryhealth.parsers.canonical import discharge_cycles
from batteryhealth.simulate import crate_acceleration, simulate_stress, temperature_acceleration

FEATURE_SHIFT_COLUMNS = ("energy_wh", "duration_s", "time_to_3v0")
PROTOCOL_APPLICABILITY = "NASA constant-current 18650 discharges near 24 °C."
MODEL_FIT_NOTE = "The SoH model is still the NASA 2.0 Ah fit. It does not take capacity as an input."
PARTIAL_NOTE = (
    "These discharges look partial relative to the NASA protocol the model was trained on."
)
STARTING_HINT = (
    "Three ways to start. Processed NASA JSON opens directly. "
    "CALCE CSV or Excel opens directly; type the nameplate beside the cycle list. "
    "A NASA .mat file has to be converted first with python -m batteryhealth.download, "
    "or POST it to the sidecar /parse/nasa, then open the processed JSON."
)


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
    """Fade-curve RUL to `fraction` of the current nameplate. Not the ONNX RUL head."""
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
    later = [p for p in points if p[0] >= current_cycle]
    if len(later) < 2:
        return 0.0
    first, last = later[0], later[-1]
    dn = last[0] - first[0]
    dc = first[1] - last[1]
    if dn <= 0 or dc <= 1e-9:
        return 0.0
    extra = max(0.0, (last[1] - threshold) / (dc / dn))
    return float(max(0.0, last[0] + extra - current_cycle))


def describe_feature_shift(
    current_cycle: int,
    current: dict[str, float],
    baseline_cycle: int,
    baseline: dict[str, float],
) -> str:
    if current_cycle == baseline_cycle:
        return "This is the first scored discharge, so there is no earlier cycle to compare."
    parts: list[str] = []
    for column in FEATURE_SHIFT_COLUMNS:
        now = current.get(column)
        then = baseline.get(column)
        if now is None or then is None or abs(then) < 1e-9:
            parts.append(f"{column} n/a")
            continue
        percent = (now - then) / abs(then) * 100.0
        parts.append(f"{column} {percent:+.1f}%")
    return f"Versus the first scored discharge (cycle {baseline_cycle}): {', '.join(parts)}."


def describe_warnings(battery: dict[str, Any], cycle: dict[str, Any] | None) -> str:
    warnings: list[str] = []
    if cycle is not None and not has_trace(cycle) and not cycle.get("features"):
        warnings.append("This cycle has no sensor trace and no features, so it cannot be scored.")
    assumed = bool(battery.get("ratedCapacityAssumed"))
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    if assumed:
        warnings.append(
            "Rated capacity was not in the file. The nameplate stays assumed until you set it. "
            "Measured SoH and both end-of-life lines follow that nameplate."
        )
    if abs(rated - RATED_CAPACITY_AH) > 1e-6:
        warnings.append(f"{MODEL_FIT_NOTE} Measured SoH and the end-of-life lines use {rated:.2f} Ah.")
    return " ".join(warnings)


def intake_report(battery: dict[str, Any]) -> dict[str, Any]:
    discharges = discharge_cycles(battery)
    traced = [c for c in discharges if has_trace(c)]
    reached = 0
    for cycle in traced:
        volts = cycle.get("voltageV") or cycle.get("voltage_v") or []
        if volts and min(float(v) for v in volts) <= 3.0:
            reached += 1
    partial = len(traced) > 0 and reached < len(traced) / 2.0
    assumed = bool(battery.get("ratedCapacityAssumed")) or "ratedCapacityAh" not in battery
    # JSON demos include ratedCapacityAh; CALCE parser does not set assumed, so infer from source.
    if battery.get("source") == "calce" and battery.get("ratedCapacityAssumed") is None:
        assumed = True
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    source = battery.get("source") or "unknown"
    lines = [
        f"Source {source}. {len(discharges)} discharge cycles, "
        f"{sum(1 for c in discharges if c.get('capacityAh') is not None)} with capacity, "
        f"{len(traced)} with a sensor trace.",
        (
            f"Nameplate {rated:.2f} Ah was not in the file and is assumed until you set it."
            if assumed
            else f"Nameplate {rated:.2f} Ah was in the file."
        ),
        f"Lab stop is 70% ({rated * 0.70:.2f} Ah). Warranty line is 80% ({rated * 0.80:.2f} Ah).",
    ]
    if partial:
        lines.append(PARTIAL_NOTE)
    return {
        "source": source,
        "dischargeCount": len(discharges),
        "withCapacity": sum(1 for c in discharges if c.get("capacityAh") is not None),
        "withTrace": len(traced),
        "nameplateAssumed": assumed,
        "nameplateAh": rated,
        "eol70Ah": rated * 0.70,
        "eol80Ah": rated * 0.80,
        "partialDischarges": partial,
        "lines": lines,
    }


def scenario_acceleration(ambient_c: float, c_rate: float, ea_ev: float) -> float:
    return temperature_acceleration(ambient_c, ea_ev=ea_ev) * crate_acceleration(c_rate)


def describe_ea_band(ambient_c: float, c_rate: float) -> str:
    low = scenario_acceleration(ambient_c, c_rate, 0.30)
    mid = scenario_acceleration(ambient_c, c_rate, 0.50)
    high = scenario_acceleration(ambient_c, c_rate, 0.70)
    return (
        f"At {ambient_c:.0f} °C and {c_rate:.2f} C, acceleration is {low:.2f} at 0.30 eV, "
        f"{mid:.2f} at 0.50 eV, and {high:.2f} at 0.70 eV. These constants were not fit to the NASA cells."
    )


def typical_protocol_error(metrics: dict[str, Any] | None) -> str | None:
    if not metrics:
        return None
    nested = metrics.get("rulNestedSoh") or {}
    pooled = nested.get("pooledExcludingCensored") or {}
    if "rmse" not in pooled or "n" not in pooled:
        return None
    rmse = float(pooled["rmse"])
    n = int(pooled["n"])
    return (
        f"Typical miss on an unseen cell from this same lab protocol: {rmse:.1f} cycles RMSE "
        f"(nested SoH to RUL, censored cells excluded, n={n}). "
        "This is an empirical error, not a calibrated prediction interval."
    )


def describe_metrics(metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return "Train the Python pipeline to populate artifacts/metrics.json."
    prod = metrics.get("productionModel") or {}
    family = prod.get("family") or prod.get("type") or "gradient boosting"
    fit_scope = prod.get("fitScope") or "all-rows"
    holdout_scope = prod.get("holdoutMetricsFitScope") or "holdout-excluded"
    n_rows = metrics.get("nRows") or 0
    batteries = ", ".join(metrics.get("batteries") or [])
    holdout = metrics.get("holdoutBattery") or "hold-out"

    def _hold(target: str) -> str:
        hold = (((metrics.get(target) or {}).get("gbr") or {}).get("holdout") or {})
        if "rmse" not in hold:
            return "hold-out metrics unavailable"
        rmse, mae, r2 = hold["rmse"], hold["mae"], hold["r2"]
        if target == "rul":
            return f"RMSE {rmse:.1f} cycles, MAE {mae:.1f}, R² {r2:.2f}"
        return f"RMSE {rmse:.4f} (fraction), MAE {mae:.4f}, R² {r2:.2f}"

    return (
        f"Shipped ONNX ({family}) fit scope: {fit_scope}"
        + (f" ({n_rows} rows, {batteries}). " if n_rows else ". ")
        + f"The {holdout} numbers use fit scope {holdout_scope}, so they are not the error of the files on disk. "
        + f"RUL {_hold('rul')}. SoH {_hold('soh')}."
    )


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
    shift = ""
    for other in discharge_cycles(battery):
        try:
            base_feats, _ = features_for_cycle(other, rated)
        except ValueError:
            continue
        if all(col in base_feats and col in feats for col in FEATURE_SHIFT_COLUMNS):
            shift = describe_feature_shift(cycle_index, feats, int(other["cycleIndex"]), base_feats)
            break
    return {
        "batteryId": battery.get("batteryId"),
        "cycleIndex": cycle_index,
        "predictedSoh": soh,
        "predictedSohPercent": soh * 100.0,
        "observedSoh": observed,
        "predictedRulCycles": rul,
        "fadeRulTo70Cycles": estimate_rul_from_fade(battery, EOL_CAPACITY_FRACTION, cycle_index),
        "fadeRulTo80Cycles": estimate_rul_from_fade(battery, EOL_CAPACITY_FRACTION_OEM, cycle_index),
        "oemRulCycles": estimate_rul_from_fade(battery, EOL_CAPACITY_FRACTION_OEM, cycle_index),
        "eolCapacityFraction": eol_frac,
        "eolCapacityAh": rated * eol_frac,
        "hasTrace": has_trace(cycle),
        "featureShift": shift,
        "warnings": describe_warnings(battery, cycle),
        "applicability": PROTOCOL_APPLICABILITY,
        "features": feats,
    }


def predict_trajectory(ort_predict, battery: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    for cycle in discharge_cycles(battery):
        try:
            pred = predict_cycle(ort_predict, battery, cycle)
        except ValueError:
            continue
        points.append(
            {
                "cycleIndex": pred["cycleIndex"],
                "predictedSoh": pred["predictedSoh"],
                "observedSoh": pred["observedSoh"],
                "predictedRulCycles": pred["predictedRulCycles"],
                "fadeRulTo70Cycles": pred["fadeRulTo70Cycles"],
                "fadeRulTo80Cycles": pred["fadeRulTo80Cycles"],
                "hasTrace": pred["hasTrace"],
                "measuredCapacityAh": cycle.get("capacityAh"),
            }
        )
    return points


def build_decision(
    ort_predict,
    battery: dict[str, Any],
    *,
    cycle_index: int | None,
    ambient_c: float,
    c_rate: float,
    typical_error: str | None,
) -> dict[str, Any]:
    points = predict_trajectory(ort_predict, battery)
    if not points:
        raise ValueError("Load a cell before exporting.")
    selected = cycle_index
    if selected is None:
        traced = [p for p in points if p["hasTrace"]]
        selected = traced[-1]["cycleIndex"] if traced else points[-1]["cycleIndex"]
    if not any(p["cycleIndex"] == selected for p in points):
        raise ValueError(f"No discharge cycle {selected}.")
    sim = simulate_stress(
        battery,
        ambient_c=ambient_c,
        c_rate=c_rate,
        current_cycle=selected,
    )
    ea030 = scenario_acceleration(ambient_c, c_rate, 0.30)
    ea050 = scenario_acceleration(ambient_c, c_rate, 0.50)
    ea070 = scenario_acceleration(ambient_c, c_rate, 0.70)
    rows = []
    chosen = None
    for point in points:
        row = {
            "cycleIndex": point["cycleIndex"],
            "measuredCapacityAh": point["measuredCapacityAh"],
            "predictedSoh": point["predictedSoh"],
            "measuredSoh": point["observedSoh"],
            "rulTo70Cycles": point["predictedRulCycles"],
            "rulTo70FadeCycles": point["fadeRulTo70Cycles"],
            "rulTo80Cycles": point["fadeRulTo80Cycles"],
            "hasTrace": point["hasTrace"],
            "selected": point["cycleIndex"] == selected,
        }
        rows.append(row)
        if row["selected"]:
            chosen = row
    decision = None
    if chosen is not None:
        decision = {
            "batteryId": battery.get("batteryId"),
            "cycle": selected,
            "nameplateAh": float(battery.get("ratedCapacityAh") or 2.0),
            "predictedSoh": chosen["predictedSoh"],
            "modelRulTo70Cycles": chosen["rulTo70Cycles"],
            "fadeRulTo70Cycles": chosen["rulTo70FadeCycles"],
            "fadeRulTo80Cycles": chosen["rulTo80Cycles"],
            "typicalProtocolError": typical_error,
            "scenarioAmbientC": ambient_c,
            "scenarioCRate": c_rate,
            "accelerationFactor": sim["accelerationFactor"],
            "accelerationAtEa030": ea030,
            "accelerationAtEa050": ea050,
            "accelerationAtEa070": ea070,
        }
    report = {
        "batteryId": battery.get("batteryId"),
        "ratedCapacityAh": float(battery.get("ratedCapacityAh") or 2.0),
        "ratedCapacityAssumed": bool(intake_report(battery)["nameplateAssumed"]),
        "applicability": PROTOCOL_APPLICABILITY,
        "typicalProtocolError": typical_error,
        "scenarioAmbientC": ambient_c,
        "scenarioCRate": c_rate,
        "accelerationFactor": sim["accelerationFactor"],
        "accelerationAtEa030": ea030,
        "accelerationAtEa050": ea050,
        "accelerationAtEa070": ea070,
        "scenarioClaim": STRESS_CLAIM,
        "decisionCycle": selected,
        "decision": decision,
        "rows": rows,
    }
    csv = _decision_csv(report)
    stem = f"{battery.get('batteryId') or 'battery'}-cycle{selected}-decision"
    return {
        "csv": csv,
        "json": report,
        "csvName": f"{stem}.csv",
        "jsonName": f"{stem}.json",
        "previewCsv": "\n".join(csv.splitlines()[:8]),
        "previewJson": json.dumps(decision, indent=2),
    }


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.9g}"


def _decision_csv(report: dict[str, Any]) -> str:
    header = (
        "cycle_index,measured_capacity_ah,predicted_soh,measured_soh,rul_to_70_cycles,"
        "rul_to_70_fade_cycles,rul_to_80_cycles,has_trace,selected,scenario_temperature_c,"
        "scenario_c_rate,acceleration_factor,acceleration_ea_0_30,acceleration_ea_0_50,"
        "acceleration_ea_0_70"
    )
    lines = [header]
    for row in report["rows"]:
        lines.append(
            ",".join(
                [
                    str(row["cycleIndex"]),
                    _fmt(row["measuredCapacityAh"]),
                    f"{row['predictedSoh']:.9g}",
                    _fmt(row["measuredSoh"]),
                    f"{row['rulTo70Cycles']:.9g}",
                    f"{row['rulTo70FadeCycles']:.9g}",
                    f"{row['rulTo80Cycles']:.9g}",
                    "true" if row["hasTrace"] else "false",
                    "true" if row["selected"] else "false",
                    f"{report['scenarioAmbientC']:.9g}",
                    f"{report['scenarioCRate']:.9g}",
                    f"{report['accelerationFactor']:.9g}",
                    f"{report['accelerationAtEa030']:.9g}",
                    f"{report['accelerationAtEa050']:.9g}",
                    f"{report['accelerationAtEa070']:.9g}",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def battery_summary(battery: dict[str, Any]) -> dict[str, Any]:
    discharges = discharge_cycles(battery)
    caps = [float(c["capacityAh"]) for c in discharges if c.get("capacityAh") is not None]
    traced = [int(c["cycleIndex"]) for c in discharges if has_trace(c)]
    rated = float(battery.get("ratedCapacityAh") or 2.0)
    eol = float(battery.get("eolCapacityFraction") or EOL_CAPACITY_FRACTION)
    intake = intake_report(battery)
    rows = []
    for cycle in discharges:
        cap = cycle.get("capacityAh")
        capacity = f"{float(cap):.3f} Ah" if cap is not None else "no capacity"
        trace = "trace" if has_trace(cycle) else "fade only"
        rows.append(
            {
                "cycleIndex": int(cycle["cycleIndex"]),
                "label": f"Cycle {cycle['cycleIndex']} · {capacity} · {trace}",
                "hasTrace": has_trace(cycle),
                "capacityAh": cap,
            }
        )
    return {
        "batteryId": battery.get("batteryId"),
        "source": battery.get("source"),
        "chemistry": battery.get("chemistry"),
        "notes": battery.get("notes"),
        "nCycles": len(discharges),
        "ratedCapacityAh": rated,
        "nameplateAssumed": intake["nameplateAssumed"],
        "eolCapacityFraction": eol,
        "eolCapacityAh": rated * eol,
        "eol70Ah": intake["eol70Ah"],
        "eol80Ah": intake["eol80Ah"],
        "firstCapacityAh": caps[0] if caps else None,
        "lastCapacityAh": caps[-1] if caps else None,
        "cycleMin": int(discharges[0]["cycleIndex"]) if discharges else 1,
        "cycleMax": int(discharges[-1]["cycleIndex"]) if discharges else 1,
        "tracedCycles": traced,
        "defaultCycle": traced[-1] if traced else (int(discharges[-1]["cycleIndex"]) if discharges else 1),
        "intakeLines": intake["lines"],
        "dischargeRows": rows,
        "startingHint": STARTING_HINT,
        "stressClaim": STRESS_CLAIM,
        "applicability": PROTOCOL_APPLICABILITY,
        "metricsApplicability": APPLICABILITY,
    }
