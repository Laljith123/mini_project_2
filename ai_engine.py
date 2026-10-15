"""
AI Engine for the College Admission Enquiry Assistant.

The assistant works in two layers:

1. Intent classification + knowledge-base retrieval (deterministic layer).
   Every question is classified into one of five intents - eligibility,
   courses, fees, procedure, facilities - and the relevant records are
   retrieved from the validated knowledge base. This layer always runs,
   because it grounds every answer in verified data (guarding against
   hallucination).

2. GPT answer generation (generative layer).
   When an OpenAI API key is configured, the retrieved records are packed
   into a system prompt and sent to the OpenAI Chat Completions API
   (model configurable via env var, default gpt-4o-mini), and the model's
   answer is returned. When no key is configured (offline mode), a
   rule-based response composer produces the answer directly from the
   retrieved records, so the application remains fully functional.

The engine returns (answer_dict, meta_dict) where meta records the intent,
the sources used and whether the answer came from GPT or the offline
composer - surfaced transparently in the UI.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
import html as _html

INTENTS = ("eligibility", "courses", "fees", "procedure", "facilities", "general")

INTENT_PATTERNS = [
    (r"\b(?:eligib\w*|qualif\w*|requirement\w*|criteria|marks|cutoff\w*)\b", "eligibility"),
    (r"\b(?:fee\w*|cost|tuition|charge\w*|how much|price|expensive)\b", "fees"),
    (r"\b(?:admission procedure|admission process|how to apply|apply\w*|application|join\w*|enrol\w*|step\w*|documents? required|certificate verification)\b", "procedure"),
    (r"\b(?:facilit\w*|hostel|librar\w*|lab\w*|laborator\w*|sports|transport|bus\b|gym|placement\w*|campus|canteen|mess|medical|wifi|wi-fi|scholarship\w*)\b", "facilities"),
    (r"\b(?:course\w*|program\w*|branch\w*|department\w*|cse|ece|mech\w*|civil| ug\b|degrees?|b\.?tech)\b", "courses"),
]

BRANCH_CODES = {
    "cse": "CSE", "computer science": "CSE", "information technology": "IT",
    "ece": "ECE", "electronics": "ECE", "mech": "MECH", "mechanical": "MECH",
    "civil": "CIVIL", "ai-ds": "AI-DS", "ai ds": "AI-DS",
    "data science": "AI-DS", "artificial intelligence": "AI-DS",
}

# Ambiguous short codes ("it", "ai") are matched only as standalone words
# in branch-mention contexts, so ordinary English words never trigger them.
_AMBIGUOUS = {"it": "IT", "ai": "AI-DS"}
_BRANCH_CONTEXT = re.compile(
    r"\b(?:fee\w*|course\w*|program\w*|branch\w*|eligib\w*|admission|intake|seats?)\b")


def detect_program(question):
    """Layer-1 step 2: detect which program the question refers to (if any)."""
    q = question.lower()
    for phrase, code in sorted(BRANCH_CODES.items(), key=lambda kv: -len(kv[0])):
        if phrase in q:
            return code
    # ambiguous two-letter codes: only accept when near a branch-context word
    for token in re.findall(r"\b[a-z-]+\b", q):
        if token in _AMBIGUOUS and _BRANCH_CONTEXT.search(q):
            return _AMBIGUOUS[token]
    return None


def classify_intent(question):
    """Layer-1 step 1: classify the question into one of the known intents."""
    q = question.lower()
    scores = {}
    for pattern, intent in INTENT_PATTERNS:
        if re.search(pattern, q):
            scores[intent] = scores.get(intent, 0) + 1
    if scores:
        return max(scores, key=scores.get), scores
    return "general", scores


def retrieve(kb, intent, program):
    """Layer-1 step 3: fetch the knowledge-base records relevant to the intent."""
    if intent == "eligibility":
        if program:
            recs = [p for p in kb["programs"] if p["code"] == program]
        else:
            recs = kb["programs"]
        return {"programs": recs}
    if intent == "courses":
        return {"programs": kb["programs"]}
    if intent == "fees":
        fees = [f for f in kb["fee_structure"]
                if program is None or f["program"] == program]
        return {"fees": fees, "hostel_fees": kb.get("hostel_fees", []),
                "totals": kb.get("derived_total_first_year_fees", {})}
    if intent == "procedure":
        return {"steps": kb["admission_procedure"],
                "dates": kb.get("important_dates", [])}
    if intent == "facilities":
        return {"facilities": kb["facilities"]}
    return {"programs": kb["programs"], "faqs": kb["faqs"]}


def _fmt_amount(n):
    return "Rs. {:,}".format(n)


def compose_offline(question, intent, program, kb, retrieved):
    """Offline composer: build the answer directly from retrieved records.

    This is the deterministic, retrieval-grounded response used when no
    OpenAI API key is configured. It formats the same records that would be
    given to GPT as context, so answers stay consistent across modes.
    """
    if intent == "eligibility":
        recs = retrieved["programs"]
        if program and recs:
            p = recs[0]
            text = "Eligibility for {} ({}): {}".format(p["name"], p["duration"],
                                                        p["eligibility"])
        else:
            lines = ["To be eligible for B.Tech admission you must have:"]
            lines.append(kb["programs"][0]["eligibility"])
            text = " ".join(lines)
        return text
    if intent == "courses":
        lines = ["The college offers the following UG programs:"]
        for p in retrieved["programs"]:
            lines.append("- {} ({}), {} years, intake {} students".format(
                p["name"], p["code"], p["duration"].split()[0], p["intake"]))
        return " ".join(lines)
    if intent == "fees":
        totals = retrieved["totals"]
        if program and totals.get(program):
            lines = ["First-year fee for {} ({}):".format(
                [p["name"] for p in kb["programs"] if p["code"] == program][0], program)]
            for f in retrieved["fees"]:
                lines.append("- {}: {} ({})".format(f["component"], _fmt_amount(f["amount"]),
                                                    f["frequency"]))
            lines.append("Total first-year fee: {}".format(_fmt_amount(totals[program])))
        else:
            lines = ["First-year fees by program:"]
            for p in kb["programs"]:
                lines.append("- {}: {}".format(p["name"], _fmt_amount(totals.get(p["code"], p["first_year_fees"]))))
            lines.append("Hostel charges: {} per year (accommodation) and {} per year (mess), additional.".format(
                _fmt_amount(retrieved["hostel_fees"][0]["amount"]) if retrieved.get("hostel_fees") else "-",
                _fmt_amount(retrieved["hostel_fees"][1]["amount"]) if len(retrieved.get("hostel_fees", [])) > 1 else "-"))
        return " ".join(lines)
    if intent == "procedure":
        lines = ["The admission procedure is as follows:"]
        for i, s in enumerate(retrieved["steps"], 1):
            lines.append("{}. {}.".format(i, s.rstrip(".")))
        if retrieved.get("dates"):
            lines.append("Key dates: " + "; ".join(
                "{} - {}".format(d["event"], d["date"]) for d in retrieved["dates"]))
        return " ".join(lines)
    if intent == "facilities":
        lines = ["The college campus provides the following facilities:"]
        for f in retrieved["facilities"]:
            lines.append("- {}: {}.".format(f["name"], f["description"].rstrip(".")))
        return " ".join(lines)
    # general
    return ("I can answer questions about admission eligibility, courses offered, "
            "fees, the admission procedure and campus facilities. For anything "
            "outside these topics, please contact the admission cell at "
            + kb["college"].get("website", "the college website") + ".")


def gpt_answer(question, intent, program, kb, retrieved, api_key, model):
    """Layer 2: ask OpenAI GPT to phrase the answer from verified records.

    The retrieved records are serialized into the prompt as the ONLY source
    of admission facts, and the model is instructed not to invent details -
    a retrieval-augmented generation (RAG) style pattern.
    """
    context = json.dumps(retrieved, indent=1, default=str)[:6000]
    system_prompt = (
        "You are the admission enquiry assistant of {college}. "
        "Answer the student's question using ONLY the admission data provided "
        "in the context below. If the context does not contain the answer, say "
        "that the student should contact the admission cell. Be brief, polite "
        "and factual; use plain sentences; do not invent fees, dates or rules.\n\n"
        "Context:\n{context}"
    ).format(college=kb["college"]["name"], context=context)
    user_prompt = question

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 350,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


class GPTAssistant:
    def __init__(self, kb):
        self.kb = kb
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.stats = {"questions_answered": 0, "gpt_calls": 0,
                      "offline_answers": 0, "by_intent": {i: 0 for i in INTENTS}}

    # -- public API ------------------------------------------------------
    def mode(self):
        return "online" if self.api_key else "offline"

    def answer(self, question):
        t0 = time.time()
        intent, scores = classify_intent(question)
        program = detect_program(question)
        retrieved = retrieve(self.kb, intent, program)

        mode_used = "offline"
        text = None
        if self.mode() == "online":
            try:
                text = gpt_answer(question, intent, program, self.kb,
                                  retrieved, self.api_key, self.model)
                mode_used = "online"
                self.stats["gpt_calls"] += 1
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                    TimeoutError, OSError) as exc:
                print("[ai] GPT call failed ({}); falling back to offline composer".format(exc))

        if text is None:
            text = compose_offline(question, intent, program, self.kb, retrieved)
            self.stats["offline_answers"] += 1

        self.stats["questions_answered"] += 1
        self.stats["by_intent"][intent] = self.stats["by_intent"].get(intent, 0) + 1

        answer = {"text": text,
                  "html": "<p>" + _html.escape(text).replace("\n", "<br/>") + "</p>"}
        meta = {"intent": intent, "program": program, "mode": mode_used,
                "latency_ms": int((time.time() - t0) * 1000),
                "model": self.model if mode_used == "online" else "kb-composer"}
        return answer, meta
