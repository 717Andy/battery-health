# BatteryHealth

Windows desktop diagnostics for **fleet managers and EV battery engineers**. BatteryHealth loads lithium-ion aging logs, plots charge/discharge sensor curves, estimates **State of Health (SoH)** and **Remaining Useful Life (RUL)**, and lets you scrub virtual ambient temperature and discharge C-rate to see how the fade curve moves.

This is a **local** tool. Inference runs in-process through ONNX Runtime. A small Python sidecar is optional for parsing raw NASA `.mat` files and for anything the shipped ONNX graphs do not cover.

## What is in this repo

| Path | Role |
| --- | --- |
| `ml/` | Python: NASA download/parse, CALCE CSV/Excel parse, per-cycle features, training, evaluation (incl. sensor noise), ONNX export, FastAPI sidecar |
| `src/BatteryHealth.Core/` | Cross-platform .NET 8 library: domain, parsers, feature math, ONNX wrapper, Arrhenius/C-rate stress model |
| `src/BatteryHealth.Cli/` | Linux/Windows CLI used to verify Core on this VM |
| `src/BatteryHealth.App/` | WinUI 3 / Windows App SDK desktop app (Fluent, MVVM) |
| `tests/` | xUnit for Core; compact NASA/CALCE fixtures |
| `artifacts/models/` | Shipped `soh.onnx`, `rul.onnx`, `feature_spec.json` |

Raw NASA `.mat` files are **not** committed (~56 MB for B0005–B0018). Use the download script.

## End-of-life definition

NASA Ames PCoE stopped these 2.0 Ah 18650 cells at **30% capacity fade** — **70% of rated capacity (1.4 Ah)**. That is the default RUL target and the label used to train the shipped models.

The app also documents the common **80% OEM / warranty** line. Toggling it on the Forecast page estimates RUL from the measured fade curve to 1.6 Ah; the ONNX RUL head itself remains a 70%-EOL model.

Citation: B. Saha and K. Goebel (2007). “Battery Data Set”, NASA Prognostics Data Repository, NASA Ames Research Center, Moffett Field, CA.

## Architecture

```
NASA .mat ──► Python parser ──► canonical JSON + features.csv
CALCE CSV/XLSX ──► Python or Core parser ──┘
                         │
          train.py ──► soh.onnx / rul.onnx
                         │
         BatteryHealth.Core (ONNX Runtime + stress math)
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
     BatteryHealth.Cli      BatteryHealth.App (WinUI 3)
              │
              └── optional FastAPI :8765  (parse .mat, extra tools)
```

**Charting:** the pitch mentioned OxyPlot.Windows. That package targets UWP / WinUI 2 and does not officially support WinUI 3. The desktop app uses **LiveCharts2** (`LiveChartsCore.SkiaSharpView.WinUI`) for Cartesian plots. Core stays chart-agnostic.

**Models:** scikit-learn Gradient Boosting (with a StandardScaler) is what we export to ONNX — `skl2onnx` + .NET ONNX Runtime agreed to ~1e-7 (SoH) / ~1e-5 (RUL). XGBoost is trained for comparison and won the SoH hold-out by a small margin. A PyTorch MLP path is in `ml/batteryhealth/train.py` and is used when `torch` is installed.

## Model results (measured on this VM)

Training set: NASA B0005, B0006, B0007, B0018 — **636 discharge cycles**. Hold-out cell: **B0018** (132 cycles). Also reported: leave-one-battery-out (LOBO).

The tables below are **hold-out-excluded** fits: the scored cell was not in that fit. The files in `artifacts/models/` are a **separate all-rows fit** of the same gradient-boosting pipeline. The forecast page states that difference. `artifacts/metrics.json` also records a nested SoH→RUL leave-one-battery-out (predicted SoH fed into RUL, which is the inference graph), ablations that drop `energy_wh`+`duration_s` and `cycle_index`, and an `eolCensoring` flag. B0007 never reaches 1.4 Ah, so its RUL labels are right-censored and are left out of `pooledExcludingCensored`.

### SoH (fraction of 2.0 Ah; features are curve stats only — no capacity column)

| Model | B0018 RMSE | B0018 MAE | B0018 R² | LOBO pooled RMSE |
| --- | ---: | ---: | ---: | ---: |
| Ridge + scaler | 0.0021 | 0.0018 | 0.999 | 0.0054 |
| Gradient boosting (shipped ONNX) | 0.0067 | 0.0059 | 0.992 | 0.0141 |
| XGBoost | **0.0053** | 0.0045 | 0.995 | 0.0144 |

Ridge is unusually strong because `energy_wh` and `duration_s` are near-linear proxies for delivered capacity on this constant-current protocol. That is expected, not a label leak: capacity itself is not a model input. We still ship GBR so the desktop graph matches the tree-model story and converts cleanly to ONNX.

### RUL (cycles until 70% / 1.4 Ah)

| Model | B0018 RMSE | B0018 MAE | B0018 R² | LOBO pooled RMSE |
| --- | ---: | ---: | ---: | ---: |
| Ridge + scaler | 20.2 | 19.2 | 0.60 | 26.4 |
| **Gradient boosting (shipped ONNX)** | **8.54** | **6.64** | **0.93** | 21.8 |
| XGBoost | 8.59 | 6.39 | 0.93 | 22.1 |

B0007 never quite reaches 1.4 Ah (last measured 1.43 Ah), so its 70% RUL labels are right-censored at the last cycle. That cell dominates LOBO error. B0005 / B0018 transfer well (~8 cycle RMSE).

ONNX vs sklearn on 32 hold-out rows: SoH max \|Δ\| = 1.1×10⁻⁷, RUL max \|Δ\| = 1.2×10⁻⁵.

### Robustness to added sensor noise

Features are recomputed after i.i.d. Gaussian noise at *σ = f × channel std* on voltage, current, and temperature (production GBR, all 636 cycles). The *f = 0* row is **in-sample**: the shipped model scored on the cycles it was fit on, not a hold-out.

| Noise *f* | SoH RMSE | RUL RMSE |
| ---: | ---: | ---: |
| 0 | 0.0011 | 2.83 |
| 1% | 0.0013 | 3.79 |
| 2% | 0.0015 | 5.19 |
| 5% | 0.0021 | 10.3 |

SoH stays stable. RUL degrades more once voltage-crossing times (`time_to_3v5` / `time_to_3v0`) jitter.

### Core inference check (same ONNX, .NET)

On the 3-cycle B0005 fixture, cycle 1: predicted SoH **0.9276** vs measured **0.9282**; predicted RUL **120** cycles. Stress at 45 °C / 2C from cycle 40 on the demo fade curve: acceleration factor **5.50**, RUL **85 → 19** cycles.

## Stress simulator

Mirrored in Python (`ml/batteryhealth/simulate.py`) and C# (`DegradationSimulator`):

- Temperature: Arrhenius, \(A_T = \exp\left[\frac{E_a}{k}\left(\frac{1}{T_\mathrm{ref}}-\frac{1}{T}\right)\right]\), \(E_a = 0.50\,\mathrm{eV}\), \(T_\mathrm{ref} = 24\,^\circ\mathrm{C}\) (NASA room-temp protocol).
- C-rate: \((C / 1\mathrm{C})^{0.60}\).
- Remaining fade after the selected cycle is multiplied by \(A_T \cdot A_C\). This is a **scenario overlay**. Ea and the C-rate exponent were not identified on the NASA cells, and the simulator says so.

## Compared with the products in the pitch

**Voltaiq** is an enterprise cloud battery-intelligence platform sold to automotive OEMs. It is built for fleet-scale ingestion, collaboration, and compliance. BatteryHealth is the opposite shape: a fast local desktop diagnostic you can run on a laptop, with inspectable models and published hold-out numbers. No account, no upload of cell data.

**Ansys Twin Builder (battery aging)** is a physics-based simulation stack (electrochemical / thermal FEM). It is the right tool when you are designing a pack and have material parameters. BatteryHealth does not solve PDEs. It fits SoH/RUL from measured V/I/T streams and applies a closed-form acceleration model so a fleet engineer can ask “what if this route runs 15 °C hotter at 2C?” in well under a second.

## Verified on the Linux build VM vs written but unverified

**Verified here (Ubuntu, Python 3.12, .NET 8.0.425):**

- Downloaded the official NASA PCoE zip and parsed B0005 / B0006 / B0007 / B0018
- Feature tables, training, LOBO, noise study, ONNX export
- `pytest` — 10 passed
- `dotnet test` on `BatteryHealth.Core.Tests` — 9 passed, including ONNX inference
- `BatteryHealth.Cli` `info` / `forecast` / `simulate` on the fixtures
- FastAPI app imports and exposes `/health`, `/predict/*`, `/simulate/stress`

**Written for Windows, not compiled or clicked on this VM:**

- Entire `src/BatteryHealth.App` WinUI 3 project (XAML, file picker, LiveCharts, Mica)
- Visual Studio designer / MSIX packaging
- Real CALCE `.xlsx` from calce.umd.edu (the CSV fixture **is** tested in Python and C#)

You need a Windows 10/11 machine with Visual Studio 2022 to build and run the desktop UI.

## Setup on Windows

### Prerequisites

1. **Windows 10 1809+ or Windows 11**
2. **Visual Studio 2022 17.8+** with workloads:
   - .NET desktop development
   - Windows application development (Windows App SDK)
3. **.NET 8 SDK**
4. **Python 3.10+** (3.12 used here)

```powershell
git clone <this-repo>
cd BatteryHealth
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ml\requirements.txt
```

Optional PyTorch MLP comparison (CPU):

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 1. Download NASA data and train (or skip — ONNX is already in git)

```powershell
$env:PYTHONPATH = "ml"
python -m batteryhealth.download
python -m batteryhealth.train
python -m pytest ml\tests -q
```

`download` pulls [NASA PCoE “5. Battery Data Set”](https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip) and writes `data/processed/B0005.json` … `B0018.json`. Retraining overwrites `artifacts/models/*.onnx`.

CALCE: drop an Arbin CSV/XLSX on the Open button, or:

```powershell
python -c "from batteryhealth.parsers.calce import parse_calce; import json; json.dump(parse_calce(r'CS2_35.xlsx', rated_capacity_ah=1.1), open(r'data/processed/CS2_35.json','w'))"
```

Typical CS2 pouch cells are ~1.1 Ah — pass `rated_capacity_ah` if you know the nameplate.

### 2. Optional Python sidecar (and Linux/browser demo)

```powershell
$env:PYTHONPATH = "ml"
python -m batteryhealth.service.app --port 8765
```

On Linux / macOS:

```bash
PYTHONPATH=ml python -m batteryhealth.service.app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765 for a browser demo of the three desktop pages (lifecycle dashboard, RUL forecast, stress simulator) running on the same ONNX graphs. The WinUI app remains the Windows desktop UI.

- `GET /health`, `GET /metrics`
- `GET /demo`, `GET /demo/B0005`, `GET /demo/calce`
- `POST /workspace/forecast`, `POST /workspace/trajectory`
- `POST /predict/soh`, `POST /predict/rul`
- `POST /simulate/stress`
- `POST /parse/nasa` (upload `.mat`), `POST /parse/calce`

The WinUI app does **not** require this process. Use it to ingest raw `.mat` files, to call the same math from another tool, or to run the browser demo on a non-Windows machine.

### 3. Build Core / CLI (any OS with .NET 8)

```powershell
dotnet test tests\BatteryHealth.Core.Tests\BatteryHealth.Core.Tests.csproj
dotnet run --project src\BatteryHealth.Cli -- forecast tests\fixtures\tiny_battery.json --cycle 1
dotnet run --project src\BatteryHealth.Cli -- simulate tests\fixtures\B0005.sample.json --temp 45 --crate 2 --cycle 40
dotnet run --project src\BatteryHealth.Cli -- export tests\fixtures\tiny_battery.json --out battery-decision.csv --temp 45 --crate 2
```

### 4. Build and run the WinUI app (Windows only)

1. Open `BatteryHealth.sln` in Visual Studio 2022.
2. Set **BatteryHealth.App** as the startup project.
3. Platform: `x64` (or `ARM64` on an ARM PC).
4. F5. The project is **unpackaged** (`WindowsPackageType=None`) and self-contained for Windows App SDK, so you should not need a separate MSIX install for local runs.

Or from a **Developer PowerShell for VS**:

```powershell
dotnet build src\BatteryHealth.App\BatteryHealth.App.csproj -c Debug -p:Platform=x64
dotnet run --project src\BatteryHealth.App\BatteryHealth.App.csproj -p:Platform=x64
```

In the app:

1. **Lifecycle dashboard** — *Load B0005 demo* or open `data/processed/B0005.json` / a CALCE file. Pick a discharge from the list (the row is that cycle index, not the nearest earlier one). Set the nameplate if the file did not carry one. The lower chart is capacity fade.
2. **RUL forecast** — predicted SoH, the model’s cycles to 70% of 2.0 Ah, the fade curve’s cycles to 70% and 80% of the nameplate, and how `energy_wh`, `duration_s`, and `time_to_3v0` moved versus the first scored discharge. Export marks that cycle and writes both 70% definitions plus the Ea 0.30 / 0.50 / 0.70 accelerations.
3. **Stress simulator** — sliders for ambient °C and C-rate; overlay stressed fade and the new RUL. The same sliders show acceleration at Ea 0.30, 0.50, and 0.70 eV. The forecast export uses the scenario last set here.

The demo JSON keeps fade for every B0005 discharge and full traces on cycles 1, 40, 80, 120, and the last cycle (to keep the file small). Processed JSON from the download script has traces for every charge and discharge.

## Feature vector

Same columns in Python and C# (`artifacts/models/feature_spec.json`):

`cycle_index`, voltage mean/std/min/max/start/end/slope, current mean/std, temperature mean/std/max/rise, `duration_s`, `energy_wh`, `time_to_3v5`, `time_to_3v0`, `ambient_temp_c`. RUL also receives `soh` (measured if the log has capacity, otherwise the SoH model’s output).

## Tests

```bash
PYTHONPATH=ml python -m pytest ml/tests -q
dotnet test BatteryHealth.Linux.slnf
# or: dotnet test tests/BatteryHealth.Core.Tests/BatteryHealth.Core.Tests.csproj
```

GitHub Actions (`.github/workflows/ci.yml`) runs those tests and a CLI `forecast` / `simulate` smoke on the fixtures. It does not retrain; the committed ONNX files are the artifact under test.

`BatteryHealth.sln` also contains the WinUI app. Restoring that `.csproj` on Linux fails with `NETSDK1100` (Windows targeting). Use the Linux solution filter above, or open the full sln only on Windows.

## License / data

NASA PCoE battery files remain NASA’s. This repo ships code, fixtures, and trained ONNX weights only.
