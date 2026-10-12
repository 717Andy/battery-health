"""Train SoH and RUL models, evaluate, and export ONNX artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from batteryhealth.config import (
    APPLICABILITY,
    DEFAULT_MODEL_DIR,
    DEFAULT_PROCESSED_DIR,
    EOL_CAPACITY_FRACTION,
    HOLDOUT_METRICS_FIT_SCOPE,
    NASA_CITATION,
    PRODUCTION_FAMILY,
    PRODUCTION_FIT_SCOPE,
    RUL_FEATURE_COLUMNS,
    SOH_FEATURE_COLUMNS,
)
from batteryhealth.dataset import records_to_frame, split_leave_one_battery_out
from batteryhealth.evaluate import (
    censoring_report,
    feature_ablations,
    leave_one_battery_out,
    nested_soh_to_rul,
    noise_robustness,
    regression_metrics,
)
from batteryhealth.export_onnx import export_sklearn, feature_spec, verify_onnx
from batteryhealth.parsers.nasa import parse_nasa_mat

try:
    import xgboost as xgb

    HAS_XGB = True
except ImportError:  # pragma: no cover
    HAS_XGB = False

try:
    import torch
    from torch import nn

    HAS_TORCH = True
except ImportError:  # pragma: no cover
    HAS_TORCH = False


def load_records(processed_dir: Path | None, raw_dir: Path | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if processed_dir and processed_dir.exists():
        for path in sorted(processed_dir.glob("*.json")):
            if path.name.endswith(".summary.json"):
                continue
            records.append(json.loads(path.read_text()))
    if records:
        return records
    if raw_dir and raw_dir.exists():
        from batteryhealth.download import process_raw_dir

        process_raw_dir(raw_dir, processed_dir or DEFAULT_PROCESSED_DIR)
        return load_records(processed_dir or DEFAULT_PROCESSED_DIR, None)
    raise FileNotFoundError(
        "No processed JSON or raw NASA .mat files found. Run: python -m batteryhealth.download"
    )


def _ridge():
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        ]
    )


def _gbr():
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "model",
                GradientBoostingRegressor(
                    n_estimators=180,
                    max_depth=3,
                    learning_rate=0.05,
                    subsample=0.9,
                    random_state=42,
                ),
            ),
        ]
    )


def _xgb():
    return xgb.XGBRegressor(
        n_estimators=250,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=4,
        reg_lambda=1.0,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=2,
        tree_method="hist",
    )


class _Mlp(nn.Module if HAS_TORCH else object):  # type: ignore[misc]
    def __init__(self, n_in: int):
        if not HAS_TORCH:
            raise RuntimeError("PyTorch is not installed")
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        return self.net(x)


def _fit_torch(x: np.ndarray, y: np.ndarray, epochs: int = 80) -> Any:
    assert HAS_TORCH
    model = _Mlp(x.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    xt = torch.tensor(x, dtype=torch.float32)
    yt = torch.tensor(y.reshape(-1, 1), dtype=torch.float32)
    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        pred = model(xt)
        loss = loss_fn(pred, yt)
        loss.backward()
        opt.step()
    model.eval()
    return model


def _predict_any(model, x: np.ndarray) -> np.ndarray:
    if HAS_TORCH and isinstance(model, nn.Module):
        with torch.no_grad():
            return model(torch.tensor(x, dtype=torch.float32)).numpy().reshape(-1)
    return np.asarray(model.predict(x), dtype=float).reshape(-1)


def _eval_family(frame: pd.DataFrame, feature_cols: tuple[str, ...], target: str) -> dict[str, Any]:
    families: dict[str, Any] = {
        "ridge": _ridge,
        "gbr": _gbr,
    }
    if HAS_XGB:
        families["xgboost"] = _xgb

    report: dict[str, Any] = {}
    holdout = "B0018" if "B0018" in set(frame["battery_id"]) else str(frame["battery_id"].iloc[-1])
    train, test = split_leave_one_battery_out(frame, holdout)
    x_train = train[list(feature_cols)].to_numpy(dtype=np.float32)
    y_train = train[target].to_numpy(dtype=float)
    x_test = test[list(feature_cols)].to_numpy(dtype=np.float32)
    y_test = test[target].to_numpy(dtype=float)

    for name, factory in families.items():
        model = factory()
        model.fit(x_train, y_train)
        pred = _predict_any(model, x_test)
        holdout_metrics = regression_metrics(y_test, pred)

        def fit_fn(x, y, factory=factory):
            m = factory()
            m.fit(x, y)
            return m

        lobo = leave_one_battery_out(
            frame,
            feature_cols=feature_cols,
            target=target,
            fit=fit_fn,
            predict=_predict_any,
        )
        report[name] = {
            "holdoutBattery": holdout,
            "holdout": holdout_metrics,
            "leaveOneBatteryOut": lobo,
        }

    if HAS_TORCH:
        model = _fit_torch(x_train, y_train)
        pred = _predict_any(model, x_test)
        report["torch_mlp"] = {
            "holdoutBattery": holdout,
            "holdout": regression_metrics(y_test, pred),
        }
    return report


def production_honesty_report(
    frame: pd.DataFrame,
    *,
    fit,
    predict,
) -> dict[str, Any]:
    """Nested SoH→RUL, protocol ablations, and censored-EOL flags for the production family."""
    return {
        "eolCensoring": censoring_report(frame),
        "rulNestedSoh": nested_soh_to_rul(frame, fit=fit, predict=predict),
        "featureAblations": {
            "soh": feature_ablations(frame, feature_cols=SOH_FEATURE_COLUMNS, target="soh", fit=fit, predict=predict),
            "rul": feature_ablations(frame, feature_cols=RUL_FEATURE_COLUMNS, target="rul", fit=fit, predict=predict),
        },
    }


def _pick_best(report: dict[str, Any]) -> str:
    # Prefer tree models that convert cleanly; pick lowest holdout RMSE.
    ranked = sorted(
        ((name, body["holdout"]["rmse"]) for name, body in report.items() if "holdout" in body),
        key=lambda kv: kv[1],
    )
    preferred = [name for name, _ in ranked if name in {"xgboost", "gbr"}]
    return preferred[0] if preferred else ranked[0][0]


def train_and_export(
    *,
    processed_dir: Path,
    raw_dir: Path | None,
    model_dir: Path,
    holdout: str = "B0018",
) -> dict[str, Any]:
    records = load_records(processed_dir, raw_dir)
    frame = records_to_frame(records, eol_fraction=EOL_CAPACITY_FRACTION)
    soh_report = _eval_family(frame, SOH_FEATURE_COLUMNS, "soh")
    rul_report = _eval_family(frame, RUL_FEATURE_COLUMNS, "rul")

    # Production ONNX: sklearn GBR pipeline (stable skl2onnx + C# ONNX Runtime).
    soh_model = _gbr()
    rul_model = _gbr()
    train, test = split_leave_one_battery_out(frame, holdout if holdout in set(frame["battery_id"]) else str(frame["battery_id"].iloc[-1]))
    soh_model.fit(train[list(SOH_FEATURE_COLUMNS)].to_numpy(dtype=np.float32), train["soh"].to_numpy(dtype=float))
    rul_model.fit(train[list(RUL_FEATURE_COLUMNS)].to_numpy(dtype=np.float32), train["rul"].to_numpy(dtype=float))

    # Also fit production models on ALL batteries for the shipped desktop weights,
    # after reporting hold-out metrics from the train/test split above.
    soh_prod = _gbr()
    rul_prod = _gbr()
    soh_prod.fit(frame[list(SOH_FEATURE_COLUMNS)].to_numpy(dtype=np.float32), frame["soh"].to_numpy(dtype=float))
    rul_prod.fit(frame[list(RUL_FEATURE_COLUMNS)].to_numpy(dtype=np.float32), frame["rul"].to_numpy(dtype=float))

    model_dir.mkdir(parents=True, exist_ok=True)
    soh_path = model_dir / "soh.onnx"
    rul_path = model_dir / "rul.onnx"
    export_sklearn(soh_prod, len(SOH_FEATURE_COLUMNS), soh_path)
    export_sklearn(rul_prod, len(RUL_FEATURE_COLUMNS), rul_path)

    x_soh = test[list(SOH_FEATURE_COLUMNS)].to_numpy(dtype=np.float32)
    x_rul = test[list(RUL_FEATURE_COLUMNS)].to_numpy(dtype=np.float32)
    # Verify ONNX against the *production* model (same weights we shipped).
    soh_check = verify_onnx(soh_path, x_soh[:32], soh_prod.predict(x_soh[:32]))
    rul_check = verify_onnx(rul_path, x_rul[:32], rul_prod.predict(x_rul[:32]))

    spec = feature_spec(
        soh_input=soh_check["inputName"],
        rul_input=rul_check["inputName"],
        soh_output=soh_check["outputName"],
        rul_output=rul_check["outputName"],
        n_rows=int(len(frame)),
        batteries=sorted(frame["battery_id"].unique().tolist()),
    )
    (model_dir / "feature_spec.json").write_text(json.dumps(spec, indent=2))

    def soh_predict(x):
        return soh_prod.predict(x)

    def rul_predict(x):
        return rul_prod.predict(x)

    noise = noise_robustness(records, soh_predict=soh_predict, rul_predict=rul_predict)

    def _fit_gbr(x, y):
        model = _gbr()
        model.fit(x, y)
        return model

    honesty = production_honesty_report(frame, fit=_fit_gbr, predict=_predict_any)

    metrics = {
        "citation": NASA_CITATION,
        "eolCapacityFraction": EOL_CAPACITY_FRACTION,
        "eolDefinition": (
            "Remaining useful life is cycles until discharge capacity falls to "
            "70% of rated capacity (NASA PCoE official stop criterion: 2.0 Ah → 1.4 Ah). "
            "An 80% OEM warranty threshold is also documented in feature_spec.json."
        ),
        "nRows": int(len(frame)),
        "batteries": sorted(frame["battery_id"].unique().tolist()),
        "holdoutBattery": str(test["battery_id"].iloc[0]),
        "soh": soh_report,
        "rul": rul_report,
        "productionModel": {
            "type": PRODUCTION_FAMILY,
            "family": PRODUCTION_FAMILY,
            "fitScope": PRODUCTION_FIT_SCOPE,
            "holdoutMetricsFitScope": HOLDOUT_METRICS_FIT_SCOPE,
            "applicability": APPLICABILITY,
            "reason": (
                "GBR converts reliably through skl2onnx and matches ONNX Runtime on Linux/.NET. "
                "XGBoost and a PyTorch MLP are trained for comparison; see soh/rul reports. "
                "soh.onnx and rul.onnx are the all-rows fit. Hold-out and leave-one-battery-out "
                "blocks are a different fit that excludes the scored cell."
            ),
            "onnxVerification": {"soh": soh_check, "rul": rul_check},
        },
        "eolCensoring": honesty["eolCensoring"],
        "rulNestedSoh": honesty["rulNestedSoh"],
        "featureAblations": honesty["featureAblations"],
        "noiseRobustness": noise,
        "bestSohByHoldoutRmse": _pick_best(soh_report),
        "bestRulByHoldoutRmse": _pick_best(rul_report),
    }
    (model_dir.parent / "metrics.json").write_text(json.dumps(metrics, indent=2))
    frame.to_csv(processed_dir / "features.csv", index=False)
    return metrics


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train BatteryHealth SoH/RUL models and export ONNX")
    parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--raw", type=Path, default=None)
    parser.add_argument("--models", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--holdout", default="B0018")
    args = parser.parse_args(argv)
    metrics = train_and_export(
        processed_dir=args.processed,
        raw_dir=args.raw,
        model_dir=args.models,
        holdout=args.holdout,
    )
    print(json.dumps({k: metrics[k] for k in ("nRows", "batteries", "bestSohByHoldoutRmse", "bestRulByHoldoutRmse")}, indent=2))
    print("SoH hold-out", metrics["soh"].get("gbr", {}).get("holdout"))
    print("RUL hold-out", metrics["rul"].get("gbr", {}).get("holdout"))
    print("Wrote", args.models)


if __name__ == "__main__":
    main()
