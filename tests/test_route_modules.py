"""Feature routes in src/routes_*.py are included without editing app.py."""
from fastapi.testclient import TestClient


def test_a_routes_module_is_served():
    import app
    assert TestClient(app.app).get("/api/_routes_loaded").json() == {"ok": True}
