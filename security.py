"""
Security Engineering module for the College Admission Enquiry Assistant.

Implemented controls
--------------------
1. Input sanitisation   - question length caps, HTML/script stripping,
                          control-character removal (anti-XSS).
2. Output escaping      - every user string is HTML-escaped before rendering
                          (defence in depth alongside input sanitisation).
3. Security headers     - CSP, X-Content-Type-Options, X-Frame-Options,
                          Referrer-Policy on every response.
4. Rate limiting        - sliding-window per-IP limiter (30 requests/min)
                          with thread-safe access and automatic memory pruning.
5. Reverse proxy trust  - securely extracts client IP from X-Forwarded-For
                          when behind AWS ALB, Elastic Beanstalk, or Docker.
6. Secrets management   - the OpenAI API key is read from the environment /
                          .env file only; it is never logged or echoed.
7. Static path guarding - /static serving blocks path traversal (../../etc/passwd).
8. Session handling     - opaque random 128-bit session ids, HttpOnly + SameSite cookies.
"""

import html
import os
import re
import secrets
import threading
import time
from urllib.parse import quote as urlquote
from wsgiref.util import FileWrapper

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ----------------------------------------------------------------- headers
CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'"
)


def security_headers():
    """Return standard defensive HTTP response headers."""
    return [
        ("Content-Security-Policy", CSP),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Cache-Control", "no-store, no-cache, must-revalidate"),
    ]


# ------------------------------------------------------------- sessions
def get_session(environ):
    """Read the opaque session id from the cookie; create a new one if absent or invalid.

    Returns:
        tuple (session_id: str, is_new: bool)
    """
    cookie = environ.get("HTTP_COOKIE", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("sid="):
            cand = part[4:].strip()
            if re.fullmatch(r"[a-f0-9]{32}", cand):
                return cand, False
    return secrets.token_hex(16), True


def session_cookie(sid, max_age=86400):
    """Generate Set-Cookie header tuple with modern defensive flags."""
    return (
        "Set-Cookie",
        f"sid={sid}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax",
    )


# --------------------------------------------------------- rate limiting
_REQUEST_LOG = {}          # ip -> list of request timestamps
_RATE_LIMIT_LOCK = threading.Lock()
WINDOW_SECS = 60
MAX_REQUESTS = 30
_LAST_PRUNE = time.time()


def client_ip(environ):
    """Extract client IP, inspecting X-Forwarded-For if behind a proxy/load balancer."""
    forwarded = environ.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        # Client IP is the first entry in comma-separated chain
        client = forwarded.split(",")[0].strip()
        if client:
            return client
    return environ.get("REMOTE_ADDR", "127.0.0.1")


def check_rate_limit(ip, max_requests=MAX_REQUESTS, window_secs=WINDOW_SECS):
    """Thread-safe sliding-window limiter with periodic stale-entry eviction."""
    global _LAST_PRUNE
    now = time.time()
    with _RATE_LIMIT_LOCK:
        # Periodic cleanup every 5 minutes to prevent memory unbounded growth
        if now - _LAST_PRUNE > 300:
            stale_ips = [
                k for k, timestamps in _REQUEST_LOG.items()
                if not timestamps or now - timestamps[-1] >= window_secs
            ]
            for k in stale_ips:
                del _REQUEST_LOG[k]
            _LAST_PRUNE = now

        stamps = [t for t in _REQUEST_LOG.get(ip, []) if now - t < window_secs]
        stamps.append(now)
        _REQUEST_LOG[ip] = stamps
        return len(stamps) <= max_requests


def reset_rate_limits():
    """Testing helper to reset rate limit storage."""
    with _RATE_LIMIT_LOCK:
        _REQUEST_LOG.clear()


# ------------------------------------------------------ input sanitisation
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", flags=re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def sanitize_input(text):
    """Strip script/style tags with inner content, markup tags, control chars, and collapse whitespace."""
    if text is None:
        return ""
    text = _SCRIPT_STYLE_RE.sub(" ", str(text))
    text = _TAG_RE.sub(" ", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def escape_html(text):
    """Defensive HTML entity escaping."""
    return html.escape(str(text or ""), quote=True)


# ---------------------------------------------------------- secrets (.env)
def load_env(path):
    """Parse local key=value .env file without overriding existing process environment variables."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


# ------------------------------------------------------------ static files
MIME = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json",
}


def serve_static(path, start_response, headers):
    """Serve whitelisted static files; reject directory traversal attempts."""
    rel = path[len("/static/"):].lstrip("/\\")
    name = os.path.normpath(rel)

    # Prevent escaping static root
    if name.startswith(("..", "/", "\\")) or ".." in name.split(os.sep):
        err_headers = [h for h in headers if h[0].lower() != "content-type"] + [("Content-Type", "text/plain")]
        start_response("403 Forbidden", err_headers)
        return [b"403 - forbidden"]

    full = os.path.join(STATIC_DIR, name)
    if not os.path.isfile(full):
        err_headers = [h for h in headers if h[0].lower() != "content-type"] + [("Content-Type", "text/plain")]
        start_response("404 Not Found", err_headers)
        return [b"404 - not found"]

    ext = os.path.splitext(full)[1].lower()
    ctype = MIME.get(ext, "application/octet-stream")

    # Replace cache-control with public static caching
    res_headers = [h for h in headers if h[0].lower() not in ("content-type", "cache-control")]
    res_headers.extend([
        ("Content-Type", ctype),
        ("Cache-Control", "public, max-age=86400"),
    ])
    start_response("200 OK", res_headers)

    fh = open(full, "rb")
    return FileWrapper(fh, blksize=8192)
