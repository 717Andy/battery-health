#!/usr/bin/env python3
"""Regenerate README result figures from committed artifacts/metrics.json.

Does not download NASA data. Numbers in the PNGs are the same hold-out-excluded
LOBO / nested figures already stored in metrics.json.

    PYTHONPATH=ml python ml/scripts/plot_results.py
    PYTHONPATH=ml python ml/scripts/plot_results.py --metrics artifacts/metrics.json --out docs/figures
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batteryhealth.config import REPO_ROOT

CELLS = ("B0005", "B0006", "B0007", "B0018")
SOH_FAMILIES = ("ridge", "gbr", "xgboost")
SOH_LABELS = {
    "ridge": "Ridge + scaler",
    "gbr": "GBR (shipped ONNX)",
    "xgboost": "XGBoost",
}
TEAL = "#0f766e"
SLATE = "#334155"
AMBER = "#d97706"
ROSE = "#be123c"
MUTED = "#64748b"


def _rmse(block: dict[str, Any], *keys: str) -> float:
    cur: Any = block
    for key in keys:
        cur = cur[key]
    return float(cur["rmse"])


def extract_values(metrics: dict[str, Any]) -> dict[str, Any]:
    soh = metrics["soh"]
    rul = metrics["rul"]
    nested = metrics["rulNestedSoh"]
    soh_holdout = {name: _rmse(soh, name, "holdout") for name in SOH_FAMILIES}
    soh_lobo = {name: _rmse(soh, name, "leaveOneBatteryOut", "pooled") for name in SOH_FAMILIES}
    rul_lobo = {
        cell: _rmse(rul, "gbr", "leaveOneBatteryOut", "perBattery", cell) for cell in CELLS
    }
    nested_per = {cell: float(nested["perBattery"][cell]["rmse"]) for cell in CELLS}
    censored = {
        cell: bool(nested["perBattery"][cell]["censored"]) for cell in CELLS
    }
    return {
        "sohHoldoutRmse": soh_holdout,
        "sohLoboPooledRmse": soh_lobo,
        "rulLoboGbrRmse": rul_lobo,
        "rulNestedPerCellRmse": nested_per,
        "censored": censored,
        "rulNestedPooledRmse": float(nested["pooled"]["rmse"]),
        "rulNestedUncensoredRmse": float(nested["pooledExcludingCensored"]["rmse"]),
        "rulNestedUncensoredN": int(nested["pooledExcludingCensored"]["n"]),
        "rulNestedPooledN": int(nested["pooled"]["n"]),
        "holdoutBattery": metrics["holdoutBattery"],
        "nRows": int(metrics["nRows"]),
        "source": "artifacts/metrics.json",
        "note": (
            "Hold-out and LOBO numbers are holdout-excluded fits. "
            "B0007 is right-censored at 70% EOL (never reaches 1.4 Ah)."
        ),
    }


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
        }
    )


def plot_lobo_rul(values: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x = np.arange(len(CELLS))
    teacher = [values["rulLoboGbrRmse"][c] for c in CELLS]
    nested = [values["rulNestedPerCellRmse"][c] for c in CELLS]
    w = 0.36
    bars_a = ax.bar(x - w / 2, teacher, w, color=TEAL, label="GBR RUL (measured SoH)")
    bars_b = ax.bar(x + w / 2, nested, w, color=AMBER, label="Nested SoH → RUL")
    for bars in (bars_a, bars_b):
        for rect, cell in zip(bars, CELLS):
            if values["censored"][cell]:
                rect.set_hatch("///")
                rect.set_edgecolor(ROSE)
    ax.set_xticks(x, CELLS)
    ax.set_ylabel("RMSE (cycles)")
    ax.set_title("Leave-one-battery-out RUL, including censored B0007")
    ax.legend(frameon=False, loc="upper left")
    ax.set_xlabel("Hatched = B0007, right-censored (never reaches 1.4 Ah)")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_soh_compare(values: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    names = list(SOH_FAMILIES)
    x = np.arange(len(names))
    w = 0.36
    hold = [values["sohHoldoutRmse"][n] for n in names]
    lobo = [values["sohLoboPooledRmse"][n] for n in names]
    ax.bar(x - w / 2, hold, w, color=TEAL, label=f"Hold-out {values['holdoutBattery']}")
    ax.bar(x + w / 2, lobo, w, color=SLATE, label="LOBO pooled")
    ax.set_xticks(x, [SOH_LABELS[n] for n in names])
    ax.set_ylabel("SoH RMSE (fraction of 2.0 Ah)")
    ax.set_title("SoH: Ridge vs GBR vs XGBoost")
    ax.legend(frameon=False)
    ax.annotate(
        "Ridge wins: energy_wh / duration_s track\ndelivered capacity on this CC protocol",
        xy=(0, hold[0]),
        xytext=(0.28, 0.62),
        textcoords="axes fraction",
        fontsize=9,
        color=MUTED,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_nested_uncensored(values: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    labels = [
        f"Pooled all cells\nn={values['rulNestedPooledN']}",
        f"Uncensored only\nn={values['rulNestedUncensoredN']}",
    ]
    heights = [values["rulNestedPooledRmse"], values["rulNestedUncensoredRmse"]]
    colors = [ROSE, TEAL]
    bars = ax.bar(labels, heights, color=colors, width=0.55)
    for rect, h in zip(bars, heights):
        ax.text(rect.get_x() + rect.get_width() / 2, h + 0.4, f"{h:.2f}", ha="center", fontweight="semibold")
    ax.set_ylabel("Nested SoH → RUL RMSE (cycles)")
    ax.set_title("Dropping censored B0007 cuts nested RUL RMSE from 21.7 to 12.0")
    ax.set_ylim(0, max(heights) * 1.2)
    ax.text(
        0.5,
        0.08,
        "Inference graph is SoH model → RUL model. Teacher-forced RUL (measured SoH) is a different, easier number.",
        transform=ax.transAxes,
        ha="center",
        fontsize=8,
        color=MUTED,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=REPO_ROOT / "artifacts" / "metrics.json")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "figures")
    args = parser.parse_args(argv)
    metrics = json.loads(args.metrics.read_text())
    values = extract_values(metrics)
    args.out.mkdir(parents=True, exist_ok=True)
    _style()
    plot_lobo_rul(values, args.out / "lobo_rul_per_cell.png")
    plot_soh_compare(values, args.out / "soh_ridge_gbr_xgb.png")
    plot_nested_uncensored(values, args.out / "nested_rul_uncensored.png")
    (args.out / "figure_values.json").write_text(json.dumps(values, indent=2) + "\n")
    print(f"Wrote figures to {args.out}")
    print(
        "nested uncensored RMSE",
        round(values["rulNestedUncensoredRmse"], 2),
        "n",
        values["rulNestedUncensoredN"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
