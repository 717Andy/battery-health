from batteryhealth.service.app import app


def test_fastapi_app_metadata():
    assert app.title.startswith("BatteryHealth")
    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/health" in routes
    assert "/predict/soh" in routes
    assert "/predict/rul" in routes
    assert "/simulate/stress" in routes
    assert "/workspace/forecast" in routes
    assert "/demo/{battery_id}" in routes


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


def test_demo_ui_and_tiny_forecast():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200
    assert b"BatteryHealth" in home.content
    demo = client.get("/demo/tiny")
    assert demo.status_code == 200
    payload = demo.json()
    assert payload["summary"]["batteryId"] == "B0005"
    battery = payload["battery"]
    forecast = client.post("/workspace/forecast", json={"battery": battery, "cycle_index": 1})
    assert forecast.status_code == 200
    body = forecast.json()
    assert 0.7 < body["predictedSoh"] < 1.1
    assert body["predictedRulCycles"] > 0
    sim = client.post(
        "/simulate/stress",
        json={"battery": battery, "ambient_temperature_c": 45, "discharge_c_rate": 2, "current_cycle": 1},
    )
    assert sim.status_code == 200
    stressed = sim.json()
    assert stressed["accelerationFactor"] > 1
    assert stressed["stressedRulCycles"] <= stressed["baselineRulCycles"]


def test_calce_demo_parses():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    demo = client.get("/demo/calce")
    assert demo.status_code == 200
    summary = demo.json()["summary"]
    assert summary["source"] == "calce"
    assert summary["nCycles"] >= 1
