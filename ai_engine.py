"""
AI Engine for the College Admission Enquiry Assistant.

The assistant works in two layers:

1. Intent classification + knowledge-base retrieval (deterministic layer).
   Every question is classified into one of five primary intents - eligibility,
   courses, fees, procedure, facilities - or matched against curated admission FAQs.
   The relevant verified records are retrieved from the validated knowledge base.
   This deterministic layer ensures answers are grounded in verified data,
   preventing hallucinations.

2. GPT answer generation (generative layer).
   When an OpenAI API key is configured, the retrieved records are passed
   into a system prompt and sent to the OpenAI Chat Completions API
   (model configurable via env var, default gpt-4o-mini).
   When no key is configured (offline mode) or when network issues occur, an
   offline composer deterministically produces the answer directly from the
   retrieved records, so the application remains 100% functional.

The engine returns (answer_dict, meta_dict) where meta records the intent,
the sources used, and whether the answer came from GPT or the offline
composer - surfaced transparently in the UI.
"""

import html as _html
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request

import data_pipeline

logger = logging.getLogger("ai_engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

INTENTS = ("eligibility", "courses", "fees", "procedure", "facilities", "faq", "general")

INTENT_PATTERNS = [
    (
        r"\b(?:eligib\w*|qualif\w*|requirement\w*|criteria|marks|percentage|percent\b|cutoff\w*|10\+2|hsc|score\w*)\b",
        "eligibility"
    ),
    (
        r"\b(?:fee\w*|cost|tuition|charge\w*|how much|price|expensive|payment\w*|mess fee\w*|hostel fee\w*)\b",
        "fees"
    ),
    (
        r"\b(?:admission procedure|admission process|how to apply|apply\w*|application|join\w*|enrol\w*|step\w*|documents? required|certificate verification|deadline\w*|last date|important dates|dates|schedule|counselling)\b",
        "procedure"
    ),
    (
        r"\b(?:facilit\w*|hostel|librar\w*|lab\w*|laborator\w*|sports|transport|bus\b|gym|placement\w*|campus|canteen|mess|medical|wifi|wi-fi|hospital)\b",
        "facilities"
    ),
    (
        r"\b(?:course\w*|program\w*|branch\w*|department\w*|cse|ece|mech\w*|civil|ug\b|degrees?|b\.?tech|seats?|intake)\b",
        "courses"
    ),
]

BRANCH_CODES = {
    "cse": "CSE",
    "computer science": "CSE",
    "computer science and engineering": "CSE",
    "information technology": "IT",
    "it": "IT",
    "ece": "ECE",
    "electronics": "ECE",
    "electronics and communication": "ECE",
    "mech": "MECH",
    "mechanical": "MECH",
    "mechanical engineering": "MECH",
    "civil": "CIVIL",
    "civil engineering": "CIVIL",
    "ai-ds": "AI-DS",
    "ai ds": "AI-DS",
    "data science": "AI-DS",
    "artificial intelligence": "AI-DS",
    "artificial intelligence and data science": "AI-DS",
}

_AMBIGUOUS = {"it": "IT", "ai": "AI-DS"}
_BRANCH_CONTEXT = re.compile(
    r"\b(?:fee\w*|course\w*|program\w*|branch\w*|department\w*|eligib\w*|admission|intake|seats?|cutoff|marks|degree\w*|offer\w*|b\.?tech|btech)\b"
)


def detect_program(question):
    """Detect which academic program the question refers to (if any)."""
    q = question.lower()
    # Sort phrases longest first so "computer science and engineering" matches before "cse"
    for phrase, code in sorted(BRANCH_CODES.items(), key=lambda kv: -len(kv[0])):
        if phrase in _AMBIGUOUS:
            continue
        if re.search(r"\b" + re.escape(phrase) + r"\b", q):
            return code

    # Check ambiguous short codes with context
    for token in re.findall(r"\b[a-z0-9-]+\b", q):
        if token in _AMBIGUOUS and _BRANCH_CONTEXT.search(q):
            return _AMBIGUOUS[token]

    return None


def classify_intent(question, kb=None):
    """Classify user question into domain intents or check curated FAQ match."""
    q = question.lower()

    # Check if this matches a curated FAQ with high confidence
    if kb:
        faq_match = data_pipeline.get_faq_match(kb, question)
        if faq_match:
            return "faq", {"faq": 1.0}, faq_match

    scores = {}
    for pattern, intent in INTENT_PATTERNS:
        matches = len(re.findall(pattern, q))
        if matches > 0:
            scores[intent] = scores.get(intent, 0) + matches

    if scores:
        top_intent = max(scores, key=scores.get)
        return top_intent, scores, None

    return "general", scores, None


def retrieve(kb, intent, program, matched_faq=None):
    """Fetch relevant knowledge-base records for the classified intent."""
    if intent == "faq" and matched_faq:
        return {"faq": matched_faq, "college": kb.get("college", {})}

    if intent == "eligibility":
        if program:
            recs = [p for p in kb["programs"] if p["code"] == program]
        else:
            recs = kb["programs"]
        return {"programs": recs, "college": kb.get("college", {})}

    if intent == "courses":
        return {"programs": kb["programs"], "college": kb.get("college", {})}

    if intent == "fees":
        fees = [f for f in kb["fee_structure"] if program is None or f["program"] == program]
        return {
            "fees": fees,
            "hostel_fees": kb.get("hostel_fees", []),
            "totals": kb.get("derived_total_first_year_fees", {}),
            "programs": kb.get("programs", []),
        }

    if intent == "procedure":
        return {
            "steps": kb["admission_procedure"],
            "dates": kb.get("important_dates", []),
            "college": kb.get("college", {}),
        }

    if intent == "facilities":
        return {
            "facilities": kb["facilities"],
            "hostel_fees": kb.get("hostel_fees", []),
        }

    # General intent fallback
    return {
        "programs": kb.get("programs", []),
        "faqs": kb.get("faqs", []),
        "college": kb.get("college", {}),
    }


def _fmt_amount(n):
    return "Rs. {:,}".format(int(n))


def compose_offline(question, intent, program, kb, retrieved, matched_faq=None):
    """Offline composer: build deterministic, retrieval-grounded responses directly from verified data."""
    if intent == "faq" and (matched_faq or retrieved.get("faq")):
        f = matched_faq or retrieved.get("faq")
        return f"Q: {f['q']}\nA: {f['a']}"

    if intent == "eligibility":
        recs = retrieved.get("programs", [])
        if program and recs:
            p = recs[0]
            return (
                f"Eligibility for {p['name']} ({p['code']}): {p['eligibility']} "
                f"Course duration is {p['duration']} with an intake of {p['intake']} seats."
            )
        lines = [
            "Eligibility criteria for B.Tech programs at Sri Manakula Vinayagar Engineering College:",
            "Pass in 10+2 with Mathematics, Physics and Chemistry with a minimum 50% aggregate marks (45% for reserved categories).",
            "Admission is conducted through counselling based on 10+2 marks / entrance rank as per Government of Puducherry norms.",
            "Offered branches include: " + ", ".join(f"{p['name']} ({p['code']})" for p in kb.get("programs", [])),
        ]
        return "\n\n".join(lines)

    if intent == "courses":
        lines = ["Sri Manakula Vinayagar Engineering College offers the following undergraduate (B.Tech) programs:"]
        for p in retrieved.get("programs", []):
            lines.append(f"• {p['name']} ({p['code']}): {p['duration']}, intake of {p['intake']} students.")
        return "\n".join(lines)

    if intent == "fees":
        totals = retrieved.get("totals", {})
        q_lower = question.lower()
        # Specific query for hostel fees
        if "hostel" in q_lower or "mess" in q_lower:
            lines = ["Hostel and accommodation fee structure:"]
            for h in retrieved.get("hostel_fees", []):
                lines.append(f"• {h['component']}: {_fmt_amount(h['amount'])} ({h['frequency']})")
            return "\n".join(lines)

        if program and program in totals:
            prog_name = next((p["name"] for p in kb["programs"] if p["code"] == program), program)
            lines = [f"First-year fee breakdown for {prog_name} ({program}):"]
            for f in retrieved.get("fees", []):
                lines.append(f"• {f['component']}: {_fmt_amount(f['amount'])} ({f['frequency']})")
            lines.append(f"Total first-year tuition & academic fees: {_fmt_amount(totals[program])}")
            return "\n".join(lines)

        lines = ["First-year academic fees by program:"]
        for p in kb["programs"]:
            lines.append(f"• {p['name']} ({p['code']}): {_fmt_amount(totals.get(p['code'], p['first_year_fees']))}")
        if retrieved.get("hostel_fees"):
            lines.append("\nOptional Hostel charges:")
            for h in retrieved["hostel_fees"]:
                lines.append(f"• {h['component']}: {_fmt_amount(h['amount'])} ({h['frequency']})")
        return "\n".join(lines)

    if intent == "procedure":
        q_lower = question.lower()
        if any(w in q_lower for w in ("date", "deadline", "schedule", "when")):
            lines = ["Important admission dates (2026):"]
            for d in retrieved.get("dates", []):
                lines.append(f"• {d['event']}: {d['date']}")
            return "\n".join(lines)

        lines = ["Step-by-step admission procedure:"]
        for i, step in enumerate(retrieved.get("steps", []), 1):
            lines.append(f"{i}. {step.rstrip('.')}.")
        if retrieved.get("dates"):
            lines.append("\nKey admission dates:")
            for d in retrieved["dates"]:
                lines.append(f"• {d['event']}: {d['date']}")
        return "\n".join(lines)

    if intent == "facilities":
        lines = ["Campus facilities available at Sri Manakula Vinayagar Engineering College:"]
        for fac in retrieved.get("facilities", []):
            lines.append(f"• {fac['name']}: {fac['description'].rstrip('.')}.")
        return "\n".join(lines)

    # General enquiry fallback
    college_site = kb.get("college", {}).get("website", "https://www.smvec.ac.in")
    return (
        "I can answer questions regarding college admissions, including eligibility criteria, "
        "courses offered, fee structures, application procedures, and campus facilities. "
        f"For specific administrative queries, please visit the admission portal at {college_site}."
    )


def gpt_answer(question, intent, program, kb, retrieved, api_key, model):
    """Layer 2: Ask OpenAI GPT to format the response grounded strictly in verified context."""
    context = json.dumps(retrieved, indent=1, default=str)[:6000]
    college_name = kb.get("college", {}).get("name", "the college")

    system_prompt = (
        f"You are the official admission enquiry assistant of {college_name}. "
        "Answer the student's enquiry using ONLY the admission data provided in the context below. "
        "If the context does not contain sufficient details to answer, politely advise the student "
        "to contact the college admission cell. "
        "Be concise, professional, courteous, and strictly factual. Never invent fees, dates, or courses.\n\n"
        f"Context:\n{context}"
    )

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "temperature": 0.2,
        "max_tokens": 350,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    choices = data.get("choices", [])
    if choices and "message" in choices[0]:
        return choices[0]["message"]["content"].strip()
    raise ValueError("Malformed response payload from OpenAI API")


class GPTAssistant:
    def __init__(self, kb):
        self.kb = kb
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._lock = threading.Lock()
        self.stats = {
            "questions_answered": 0,
            "gpt_calls": 0,
            "offline_answers": 0,
            "by_intent": {i: 0 for i in INTENTS},
        }

    def mode(self):
        """Current operational mode ('online' when API key is present, 'offline' otherwise)."""
        return "online" if self.api_key else "offline"

    def answer(self, question):
        """Process an enquiry question through intent classification, retrieval, and synthesis."""
        t0 = time.time()
        intent, scores, matched_faq = classify_intent(question, self.kb)
        program = detect_program(question)
        retrieved = retrieve(self.kb, intent, program, matched_faq)

        mode_used = "offline"
        text = None

        if self.mode() == "online":
            try:
                text = gpt_answer(
                    question, intent, program, self.kb,
                    retrieved, self.api_key, self.model
                )
                mode_used = "online"
                with self._lock:
                    self.stats["gpt_calls"] += 1
            except Exception as exc:
                logger.warning("GPT API call failed (%s); falling back to offline composer", exc)

        if text is None:
            text = compose_offline(
                question, intent, program, self.kb, retrieved, matched_faq
            )
            with self._lock:
                self.stats["offline_answers"] += 1

        with self._lock:
            self.stats["questions_answered"] += 1
            self.stats["by_intent"][intent] = self.stats["by_intent"].get(intent, 0) + 1

        formatted_html = "<p>" + _html.escape(text).replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
        answer = {
            "text": text,
            "html": formatted_html,
        }
        meta = {
            "intent": intent,
            "program": program,
            "mode": mode_used,
            "latency_ms": int((time.time() - t0) * 1000),
            "model": self.model if mode_used == "online" else "kb-composer",
        }
        return answer, meta
