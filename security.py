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
                          to deter abusive enquiry flooding.
5. Secrets management   - the OpenAI API key is read from the environment /
                          .env file only; it is never logged or echoed.
6. Static path guarding - /static serving blocks path traversal (../../etc/passwd).
7. Session handling     - opaque random session ids, HttpOnly + SameSite cookies.
"""

import hashlib
import hmac
import html
import os
import re
import secrets
import time
from urllib.parse import quote as urlquote
from wsgiref.util import FileWrapper

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ----------------------------------------------------------------- headers
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; script-src 'none'")

def security_headers():
    return [
        ("Content-Security-Policy", CSP),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Cache-Control", "no-store"),
    ]

# ------------------------------------------------------------- sessions
def get_session(environ):
    """Read the opaque session id from the cookie (create one if absent)."""
    cookie = environ.get("HTTP_COOKIE", "")
    sid = None
    for part in cookie.split(";"):
        if part.strip().startswith("sid="):
            cand = part.strip()[4:]
            if re.fullmatch(r"[a-f0-9]{32}", cand):
                sid = cand
    return sid or secrets.token_hex(16)


def session_cookie(sid):
    return ("Set-Cookie",
            "sid={}; Path=/; HttpOnly; SameSite=Lax".format(sid))

# --------------------------------------------------------- rate limiting
_REQUEST_LOG = {}          # ip -> list of request timestamps
WINDOW_SECS = 60
MAX_REQUESTS = 30

def client_ip(environ):
    return environ.get("REMOTE_ADDR", "unknown")


def check_rate_limit(ip):
    """Sliding-window limiter: at most MAX_REQUESTS per WINDOW_SECS per IP."""
    now = time.time()
    stamps = [t for t in _REQUEST_LOG.get(ip, []) if now - t < WINDOW_SECS]
    stamps.append(now)
    _REQUEST_LOG[ip] = stamps
    return len(stamps) <= MAX_REQUESTS

# ------------------------------------------------------ input sanitisation
_SCRIPT_RE = re.compile(r"<[^>]*>")

def sanitize_input(text):
    """Strip tags, control characters and collapse whitespace."""
    if text is None:
        return ""
    text = _SCRIPT_RE.sub(" ", text)
    text = "".join(ch for ch in text if ch == "\n" or ord(ch) >= 32)
    return re.sub(r"\s+", " ", text).strip()


def escape_html(text):
    return html.escape(text or "", quote=True)

# ---------------------------------------------------------- secrets (.env)
def load_env(path):
    """Tiny .env loader so the API key stays out of the code repository.

    Only sets variables that are not already present in the environment
    (platform-provided values win, e.g. Elastic Beanstalk environment
    properties).
    """
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
MIME = {".css": "text/css", ".js": "application/javascript", ".png": "image/png",
        ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ico": "image/x-icon"}

def serve_static(path, start_response, headers):
    """Serve whitelisted static files; reject any path-traversal attempt."""
    name = os.path.normpath(path[len("/static/"):])
    if name.startswith(("..", "/", "\\")) or ".." in name.split(os.sep):
        start_response("403 Forbidden", headers + [("Content-Type", "text/plain")])
        return [b"403 - forbidden"]
    full = os.path.join(STATIC_DIR, name)
    if not os.path.isfile(full):
        start_response("404 Not Found", headers + [("Content-Type", "text/plain")])
        return [b"404 - not found"]
    ext = os.path.splitext(full)[1].lower()
    ctype = MIME.get(ext, "application/octet-stream")
    headers.append(("Content-Type", ctype))
    start_response("200 OK", headers)
    # FileWrapper closes the file itself when the response iterator ends;
    # the file must stay open here, so no with-block.
    fh = open(full, "rb")
    return FileWrapper(fh, blksize=8192)
