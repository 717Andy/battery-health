import numpy as np
import pandas as pd

from batteryhealth.early_cycle import (
    cell_table,
    domain_shift,
    early_features,
    eol_cycle,
    leave_one_cell_out,
    linear_eol,
)


def _cell(battery_id: str, q0: float, slope: float, n: int = 200) -> pd.DataFrame:
    cycles = np.arange(1, n + 1)
    cap = q0 + slope * (cycles - 1)
    cap = np.clip(cap, 0.05, None)
    return pd.DataFrame(
        {
            "battery_id": battery_id,
            "source": "toy",
            "cycle": cycles,
            "capacity_ah": cap,
            "rated_capacity_ah": q0,
        }
    )


def _fade() -> pd.DataFrame:
    # Three cells that all cross 80% of q0 after cycle 40 and before n.
    return pd.concat(
        [
            _cell("A", 1.10, -0.0020, 250),  # ~100 cycles
            _cell("B", 1.10, -0.0015, 250),  # ~133 cycles
            _cell("C", 1.05, -0.0010, 280),  # ~210 cycles
        ],
        ignore_index=True,
    )


def test_eol_and_linear_on_straight_fade():
    fade = _cell("A", 1.0, -0.002, 200)
    eol, censored = eol_cycle(fade["cycle"].to_numpy(), fade["capacity_ah"].to_numpy(), fraction=0.80)
    assert not censored
    assert 90 < eol < 120  # 0.2 drop / 0.002 = 100
    hat = linear_eol(fade["cycle"].to_numpy(), fade["capacity_ah"].to_numpy(), k=40, threshold=0.80)
    assert abs(hat - 100) < 3


def test_lobo_and_domain_shift_run():
    fade = _fade()
    cells = cell_table(fade, fraction=0.80)
    assert set(cells["battery_id"]) == {"A", "B", "C"}
    report = leave_one_cell_out(fade, k=40)
    assert report["nCells"] >= 2
    assert "rmse" in report["pooled"]["persist"]
    feats = early_features(fade[fade.battery_id == "A"]["cycle"].to_numpy(float), fade[fade.battery_id == "A"]["capacity_ah"].to_numpy(float), 40)
    assert feats["drop"] >= 0
    other = pd.concat([_cell("X", 2.0, -0.004, 180), _cell("Y", 2.0, -0.003, 180)], ignore_index=True)
    shift = domain_shift(fade, other, k=40)
    assert shift["testCells"]
    assert shift["pooled"]["persist"]["n"] == len(shift["testCells"])


def test_committed_early_cycle_metrics_are_honest():
    import json
    from batteryhealth.config import REPO_ROOT

    path = REPO_ROOT / "artifacts" / "early_cycle" / "metrics.json"
    report = json.loads(path.read_text())
    assert report["nasaK40"]["nCells"] == 4
    assert report["calceK100"]["nCells"] == 3
    # Domain shift NASA→CALCE is expected to be bad (lifetimes ~90 vs ~500).
    assert report["nasaToCalceK40"]["pooled"]["persist"]["rmse"] > 300
    # CALCE n=3: persist should beat the overfit Ridge/log-var models.
    calce = report["calceK100"]["pooled"]
    assert calce["persist"]["rmse"] < calce["ridge"]["rmse"]
    assert calce["persist"]["rmse"] < calce["severson_logvar"]["rmse"]
