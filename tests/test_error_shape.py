"""#10 — a refused request carries its sentence in `error` and `detail`."""
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as app_module


def test_http_exception_body_has_error_and_detail():
    @app_module.app.get("/api/_test_refuse")
    def _refuse():
        raise HTTPException(status_code=400, detail="bad thing")

    try:
        r = TestClient(app_module.app).get("/api/_test_refuse")
    finally:
        app_module.app.router.routes.pop()
    assert r.status_code == 400
    assert r.json() == {"error": "bad thing", "detail": "bad thing"}


def test_unknown_route_404_has_error_and_detail():
    r = TestClient(app_module.app).get("/api/definitely-not-a-route")
    assert r.status_code == 404
    assert r.json()["error"] == r.json()["detail"]
