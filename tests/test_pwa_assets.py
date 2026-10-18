"""The installable-app files in web/public are served under /v2 with usable types and scope (#130)."""
import json
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web_spa import mount_spa

WEB = Path(__file__).resolve().parent.parent / "web"


def _client(tmp_path):
    shutil.copytree(WEB / "public", tmp_path, dirs_exist_ok=True)
    shutil.copy(WEB / "index.html", tmp_path / "index.html")
    app = FastAPI()
    assert mount_spa(app, tmp_path)
    return TestClient(app)


def test_manifest_is_installable(tmp_path):
    c = _client(tmp_path)
    r = c.get("/v2/manifest.webmanifest")
    assert r.status_code == 200 and "manifest+json" in r.headers["content-type"]
    m = r.json()
    assert m["name"] == "Shepherd" and m["display"] == "standalone"
    assert m["start_url"].startswith("/v2/") and m["scope"] == "/v2/"
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(i.get("purpose") == "maskable" for i in m["icons"])
    for i in m["icons"]:
        icon = c.get("/v2/" + i["src"])
        assert icon.status_code == 200 and icon.headers["content-type"] == "image/png", i["src"]


def test_service_worker_is_served_from_inside_its_scope(tmp_path):
    r = _client(tmp_path).get("/v2/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    # Served at /v2/sw.js, so its default scope is /v2/ and no Service-Worker-Allowed header is needed.
    assert "/api" in r.text  # the guard that keeps API requests out of the cache (behaviour: web/src/lib/pwa.test.ts)


def test_page_links_the_manifest_with_credentials():
    html = (WEB / "index.html").read_text()
    assert 'rel="manifest"' in html and 'crossorigin="use-credentials"' in html
    assert 'name="theme-color"' in html
    json.loads((WEB / "public" / "manifest.webmanifest").read_text())
