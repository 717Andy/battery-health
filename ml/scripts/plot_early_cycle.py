#!/usr/bin/env python3
"""Bar chart of early-cycle RMSE from artifacts/early_cycle/metrics.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batteryhealth.config import REPO_ROOT

METHODS = ("persist", "linear", "ridge", "severson_logvar")
LABELS = {
    "persist": "Persist",
    "linear": "Linear",
    "ridge": "Ridge",
    "severson_logvar": "log-var",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, default=REPO_ROOT / "artifacts" / "early_cycle" / "metrics.json")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "figures" / "early_cycle_rmse.png")
    args = parser.parse_args(argv)
    report = json.loads(args.metrics.read_text())
    panels = [
        ("NASA LOO, K=40", report["nasaK40"]["pooled"], report["nasaK40"]["nCells"]),
        ("CALCE CS2 LOO, K=100", report["calceK100"]["pooled"], report["calceK100"]["nCells"]),
        ("NASA → CALCE, K=40", report["nasaToCalceK40"]["pooled"], report["nasaToCalceK40"]["pooled"]["persist"]["n"]),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 4.0), sharey=False)
    colors = ["#0f766e", "#d97706", "#334155", "#be123c"]
    for ax, (title, pooled, n) in zip(axes, panels):
        vals = [pooled[m]["rmse"] for m in METHODS]
        ax.bar(range(len(METHODS)), vals, color=colors)
        ax.set_xticks(range(len(METHODS)), [LABELS[m] for m in METHODS], fontsize=9)
        ax.set_title(f"{title}\nn={n} cells")
        ax.set_ylabel("EOL-cycle RMSE")
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle("Early-cycle lifetime prediction (80% of each cell's initial capacity)", fontsize=12)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=140)
    print("Wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
