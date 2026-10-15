"""
Data Engineering pipeline for the College Admission Enquiry Assistant.

Stage 1 - Collection : admission data curated into a single JSON source.
Stage 2 - Validation : every record is checked (required fields, types,
                       referential integrity of fee -> program links,
                       non-negative amounts, complete facility & FAQ records).
Stage 3 - Transform  : derived views are computed (fee totals per program,
                       keyword index for fast retrieval, normalized query maps).
Stage 4 - Loading    : the validated knowledge base is handed to the AI
                       engine and to the /kb browser view.

The validation report produced by validate() is surfaced in the web UI so
that data quality is continuously visible, not assumed.
"""

import json
import re

REQUIRED_PROGRAM_FIELDS = [
    "code", "name", "duration", "intake",
    "eligibility", "first_year_fees"
]
REQUIRED_FEE_FIELDS = ["program", "component", "amount", "frequency"]
REQUIRED_FACILITY_FIELDS = ["name", "description"]
REQUIRED_FAQ_FIELDS = ["q", "a"]


def load_raw(path):
    """Stage 1 - Collection: read the raw JSON data source."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(kb):
    """Stage 2 - Validation: inspect all records and return human-readable findings and error count."""
    findings = []
    errors = 0

    # College metadata
    college = kb.get("college", {})
    if not isinstance(college, dict) or not college.get("name"):
        findings.append("college: missing required college name")
        errors += 1

    # Programs
    program_codes = set()
    programs = kb.get("programs", [])
    if not programs:
        findings.append("programs: list is empty")
        errors += 1

    for p in programs:
        for field in REQUIRED_PROGRAM_FIELDS:
            if field not in p:
                findings.append(f"program '{p.get('name', '?')}': missing field '{field}'")
                errors += 1
        if not isinstance(p.get("intake"), int) or p.get("intake", 0) <= 0:
            findings.append(f"program '{p.get('name', '?')}': intake must be a positive integer")
            errors += 1
        if not isinstance(p.get("first_year_fees"), (int, float)) or p.get("first_year_fees", 0) < 0:
            findings.append(f"program '{p.get('name', '?')}': first_year_fees must be non-negative")
            errors += 1
        code = p.get("code")
        if code:
            program_codes.add(code)

    # Fee structure
    for f in kb.get("fee_structure", []):
        for field in REQUIRED_FEE_FIELDS:
            if field not in f:
                findings.append(f"fee entry: missing field '{field}'")
                errors += 1
        if f.get("program") and f["program"] not in program_codes:
            findings.append(f"fee entry references unknown program code '{f.get('program')}'")
            errors += 1
        if not isinstance(f.get("amount"), (int, float)) or f.get("amount", 0) < 0:
            findings.append(f"fee entry '{f.get('component', '?')}': amount must be a non-negative number")
            errors += 1

    # Hostel fees
    for h in kb.get("hostel_fees", []):
        if not h.get("component"):
            findings.append("hostel fee: missing component name")
            errors += 1
        if not isinstance(h.get("amount"), (int, float)) or h.get("amount", 0) < 0:
            findings.append(f"hostel fee '{h.get('component', '?')}': amount must be non-negative")
            errors += 1

    # Admission procedure
    steps = kb.get("admission_procedure", [])
    if not isinstance(steps, list) or not steps:
        findings.append("admission_procedure: must be a non-empty list of steps")
        errors += 1

    # Facilities
    for fac in kb.get("facilities", []):
        for field in REQUIRED_FACILITY_FIELDS:
            if field not in fac or not fac[field]:
                findings.append(f"facility '{fac.get('name', '?')}': missing field '{field}'")
                errors += 1

    # FAQs
    for faq in kb.get("faqs", []):
        for field in REQUIRED_FAQ_FIELDS:
            if field not in faq or not faq[field]:
                findings.append(f"faq entry: missing field '{field}'")
                errors += 1

    if not findings:
        findings.append("all records passed validation (0 errors)")
    return findings, errors


def transform(kb):
    """Stage 3 - Transform: compute derived views and indices used by the AI engine.

    - total_first_year_fees per program code
    - inverted keyword index mapping normalized terms -> entities
    - normalized query lookup for curated FAQs
    """
    totals = {}
    for entry in kb.get("fee_structure", []):
        code = entry.get("program")
        if entry.get("frequency") == "yearly":
            totals[code] = totals.get(code, 0) + entry.get("amount", 0)
    kb["derived_total_first_year_fees"] = totals

    index = {}
    stopwords = {"what", "is", "the", "for", "in", "and", "to", "of", "a", "an", "how", "much", "are"}

    for p in kb.get("programs", []):
        text = " ".join([
            p.get("code", ""),
            p.get("name", ""),
            p.get("eligibility", ""),
            p.get("about", "")
        ]).lower()
        for term in re.findall(r"[a-z0-9]+", text):
            if len(term) >= 2 and term not in stopwords:
                index.setdefault(term, set()).add(("program", p["code"]))

    for fac in kb.get("facilities", []):
        text = " ".join([fac.get("name", ""), fac.get("description", "")]).lower()
        for term in re.findall(r"[a-z0-9]+", text):
            if len(term) >= 2 and term not in stopwords:
                index.setdefault(term, set()).add(("facility", fac["name"]))

    for idx, faq in enumerate(kb.get("faqs", [])):
        text = " ".join([faq.get("q", ""), faq.get("a", "")]).lower()
        for term in re.findall(r"[a-z0-9]+", text):
            if len(term) >= 2 and term not in stopwords:
                index.setdefault(term, set()).add(("faq", idx))

    # Convert sets to sorted lists for JSON serializability and stability
    kb["keyword_index"] = {k: sorted(v) for k, v in index.items()}
    return kb


def get_faq_match(kb, question):
    """Match a user question against curated FAQs using token overlap scoring.

    Returns the matching FAQ dict or None if no confident match is found.
    """
    q_tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    stopwords = {"what", "is", "the", "for", "in", "and", "to", "of", "a", "an", "how", "much", "are", "do", "does", "can", "i"}
    meaningful = q_tokens - stopwords
    if not meaningful:
        return None

    best_faq = None
    best_score = 0.0

    for faq in kb.get("faqs", []):
        faq_tokens = set(re.findall(r"[a-z0-9]+", faq["q"].lower())) - stopwords
        if not faq_tokens:
            continue
        overlap = meaningful & faq_tokens
        if not overlap:
            continue
        # Jaccard-like similarity coefficient
        score = len(overlap) / len(meaningful | faq_tokens)
        if score > best_score:
            best_score = score
            best_faq = faq

    # Confidence threshold for direct FAQ answering
    if best_score >= 0.35:
        return best_faq
    return None


def get_program_by_code(kb, code):
    """Retrieve program record by branch code."""
    for p in kb.get("programs", []):
        if p.get("code") == code:
            return p
    return None


def knowledge_base_stats(kb):
    """Summary statistics shown on the knowledge base browser page."""
    findings, errors = validate(kb)
    return {
        "programs": len(kb.get("programs", [])),
        "fee_components": len(kb.get("fee_structure", [])),
        "facilities": len(kb.get("facilities", [])),
        "faqs": len(kb.get("faqs", [])),
        "validation_errors": errors,
        "validation_report": "; ".join(findings),
    }


def load_and_validate(path):
    """Run the full pipeline: load -> validate -> transform -> return KB."""
    kb = load_raw(path)
    findings, errors = validate(kb)
    print("[data] validation report:")
    for f in findings:
        print("[data]   " + f)
    if errors:
        raise ValueError(f"knowledge base failed validation: {errors} errors")
    kb = transform(kb)
    print(f"[data] transform complete: {len(kb['keyword_index'])} indexed terms, {len(kb['derived_total_first_year_fees'])} program fee totals")
    return kb


if __name__ == "__main__":
    import sys
    kb = load_and_validate(sys.argv[1] if len(sys.argv) > 1 else "knowledge_base.json")
    print(json.dumps(kb["derived_total_first_year_fees"], indent=2))
