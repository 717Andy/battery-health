"""Extract per-cycle discharge capacity from official CALCE CS2/CX2 zip files.

Each cell zip is a dated sequence of Arbin .xlsx files whose Cycle_Index often
restarts at 1. Files are concatenated in name order with an offset. Only the
capacity time series is kept — not the 30–40 MB of raw traces.

Source: https://web.calce.umd.edu/batteries/data/  (CS2 pouch, 1.1 Ah, 1C).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CALCE_CELLS = {
    "CS2_35": "https://web.calce.umd.edu/batteries/data/CS2_35.zip",
    "CS2_36": "https://web.calce.umd.edu/batteries/data/CS2_36.zip",
    "CS2_38": "https://web.calce.umd.edu/batteries/data/CS2_38.zip",
}
CALCE_RATED_AH = 1.1
CALCE_CITATION = (
    "CALCE Battery Research Group, University of Maryland. CS2 pouch cells "
    "(LiCoO2, 1.1 Ah). https://web.calce.umd.edu/batteries/data/"
)


def _channel_frame(raw: bytes) -> pd.DataFrame:
    xl = pd.ExcelFile(io.BytesIO(raw))
    channel = next((s for s in xl.sheet_names if s.lower().startswith("channel")), None)
    if channel is None:
        raise ValueError(f"No Channel sheet in {xl.sheet_names}")
    return pd.read_excel(xl, sheet_name=channel, usecols=lambda c: True)


def fade_from_xlsx_bytes(raw: bytes) -> pd.DataFrame:
    frame = _channel_frame(raw)
    cols = {str(c).strip(): c for c in frame.columns}

    def _find(*needles: str) -> str | None:
        for needle in needles:
            for name, orig in cols.items():
                if needle in name.lower().replace(" ", ""):
                    return orig
        return None

    cycle_col = _find("cycle_index", "cycleindex")
    cap_col = _find("discharge_capacity")
    curr_col = _find("current(a)", "current")
    if cycle_col is None or cap_col is None:
        raise ValueError(f"Missing cycle/capacity columns: {list(frame.columns)}")
    cycle = pd.to_numeric(frame[cycle_col], errors="coerce")
    cap = pd.to_numeric(frame[cap_col], errors="coerce")
    if curr_col is not None:
        current = pd.to_numeric(frame[curr_col], errors="coerce")
        mask = current < -0.05
        if mask.sum() < 10:
            mask = cap > 0.05
        cycle, cap = cycle[mask], cap[mask]
    grouped = (
        pd.DataFrame({"cycle": cycle, "capacity_ah": cap})
        .dropna()
        .groupby("cycle", sort=True)["capacity_ah"]
        .agg(cap_max="max", cap_min="min")
        .reset_index()
    )
    # Arbin sometimes resets Discharge_Capacity each cycle (use max) and
    # sometimes accumulates (use max-min). The delta is safe for both.
    grouped["capacity_ah"] = grouped["cap_max"] - grouped["cap_min"]
    reset = grouped["cap_min"] < 0.05
    grouped.loc[reset, "capacity_ah"] = grouped.loc[reset, "cap_max"]
    grouped["cycle"] = grouped["cycle"].astype(int)
    plausible = grouped["capacity_ah"].between(0.15, 1.40)
    return grouped.loc[plausible, ["cycle", "capacity_ah"]]


_DATE_IN_NAME = re.compile(r"_(\d{1,2})_(\d{1,2})_(\d{2})$")


def _file_date(name: str) -> datetime:
    """Parse CS2_35_8_17_10.xlsx → 2010-08-17. Lexicographic zip order is wrong."""
    match = _DATE_IN_NAME.search(Path(name).stem)
    if not match:
        return datetime(1970, 1, 1)
    month, day, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    year = 2000 + year if year < 80 else 1900 + year
    try:
        return datetime(year, month, day)
    except ValueError:
        return datetime(1970, 1, 1)


def fade_from_zip(zip_path: Path, battery_id: str | None = None) -> pd.DataFrame:
    battery_id = battery_id or zip_path.stem
    parts: list[pd.DataFrame] = []
    offset = 0
    with zipfile.ZipFile(zip_path) as zf:
        names = [
            n
            for n in zf.namelist()
            if n.lower().endswith((".xlsx", ".xls")) and not Path(n).name.startswith("._")
        ]
        names.sort(key=_file_date)
        for name in names:
            grouped = fade_from_xlsx_bytes(zf.read(name))
            if grouped.empty:
                continue
            local = grouped["cycle"].to_numpy()
            if parts and int(local.min()) <= 2:
                offset = int(parts[-1]["cycle"].max())
            grouped = grouped.copy()
            grouped["cycle"] = grouped["cycle"] + offset
            grouped["source_file"] = Path(name).name
            parts.append(grouped)
    if not parts:
        raise ValueError(f"No discharge cycles in {zip_path}")
    fade = pd.concat(parts, ignore_index=True)
    fade = fade.sort_values("cycle").drop_duplicates("cycle", keep="last")
    fade["battery_id"] = battery_id
    fade["rated_capacity_ah"] = CALCE_RATED_AH
    fade["source"] = "calce"
    return fade.reset_index(drop=True)


def fade_table_from_zips(raw_dir: Path, cells: tuple[str, ...] = tuple(CALCE_CELLS)) -> pd.DataFrame:
    frames = []
    for cell in cells:
        path = raw_dir / f"{cell}.zip"
        if not path.exists():
            matches = list(raw_dir.glob(f"{cell}*.zip"))
            if not matches:
                continue
            path = matches[0]
        frames.append(fade_from_zip(path, battery_id=cell))
    if not frames:
        raise FileNotFoundError(f"No CALCE zips in {raw_dir}")
    return pd.concat(frames, ignore_index=True)


def record_from_fade(fade: pd.DataFrame, battery_id: str) -> dict[str, Any]:
    sub = fade[fade["battery_id"] == battery_id].sort_values("cycle")
    cycles = []
    for row in sub.itertuples():
        cycles.append(
            {
                "cycleIndex": int(row.cycle),
                "type": "discharge",
                "capacityAh": float(row.capacity_ah),
                "timeS": [],
                "voltageV": [],
                "currentA": [],
                "temperatureC": [],
            }
        )
    return {
        "batteryId": battery_id,
        "source": "calce",
        "ratedCapacityAh": CALCE_RATED_AH,
        "eolCapacityFraction": 0.80,
        "chemistry": "LiCoO2 pouch (CALCE CS2)",
        "cycles": cycles,
        "notes": CALCE_CITATION,
    }
