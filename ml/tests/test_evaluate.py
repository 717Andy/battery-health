"""Honesty checks: censored EOL, nested SoH→RUL, and protocol-column ablations."""

from batteryhealth.config import RUL_FEATURE_COLUMNS, SOH_FEATURE_COLUMNS
from batteryhealth.dataset import records_to_frame
from batteryhealth.evaluate import censoring_report, feature_ablations, nested_soh_to_rul, noise_robustness
from batteryhealth.train import _gbr, _predict_any


def _cycle(index: int, capacity: float) -> dict:
    features = {col: float(index) for col in SOH_FEATURE_COLUMNS}
    features["energy_wh"] = capacity * 3.0
    features["duration_s"] = capacity * 1000.0
    features["cycle_index"] = float(index)
    return {
        "cycleIndex": index,
        "type": "discharge",
        "capacityAh": capacity,
        "features": features,
        "timeS": [0.0, 10.0],
        "voltageV": [4.0, 3.2],
        "currentA": [-1.0, -1.0],
        "temperatureC": [24.0, 25.0],
    }


def _record(battery_id: str, capacities: list[float]) -> dict:
    return {
        "batteryId": battery_id,
        "ratedCapacityAh": 2.0,
        "eolCapacityFraction": 0.70,
        "cycles": [_cycle(i, cap) for i, cap in enumerate(capacities, start=1)],
    }


def _frame():
    records = [
        _record("A", [2.0, 1.8, 1.6, 1.4, 1.2]),
        _record("B", [2.0, 1.75, 1.5, 1.35, 1.2]),
        _record("C", [1.95, 1.9, 1.85, 1.8]),
    ]
    return records_to_frame(records)


def _fit(x, y):
    model = _gbr()
    model.fit(x, y)
    return model


def test_censored_cell_is_flagged_and_excluded_from_uncensored_pool():
    frame = _frame()
    report = censoring_report(frame)
    assert report["batteries"]["C"]["censored"] is True
    assert report["batteries"]["A"]["censored"] is False
    assert report["censoredBatteries"] == ["C"]
    nested = nested_soh_to_rul(frame, fit=_fit, predict=_predict_any)
    assert nested["perBattery"]["C"]["censored"] is True
    assert nested["pooled"]["n"] == len(frame)
    assert nested["pooledExcludingCensored"]["n"] == len(frame) - int((frame["battery_id"] == "C").sum())


def test_ablations_drop_protocol_columns_on_the_same_split():
    frame = _frame()
    soh = feature_ablations(frame, feature_cols=SOH_FEATURE_COLUMNS, target="soh", fit=_fit, predict=_predict_any, holdout="B")
    assert "energy_wh" not in soh["dropEnergyAndDuration"]["columns"]
    assert "duration_s" not in soh["dropEnergyAndDuration"]["columns"]
    assert "cycle_index" not in soh["dropCycleIndex"]["columns"]
    assert soh["dropEnergyAndDuration"]["holdout"]["n"] == int((frame["battery_id"] == "B").sum())
    rul = feature_ablations(frame, feature_cols=RUL_FEATURE_COLUMNS, target="rul", fit=_fit, predict=_predict_any, holdout="B")
    assert "soh" in rul["dropEnergyAndDuration"]["columns"]
    assert "energy_wh" not in rul["dropEnergyAndDuration"]["columns"]


def test_zero_noise_scope_is_in_sample():
    record = _record("A", [2.0, 1.5, 1.2])
    out = noise_robustness(
        [record],
        soh_predict=lambda x: [0.5] * len(x),
        rul_predict=lambda x: [1.0] * len(x),
        levels=(0.0, 0.01),
    )
    assert out["0.0"]["scope"] == "in-sample"
    assert "not a hold-out" in out["0.0"]["note"]
    assert out["0.01"]["scope"] == "in-sample-perturbed"
