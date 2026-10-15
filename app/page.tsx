"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import { ChatResponse } from "../lib/types";

interface MessageItem {
  id: string;
  sender: "user" | "bot";
  text?: string;
  html?: string;
  meta?: ChatResponse["meta"];
}

const EXAMPLE_QUESTIONS = [
  "What is the eligibility for B.Tech Computer Science?",
  "How much is the first year fee for ECE?",
  "What is the admission procedure?",
  "What facilities are available on campus?",
  "Which UG courses are offered by the college?",
  "Are scholarships available?",
  "Is hostel accommodation guaranteed?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "initial",
      sender: "bot",
      text:
        "Hello! Welcome to the Sri Manakula Vinayagar Engineering College Admission Assistant. " +
        "Ask me anything about admissions — eligibility criteria, courses offered, fee structures, " +
        "application steps, or campus facilities.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const conversationBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (conversationBoxRef.current) {
      conversationBoxRef.current.scrollTop =
        conversationBoxRef.current.scrollHeight;
    }
  }, [messages, loading]);

  async function handleSend(questionText: string) {
    const q = questionText.trim();
    if (!q || loading) return;

    const userMsg: MessageItem = {
      id: Date.now() + "-user",
      sender: "user",
      text: q,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ question: q }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || `Server responded with ${res.status}`);
      }

      const data: ChatResponse = await res.json();
      const botMsg: MessageItem = {
        id: Date.now() + "-bot",
        sender: "bot",
        text: data.answer,
        html: data.html,
        meta: data.meta,
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error ? err.message : "An error occurred while answering.";
      const botErr: MessageItem = {
        id: Date.now() + "-err",
        sender: "bot",
        text: `Error: ${errorMessage}. Please try again.`,
      };
      setMessages((prev) => [...prev, botErr]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    handleSend(input);
  }

  function handleReset() {
    setMessages([
      {
        id: Date.now() + "-reset",
        sender: "bot",
        text:
          "Conversation reset. How can I help you with your college admission enquiry today?",
      },
    ]);
  }

  return (
    <section className="chat-card">
      <div className="card-header">
        <h2>Ask about admissions</h2>
        <button
          type="button"
          onClick={handleReset}
          className="btn-clear"
          title="Reset conversation history"
        >
          Reset conversation
        </button>
      </div>

      <div className="conversation" ref={conversationBoxRef}>
        {messages.map((m) => {
          if (m.sender === "user") {
            return (
              <div key={m.id} className="msg user">
                <div className="who">You</div>
                <div className="bubble">{m.text}</div>
              </div>
            );
          }

          const modeLabel =
            m.meta?.mode === "online"
              ? "GPT-4o (OpenAI)"
              : "Knowledge Base Engine";
          const intentLabel = m.meta?.intent
            ? m.meta.intent.charAt(0).toUpperCase() + m.meta.intent.slice(1)
            : "General";
          const latency =
            m.meta?.latency_ms !== undefined
              ? ` · ${m.meta.latency_ms}ms`
              : "";

          return (
            <div key={m.id} className="msg bot">
              <div className="who">
                Assistant {m.meta && `· ${modeLabel} · Intent: ${intentLabel}${latency}`}
              </div>
              {m.html ? (
                <div
                  className="bubble"
                  dangerouslySetInnerHTML={{ __html: m.html }}
                />
              ) : (
                <div className="bubble">{m.text}</div>
              )}
            </div>
          );
        })}

        {loading && (
          <div className="msg bot loading-msg">
            <div className="who">Assistant</div>
            <div className="bubble">
              <em>Thinking...</em>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="ask-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={500}
          placeholder="e.g. What is the eligibility for B.Tech CSE?"
          required
          autoComplete="off"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? "..." : "Ask"}
        </button>
      </form>

      <p className="hint">Try asking:</p>
      <div className="suggestions">
        {EXAMPLE_QUESTIONS.map((s, idx) => (
          <button
            key={idx}
            type="button"
            className="suggestion"
            onClick={() => handleSend(s)}
            disabled={loading}
          >
            {s}
          </button>
        ))}
      </div>
    </section>
  );
}
