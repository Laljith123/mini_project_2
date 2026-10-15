"""
Data Engineering pipeline for the College Admission Enquiry Assistant.

Stage 1 - Collection : admission data curated into a single JSON source.
Stage 2 - Validation : every record is checked (required fields, types,
                       referential integrity of fee -> program links).
Stage 3 - Transform  : derived views are computed (fee totals per program,
                       keyword index for retrieval).
Stage 4 - Loading    : the validated knowledge base is handed to the AI
                       engine and to the /kb browser view.

The validation report produced by validate() is surfaced in the web UI so
that data quality is continuously visible, not assumed.
"""

import json
import re

REQUIRED_PROGRAM_FIELDS = ["code", "name", "duration", "intake",
                           "eligibility", "first_year_fees"]
REQUIRED_FEE_FIELDS = ["program", "component", "amount", "frequency"]


def load_raw(path):
    """Stage 1 - Collection: read the raw JSON data source."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(kb):
    """Stage 2 - Validation: returns a list of human-readable findings."""
    findings = []
    errors = 0

    program_codes = set()
    for p in kb.get("programs", []):
        for field in REQUIRED_PROGRAM_FIELDS:
            if field not in p:
                findings.append("program '{}': missing field '{}'".format(
                    p.get("name", "?"), field))
                errors += 1
        if not isinstance(p.get("intake"), int):
            findings.append("program '{}': intake must be an integer".format(
                p.get("name", "?")))
            errors += 1
        program_codes.add(p.get("code"))

    for f in kb.get("fee_structure", []):
        for field in REQUIRED_FEE_FIELDS:
            if field not in f:
                findings.append("fee entry: missing field '{}'".format(field))
                errors += 1
        if f.get("program") and f["program"] not in program_codes:
            findings.append("fee entry for unknown program code '{}'".format(
                f.get("program")))
            errors += 1
        if not isinstance(f.get("amount"), (int, float)) or f.get("amount", 0) < 0:
            findings.append("fee entry '{}': amount must be a positive number".format(
                f.get("component", "?")))
            errors += 1

    if not findings:
        findings.append("all records passed validation (0 errors)")
    return findings, errors


def transform(kb):
    """Stage 3 - Transform: compute derived views used by the AI engine.

    - total_first_year_fees per program code
    - an inverted keyword index mapping terms -> program codes / facility ids
    """
    totals = {}
    for entry in kb.get("fee_structure", []):
        code = entry["program"]
        if entry["frequency"] == "yearly":
            totals[code] = totals.get(code, 0) + entry["amount"]
    kb["derived_total_first_year_fees"] = totals

    index = {}
    for p in kb.get("programs", []):
        text = " ".join([p["code"], p["name"], p.get("eligibility", ""),
                         p.get("about", "")]).lower()
        for term in re.findall(r"[a-z]+", text):
            index.setdefault(term, set()).add(("program", p["code"]))
    for fac in kb.get("facilities", []):
        text = " ".join([fac["name"], fac.get("description", "")]).lower()
        for term in re.findall(r"[a-z]+", text):
            index.setdefault(term, set()).add(("facility", fac["name"]))
    for faq in kb.get("faqs", []):
        text = " ".join([faq["q"], faq["a"]]).lower()
        for term in re.findall(r"[a-z]+", text):
            index.setdefault(term, set()).add(("faq", faq["q"]))
    # convert sets -> sorted lists so the structure is JSON-serializable
    kb["keyword_index"] = {k: sorted(v) for k, v in index.items()}
    return kb


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
        raise ValueError("knowledge base failed validation: {} errors".format(errors))
    kb = transform(kb)
    print("[data] transform complete: {} indexed terms, {} program fee totals".format(
        len(kb["keyword_index"]), len(kb["derived_total_first_year_fees"])))
    return kb


if __name__ == "__main__":
    import sys
    kb = load_and_validate(sys.argv[1] if len(sys.argv) > 1 else "knowledge_base.json")
    import json as j
    print(j.dumps(kb["derived_total_first_year_fees"], indent=2))
