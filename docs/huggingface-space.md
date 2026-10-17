# Hugging Face Space (Docker)

The browser demo is a FastAPI app. Hugging Face Spaces with `sdk: docker` run the
`Dockerfile` at the repo root and listen on **port 7860**.

Runtime data:

- `artifacts/models/soh.onnx` and `rul.onnx` (committed)
- `artifacts/metrics.json` (honest hold-out / LOBO numbers shown on Forecast)
- `tests/fixtures/B0005.sample.json`, `tiny_battery.json`, `calce_sample.csv`

The Space **does not** download the NASA PCoE zip (~210 MB). Retraining still
uses `python -m batteryhealth.download` on a machine that wants the full cells.

## Run locally (same image the Space uses)

```bash
docker build -t batteryhealth-demo .
docker run --rm -p 7860:7860 batteryhealth-demo
# open http://127.0.0.1:7860
```

Without Docker:

```bash
python -m pip install -r ml/requirements-space.txt
PYTHONPATH=ml python -m batteryhealth.service.app --host 127.0.0.1 --port 8765
```

## One-command deploy (needs `HF_TOKEN`)

This repo is packaged for Spaces. Publishing requires a Hugging Face write
token; this environment does not have one.

```bash
python -m pip install huggingface_hub
HF_TOKEN=hf_xxx python scripts/deploy_hf_space.py
```

That creates (or updates) `https://huggingface.co/spaces/717Andy/battery-health`
unless you override `HF_SPACE_ID=your-user/battery-health`.

Space metadata lives in the YAML frontmatter of `README.md` (`sdk: docker`,
`app_port: 7860`). After the first upload, Hugging Face builds the Dockerfile.
The first build takes a few minutes; later pushes rebuild from cache.
