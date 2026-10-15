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
    let apiKey: string | undefined = undefined;
    const contentType = req.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      try {
        const body = await req.json();
        question = body?.question || "";
        if (typeof body?.apiKey === "string") {
          apiKey = body.apiKey.trim();
        }
      } catch {
        return NextResponse.json(
          { error: "Invalid JSON in request body." },
          { status: 400 }
        );
      }
    } else {
      try {
        const formData = await req.formData();
        question = (formData.get("question") as string) || "";
        const formKey = formData.get("apiKey") as string | null;
        if (formKey) {
          apiKey = formKey.trim();
        }
      } catch {
        return NextResponse.json(
          { error: "Invalid form data in request body." },
          { status: 400 }
        );
      }
    }

    if (!apiKey) {
      const headerKey = req.headers.get("x-openai-api-key");
      if (headerKey) {
        apiKey = headerKey.trim();
      }
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

    const response = await answerEnquiry(cleaned, apiKey);
    return NextResponse.json(response);
  } catch (error) {
    console.error("Error processing enquiry in /api/chat:", error);
    return NextResponse.json(
      { error: "Internal server error. Please try again." },
      { status: 500 }
    );
  }
}
