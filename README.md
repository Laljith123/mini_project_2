# College Admission Enquiry Assistant using GPT (Next.js)

A modern web application built with **Next.js 14 (App Router)** and **TypeScript** that answers student enquiries about college admissions — eligibility criteria, courses offered, fee structures, admission procedures, campus facilities, and frequently asked questions. Powered by a conversational assistant grounded in a verified admissions knowledge base.

**Live Production Deployment**: [https://first-tan-three.vercel.app](https://first-tan-three.vercel.app)

---

## Architecture

```
                    +------------------------------------+
                    |  Next.js Client (React 18 / TS)   |
                    |  - Interactive Chat Interface      |
                    |  - Knowledge Base Browser (/kb)    |
                    +-----------------+------------------+
                                      |
                     HTTP / JSON      v
                    +------------------------------------+
                    | Next.js API Routes (Serverless)    |
                    |  - POST /api/chat                  |
                    |  - GET  /api/health                |
                    |  - Anti-XSS Sanitisation & Limiter |
                    +-----------------+------------------+
                                      |
                     Enquiry Query    v
                    +------------------------------------+
                    |     AI Engine (lib/aiEngine.ts)    |
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
                    | - Schema Validation & Transforms   |
                    +------------------------------------+
```

---

## Features

- **Next.js 14 App Router**: Server and client component architecture with zero cold-start latency.
- **Conversational UI**: Interactive chat interface with session history, optimistic message updates, typing indicators, and auto-scrolling.
- **Intent Classification & Entity Recognition**: Classifies questions into 6 domains (`eligibility`, `courses`, `fees`, `procedure`, `facilities`, `faq`) and identifies program entities (`CSE`, `ECE`, `MECH`, `CIVIL`, `IT`, `AI-DS`).
- **Semantic FAQ Matching**: Token overlap matching against curated admissions FAQs (management quota, scholarships, hostel guarantees, branch transfers, JEE Main scores).
- **RAG-Grounded Answers**: Context injection ensures every admission fact comes strictly from verified institutional records, preventing hallucinations.
- **Dual-Mode AI Engine**:
  - **Online**: GPT-4o-mini with verified context injection.
  - **Offline**: Instant deterministic composer guaranteeing 100% functionality without internet or external API dependencies.
- **Staff Knowledge Base Explorer (`/kb`)**: Interactive overview of program intakes, fee breakdowns, and real-time schema validation reports.
- **REST JSON API (`/api/chat` & `/api/health`)**: First-class API endpoints for programmatic integration and load balancer probes.
- **Defensive Security Controls**:
  - Script & style tag stripping with inner content removal + entity escaping.
  - In-memory sliding-window rate limiting (30 req/min/IP) with automatic memory eviction.
  - Reverse proxy awareness (`x-forwarded-for` inspection).

---

## Project Structure

```
├── app/
│   ├── layout.tsx          # Root site layout (Header, Brand, Nav, Footer)
│   ├── page.tsx            # Interactive chat client component
│   ├── globals.css         # Responsive styling
│   ├── kb/
│   │   └── page.tsx        # Knowledge base staff reference table
│   └── api/
│       ├── chat/
│       │   └── route.ts    # POST /api/chat enquiry endpoint
│       └── health/
│           └── route.ts    # GET /api/health monitoring probe
├── lib/
│   ├── types.ts            # TypeScript interfaces & domain types
│   ├── security.ts         # Anti-XSS sanitisation & rate limiter
│   ├── knowledgeBase.ts    # Schema validation, fee transforms & FAQ matcher
│   └── aiEngine.ts         # Intent classification, entity detection & GPT/composer
├── public/
│   └── logo.png            # Institution logo
├── test/
│   └── test-suite.js       # Automated test suite (schema, security, intents, entities)
├── knowledge_base.json     # Curated admissions dataset (single source of truth)
├── vercel.json             # Vercel deployment framework configuration
├── tsconfig.json           # TypeScript configuration
├── next.config.js          # Next.js configuration
├── package.json            # Project dependencies and scripts
└── README.md               # Project documentation
```

---

## Quickstart

### 1. Running Locally

Clone the repository and install dependencies:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your web browser.

### 2. Optional: OpenAI GPT Integration

To enable online GPT-powered phrasing:

1. Create a `.env.local` file:
   ```ini
   OPENAI_API_KEY=sk-your-openai-api-key
   OPENAI_MODEL=gpt-4o-mini
   ```

*Note: Without an API key, the assistant automatically runs in offline mode using the built-in deterministic knowledge composer.*

### 3. Running Automated Tests

Run the test suite:

```bash
npm test
```

Verifies:
- Knowledge base schema integrity & derived fee calculations
- Anti-XSS sanitization and control character filtering
- Academic program entity recognition
- Intent classification across all 5 domain intents
- Sliding-window rate limiting

### 4. Production Build

```bash
npm run build
npm start
```

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

### 2. `GET /api/health`
System diagnostics and uptime probe.

**Response (200 OK):**
```json
{
  "status": "ok",
  "service": "admission-assistant-nextjs",
  "ai_mode": "offline",
  "model": "kb-composer",
  "stats": {
    "questions_answered": 1,
    "gpt_calls": 0,
    "offline_answers": 1,
    "by_intent": { "fees": 1, "eligibility": 0, "courses": 0, "procedure": 0, "facilities": 0, "faq": 0, "general": 0 }
  },
  "kb_stats": {
    "programs": 6,
    "fee_components": 18,
    "facilities": 8,
    "faqs": 5,
    "validation_errors": 0,
    "validation_report": "all records passed validation (0 errors)"
  }
}
```

---

## Deployment to Vercel

The application is pre-configured for native Next.js deployment on Vercel:

```bash
# Deploy to production
npx vercel --prod
```

Or connect the repository on your [Vercel Dashboard](https://vercel.com/dashboard) (`Laljith123/mini_project_2`) for automatic continuous deployment on every git push.
