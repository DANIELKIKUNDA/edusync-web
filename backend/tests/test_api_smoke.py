from fastapi.testclient import TestClient

from edusync.bootstrap.app import create_app

client = TestClient(create_app())


def test_health_point4d_without_database_connection():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "lot": "POINT-4D-EFFECTIFS-DEPOTS"}


def test_atelier_pro_requires_real_bearer_not_dev_header():
    assert client.get("/api/v1/platform/schools").status_code == 401
    assert client.get("/api/v1/platform/schools", headers={"X-Platform-Admin": "web0a-dev-platform-admin"}).status_code == 401


def test_openapi_exposes_auth_and_platform_routes():
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/platform/schools" in paths
    assert "/api/v1/effectifs/overview" in paths
    assert "/api/v1/effectifs/counts" in paths
