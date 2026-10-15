import { NextResponse } from "next/server";
import { AI_STATS } from "../../../lib/aiEngine";
import { getKnowledgeBaseStats } from "../../../lib/knowledgeBase";

export async function GET() {
  const kbStats = getKnowledgeBaseStats();
  const online = Boolean(process.env.OPENAI_API_KEY?.trim());

  return NextResponse.json({
    status: "ok",
    service: "admission-assistant-nextjs",
    ai_mode: online ? "online" : "offline",
    model: online
      ? process.env.OPENAI_MODEL?.trim() || "gpt-4o-mini"
      : "kb-composer",
    stats: AI_STATS,
    kb_stats: kbStats,
  });
}
