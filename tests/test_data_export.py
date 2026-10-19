"""CSV and backup downloads (#129)."""
import csv
import io
import tarfile

import pytest
from fastapi.testclient import TestClient

import data_export
import db


def test_csv_has_the_named_columns_and_keeps_formula_text_inert():
    rows = [{"id": "a1", "date": "2026-01-02", "name": "=HYPERLINK(\"x\")", "sport": "Run", "tss": 55.5, "raw_json": "{}"}]
    out = list(csv.DictReader(io.StringIO(data_export.to_csv("activities", rows))))
    assert out[0]["name"] == "'=HYPERLINK(\"x\")" and out[0]["tss"] == "55.5" and "raw_json" not in out[0]
    assert data_export.to_csv("wellness", []).startswith("date,ctl,atl")
    with pytest.raises(ValueError):
        data_export.to_csv("nope", [])


def test_endpoints_download_csv_and_a_secret_free_backup():
    import app
    c = TestClient(app.app)
    db.upsert_daily_log("2026-01-05", 3, 3, 3, 3, 3, notes="+cmd")
    r = c.get("/api/export/checkins.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "'+cmd" in r.text and "attachment" in r.headers["content-disposition"]
    assert c.get("/api/export/activities.csv").text.startswith("id,date,name")
    assert c.get("/api/export/secrets.csv").status_code == 404
    b = c.get("/api/export/backup")
    assert b.status_code == 200 and b.headers["content-type"] == "application/gzip"
    with tarfile.open(fileobj=io.BytesIO(b.content)) as t:
        assert "manifest.json" in t.getnames() and not any(n.endswith((".env", "llm.json")) for n in t.getnames())


def test_backup_upload_is_staged_and_applied_at_startup(tmp_path, monkeypatch):
    import json

    import backup
    from fastapi.testclient import TestClient

    import app
    home = tmp_path / "home"
    prof = home / "profiles" / "default"
    prof.mkdir(parents=True)
    (prof / "athlete.json").write_text(json.dumps({"ftp": 251}))
    archive = tmp_path / "b.tar.gz"
    backup.create_backup(home, archive, exclude_secrets=True)
    (prof / "athlete.json").write_text(json.dumps({"ftp": 100}))
    (prof / ".env").write_text("ICU_ACCESS_TOKEN=keep-me\n")
    monkeypatch.setattr("routes_backup.shepherd_home", lambda: home)
    c = TestClient(app.app)
    assert c.get("/api/import/backup").json()["pending"] is False
    bad = c.post("/api/import/backup", files={"file": ("x.tar.gz", b"not a tarball")})
    assert bad.status_code == 400 and not (home / backup.PENDING).exists() and not list(home.glob("*.part"))
    ok = c.post("/api/import/backup", files={"file": ("b.tar.gz", archive.read_bytes())})
    assert ok.status_code == 200 and ok.json()["pending"] and ok.json()["secrets_excluded"]
    assert json.loads((prof / "athlete.json").read_text())["ftp"] == 100      # nothing changes until restart
    assert c.get("/api/import/backup").json()["pending"]
    assert c.delete("/api/import/backup").json()["pending"] is False and not (home / backup.PENDING).exists()
    c.post("/api/import/backup", files={"file": ("b.tar.gz", archive.read_bytes())})
    (home / ".lock").write_text("")
    assert backup.apply_pending(home)["data_format"] == 1                      # the next start
    assert json.loads((prof / "athlete.json").read_text())["ftp"] == 251
    assert (prof / ".env").read_text() == "ICU_ACCESS_TOKEN=keep-me\n"          # keys survive a keyless backup
    assert (home / ".lock").exists() and not (home / backup.PENDING).exists()
    assert backup.apply_pending(home) is None
