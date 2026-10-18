"""#10: every /api route the web app calls declares a response model (or is exempt for a stated reason).

The route list is read from the web sources, not hard-coded: a new `api("/api/...")` call in
web/src whose route has no `responses={200: {"model": ...}}` fails here until it gets a model in
src/api_models.py or an entry in EXEMPT below. Literals that match no route (URLs built by a
helper such as `one(id)`) are ignored, so the check can miss a route but cannot fail on a typo.
"""
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "src"

# (method, path) -> why no JSON model fits. Keep reasons honest; add a model instead when a body exists.
EXEMPT = {
    ("post", "/api/activity/{activity_id}/race"): "204 No Content, no body",
    ("get", "/api/download/zwo/{filename}"): "file download",
    ("get", "/api/workout/download/{filename}"): "file download",
    ("get", "/api/export/backup"): "file download (tar.gz)",
    ("get", "/api/export/fit-workout"): "file download (FIT)",
    ("get", "/api/export/{table}.csv"): "file download (CSV)",
    ("get", "/api/programme/summary/png"): "image",
    ("get", "/api/rides/{ride_id}/fit"): "file download (FIT)",
    ("get", "/api/swim/sessions/{session_id}/text"): "file download (plain text)",
    ("get", "/api/run/sessions/{session_id}/download"): "file download (FIT or plain text)",
}

_QUOTE = re.compile(r"(?<![\w/])([\"'`])(/api/)")
_TEMPLATE_EXPR = re.compile(r"\$\{(?:[^{}]|\{[^{}]*\})*\}")


def _literals():
    """Yield (method, path-with-X-for-${...}, source file) for each /api literal in the web sources."""
    for f in WEB.rglob("*"):
        if f.suffix not in (".ts", ".tsx") or ".test." in f.name or f.name == "schema.d.ts":
            continue
        t = f.read_text(encoding="utf-8")
        for m in _QUOTE.finditer(t):
            q, i, depth, j = m.group(1), m.start() + 1, 0, m.start() + 1
            while j < len(t):                      # find the closing quote, skipping ${...} in templates
                if q == "`" and t[j] == "$" and t[j + 1:j + 2] == "{":
                    depth, j = depth + 1, j + 2
                    continue
                if depth and t[j] == "}":
                    depth -= 1
                elif not depth and t[j] == q:
                    break
                j += 1
            path = _TEMPLATE_EXPR.sub("X", t[i:j]).split("?")[0]
            # the method option sits in the same call, before the next URL or declaration
            window = re.split(r"/api/|\nexport |\nconst |\nfunction ", t[j:j + 300])[0]
            mm = re.search(r"method:\s*[\"'](\w+)", window)
            yield (mm.group(1).lower() if mm else "get"), path, f.name


def _openapi():
    os.environ.setdefault("SHEPHERD_HOME", tempfile.mkdtemp(prefix="domestique-inventory-"))
    import app as app_module
    return app_module.app.openapi()["paths"]


def _has_model(op: dict) -> bool:
    schema = op.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
    return "$ref" in schema or "$ref" in schema.get("items", {})


def test_every_ui_route_has_a_response_model_or_a_stated_exemption():
    paths = _openapi()
    templates = [(p, re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "$")) for p in paths]
    seen, untyped = set(), []
    for method, lit, fname in _literals():
        for p, rx in templates:
            if method in paths[p] and rx.match(lit):
                seen.add((method, p))
                if not _has_model(paths[p][method]) and (method, p) not in EXEMPT:
                    untyped.append(f"{method.upper()} {p} (called from {fname})")
    assert len(seen) > 100, f"scanner found only {len(seen)} UI routes; the pattern probably broke"
    assert not untyped, ("UI routes without a response model; add one to src/api_models.py and attach it with "
                         "responses={200: {'model': ...}}, or add an EXEMPT entry with a reason:\n  " + "\n  ".join(sorted(set(untyped))))


def test_exemptions_are_real_routes_without_a_model():
    paths = _openapi()
    for (method, p), why in EXEMPT.items():
        assert p in paths and method in paths[p], f"stale exemption {method.upper()} {p} ({why}): route is gone"
        assert not _has_model(paths[p][method]), f"{method.upper()} {p} now has a model; drop its exemption"
