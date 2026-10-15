# College Admission Enquiry Assistant using GPT

A web application that answers student questions about college admissions -
eligibility, courses offered, fee structure, admission procedure and campus
facilities - using a GPT-powered conversational assistant grounded in a
validated admission knowledge base.

## Features

- Conversational web interface with per-session history
- Intent classification into 5 domains (eligibility / courses / fees /
  procedure / facilities)
- Retrieval-grounded answers: every fact comes from the validated knowledge
  base, never invented by the model
- GPT integration via the OpenAI Chat Completions API with an automatic
  offline knowledge-base composer fallback
- Staff view of the validated knowledge base (/kb) with live validation report
- Security: input sanitisation, output escaping, CSP and security headers,
  per-IP rate limiting, path-traversal-guarded static serving, cookie-based
  sessions, secrets via environment

## Project structure

    app.py                  WSGI web application (routing, sessions, responses)
    ai_engine.py            Intent classification, retrieval, GPT call + fallback
    data_pipeline.py        Data engineering: collection, validation, transform
    security.py             Security engineering: sanitisation, rate limit, headers
    knowledge_base.json     Curated admission dataset (single source of truth)
    templates/              HTML templates (base, chat, knowledge base browser)
    static/                 CSS and logo
    Dockerfile              Container image definition (cloud deployment)
    .ebextensions/          AWS Elastic Beanstalk environment configuration
    requirements.txt        Dependencies (gunicorn for production)

## Running locally

    python app.py
    # open http://localhost:8000

Optional: create a `.env` file to enable live GPT answers:

    OPENAI_API_KEY=sk-...
    OPENAI_MODEL=gpt-4o-mini    # optional, this is the default

Without a key the assistant runs in offline mode and answers from the
knowledge base directly (fully functional, no external calls).

## Running in production (AWS Elastic Beanstalk)

    eb init -p docker admission-assistant
    eb create admission-assistant-env
    # set the secret in the EB console (or `eb setenv OPENAI_API_KEY=...`)
    eb deploy

The health endpoint `/health` is used by the load balancer.

## Data quality

    python data_pipeline.py knowledge_base.json

Validates every program / fee / facility / FAQ record and prints the derived
views (first-year fee totals, keyword index size).
"# mini_project_2" 
