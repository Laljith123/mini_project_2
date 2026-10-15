/**
 * AI Engine module for Next.js Admission Enquiry Assistant.
 */

import {
  FAQ,
  Intent,
  KnowledgeBase,
  ChatResponse,
  AnswerMeta,
} from "./types";
import { getKnowledgeBase, getFaqMatch } from "./knowledgeBase";
import { formatAnswerHtml } from "./security";

const INTENT_PATTERNS: [RegExp, Intent, number][] = [
  [
    /\b(?:eligib\w*|qualif\w*|requirement\w*|criteria|marks|percentage|percent\b|cutoff\w*|10\+2|hsc|score\w*)\b/i,
    "eligibility",
    3,
  ],
  [
    /\b(?:fee\w*|cost|tuition|charge\w*|how much|price|expensive|payment\w*|mess fee\w*|hostel fee\w*)\b/i,
    "fees",
    3,
  ],
  [
    /\b(?:admission procedure|admission process|how to apply|apply\w*|application|join\w*|enrol\w*|step\w*|documents? required|certificate verification|deadline\w*|last date|important dates|dates|schedule|counselling)\b/i,
    "procedure",
    3,
  ],
  [
    /\b(?:facilit\w*|hostel|librar\w*|lab\w*|laborator\w*|sports|transport|bus\b|gym|placement\w*|campus|canteen|mess|medical|wifi|wi-fi|hospital)\b/i,
    "facilities",
    3,
  ],
  [
    /\b(?:course\w*|programs? offered|branches? offered|what branches|what courses|degrees? offered|ug courses|curriculum|syllabus)\b/i,
    "courses",
    3,
  ],
  [
    /\b(?:program\w*|branch\w*|department\w*|courses?|intake|seats?)\b/i,
    "courses",
    1,
  ],
];

const BRANCH_CODES: Record<string, string> = {
  cse: "CSE",
  "computer science": "CSE",
  "computer science and engineering": "CSE",
  "information technology": "IT",
  it: "IT",
  ece: "ECE",
  electronics: "ECE",
  "electronics and communication": "ECE",
  mech: "MECH",
  mechanical: "MECH",
  "mechanical engineering": "MECH",
  civil: "CIVIL",
  "civil engineering": "CIVIL",
  "ai-ds": "AI-DS",
  "ai ds": "AI-DS",
  "data science": "AI-DS",
  "artificial intelligence": "AI-DS",
  "artificial intelligence and data science": "AI-DS",
};

const AMBIGUOUS: Record<string, string> = { it: "IT", ai: "AI-DS" };
const BRANCH_CONTEXT =
  /\b(?:fee\w*|course\w*|program\w*|branch\w*|department\w*|eligib\w*|admission|intake|seats?|cutoff|marks|degree\w*|offer\w*|b\.?tech|btech)\b/i;

export function detectProgram(question: string): string | null {
  const q = question.toLowerCase();

  const sortedPhrases = Object.keys(BRANCH_CODES).sort(
    (a, b) => b.length - a.length
  );
  for (const phrase of sortedPhrases) {
    if (phrase in AMBIGUOUS) continue;
    const regex = new RegExp(`\\b${phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    if (regex.test(q)) {
      return BRANCH_CODES[phrase];
    }
  }

  const tokens = q.match(/\b[a-z0-9-]+\b/g) || [];
  for (const token of tokens) {
    if (token in AMBIGUOUS && BRANCH_CONTEXT.test(q)) {
      return AMBIGUOUS[token];
    }
  }

  return null;
}

export function classifyIntent(
  question: string,
  kb: KnowledgeBase
): { intent: Intent; scores: Record<string, number>; matchedFaq: FAQ | null } {
  const faqMatch = getFaqMatch(kb, question);
  if (faqMatch) {
    return { intent: "faq", scores: { faq: 1.0 }, matchedFaq: faqMatch };
  }

  const scores: Record<string, number> = {};
  for (const [pattern, intent, weight] of INTENT_PATTERNS) {
    const matches = question.match(new RegExp(pattern.source, "gi"));
    if (matches && matches.length > 0) {
      scores[intent] = (scores[intent] || 0) + matches.length * weight;
    }
  }

  const topIntent = Object.keys(scores).reduce<Intent | null>((best, curr) => {
    if (!best || scores[curr] > (scores[best] || 0)) {
      return curr as Intent;
    }
    return best;
  }, null);

  if (topIntent) {
    return { intent: topIntent, scores, matchedFaq: null };
  }

  return { intent: "general", scores, matchedFaq: null };
}

export function retrieve(
  kb: KnowledgeBase,
  intent: Intent,
  program: string | null,
  matchedFaq: FAQ | null
): Record<string, unknown> {
  if (intent === "faq" && matchedFaq) {
    return { faq: matchedFaq, college: kb.college };
  }
  if (intent === "eligibility") {
    const recs = program
      ? (kb.programs || []).filter((p) => p.code === program)
      : kb.programs;
    return { programs: recs, college: kb.college };
  }
  if (intent === "courses") {
    return { programs: kb.programs, college: kb.college };
  }
  if (intent === "fees") {
    const fees = (kb.fee_structure || []).filter(
      (f) => program === null || f.program === program
    );
    return {
      fees,
      hostel_fees: kb.hostel_fees,
      totals: kb.derived_total_first_year_fees,
      programs: kb.programs,
    };
  }
  if (intent === "procedure") {
    return {
      steps: kb.admission_procedure,
      dates: kb.important_dates || [],
      college: kb.college,
    };
  }
  if (intent === "facilities") {
    return {
      facilities: kb.facilities,
      hostel_fees: kb.hostel_fees,
    };
  }
  return {
    programs: kb.programs,
    faqs: kb.faqs,
    college: kb.college,
  };
}

function fmtAmount(n: number): string {
  return "Rs. " + Math.round(n).toLocaleString();
}

export function composeOffline(
  question: string,
  intent: Intent,
  program: string | null,
  kb: KnowledgeBase,
  retrieved: Record<string, unknown>,
  matchedFaq: FAQ | null
): string {
  if (intent === "faq" && (matchedFaq || retrieved.faq)) {
    const f = (matchedFaq || retrieved.faq) as FAQ;
    return `Q: ${f.q}\nA: ${f.a}`;
  }

  if (intent === "eligibility") {
    const recs = (retrieved.programs || []) as KnowledgeBase["programs"];
    if (program && recs.length > 0) {
      const p = recs[0];
      return `Eligibility for ${p.name} (${p.code}): ${p.eligibility} Course duration is ${p.duration} with an intake of ${p.intake} seats.`;
    }
    const lines = [
      "Eligibility criteria for B.Tech programs at Sri Manakula Vinayagar Engineering College:",
      "Pass in 10+2 with Mathematics, Physics and Chemistry with a minimum 50% aggregate marks (45% for reserved categories).",
      "Admission is conducted through counselling based on 10+2 marks / entrance rank as per Government of Puducherry norms.",
      "Offered branches include: " +
        (kb.programs || []).map((p) => `${p.name} (${p.code})`).join(", "),
    ];
    return lines.join("\n\n");
  }

  if (intent === "courses") {
    const lines = [
      "Sri Manakula Vinayagar Engineering College offers the following undergraduate (B.Tech) programs:",
    ];
    for (const p of (retrieved.programs || []) as KnowledgeBase["programs"]) {
      lines.push(
        `• ${p.name} (${p.code}): ${p.duration}, intake of ${p.intake} students.`
      );
    }
    return lines.join("\n");
  }

  if (intent === "fees") {
    const totals = (retrieved.totals || {}) as Record<string, number>;
    const qLower = question.toLowerCase();

    if (qLower.includes("hostel") || qLower.includes("mess")) {
      const lines = ["Hostel and accommodation fee structure:"];
      for (const h of (retrieved.hostel_fees || []) as KnowledgeBase["hostel_fees"]) {
        lines.push(`• ${h.component}: ${fmtAmount(h.amount)} (${h.frequency})`);
      }
      return lines.join("\n");
    }

    if (program && totals[program]) {
      const pName =
        (kb.programs || []).find((p) => p.code === program)?.name || program;
      const lines = [`First-year fee breakdown for ${pName} (${program}):`];
      for (const f of (retrieved.fees || []) as KnowledgeBase["fee_structure"]) {
        lines.push(`• ${f.component}: ${fmtAmount(f.amount)} (${f.frequency})`);
      }
      lines.push(
        `Total first-year tuition & academic fees: ${fmtAmount(totals[program])}`
      );
      return lines.join("\n");
    }

    const lines = ["First-year academic fees by program:"];
    for (const p of kb.programs || []) {
      lines.push(
        `• ${p.name} (${p.code}): ${fmtAmount(
          totals[p.code] || p.first_year_fees
        )}`
      );
    }
    if ((retrieved.hostel_fees as unknown[])?.length) {
      lines.push("\nOptional Hostel charges:");
      for (const h of (retrieved.hostel_fees || []) as KnowledgeBase["hostel_fees"]) {
        lines.push(`• ${h.component}: ${fmtAmount(h.amount)} (${h.frequency})`);
      }
    }
    return lines.join("\n");
  }

  if (intent === "procedure") {
    const qLower = question.toLowerCase();
    if (["date", "deadline", "schedule", "when"].some((w) => qLower.includes(w))) {
      const lines = ["Important admission dates (2026):"];
      for (const d of (retrieved.dates || []) as NonNullable<KnowledgeBase["important_dates"]>) {
        lines.push(`• ${d.event}: ${d.date}`);
      }
      return lines.join("\n");
    }

    const lines = ["Step-by-step admission procedure:"];
    const steps = (retrieved.steps || []) as string[];
    steps.forEach((step, idx) => {
      lines.push(`${idx + 1}. ${step.replace(/\.+$/, "")}.`);
    });
    if ((retrieved.dates as unknown[])?.length) {
      lines.push("\nKey admission dates:");
      for (const d of (retrieved.dates || []) as NonNullable<KnowledgeBase["important_dates"]>) {
        lines.push(`• ${d.event}: ${d.date}`);
      }
    }
    return lines.join("\n");
  }

  if (intent === "facilities") {
    const lines = [
      "Campus facilities available at Sri Manakula Vinayagar Engineering College:",
    ];
    for (const fac of (retrieved.facilities || []) as KnowledgeBase["facilities"]) {
      lines.push(`• ${fac.name}: ${fac.description.replace(/\.+$/, "")}.`);
    }
    return lines.join("\n");
  }

  const website = kb.college?.website || "https://www.smvec.ac.in";
  return (
    "I can answer questions regarding college admissions, including eligibility criteria, " +
    "courses offered, fee structures, application procedures, and campus facilities. " +
    `For specific administrative queries, please visit the admission portal at ${website}.`
  );
}

export async function gptAnswer(
  question: string,
  kb: KnowledgeBase,
  retrieved: Record<string, unknown>,
  apiKey: string,
  model: string = "gpt-4o-mini"
): Promise<string> {
  const context = JSON.stringify(retrieved, null, 1).slice(0, 6000);
  const collegeName = kb.college?.name || "the college";

  const systemPrompt =
    `You are the official admission enquiry assistant of ${collegeName}. ` +
    "Answer the student's enquiry using ONLY the admission data provided in the context below. " +
    "If the context does not contain sufficient details to answer, politely advise the student " +
    "to contact the college admission cell. " +
    "Be concise, professional, courteous, and strictly factual. Never invent fees, dates, or courses.\n\n" +
    `Context:\n${context}`;

  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: question },
      ],
      temperature: 0.2,
      max_tokens: 350,
    }),
  });

  if (!res.ok) {
    throw new Error(`OpenAI API returned status ${res.status}`);
  }

  const data = await res.json();
  const choice = data.choices?.[0]?.message?.content;
  if (!choice) {
    throw new Error("Empty completion choices from OpenAI API");
  }
  return choice.trim();
}

// Diagnostics state
export const AI_STATS = {
  questions_answered: 0,
  gpt_calls: 0,
  offline_answers: 0,
  by_intent: {
    eligibility: 0,
    courses: 0,
    fees: 0,
    procedure: 0,
    facilities: 0,
    faq: 0,
    general: 0,
  } as Record<Intent, number>,
};

export async function answerEnquiry(
  question: string,
  clientApiKey?: string
): Promise<ChatResponse> {
  const t0 = Date.now();
  const kb = getKnowledgeBase();
  const { intent, matchedFaq } = classifyIntent(question, kb);
  const program = detectProgram(question);
  const retrieved = retrieve(kb, intent, program, matchedFaq);

  const apiKey = clientApiKey?.trim() || process.env.OPENAI_API_KEY?.trim() || "";
  const model = process.env.OPENAI_MODEL?.trim() || "gpt-4o-mini";

  let modeUsed: "online" | "offline" = "offline";
  let answerText: string | null = null;

  if (apiKey) {
    try {
      answerText = await gptAnswer(question, kb, retrieved, apiKey, model);
      modeUsed = "online";
      AI_STATS.gpt_calls++;
    } catch (err) {
      console.warn("GPT call failed, falling back to offline composer:", err);
    }
  }

  if (!answerText) {
    answerText = composeOffline(
      question,
      intent,
      program,
      kb,
      retrieved,
      matchedFaq
    );
    AI_STATS.offline_answers++;
  }

  AI_STATS.questions_answered++;
  AI_STATS.by_intent[intent] = (AI_STATS.by_intent[intent] || 0) + 1;

  const latency_ms = Date.now() - t0;
  const meta: AnswerMeta = {
    intent,
    program,
    mode: modeUsed,
    latency_ms,
    model: modeUsed === "online" ? model : "kb-composer",
  };

  return {
    question,
    answer: answerText,
    html: formatAnswerHtml(answerText),
    meta,
  };
}
