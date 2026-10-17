import json
from pathlib import Path

from batteryhealth.config import REPO_ROOT


def test_plot_results_matches_committed_metrics(tmp_path):
    from scripts.plot_results import extract_values, main

    metrics = json.loads((REPO_ROOT / "artifacts" / "metrics.json").read_text())
    values = extract_values(metrics)
    assert values["censored"]["B0007"] is True
    assert values["censored"]["B0005"] is False
    assert 11.5 < values["rulNestedUncensoredRmse"] < 12.5
    assert values["rulNestedUncensoredN"] == 468
    assert values["rulLoboGbrRmse"]["B0007"] > values["rulLoboGbrRmse"]["B0005"]
    assert values["sohHoldoutRmse"]["ridge"] < values["sohHoldoutRmse"]["gbr"]

    out = tmp_path / "figures"
    assert main(["--out", str(out)]) == 0
    for name in (
        "lobo_rul_per_cell.png",
        "soh_ridge_gbr_xgb.png",
        "nested_rul_uncensored.png",
        "figure_values.json",
    ):
        assert (out / name).exists()
        assert (out / name).stat().st_size > 100
