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
  const [apiKey, setApiKey] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [showKeyText, setShowKeyText] = useState(false);
  const [keyLoaded, setKeyLoaded] = useState(false);

  const conversationBoxRef = useRef<HTMLDivElement>(null);

  // Check stored API key on client mount and ask on startup if not set
  useEffect(() => {
    try {
      const stored = localStorage.getItem("openai_api_key");
      if (stored === null) {
        // Initial visit: prompt user for key or offline mode
        setShowKeyModal(true);
      } else if (stored) {
        setApiKey(stored);
        setKeyInput(stored);
      }
    } catch {
      // localStorage may be disabled in private mode
    } finally {
      setKeyLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (conversationBoxRef.current) {
      conversationBoxRef.current.scrollTop =
        conversationBoxRef.current.scrollHeight;
    }
  }, [messages, loading]);

  function handleSaveKey() {
    const trimmed = keyInput.trim();
    if (!trimmed) {
      handleUseOffline();
      return;
    }
    try {
      localStorage.setItem("openai_api_key", trimmed);
    } catch {
      // ignore
    }
    setApiKey(trimmed);
    setShowKeyModal(false);
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now() + "-keysaved",
        sender: "bot",
        text: "🔑 OpenAI API key saved! Your admissions enquiries will now use live GPT-4o generation grounded in official college admission records.",
      },
    ]);
  }

  function handleUseOffline() {
    try {
      localStorage.setItem("openai_api_key", "");
    } catch {
      // ignore
    }
    setApiKey("");
    setKeyInput("");
    setShowKeyModal(false);
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now() + "-offline",
        sender: "bot",
        text: "⚡ Offline Knowledge Base mode enabled! All queries will be answered instantly for free using the built-in admissions database without calling OpenAI.",
      },
    ]);
  }

  function handleRemoveKey() {
    try {
      localStorage.removeItem("openai_api_key");
    } catch {
      // ignore
    }
    setApiKey("");
    setKeyInput("");
    setShowKeyModal(false);
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now() + "-removed",
        sender: "bot",
        text: "API key removed. Assistant switched back to free Offline Knowledge Base mode.",
      },
    ]);
  }

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
      const activeKey = apiKey || (typeof window !== "undefined" ? localStorage.getItem("openai_api_key") || "" : "");
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(activeKey ? { "x-openai-api-key": activeKey } : {}),
        },
        body: JSON.stringify({
          question: q,
          apiKey: activeKey || undefined,
        }),
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
    <>
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

        {/* API Key Status Bar */}
        <div className="api-status-bar">
          <div className="api-status-left">
            <span className={`status-badge ${apiKey ? "online" : "offline"}`}>
              {apiKey ? "🟢 GPT-4o Connected" : "⚡ Offline KB Mode"}
            </span>
            {apiKey ? (
              <span className="status-key-preview">
                Key: ••••••••{apiKey.slice(-4)}
              </span>
            ) : (
              <span style={{ color: "#64748b", fontSize: "12px" }}>
                Zero API calls · Free &amp; instant
              </span>
            )}
          </div>
          <button
            type="button"
            className="btn-config-key"
            onClick={() => {
              setKeyInput(apiKey);
              setShowKeyModal(true);
            }}
          >
            {apiKey ? "Change Key" : "Connect OpenAI Key"}
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

      {/* Modal Dialog for API Key Prompt */}
      {showKeyModal && keyLoaded && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          onClick={() => setShowKeyModal(false)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>🔑 OpenAI API Key Configuration</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowKeyModal(false)}
                aria-label="Close"
              >
                &times;
              </button>
            </div>
            <div className="modal-body">
              <p>
                Enter your OpenAI API key to enable live GPT-4o generation.
                Your key is stored <strong>strictly in your browser</strong> and is never hardcoded or saved on our servers.
              </p>

              <label
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#334155",
                  display: "block",
                  marginBottom: 6,
                }}
              >
                OpenAI API Key (sk-...)
              </label>
              <div className="key-input-wrapper">
                <input
                  type={showKeyText ? "text" : "password"}
                  placeholder="sk-proj-..."
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  autoComplete="off"
                  spellCheck="false"
                />
                <button
                  type="button"
                  className="btn-toggle-visibility"
                  onClick={() => setShowKeyText(!showKeyText)}
                  title={showKeyText ? "Hide key" : "Show key"}
                >
                  {showKeyText ? "🙈" : "👁️"}
                </button>
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-primary-modal"
                  onClick={handleSaveKey}
                  disabled={!keyInput.trim()}
                >
                  Save &amp; Enable GPT-4o
                </button>
                <button
                  type="button"
                  className="btn-secondary-modal"
                  onClick={handleUseOffline}
                >
                  Continue in Free Offline Mode (No Key Needed)
                </button>
                {apiKey && (
                  <button
                    type="button"
                    className="btn-danger-modal"
                    onClick={handleRemoveKey}
                  >
                    Remove Stored Key
                  </button>
                )}
              </div>

              <p className="modal-footer-note">
                💡 <strong>No API key?</strong> All college admission questions (fees, eligibility, courses, steps, campus facilities) work 100% free with the verified Knowledge Base composer without any API key.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
