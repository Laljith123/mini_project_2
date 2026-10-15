/**
 * Security Engineering module for Next.js Admission Enquiry Assistant.
 */

const SCRIPT_STYLE_RE = /<(script|style)[^>]*>[\s\S]*?<\/\1>/gi;
const TAG_RE = /<[^>]*>/g;
const CONTROL_CHARS_RE = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g;

export function sanitizeInput(text: string | null | undefined): string {
  if (!text) return "";
  let cleaned = String(text).replace(SCRIPT_STYLE_RE, " ");
  cleaned = cleaned.replace(TAG_RE, " ");
  cleaned = cleaned.replace(CONTROL_CHARS_RE, "");
  return cleaned.replace(/\s+/g, " ").trim();
}

export function escapeHtml(text: string | null | undefined): string {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function formatAnswerHtml(text: string): string {
  const safe = escapeHtml(text);
  const paragraphs = safe.split(/\n\n+/).filter(Boolean);
  if (paragraphs.length > 0) {
    return paragraphs
      .map((p) => `<p>${p.replace(/\n/g, "<br/>")}</p>`)
      .join("");
  }
  return `<p>${safe.replace(/\n/g, "<br/>")}</p>`;
}

// In-memory sliding-window rate limiter with periodic pruning
const requestLog = new Map<string, number[]>();
const WINDOW_MS = 60 * 1000;
const MAX_REQUESTS = 30;
let lastPrune = Date.now();

export function checkRateLimit(
  ip: string,
  maxRequests: number = MAX_REQUESTS,
  windowMs: number = WINDOW_MS
): boolean {
  const now = Date.now();

  // Prune stale IPs every 5 minutes
  if (now - lastPrune > 300 * 1000) {
    requestLog.forEach((timestamps, key) => {
      const active = timestamps.filter((t) => now - t < windowMs);
      if (active.length === 0) {
        requestLog.delete(key);
      } else {
        requestLog.set(key, active);
      }
    });
    lastPrune = now;
  }

  const timestamps = requestLog.get(ip) || [];
  const activeStamps = timestamps.filter((t) => now - t < windowMs);
  activeStamps.push(now);
  requestLog.set(ip, activeStamps);

  return activeStamps.length <= maxRequests;
}

export function resetRateLimits(): void {
  requestLog.clear();
}

export function getClientIp(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return headers.get("x-real-ip") || "127.0.0.1";
}
