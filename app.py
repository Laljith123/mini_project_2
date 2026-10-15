"""
College Admission Enquiry Assistant using GPT
=============================================
A web application that answers student questions about college admissions:
eligibility, courses offered, fee structure, admission procedure, facilities,
and frequently asked questions.

Architecture
------------
    Browser / Client  ->  WSGI Application (app.py)  ->  AI Engine (ai_engine.py)
                                                         - intent classification & FAQ matching
                                                         - knowledge-base retrieval
                                                         - OpenAI GPT answer generation
                                                           (or offline composer fallback)
                          Knowledge base (knowledge_base.json) is loaded and
                          validated by data_pipeline.py.

Run (development):
    python app.py          ->  http://localhost:8000

Run (production / AWS Elastic Beanstalk / Docker):
    gunicorn app:application      (application is the WSGI callable)
"""

import json
import logging
import os
import threading
import time
import traceback
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

import ai_engine
import data_pipeline
import security

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s"
)
logger = logging.getLogger("app")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# Thread-safe in-memory conversation store with automatic LRU / TTL cleanup
_STORE_LOCK = threading.Lock()
_CONVERSATIONS = {}  # session_id -> {"updated_at": timestamp, "turns": [(q, a, meta)]}
MAX_SESSIONS = 500
SESSION_TTL_SECS = 86400  # 24 hours


def _prune_sessions():
    """Prune inactive sessions to ensure bounded memory usage."""
    now = time.time()
    stale_keys = [
        sid for sid, data in _CONVERSATIONS.items()
        if now - data.get("updated_at", 0) > SESSION_TTL_SECS
    ]
    for sid in stale_keys:
        del _CONVERSATIONS[sid]

    # If still above capacity, remove the oldest sessions
    if len(_CONVERSATIONS) > MAX_SESSIONS:
        sorted_sessions = sorted(_CONVERSATIONS.items(), key=lambda kv: kv[1]["updated_at"])
        overflow = len(_CONVERSATIONS) - MAX_SESSIONS
        for sid, _ in sorted_sessions[:overflow]:
            del _CONVERSATIONS[sid]


def get_conversation_turns(session_id):
    """Retrieve history for a given session."""
    with _STORE_LOCK:
        entry = _CONVERSATIONS.get(session_id)
        if entry:
            return list(entry["turns"])
        return []


def append_conversation_turn(session_id, question, answer, meta):
    """Record a turn in the conversation store."""
    with _STORE_LOCK:
        _prune_sessions()
        entry = _CONVERSATIONS.setdefault(session_id, {"updated_at": time.time(), "turns": []})
        entry["updated_at"] = time.time()
        turns = entry["turns"]
        turns.append((question, answer, meta))
        if len(turns) > 30:
            del turns[:-30]


def clear_conversation(session_id):
    """Reset history for a given session."""
    with _STORE_LOCK:
        _CONVERSATIONS.pop(session_id, None)


def load_template(name):
    """Load an HTML template from the template directory."""
    with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def render_page(title, body_html):
    """Wrap body content in standard site chrome."""
    tpl = load_template("base.html")
    return tpl.replace("{{TITLE}}", security.escape_html(title)) \
              .replace("{{BODY}}", body_html)


def build_chat_body(session):
    """Render conversation history, suggestions, and form controls."""
    turns = get_conversation_turns(session)
    rows = []
    for q, a, meta in turns:
        mode = "GPT-4o (OpenAI)" if meta["mode"] == "online" else "Knowledge Base Engine"
        intent_label = meta.get("intent", "general").capitalize()
        latency = f" &middot; {meta['latency_ms']}ms" if "latency_ms" in meta else ""
        rows.append(
            '<div class="msg user"><div class="who">You</div>'
            f'<div class="bubble">{security.escape_html(q)}</div></div>'
            f'<div class="msg bot"><div class="who">Assistant &middot; {mode} &middot; Intent: {security.escape_html(intent_label)}{latency}</div>'
            f'<div class="bubble">{a["html"]}</div></div>'
        )
    history = "\n".join(rows) if rows else (
        '<div class="msg bot"><div class="who">Assistant</div>'
        '<div class="bubble">Hello! Welcome to the Sri Manakula Vinayagar Engineering College Admission Assistant. '
        'Ask me anything about admissions &mdash; eligibility criteria, courses offered, fee structures, '
        'application steps, or campus facilities.</div></div>'
    )

    suggestions = "".join(
        '<a class="suggestion" href="/?q={}">{}</a>'.format(
            security.urlquote(s), security.escape_html(s))
        for s in EXAMPLE_QUESTIONS
    )
    return load_template("chat.html").replace("{{HISTORY}}", history) \
                                      .replace("{{SUGGESTIONS}}", suggestions)


EXAMPLE_QUESTIONS = [
    "What is the eligibility for B.Tech Computer Science?",
    "How much is the first year fee for ECE?",
    "What is the admission procedure?",
    "What facilities are available on campus?",
    "Which UG courses are offered by the college?",
    "Are scholarships available?",
    "Is hostel accommodation guaranteed?",
]


def handle_ask(environ, session):
    """Process a submitted enquiry question (supports urlencoded form or JSON payload)."""
    try:
        content_type = environ.get("CONTENT_TYPE", "").lower()
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length > 4000:
            return None, None, "Question too long (limit 4000 bytes)."

        raw = environ["wsgi.input"].read(length).decode("utf-8", "replace") if length > 0 else ""

        if "application/json" in content_type:
            payload = json.loads(raw) if raw else {}
            question = payload.get("question", "")
        else:
            fields = parse_qs(raw, keep_blank_values=True)
            question = (fields.get("question") or [""])[0]

    except Exception:
        return None, None, "Malformed request payload."

    question = security.sanitize_input(question)
    if not question or not question.strip():
        return None, None, "Please type a question before submitting."
    if len(question) > 500:
        return None, None, "Please keep your question under 500 characters."

    # Execute AI engine query
    answer, meta = ASSISTANT.answer(question)
    append_conversation_turn(session, question, answer, meta)
    return question, (answer, meta), None


def handle_kb_page():
    """Read-only knowledge base browser (staff and student reference view)."""
    stats = data_pipeline.KB_STATS
    programs_rows = "".join(
        f"<tr><td><strong>{security.escape_html(p['code'])}</strong></td>"
        f"<td>{security.escape_html(p['name'])}</td>"
        f"<td>{security.escape_html(p['duration'])}</td>"
        f"<td>{p['intake']}</td>"
        f"<td>Rs. {p['first_year_fees']:,}</td></tr>"
        for p in ASSISTANT.kb["programs"]
    )
    body = load_template("kb_browser.html")
    body = body.replace("{{N_PROGRAMS}}", str(stats["programs"])) \
               .replace("{{N_SUBJECTS}}", str(stats["fee_components"])) \
               .replace("{{N_FAQS}}", str(stats["faqs"])) \
               .replace("{{N_FACILITIES}}", str(stats["facilities"])) \
               .replace("{{VALIDATION}}", security.escape_html(stats["validation_report"])) \
               .replace("{{PROGRAM_ROWS}}", programs_rows)
    return body


def dispatch(environ, start_response):
    """Core WSGI application: routing, session handling, API endpoints, and security."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    session, is_new_session = security.get_session(environ)
    headers = security.security_headers()

    # Always ensure the session cookie is transmitted on new sessions
    if is_new_session:
        headers.append(security.session_cookie(session))

    try:
        # Rate limiting per client IP
        client_ip = security.client_ip(environ)
        if not security.check_rate_limit(client_ip):
            headers.append(("Content-Type", "application/json" if "application/json" in environ.get("HTTP_ACCEPT", "") else "text/html; charset=utf-8"))
            start_response("429 Too Many Requests", headers)
            if "application/json" in environ.get("HTTP_ACCEPT", ""):
                return [json.dumps({"error": "Rate limit exceeded. Please wait a moment."}).encode("utf-8")]
            return [render_page("429 - Too Many Requests", "<h1>429 - Rate limit exceeded</h1><p>Please wait a moment before sending more queries.</p>").encode("utf-8")]

        # Static asset serving
        if path.startswith("/static/"):
            return security.serve_static(path, start_response, headers)

        # GET / - Home chat page
        if path == "/" and method == "GET":
            qs = parse_qs(environ.get("QUERY_STRING", ""))
            if qs.get("q"):
                q = security.sanitize_input(qs["q"][0])
                if q:
                    ans, meta = ASSISTANT.answer(q)
                    append_conversation_turn(session, q, ans, meta)
            body = build_chat_body(session)
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [render_page("College Admission Enquiry Assistant", body).encode("utf-8")]

        # POST /ask or /api/chat - Process question
        if path in ("/ask", "/api/chat") and method == "POST":
            wants_json = (
                "application/json" in environ.get("HTTP_ACCEPT", "").lower() or
                "application/json" in environ.get("CONTENT_TYPE", "").lower() or
                path == "/api/chat"
            )
            q_clean, res, error = handle_ask(environ, session)

            if error:
                headers.append(("Content-Type", "application/json" if wants_json else "text/html; charset=utf-8"))
                start_response("400 Bad Request", headers)
                if wants_json:
                    return [json.dumps({"error": error}).encode("utf-8")]
                return [render_page("Error", f"<h1>400 - Bad Request</h1><p>{security.escape_html(error)}</p>").encode("utf-8")]

            answer, meta = res
            if wants_json:
                headers.append(("Content-Type", "application/json"))
                start_response("200 OK", headers)
                return [json.dumps({
                    "question": q_clean,
                    "answer": answer["text"],
                    "html": answer["html"],
                    "meta": meta
                }).encode("utf-8")]

            body = build_chat_body(session)
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [render_page("College Admission Enquiry Assistant", body).encode("utf-8")]

        # POST /clear or GET /clear - Reset conversation history
        if path == "/clear":
            clear_conversation(session)
            headers.append(("Location", "/"))
            headers.append(("Content-Type", "text/plain"))
            start_response("303 See Other", headers)
            return [b""]

        # GET /kb - Knowledge base explorer
        if path == "/kb" and method == "GET":
            body = handle_kb_page()
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [render_page("Knowledge Base Browser", body).encode("utf-8")]

        # GET /health - Load balancer & monitoring health probe
        if path == "/health":
            headers.append(("Content-Type", "application/json"))
            start_response("200 OK", headers)
            with _STORE_LOCK:
                active_sessions = len(_CONVERSATIONS)
            return [json.dumps({
                "status": "ok",
                "service": "admission-assistant",
                "ai_mode": ASSISTANT.mode(),
                "model": ASSISTANT.model if ASSISTANT.mode() == "online" else "kb-composer",
                "active_sessions": active_sessions,
                "stats": ASSISTANT.stats
            }).encode("utf-8")]

        # Unknown route
        headers.append(("Content-Type", "text/html; charset=utf-8"))
        start_response("404 Not Found", headers)
        return [render_page("Not Found", "<h1>404 - Page not found</h1><p>The requested URL was not found on this server.</p>").encode("utf-8")]

    except Exception:
        logger.error("Unhandled server exception: %s", traceback.format_exc())
        headers.append(("Content-Type", "text/html; charset=utf-8"))
        start_response("500 Internal Server Error", headers)
        return [render_page("Error", "<h1>500 - Internal server error</h1><p>An unexpected error occurred. Please try again.</p>").encode("utf-8")]


application = dispatch  # WSGI entry point (gunicorn / Elastic Beanstalk)


def init():
    """Load and validate the knowledge base and initialize the AI engine."""
    global ASSISTANT
    security.load_env(os.path.join(BASE_DIR, ".env"))
    kb = data_pipeline.load_and_validate(os.path.join(BASE_DIR, "knowledge_base.json"))
    data_pipeline.KB_STATS = data_pipeline.knowledge_base_stats(kb)
    ASSISTANT = ai_engine.GPTAssistant(kb)
    logger.info("Knowledge base successfully initialized:")
    logger.info("  • Programs       : %d", data_pipeline.KB_STATS["programs"])
    logger.info("  • Fee Components : %d", data_pipeline.KB_STATS["fee_components"])
    logger.info("  • Facilities     : %d", data_pipeline.KB_STATS["facilities"])
    logger.info("  • FAQs           : %d", data_pipeline.KB_STATS["faqs"])
    logger.info("AI engine mode     : %s", ASSISTANT.mode())


data_pipeline.KB_STATS = {}
init()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info("Starting development server on http://localhost:%d/", port)
    with make_server("0.0.0.0", port, application) as httpd:
        httpd.serve_forever()
