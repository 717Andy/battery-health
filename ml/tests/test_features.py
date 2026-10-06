from batteryhealth.config import SOH_FEATURE_COLUMNS
from batteryhealth.features import extract_cycle_features, feature_vector


def test_extract_cycle_features_shape():
    t = [0, 60, 120, 180, 240]
    v = [4.1, 3.9, 3.6, 3.3, 2.9]
    i = [-2.0, -2.0, -2.0, -2.0, -2.0]
    temp = [24.0, 25.0, 26.0, 27.0, 28.0]
    feats = extract_cycle_features(
        cycle_index=3,
        time_s=t,
        voltage_v=v,
        current_a=i,
        temperature_c=temp,
        ambient_temp_c=24.0,
        soh=0.92,
    )
    assert feats["cycle_index"] == 3
    assert feats["voltage_max"] > feats["voltage_min"]
    assert feats["duration_s"] == 240
    assert feats["temp_rise"] == 4.0
    assert feats["time_to_3v5"] > 0
    assert feats["soh"] == 0.92
    vec = feature_vector(feats, SOH_FEATURE_COLUMNS)
    assert vec.shape == (len(SOH_FEATURE_COLUMNS),)
    assert "capacity" not in feats


def test_time_to_voltage_interpolation():
    feats = extract_cycle_features(
        cycle_index=1,
        time_s=[0, 10, 20],
        voltage_v=[4.0, 3.5, 3.0],
        current_a=[-1, -1, -1],
        temperature_c=[24, 24, 24],
    )
    assert abs(feats["time_to_3v5"] - 10.0) < 1e-6
    assert abs(feats["time_to_3v0"] - 20.0) < 1e-6
