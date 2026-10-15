import { NextRequest, NextResponse } from "next/server";
import { answerEnquiry } from "../../../lib/aiEngine";
import { sanitizeInput, checkRateLimit, getClientIp } from "../../../lib/security";

export async function POST(req: NextRequest) {
  try {
    const ip = getClientIp(req.headers);
    if (!checkRateLimit(ip)) {
      return NextResponse.json(
        { error: "Rate limit exceeded. Please wait a moment." },
        { status: 429 }
      );
    }

    let question = "";
    const contentType = req.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      const body = await req.json();
      question = body?.question || "";
    } else {
      const formData = await req.formData();
      question = (formData.get("question") as string) || "";
    }

    const cleaned = sanitizeInput(question);
    if (!cleaned) {
      return NextResponse.json(
        { error: "Please enter a question before submitting." },
        { status: 400 }
      );
    }

    if (cleaned.length > 500) {
      return NextResponse.json(
        { error: "Please keep your question under 500 characters." },
        { status: 400 }
      );
    }

    const response = await answerEnquiry(cleaned);
    return NextResponse.json(response);
  } catch (error) {
    console.error("Error processing enquiry in /api/chat:", error);
    return NextResponse.json(
      { error: "Internal server error. Please try again." },
      { status: 500 }
    );
  }
}
