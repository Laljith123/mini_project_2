"""
College Admission Enquiry Assistant using GPT
=============================================
A web application that answers student questions about college admissions:
eligibility, courses offered, fee structure, admission procedure and
facilities.

Architecture
------------
    Browser  ->  WSGI App (app.py)  ->  AI Engine (ai_engine.py)
                                        - intent classification
                                        - knowledge-base retrieval
                                        - OpenAI GPT answer generation
                                          (or offline composer fallback)
                 Knowledge base (knowledge_base.json) is loaded and
                 validated by data_pipeline.py.

Run (development):
    python app.py          ->  http://localhost:8000

Run (production / AWS Elastic Beanstalk):
    gunicorn app:application      (application is the WSGI callable)
"""

import os
import json
import traceback
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

import ai_engine
import data_pipeline
import security

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# In-memory conversation store, keyed by session id (demo-scale storage;
# a production deployment would use a database-backed session store).
CONVERSATIONS = {}


def load_template(name):
    with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def render_page(title, body_html):
    """Wrap body content in the standard site chrome."""
    tpl = load_template("base.html")
    return tpl.replace("{{TITLE}}", security.escape_html(title)) \
              .replace("{{BODY}}", body_html)


def build_chat_body(session):
    """Render the conversation history + question form."""
    turns = CONVERSATIONS.get(session, [])
    rows = []
    for q, a, meta in turns:
        mode = "GPT (OpenAI API)" if meta["mode"] == "online" else "Knowledge base engine"
        rows.append(
            '<div class="msg user"><div class="who">You</div>'
            '<div class="bubble">{}</div></div>'.format(security.escape_html(q)) +
            '<div class="msg bot"><div class="who">Assistant &middot; {} &middot; intent: {}</div>'
            '<div class="bubble">{}</div></div>'.format(
                mode, security.escape_html(meta["intent"]),
                a["html"]))
    history = "\n".join(rows) if rows else (
        '<div class="msg bot"><div class="who">Assistant</div>'
        '<div class="bubble">Hello! Ask me anything about admissions - '
        'eligibility, courses, fees, admission procedure or college facilities.'
        '</div></div>')

    suggestions = "".join(
        '<a class="suggestion" href="/?q={}">{}</a>'.format(
            security.urlquote(s), security.escape_html(s))
        for s in EXAMPLE_QUESTIONS)
    return load_template("chat.html").replace("{{HISTORY}}", history) \
                                      .replace("{{SUGGESTIONS}}", suggestions)


EXAMPLE_QUESTIONS = [
    "What is the eligibility for B.Tech Computer Science?",
    "How much is the first year fee for ECE?",
    "What is the admission procedure?",
    "What facilities are available on campus?",
    "Which UG courses are offered by the college?",
]


def handle_ask(environ, session):
    """POST /ask - process a submitted question through the AI engine."""
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length > 2000:
            return None, "Question too long (limit 2000 characters)."
        raw = environ["wsgi.input"].read(length).decode("utf-8", "replace")
        fields = parse_qs(raw, keep_blank_values=True)
        question = (fields.get("question") or [""])[0]
    except Exception:
        return None, "Malformed form submission."

    question = security.sanitize_input(question)
    if not question or not question.strip():
        return None, "Please type a question before submitting."
    if len(question) > 500:
        return None, "Please keep your question under 500 characters."

    # Ask the AI engine (GPT API when configured, KB engine otherwise).
    answer, meta = ASSISTANT.answer(question)
    turns = CONVERSATIONS.setdefault(session, [])
    turns.append((question, answer, meta))
    if len(turns) > 30:          # keep memory bounded
        del turns[:-30]
    return answer, None


def handle_kb_page():
    """Read-only knowledge base browser (staff reference view)."""
    stats = data_pipeline.KB_STATS
    programs_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            security.escape_html(p["code"]), security.escape_html(p["name"]),
            security.escape_html(p["duration"]), p["intake"])
        for p in ASSISTANT.kb["programs"])
    body = load_template("kb_browser.html")
    body = body.replace("{{N_PROGRAMS}}", str(stats["programs"])) \
               .replace("{{N_SUBJECTS}}", str(stats["fee_components"])) \
               .replace("{{N_FAQS}}", str(stats["faqs"])) \
               .replace("{{N_FACILITIES}}", str(stats["facilities"])) \
               .replace("{{VALIDATION}}", security.escape_html(stats["validation_report"])) \
               .replace("{{PROGRAM_ROWS}}", programs_rows)
    return body


def dispatch(environ, start_response):
    """Core WSGI application: routing + security enforcement."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    session = security.get_session(environ)
    headers = security.security_headers()

    try:
        # -- rate limiting (per client IP) --------------------------------
        if not security.check_rate_limit(security.client_ip(environ)):
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("429 Too Many Requests", headers)
            return [b"<h1>429 - Too many requests</h1><p>Please slow down.</p>"]

        # -- static files --------------------------------------------------
        if path.startswith("/static/"):
            return security.serve_static(path, start_response, headers)

        if path == "/" and method == "GET":
            # Optional ?q= quick-ask (suggestion links)
            qs = parse_qs(environ.get("QUERY_STRING", ""))
            if qs.get("q"):
                q = security.sanitize_input(qs["q"][0])
                if q:
                    answer, meta = ASSISTANT.answer(q)
                    CONVERSATIONS.setdefault(session, []).append((q, answer, meta))
            body = build_chat_body(session)
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [render_page("Admission Enquiry Assistant", body).encode("utf-8")]

        if path == "/ask" and method == "POST":
            answer, error = handle_ask(environ, session)
            if error:
                headers.append(("Content-Type", "text/html; charset=utf-8"))
                start_response("400 Bad Request", headers)
                return [render_page("Error", "<h1>400</h1><p>{}</p>".format(
                    security.escape_html(error))).encode("utf-8")]
            body = build_chat_body(session)
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [render_page("Admission Enquiry Assistant", body).encode("utf-8")]

        if path == "/kb" and method == "GET":
            body = handle_kb_page()
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [render_page("Knowledge Base Browser", body).encode("utf-8")]

        if path == "/health":
            headers.append(("Content-Type", "application/json"))
            start_response("200 OK", headers)
            return [json.dumps({"status": "ok", "service": "admission-assistant",
                                "ai_mode": ASSISTANT.mode()}).encode("utf-8")]

        # -- unknown path ---------------------------------------------------
        headers.append(("Content-Type", "text/html; charset=utf-8"))
        start_response("404 Not Found", headers)
        return [render_page("Not Found", "<h1>404 - Page not found</h1>").encode("utf-8")]

    except Exception:
        traceback.print_exc()
        headers.append(("Content-Type", "text/html; charset=utf-8"))
        start_response("500 Internal Server Error", headers)
        return [render_page("Error", "<h1>500 - Internal server error</h1>").encode("utf-8")]


application = dispatch          # WSGI entry point (gunicorn / Elastic Beanstalk)


def init():
    """Load + validate the knowledge base and start the AI engine."""
    global ASSISTANT
    security.load_env(os.path.join(BASE_DIR, ".env"))
    kb = data_pipeline.load_and_validate(
        os.path.join(BASE_DIR, "knowledge_base.json"))
    data_pipeline.KB_STATS = data_pipeline.knowledge_base_stats(kb)
    ASSISTANT = ai_engine.GPTAssistant(kb)
    print("[init] knowledge base loaded and validated:")
    print("[init]   - programs        : {}".format(data_pipeline.KB_STATS["programs"]))
    print("[init]   - fee components  : {}".format(data_pipeline.KB_STATS["fee_components"]))
    print("[init]   - facilities      : {}".format(data_pipeline.KB_STATS["facilities"]))
    print("[init]   - faqs            : {}".format(data_pipeline.KB_STATS["faqs"]))
    print("[init] AI engine mode     : {}".format(ASSISTANT.mode()))


data_pipeline.KB_STATS = {}
init()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("[server] College Admission Enquiry Assistant")
    print("[server] starting development server on http://localhost:{}/".format(port))
    with make_server("0.0.0.0", port, application) as httpd:
        httpd.serve_forever()
