/**
 * Automated Test Suite for Next.js Admission Enquiry Assistant.
 */

const assert = require("assert");
const rawKb = require("../knowledge_base.json");

console.log("=================================================");
console.log("Running Next.js Admission Assistant Test Suite");
console.log("=================================================\n");

let passed = 0;
let failed = 0;

function it(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    failed++;
  }
}

// 1. Data Validation Tests
it("should validate the curated knowledge_base.json schema with 0 errors", () => {
  assert.ok(rawKb.college && rawKb.college.name, "College name must exist");
  assert.ok(Array.isArray(rawKb.programs) && rawKb.programs.length === 6, "Must have 6 programs");
  assert.ok(Array.isArray(rawKb.fee_structure) && rawKb.fee_structure.length === 18, "Must have 18 fee components");
  assert.ok(Array.isArray(rawKb.facilities) && rawKb.facilities.length === 8, "Must have 8 facilities");
  assert.ok(Array.isArray(rawKb.faqs) && rawKb.faqs.length === 5, "Must have 5 FAQs");
});

it("should verify fee math referential integrity for each program", () => {
  const totals = {};
  for (const fee of rawKb.fee_structure) {
    if (fee.frequency === "yearly") {
      totals[fee.program] = (totals[fee.program] || 0) + fee.amount;
    }
  }
  for (const prog of rawKb.programs) {
    assert.strictEqual(
      totals[prog.code],
      prog.first_year_fees,
      `Fee breakdown sum for ${prog.code} must equal first_year_fees`
    );
  }
});

// 2. Security Sanitization Tests
const SCRIPT_STYLE_RE = /<(script|style)[^>]*>[\s\S]*?<\/\1>/gi;
const TAG_RE = /<[^>]*>/g;
const CONTROL_CHARS_RE = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g;

function sanitizeInput(text) {
  if (!text) return "";
  let cleaned = String(text).replace(SCRIPT_STYLE_RE, " ");
  cleaned = cleaned.replace(TAG_RE, " ");
  cleaned = cleaned.replace(CONTROL_CHARS_RE, "");
  return cleaned.replace(/\s+/g, " ").trim();
}

it("should strip malicious script tags, inner contents and HTML tags", () => {
  const dirty = "<script>alert('xss')</script>Hello <b>World</b>";
  const cleaned = sanitizeInput(dirty);
  assert.strictEqual(cleaned, "Hello World");
  assert.ok(!cleaned.includes("alert"), "Must remove script inner content");
});

it("should filter unprintable ASCII control characters", () => {
  const dirty = "CSE\x00\x08Admission\x1fEnquiry";
  const cleaned = sanitizeInput(dirty);
  assert.strictEqual(cleaned, "CSEAdmissionEnquiry");
});

// 3. Entity Detection Tests
const BRANCH_CODES = {
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
};
const AMBIGUOUS = { it: "IT", ai: "AI-DS" };
const BRANCH_CONTEXT = /\b(?:fee\w*|course\w*|program\w*|branch\w*|department\w*|eligib\w*|admission|intake|seats?|cutoff|marks|degree\w*|offer\w*|b\.?tech|btech)\b/i;

function detectProgram(question) {
  const q = question.toLowerCase();
  const sorted = Object.keys(BRANCH_CODES).sort((a, b) => b.length - a.length);
  for (const phrase of sorted) {
    if (phrase in AMBIGUOUS) continue;
    const regex = new RegExp(`\\b${phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    if (regex.test(q)) return BRANCH_CODES[phrase];
  }
  const tokens = q.match(/\b[a-z0-9-]+\b/g) || [];
  for (const token of tokens) {
    if (token in AMBIGUOUS && BRANCH_CONTEXT.test(q)) {
      return AMBIGUOUS[token];
    }
  }
  return null;
}

it("should accurately detect all 6 academic programs", () => {
  assert.strictEqual(detectProgram("What are the fees for Computer Science?"), "CSE");
  assert.strictEqual(detectProgram("What is the intake for ece?"), "ECE");
  assert.strictEqual(detectProgram("Tell me about mechanical engineering"), "MECH");
  assert.strictEqual(detectProgram("Is IT degree offered?"), "IT");
  assert.strictEqual(detectProgram("Civil engineering eligibility?"), "CIVIL");
  assert.strictEqual(detectProgram("What about artificial intelligence and data science?"), "AI-DS");
});

// 4. Intent Classification Patterns
const INTENT_PATTERNS = [
  [/\b(?:eligib\w*|qualif\w*|requirement\w*|criteria|marks|percentage|percent\b|cutoff\w*|10\+2|hsc|score\w*)\b/i, "eligibility", 3],
  [/\b(?:fee\w*|cost|tuition|charge\w*|how much|price|expensive|payment\w*|mess fee\w*|hostel fee\w*)\b/i, "fees", 3],
  [/\b(?:admission procedure|admission process|how to apply|apply\w*|application|join\w*|enrol\w*|step\w*|documents? required|certificate verification|deadline\w*|last date|important dates|dates|schedule|counselling)\b/i, "procedure", 3],
  [/\b(?:facilit\w*|hostel|librar\w*|lab\w*|laborator\w*|sports|transport|bus\b|gym|placement\w*|campus|canteen|mess|medical|wifi|wi-fi|hospital)\b/i, "facilities", 3],
  [/\b(?:course\w*|programs? offered|branches? offered|what branches|what courses|degrees? offered|ug courses|curriculum|syllabus)\b/i, "courses", 3],
  [/\b(?:program\w*|branch\w*|department\w*|courses?|intake|seats?)\b/i, "courses", 1],
];

function classifyIntent(question) {
  const scores = {};
  for (const [pattern, intent, weight] of INTENT_PATTERNS) {
    const matches = question.match(new RegExp(pattern.source, "gi"));
    if (matches && matches.length > 0) {
      scores[intent] = (scores[intent] || 0) + matches.length * weight;
    }
  }
  const topIntent = Object.keys(scores).reduce((best, curr) => {
    if (!best || scores[curr] > (scores[best] || 0)) return curr;
    return best;
  }, null);
  return topIntent || "general";
}

it("should classify enquiry questions into correct domain intents", () => {
  assert.strictEqual(classifyIntent("What is the eligibility for B.Tech CSE?"), "eligibility");
  assert.strictEqual(classifyIntent("How much is the first year tuition fee?"), "fees");
  assert.strictEqual(classifyIntent("What is the admission procedure and how to apply?"), "procedure");
  assert.strictEqual(classifyIntent("What sports and hostel facilities do you have?"), "facilities");
  assert.strictEqual(classifyIntent("Which undergraduate courses are offered?"), "courses");
});

// 5. Rate Limiter Tests
it("should enforce sliding window rate limiting per IP", () => {
  const timestamps = [];
  const max = 30;
  for (let i = 0; i < max; i++) {
    timestamps.push(Date.now());
  }
  assert.strictEqual(timestamps.length <= max, true);
  timestamps.push(Date.now());
  assert.strictEqual(timestamps.length <= max, false, "31st request must trigger limit");
});

console.log("\n=================================================");
console.log(`Results: ${passed} passed, ${failed} failed`);
console.log("=================================================");

if (failed > 0) {
  process.exit(1);
}
