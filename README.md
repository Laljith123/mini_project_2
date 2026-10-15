# College Admission Enquiry Assistant using GPT

A web application that answers student enquiries about college admissions — eligibility criteria, courses offered, fee structure, admission procedures, campus facilities, and frequently asked questions — using a GPT-powered conversational assistant grounded in a verified, validated admission knowledge base.

---

## Architecture

```
                    +------------------------------------+
                    |  Browser Client / REST API Client  |
                    +-----------------+------------------+
                                      |
                     HTTP / JSON      v
                    +------------------------------------+
                    |        WSGI Web App (app.py)       |
                    |  - Routing & Session Management    |
                    |  - Security & Rate Limiting        |
                    |  - HTML & REST JSON Endpoints      |
                    +-----------------+------------------+
                                      |
                     Enquiry Query    v
                    +------------------------------------+
                    |        AI Engine (ai_engine.py)    |
                    |  - Intent Classification (6 domains|
                    |  - Program Entity Detection        |
                    |  - Semantic FAQ Matcher            |
                    |  - Grounded Context Retrieval      |
                    +--------+------------------+--------+
                             |                  |
           Online (API Key)  v                  v  Offline / Fallback
             +--------------------+    +--------------------+
             | OpenAI Chat API    |    | Offline Composer   |
             | (GPT-4o-mini / RAG)|    | (Deterministic KB) |
             +--------------------+    +--------------------+
                             \                  /
                              v                v
                    +------------------------------------+
                    | Verified Knowledge Base (data)     |
                    | - Curated Single Source of Truth   |
                    | - Pipeline Validation & Transforms |
                    +------------------------------------+
```

---

## Features

- **Conversational Interface**: Stateful per-session chat history with automatic thread-safe LRU pruning and 24-hour TTL.
- **Progressive Enhancement**: Real-time async AJAX chat with typing indicators and auto-scroll, with zero-JavaScript fallback.
- **Intent Classification & Entity Extraction**: Identifies 6 intents (`eligibility`, `courses`, `fees`, `procedure`, `facilities`, `faq`) and detects academic program branches (`CSE`, `ECE`, `MECH`, `CIVIL`, `IT`, `AI-DS`).
- **Semantic FAQ Matching**: Token overlap matching against curated admissions FAQs (management quota, scholarships, hostel guarantees, branch transfers, entrance exam scores).
- **RAG-Grounded Answers**: Context-injected generation ensures every fact comes strictly from verified admission records, eliminating hallucinations.
- **Dual-Mode AI Engine**:
  - **Online**: GPT-4o-mini with verified context injection.
  - **Offline**: Instant deterministic composer guaranteeing 100% functionality without internet or external API dependencies.
- **Staff Knowledge Base Browser (`/kb`)**: Live inspection of program intakes, fee breakdowns, and real-time schema validation reports.
- **REST JSON API (`/api/chat`)**: First-class API endpoint for programmatic integration.
- **Comprehensive Security Engineering**:
  - Tag & inner-content anti-XSS stripping + output escaping.
  - Strict Content Security Policy (CSP), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`.
  - Sliding-window thread-safe rate limiter (30 req/min/IP) with automatic memory eviction.
  - Reverse proxy awareness (`X-Forwarded-For` inspection).
  - Cryptographically secure 128-bit session IDs with `HttpOnly; SameSite=Lax` cookies.
  - Whitelist-guarded static asset serving with path-traversal prevention.

---

## Project Structure

```
├── app.py                  # Core WSGI web application (routing, sessions, API)
├── ai_engine.py            # AI Engine: Intent classification, retrieval, GPT/fallback
├── data_pipeline.py        # Data pipeline: Validation, transform, keyword indexing
├── security.py             # Security module: Sanitisation, rate limiter, headers
├── knowledge_base.json     # Curated admissions dataset (single source of truth)
├── templates/              # Semantic HTML5 templates
│   ├── base.html           # Site chrome layout
│   ├── chat.html           # Chat UI with progressive enhancement
│   └── kb_browser.html     # Knowledge base staff reference table
├── static/                 # Static assets
│   ├── logo.png            # Institution emblem
│   └── style.css           # Responsive stylesheet
├── tests/                  # Automated test suite (27 unit & integration tests)
│   ├── __init__.py
│   └── test_suite.py       # Security, data pipeline, AI engine & WSGI tests
├── Dockerfile              # Production container definition (gunicorn on Python 3.11)
├── .ebextensions/          # AWS Elastic Beanstalk cloud deployment configuration
│   └── admission-assistant.config
├── example.env             # Environment variable template
├── requirements.txt        # Production dependencies (gunicorn)
└── README.md               # Project documentation
```

---

## Quickstart

### 1. Running Locally

Clone the repository and run using the Python standard library:

```bash
python app.py
```

Open [http://localhost:8000](http://localhost:8000) in your web browser.

### 2. Optional: OpenAI GPT Integration

To enable online GPT-powered phrasing:

1. Copy `example.env` to `.env`:
   ```bash
   cp example.env .env
   ```
2. Add your OpenAI API key in `.env`:
   ```ini
   OPENAI_API_KEY=sk-your-openai-api-key
   OPENAI_MODEL=gpt-4o-mini
   ```

*Note: Without an API key, the assistant runs in offline mode using the built-in deterministic knowledge composer.*

---

## Running the Automated Test Suite

Run all unit and integration tests using Python's built-in `unittest` runner:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

All 27 test cases cover:
- Input sanitization (XSS and control character filtering)
- Session creation and cookie transmission
- Client IP resolution through reverse proxies
- Rate limiting and sliding-window enforcement
- Static file path traversal protection
- Knowledge base schema and referential integrity validation
- Intent classification and program entity recognition
- Offline composer responses across all intents
- Full WSGI request/response cycle and JSON API endpoints

---

## API Reference

### 1. `POST /api/chat`
Enquiry endpoint accepting JSON payloads.

**Request:**
```http
POST /api/chat HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "question": "What is the fee for B.Tech CSE?"
}
```

**Response (200 OK):**
```json
{
  "question": "What is the fee for B.Tech CSE?",
  "answer": "First-year fee breakdown for B.Tech Computer Science and Engineering (CSE):\n• Tuition fee: Rs. 65,000 (yearly)\n• Development fee: Rs. 12,000 (yearly)\n• Exam fee: Rs. 8,000 (yearly)\nTotal first-year tuition & academic fees: Rs. 85,000",
  "html": "<p>First-year fee breakdown for B.Tech Computer Science and Engineering (CSE):<br/>• Tuition fee: Rs. 65,000 (yearly)<br/>• Development fee: Rs. 12,000 (yearly)<br/>• Exam fee: Rs. 8,000 (yearly)<br/>Total first-year tuition & academic fees: Rs. 85,000</p>",
  "meta": {
    "intent": "fees",
    "program": "CSE",
    "mode": "offline",
    "latency_ms": 1,
    "model": "kb-composer"
  }
}
```

### 2. `GET /health`
System diagnostics and load-balancer health probe.

**Response (200 OK):**
```json
{
  "status": "ok",
  "service": "admission-assistant",
  "ai_mode": "offline",
  "model": "kb-composer",
  "active_sessions": 1,
  "stats": {
    "questions_answered": 1,
    "gpt_calls": 0,
    "offline_answers": 1,
    "by_intent": { "fees": 1, "eligibility": 0, "courses": 0, "procedure": 0, "facilities": 0, "faq": 0, "general": 0 }
  }
}
```

### 3. `GET /clear`
Resets the conversation history for the current session.

---

## Production Deployment

### Docker

Build and run the container locally:

```bash
docker build -t admission-assistant .
docker run -p 8000:8000 -e PORT=8000 admission-assistant
```

### AWS Elastic Beanstalk

Deploy via the AWS EB CLI:

```bash
eb init -p docker admission-assistant
eb create admission-assistant-env
eb setenv OPENAI_API_KEY=sk-... OPENAI_MODEL=gpt-4o-mini
eb deploy
```
