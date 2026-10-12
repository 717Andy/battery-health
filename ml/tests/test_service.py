from batteryhealth.service.app import app


def test_fastapi_app_metadata():
    assert app.title.startswith("BatteryHealth")
    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/health" in routes
    assert "/predict/soh" in routes
    assert "/predict/rul" in routes
    assert "/simulate/stress" in routes


def test_health_and_metrics_endpoints():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["holdoutBattery"] == "B0018"
    assert body["nRows"] == 636
    prod = body["productionModel"]
    assert prod["fitScope"] == "all-rows"
    assert prod["holdoutMetricsFitScope"] == "holdout-excluded"
    assert body["noiseRobustness"]["0.0"]["scope"] == "in-sample"
    assert "B0007" in body["eolCensoring"]["censoredBatteries"]
    assert body["rulNestedSoh"]["fitScope"] == "holdout-excluded"
    assert "pooledExcludingCensored" in body["rulNestedSoh"]
    assert "dropEnergyAndDuration" in body["featureAblations"]["soh"]
    assert "dropCycleIndex" in body["featureAblations"]["rul"]


def test_upload_rejects_client_paths_and_oversize_bodies(monkeypatch):
    from pathlib import Path

    from fastapi.testclient import TestClient

    import batteryhealth.service.app as service

    client = TestClient(app)
    rejected = client.post(
        "/parse/nasa",
        files={"file": ("../../etc/passwd", b"nope", "application/octet-stream")},
    )
    assert rejected.status_code == 400

    captured: dict = {}

    def _capture(data: bytes, suffix: str) -> Path:
        captured["suffix"] = suffix
        captured["data"] = data
        path = Path("/tmp/batteryhealth-unit-upload.mat")
        path.write_bytes(data)
        return path

    monkeypatch.setattr(service, "write_temp", _capture)
    monkeypatch.setattr(service, "parse_nasa_mat", lambda path: {"ok": True})
    accepted = client.post(
        "/parse/nasa",
        files={"file": ("../../tmp/evil.mat", b"payload", "application/octet-stream")},
    )
    assert accepted.status_code == 200
    assert captured["suffix"] == ".mat"
    assert captured["data"] == b"payload"

    monkeypatch.setattr(service, "MAX_UPLOAD_BYTES", 4)
    oversized = client.post(
        "/parse/calce",
        files={"file": ("log.csv", b"0123456789", "text/csv")},
    )
    assert oversized.status_code == 413
