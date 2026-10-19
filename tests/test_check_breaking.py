"""tools/check_breaking.py flags removed routes, fields and SHEPHERD_* variables."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_breaking", Path(__file__).resolve().parent.parent / "tools" / "check_breaking.py"
)
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)


def test_routes_and_fields_lists_methods_and_properties():
    contract = {
        "paths": {"/api/a": {"get": {}, "post": {}}},
        "components": {"schemas": {"A": {"properties": {"x": {}, "y": {}}}}},
    }
    routes, fields = cb.routes_and_fields(contract)
    assert routes == {"GET /api/a", "POST /api/a"}
    assert fields == {"A.x", "A.y"}


def test_nothing_removed_against_head():
    assert not any(cb.removed("HEAD").values())


def test_decorated_routes_include_untyped_routes():
    routes = cb.decorated_routes()
    assert "GET /api/version" in routes
