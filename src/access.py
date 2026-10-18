"""Access control for network-exposed (server) deployments (#13).

Desktop use is unchanged: with no token configured nothing here gates a
request. A server deployment sets SHEPHERD_SERVER_MODE=1, which makes the
app refuse to start without SHEPHERD_ACCESS_TOKEN (fail closed).

Boundary: when a token is configured, EVERY route except /login, /logout and
/healthz needs either ``Authorization: Bearer <token>`` or the session cookie
issued by POST /login. The check ignores the peer address and forwarding
headers, so a reverse proxy or an apparent loopback peer cannot bypass it.
This is a single shared secret for a personal server, not user accounts.
"""
from __future__ import annotations
import envcompat  # noqa: F401  (old DOMESTIQUE_* names -> SHEPHERD_*, before anything reads them)

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque

COOKIE = "shepherd_session"
OPEN_PATHS = ("/login", "/logout", "/healthz")
MIN_TOKEN_LEN = 24                  # server mode refuses shorter tokens (#152)
SESSION_MAX_AGE = 30 * 24 * 3600    # enforced server-side, not just by the browser (#152)
MAX_FAILURES = 5                    # wrong credentials allowed per client ...
FAILURE_WINDOW = 60.0               # ... per this many seconds, then 429 (#152)


def server_mode() -> bool:
    return os.environ.get("SHEPHERD_SERVER_MODE", "").strip().lower() in ("1", "true", "yes")


def configured_token() -> str:
    return os.environ.get("SHEPHERD_ACCESS_TOKEN", "").strip()


def trusted_origins() -> frozenset[str]:
    """Exact origins (scheme://host[:port]) allowed to make mutating requests,
    in addition to loopback. SHEPHERD_TRUSTED_ORIGINS, comma separated."""
    raw = os.environ.get("SHEPHERD_TRUSTED_ORIGINS", "")
    return frozenset(o.strip().rstrip("/").lower() for o in raw.split(",") if o.strip())


def origin_allowed(origin: str, loopback_prefixes: tuple[str, ...]) -> bool:
    if origin.startswith(loopback_prefixes):
        return True
    return origin.rstrip("/").lower() in trusted_origins()


def session_value(token: str, issued_at: float | None = None) -> str:
    """Cookie value ``<issued-at>.<hmac>``: signed with the token, never contains it."""
    iat = f"{time.time() if issued_at is None else issued_at:.3f}"
    return f"{iat}.{_sign(token, iat)}"


def _sign(token: str, iat: str) -> str:
    return hmac.new(token.encode(), f"shepherd-session-v2:{iat}".encode(), hashlib.sha256).hexdigest()


def _valid_after_file():
    from user_home import shepherd_home
    return shepherd_home() / "sessions_valid_after"


def sessions_valid_after() -> float:
    try:
        return float(_valid_after_file().read_text().strip())
    except (OSError, ValueError):
        return 0.0


def revoke_all_sessions() -> None:
    """Sign out everywhere: every cookie issued up to now stops working."""
    from atomic_io import write_text_atomic
    write_text_atomic(_valid_after_file(), f"{time.time():.3f}")


def _cookie_ok(token: str, cookie: str) -> bool:
    iat, _, sig = cookie.rpartition(".")
    if not hmac.compare_digest(sig.encode(), _sign(token, iat).encode()):
        return False
    try:
        issued = float(iat)
    except ValueError:
        return False
    return issued > sessions_valid_after() and time.time() - issued <= SESSION_MAX_AGE


def has_bearer(authorization: str) -> bool:
    return authorization.lower().startswith("bearer ")


def is_authorized(token: str, authorization: str, cookie: str) -> bool:
    if has_bearer(authorization):
        if hmac.compare_digest(authorization[7:].strip().encode(), token.encode()):
            return True
    return bool(cookie) and _cookie_ok(token, cookie)


# ponytail: in-memory, per client address; behind a reverse proxy every rider shares
# one address, which only makes it stricter. Persist/key by header if that ever bites.
_failures: dict[str, deque] = defaultdict(deque)


def retry_after(client: str, now: float | None = None) -> int:
    """Seconds until ``client`` may try again; 0 when not throttled."""
    now = time.monotonic() if now is None else now
    q = _failures[client]
    while q and now - q[0] > FAILURE_WINDOW:
        q.popleft()
    if not q:
        _failures.pop(client, None)
        return 0
    return int(FAILURE_WINDOW - (now - q[0])) + 1 if len(q) >= MAX_FAILURES else 0


def record_failure(client: str, now: float | None = None) -> None:
    _failures[client].append(time.monotonic() if now is None else now)


def clear_failures(client: str) -> None:
    _failures.pop(client, None)


def check_startup() -> None:
    if server_mode() and not configured_token():
        raise RuntimeError(
            "SHEPHERD_SERVER_MODE is set but SHEPHERD_ACCESS_TOKEN is empty: "
            "refusing to start a network-exposed server without access control."
        )
    if server_mode() and len(configured_token()) < MIN_TOKEN_LEN:
        raise RuntimeError(
            f"SHEPHERD_ACCESS_TOKEN is shorter than {MIN_TOKEN_LEN} characters: refusing to "
            "start a network-exposed server with a guessable token (try: openssl rand -hex 32)."
        )
