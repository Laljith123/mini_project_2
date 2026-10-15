export interface CollegeInfo {
  name: string;
  location: string;
  type: string;
  website: string;
}

export interface Program {
  code: string;
  name: string;
  duration: string;
  intake: number;
  eligibility: string;
  first_year_fees: number;
  about?: string;
}

export interface FeeComponent {
  program: string;
  component: string;
  amount: number;
  frequency: string;
}

export interface HostelFee {
  component: string;
  amount: number;
  frequency: string;
}

export interface ImportantDate {
  event: string;
  date: string;
}

export interface Facility {
  name: string;
  description: string;
}

export interface FAQ {
  q: string;
  a: string;
}

export interface KnowledgeBase {
  college: CollegeInfo;
  programs: Program[];
  fee_structure: FeeComponent[];
  hostel_fees: HostelFee[];
  admission_procedure: string[];
  important_dates?: ImportantDate[];
  facilities: Facility[];
  faqs: FAQ[];
  derived_total_first_year_fees?: Record<string, number>;
  keyword_index?: Record<string, [string, string | number][]>;
}

export type Intent =
  | "eligibility"
  | "courses"
  | "fees"
  | "procedure"
  | "facilities"
  | "faq"
  | "general";

export interface AnswerMeta {
  intent: Intent;
  program: string | null;
  mode: "online" | "offline";
  latency_ms: number;
  model: string;
}

export interface ChatResponse {
  question: string;
  answer: string;
  html: string;
  meta: AnswerMeta;
}

export interface KBStats {
  programs: number;
  fee_components: number;
  facilities: number;
  faqs: number;
  validation_errors: number;
  validation_report: string;
}
