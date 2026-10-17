from batteryhealth.service.app import app


def test_fastapi_app_metadata():
    assert app.title.startswith("BatteryHealth")
    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/health" in routes
    assert "/predict/soh" in routes
    assert "/predict/rul" in routes
    assert "/simulate/stress" in routes
    assert "/workspace/forecast" in routes
    assert "/workspace/export" in routes
    assert "/demo/{battery_id}" in routes
    assert "/workspace/copy" in routes


def test_health_and_metrics_endpoints():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    body_health = health.json()
    assert body_health["status"] == "ok"
    assert body_health["downloadsNasaZip"] is False
    assert body_health["demoData"] == "bundled-fixtures"
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


def test_demo_ui_and_tiny_forecast():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200
    assert b"BatteryHealth" in home.content
    assert b"Export CSV and JSON" in home.content
    assert b"/static/chart.umd.min.js" in home.content
    assert b"cdn.jsdelivr.net" not in home.content
    chart = client.get("/static/chart.umd.min.js")
    assert chart.status_code == 200
    assert len(chart.content) > 50_000
    demo = client.get("/demo/tiny")
    assert demo.status_code == 200
    payload = demo.json()
    assert payload["summary"]["batteryId"] == "B0005"
    assert payload["summary"]["intakeLines"]
    battery = payload["battery"]
    forecast = client.post("/workspace/forecast", json={"battery": battery, "cycle_index": 1})
    assert forecast.status_code == 200
    body = forecast.json()
    assert 0.7 < body["predictedSoh"] < 1.1
    assert body["predictedRulCycles"] > 0
    assert "fadeRulTo70Cycles" in body
    assert "fadeRulTo80Cycles" in body
    sim = client.post(
        "/simulate/stress",
        json={"battery": battery, "ambient_temperature_c": 45, "discharge_c_rate": 2, "current_cycle": 1},
    )
    assert sim.status_code == 200
    stressed = sim.json()
    assert stressed["accelerationFactor"] > 1
    assert stressed["stressedRulCycles"] <= stressed["baselineRulCycles"]
    exported = client.post(
        "/workspace/export",
        json={
            "battery": battery,
            "cycle_index": 1,
            "ambient_temperature_c": 45,
            "discharge_c_rate": 2,
        },
    )
    assert exported.status_code == 200
    report = exported.json()
    assert "cycle_index,measured_capacity_ah" in report["csv"]
    assert report["json"]["decision"]["cycle"] == 1
    assert report["csvName"].endswith(".csv")
    catalog = client.get("/demo")
    assert catalog.status_code == 200
    listed = {item["id"] for item in catalog.json()["demos"]}
    assert {"B0005", "tiny", "calce"} <= listed
    assert "NASA PCoE zip is not downloaded" in catalog.json()["note"]
    copy = client.get("/workspace/copy")
    assert copy.status_code == 200
    assert "Typical miss" in (copy.json()["typicalError"] or "")
    assert "does not fetch the NASA PCoE zip" in copy.json()["demoNote"]
    b0005 = client.get("/demo/B0005")
    assert b0005.status_code == 200
    assert b0005.json()["summary"]["batteryId"] == "B0005"


def test_calce_demo_parses():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    demo = client.get("/demo/calce")
    assert demo.status_code == 200
    summary = demo.json()["summary"]
    assert summary["source"] == "calce"
    assert summary["nCycles"] >= 1
    assert summary["nameplateAssumed"] is True
