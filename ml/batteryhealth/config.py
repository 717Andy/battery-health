"""Shared constants. NASA PCoE cells are 2.0 Ah 18650 Li-ion; official EOL is 70% (1.4 Ah)."""

from __future__ import annotations

from pathlib import Path

RATED_CAPACITY_AH = 2.0
# NASA Ames PCoE protocol: experiments stopped at 30% fade (2.0 Ah → 1.4 Ah).
EOL_CAPACITY_FRACTION = 0.70
# Common automotive warranty / OEM replacement threshold.
EOL_CAPACITY_FRACTION_OEM = 0.80

NASA_BATTERIES = ("B0005", "B0006", "B0007", "B0018")
NASA_DOWNLOAD_URL = "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
NASA_INNER_ZIP = "5. Battery Data Set/1. BatteryAgingARC-FY08Q4.zip"
NASA_CITATION = (
    "B. Saha and K. Goebel (2007). “Battery Data Set”, NASA Prognostics Data "
    "Repository, NASA Ames Research Center, Moffett Field, CA."
)

# Sensor-curve features only — no capacity / SoH leak into the SoH model.
SOH_FEATURE_COLUMNS: tuple[str, ...] = (
    "cycle_index",
    "voltage_mean",
    "voltage_std",
    "voltage_min",
    "voltage_max",
    "voltage_start",
    "voltage_end",
    "voltage_slope",
    "current_mean",
    "current_std",
    "temp_mean",
    "temp_std",
    "temp_max",
    "temp_rise",
    "duration_s",
    "energy_wh",
    "time_to_3v5",
    "time_to_3v0",
    "ambient_temp_c",
)

# RUL may use measured or predicted SoH plus the same curve stats.
RUL_FEATURE_COLUMNS: tuple[str, ...] = SOH_FEATURE_COLUMNS + ("soh",)

FEATURE_COLUMNS: tuple[str, ...] = RUL_FEATURE_COLUMNS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "nasa"
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts"
DEFAULT_MODEL_DIR = DEFAULT_ARTIFACT_DIR / "models"

MAX_TRACE_POINTS = 256

# Arrhenius / C-rate stress model (also implemented in BatteryHealth.Core).
# These constants are a scenario overlay. They were not identified on the NASA cells.
ARRHENIUS_EA_EV = 0.50
BOLTZMANN_EV_PER_K = 8.617333262145e-5
REF_TEMPERATURE_C = 24.0
REF_C_RATE = 1.0
C_RATE_EXPONENT = 0.60
STRESS_CLAIM = (
    "Scenario acceleration referenced to 24 °C and 1C. "
    "Ea = 0.50 eV and the C-rate exponent 0.60 were not identified on the NASA cells."
)

# Shipped desktop weights vs the fit that produced the hold-out tables.
PRODUCTION_FAMILY = "sklearn Pipeline(StandardScaler + GradientBoostingRegressor)"
PRODUCTION_FIT_SCOPE = "all-rows"
HOLDOUT_METRICS_FIT_SCOPE = "holdout-excluded"
APPLICABILITY = (
    "NASA PCoE constant-current 18650 discharges near 24 °C. "
    "energy_wh and duration_s track delivered capacity on this protocol; "
    "cycle_index tracks position along a cell's own fade curve."
)
