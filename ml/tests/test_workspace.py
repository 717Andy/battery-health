from batteryhealth.service.workspace import (
    battery_summary,
    cycle_at,
    estimate_rul_from_fade,
    has_trace,
)


def _battery():
    cycles = []
    for i in range(1, 11):
        cap = 1.9 - 0.05 * (i - 1)  # 1.6 Ah at cycle 7; 1.4 Ah at cycle 11 (extrapolated)
        cycles.append(
            {
                "cycleIndex": i,
                "type": "discharge",
                "capacityAh": cap,
                "timeS": [0, 10] if i in {1, 10} else [],
                "voltageV": [4.1, 3.1] if i in {1, 10} else [],
                "currentA": [-2.0, -2.0] if i in {1, 10} else [],
                "temperatureC": [24.0, 26.0] if i in {1, 10} else [],
                "features": {"cycle_index": float(i), "voltage_mean": 3.5},
            }
        )
    return {
        "batteryId": "TOY",
        "source": "nasa",
        "ratedCapacityAh": 2.0,
        "eolCapacityFraction": 0.7,
        "cycles": cycles,
    }


def test_cycle_at_snaps_to_last_traced_by_default():
    rec = _battery()
    assert cycle_at(rec, None)["cycleIndex"] == 10
    assert cycle_at(rec, 4)["cycleIndex"] == 4
    assert has_trace(cycle_at(rec, 1))
    assert not has_trace(cycle_at(rec, 4))


def test_oem_rul_hits_80_percent_sooner_than_70():
    rec = _battery()
    oem = estimate_rul_from_fade(rec, 0.80, 1)
    nasa = estimate_rul_from_fade(rec, 0.70, 1)
    assert oem < nasa
    assert oem == 6  # cycle 7 is 1.60 Ah


def test_summary_counts_traced_cycles():
    summary = battery_summary(_battery())
    assert summary["nCycles"] == 10
    assert summary["tracedCycles"] == [1, 10]
    assert summary["defaultCycle"] == 10
