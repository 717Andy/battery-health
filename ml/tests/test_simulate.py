from batteryhealth.simulate import combined_acceleration, simulate_stress, temperature_acceleration


def _toy_battery():
    cycles = []
    for i in range(1, 21):
        cap = 2.0 - 0.04 * (i - 1)  # hits 1.4 Ah at cycle 16
        cycles.append(
            {
                "cycleIndex": i,
                "type": "discharge",
                "capacityAh": cap,
                "timeS": [0, 100],
                "voltageV": [4.0, 3.0],
                "currentA": [-2.0, -2.0],
                "temperatureC": [24.0, 26.0],
            }
        )
    return {
        "batteryId": "TOY",
        "ratedCapacityAh": 2.0,
        "eolCapacityFraction": 0.70,
        "cycles": cycles,
    }


def test_acceleration_is_one_at_reference():
    assert abs(temperature_acceleration(24.0) - 1.0) < 1e-9
    assert combined_acceleration(24.0, 1.0) == temperature_acceleration(24.0) * 1.0


def test_hotter_and_faster_age_quicker():
    assert temperature_acceleration(45.0) > temperature_acceleration(24.0)
    assert combined_acceleration(45.0, 2.0) > combined_acceleration(24.0, 1.0)


def test_stress_shortens_rul():
    result = simulate_stress(_toy_battery(), ambient_c=45.0, c_rate=2.0, current_cycle=5)
    assert result["accelerationFactor"] > 1.0
    assert result["stressedRulCycles"] <= result["baselineRulCycles"]
    assert result["stressed"][-1]["capacityAh"] <= result["baseline"][-1]["capacityAh"]
    assert result["identifiedOnDataset"] is False
    assert "not identified" in result["claim"]
