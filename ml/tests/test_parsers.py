from pathlib import Path

from batteryhealth.parsers.calce import parse_calce
from batteryhealth.parsers.canonical import dict_to_summary

FIXTURE = Path(__file__).parent / "fixtures" / "calce_sample.csv"


def test_calce_csv_parser():
    record = parse_calce(FIXTURE, battery_id="CS2_TEST", rated_capacity_ah=1.1)
    assert record["source"] == "calce"
    assert record["batteryId"] == "CS2_TEST"
    discharges = [c for c in record["cycles"] if c["type"] == "discharge"]
    assert len(discharges) == 2
    assert discharges[0]["capacityAh"] > 0
    assert discharges[0]["features"]["voltage_mean"] > 0
    summary = dict_to_summary(record)
    assert summary["nCycles"] == 2


def test_nasa_parser_on_real_data():
    raw = Path(__file__).resolve().parents[2] / "data" / "raw" / "nasa" / "B0005.mat"
    if not raw.exists():
        return
    from batteryhealth.parsers.nasa import parse_nasa_mat

    record = parse_nasa_mat(raw)
    assert record["batteryId"] == "B0005"
    discharges = [c for c in record["cycles"] if c["type"] == "discharge"]
    assert len(discharges) > 100
    assert discharges[0]["capacityAh"] > 1.5
    assert discharges[-1]["capacityAh"] < discharges[0]["capacityAh"]
