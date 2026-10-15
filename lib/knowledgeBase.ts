/**
 * Data Pipeline module for College Admission Knowledge Base.
 */

import rawKnowledgeBase from "../knowledge_base.json";
import { FAQ, KnowledgeBase, KBStats } from "./types";

const REQUIRED_PROGRAM_FIELDS = [
  "code",
  "name",
  "duration",
  "intake",
  "eligibility",
  "first_year_fees",
];
const REQUIRED_FEE_FIELDS = ["program", "component", "amount", "frequency"];

export function validate(kb: KnowledgeBase): {
  findings: string[];
  errors: number;
} {
  const findings: string[] = [];
  let errors = 0;

  if (!kb.college?.name) {
    findings.push("college: missing required college name");
    errors++;
  }

  const programCodes = new Set<string>();
  if (!Array.isArray(kb.programs) || kb.programs.length === 0) {
    findings.push("programs: list is empty");
    errors++;
  } else {
    for (const p of kb.programs) {
      for (const field of REQUIRED_PROGRAM_FIELDS) {
        if (!(field in p)) {
          findings.push(`program '${p.name || "?"}': missing field '${field}'`);
          errors++;
        }
      }
      if (typeof p.intake !== "number" || p.intake <= 0) {
        findings.push(
          `program '${p.name || "?"}': intake must be a positive integer`
        );
        errors++;
      }
      if (typeof p.first_year_fees !== "number" || p.first_year_fees < 0) {
        findings.push(
          `program '${p.name || "?"}': first_year_fees must be non-negative`
        );
        errors++;
      }
      if (p.code) {
        programCodes.add(p.code);
      }
    }
  }

  for (const f of kb.fee_structure || []) {
    for (const field of REQUIRED_FEE_FIELDS) {
      if (!(field in f)) {
        findings.push(`fee entry: missing field '${field}'`);
        errors++;
      }
    }
    if (f.program && !programCodes.has(f.program)) {
      findings.push(
        `fee entry references unknown program code '${f.program}'`
      );
      errors++;
    }
    if (typeof f.amount !== "number" || f.amount < 0) {
      findings.push(
        `fee entry '${f.component || "?"}': amount must be a non-negative number`
      );
      errors++;
    }
  }

  for (const h of kb.hostel_fees || []) {
    if (!h.component) {
      findings.push("hostel fee: missing component name");
      errors++;
    }
    if (typeof h.amount !== "number" || h.amount < 0) {
      findings.push(
        `hostel fee '${h.component || "?"}': amount must be non-negative`
      );
      errors++;
    }
  }

  if (
    !Array.isArray(kb.admission_procedure) ||
    kb.admission_procedure.length === 0
  ) {
    findings.push("admission_procedure: must be a non-empty list of steps");
    errors++;
  }

  for (const fac of kb.facilities || []) {
    if (!fac.name || !fac.description) {
      findings.push(`facility '${fac.name || "?"}': missing required fields`);
      errors++;
    }
  }

  for (const faq of kb.faqs || []) {
    if (!faq.q || !faq.a) {
      findings.push("faq entry: missing required fields 'q' and 'a'");
      errors++;
    }
  }

  if (findings.length === 0) {
    findings.push("all records passed validation (0 errors)");
  }

  return { findings, errors };
}

export function transform(kb: KnowledgeBase): KnowledgeBase {
  const totals: Record<string, number> = {};
  for (const entry of kb.fee_structure || []) {
    if (entry.frequency === "yearly") {
      totals[entry.program] = (totals[entry.program] || 0) + entry.amount;
    }
  }
  kb.derived_total_first_year_fees = totals;

  const index: Record<string, Set<string>> = {};
  const stopwords = new Set([
    "what",
    "is",
    "the",
    "for",
    "in",
    "and",
    "to",
    "of",
    "a",
    "an",
    "how",
    "much",
    "are",
  ]);

  for (const p of kb.programs || []) {
    const text = `${p.code} ${p.name} ${p.eligibility || ""} ${p.about || ""}`.toLowerCase();
    const terms = text.match(/[a-z0-9]+/g) || [];
    for (const term of terms) {
      if (term.length >= 2 && !stopwords.has(term)) {
        if (!index[term]) index[term] = new Set();
        index[term].add(`program:${p.code}`);
      }
    }
  }

  for (const fac of kb.facilities || []) {
    const text = `${fac.name} ${fac.description || ""}`.toLowerCase();
    const terms = text.match(/[a-z0-9]+/g) || [];
    for (const term of terms) {
      if (term.length >= 2 && !stopwords.has(term)) {
        if (!index[term]) index[term] = new Set();
        index[term].add(`facility:${fac.name}`);
      }
    }
  }

  for (let idx = 0; idx < (kb.faqs || []).length; idx++) {
    const faq = kb.faqs[idx];
    const text = `${faq.q} ${faq.a}`.toLowerCase();
    const terms = text.match(/[a-z0-9]+/g) || [];
    for (const term of terms) {
      if (term.length >= 2 && !stopwords.has(term)) {
        if (!index[term]) index[term] = new Set();
        index[term].add(`faq:${idx}`);
      }
    }
  }

  const serializedIndex: Record<string, [string, string | number][]> = {};
  for (const [k, v] of Object.entries(index)) {
    serializedIndex[k] = Array.from(v)
      .sort()
      .map((item) => {
        const [type, id] = item.split(":");
        return [type, isNaN(Number(id)) ? id : Number(id)];
      });
  }
  kb.keyword_index = serializedIndex;

  return kb;
}

export function getFaqMatch(kb: KnowledgeBase, question: string): FAQ | null {
  const qTokens = new Set(question.toLowerCase().match(/[a-z0-9]+/g) || []);
  const stopwords = new Set([
    "what",
    "is",
    "the",
    "for",
    "in",
    "and",
    "to",
    "of",
    "a",
    "an",
    "how",
    "much",
    "are",
    "do",
    "does",
    "can",
    "i",
  ]);

  const meaningful = new Set(
    Array.from(qTokens).filter((t) => !stopwords.has(t))
  );
  if (meaningful.size === 0) return null;

  let bestFaq: FAQ | null = null;
  let bestScore = 0.0;

  for (const faq of kb.faqs || []) {
    const faqTokens = new Set(
      (faq.q.toLowerCase().match(/[a-z0-9]+/g) || []).filter(
        (t) => !stopwords.has(t)
      )
    );
    if (faqTokens.size === 0) continue;

    let overlapCount = 0;
    for (const token of Array.from(meaningful)) {
      if (faqTokens.has(token)) overlapCount++;
    }

    if (overlapCount === 0) continue;

    const unionCount = new Set([...Array.from(meaningful), ...Array.from(faqTokens)]).size;
    const score = overlapCount / unionCount;

    if (score > bestScore) {
      bestScore = score;
      bestFaq = faq;
    }
  }

  if (bestScore >= 0.35) {
    return bestFaq;
  }
  return null;
}

let cachedKB: KnowledgeBase | null = null;

export function getKnowledgeBase(): KnowledgeBase {
  if (!cachedKB) {
    const raw = JSON.parse(JSON.stringify(rawKnowledgeBase)) as KnowledgeBase;
    const { errors, findings } = validate(raw);
    if (errors > 0) {
      throw new Error(`Knowledge base failed validation: ${findings.join("; ")}`);
    }
    cachedKB = transform(raw);
  }
  return cachedKB;
}

export function getKnowledgeBaseStats(): KBStats {
  const kb = getKnowledgeBase();
  const { errors, findings } = validate(kb);
  return {
    programs: (kb.programs || []).length,
    fee_components: (kb.fee_structure || []).length,
    facilities: (kb.facilities || []).length,
    faqs: (kb.faqs || []).length,
    validation_errors: errors,
    validation_report: findings.join("; "),
  };
}
