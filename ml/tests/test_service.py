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
