"use client";

// NovaAskPanel — read-only Q&A panel inside the Nova drawer.
// Posts questions to POST /api/nova-chat and renders deterministic answers.
// No AI calls, no state mutation, no side effects beyond the network request.

import React, { useState, useRef, useEffect, useCallback } from "react";
import { getStoredSessionId } from "@/lib/session";

// ── Types ─────────────────────────────────────────────────────────────────────

type MessageRole = "user" | "nova";

type Message = {
  role: MessageRole;
  text: string;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE =
  (process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "")) ??
  "";

const MAX_MESSAGES = 8;

const SUGGESTED_QUESTIONS = [
  "Why is this job blocked?",
  "What should I do next?",
  "Which items were overridden?",
  "Did plans help routing?",
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function NovaAskPanel() {
  const [messages, setMessages]   = useState<Message[]>([]);
  const [input, setInput]         = useState("");
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to the bottom whenever messages or loading state change.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleAsk = useCallback(async () => {
    const question = input.trim();
    if (!question || loading) return;

    const sessionId = getStoredSessionId();

    // Capture context before appending the new user message.
    const contextMessages = messages.slice(-6).map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.text,
    }));

    // Optimistically append the user message.
    setMessages((prev) =>
      [...prev, { role: "user" as const, text: question }].slice(-MAX_MESSAGES)
    );
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/nova-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId, recent_messages: contextMessages }),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => "(no body)");
        throw new Error(`Server error (${res.status}): ${text}`);
      }

      const data = await res.json();
      if (!data.success) {
        throw new Error(data.error || "Unknown error from Nova.");
      }

      setMessages((prev) =>
        [...prev, { role: "nova" as const, text: String(data.answer ?? "") }].slice(-MAX_MESSAGES)
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setMessages((prev) =>
        [...prev, { role: "nova" as const, text: `⚠ Could not reach Nova: ${msg}` }].slice(-MAX_MESSAGES)
      );
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter submits; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  }

  function handleSuggestedQuestion(q: string) {
    setInput(q);
    inputRef.current?.focus();
  }

  return (
    <div>
      {/* ── Section header ────────────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 12,
        }}
      >
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            border: "none",
            background: "transparent",
            padding: 0,
            fontSize: 10,
            fontWeight: 800,
            color: "#94a3b8",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            flexShrink: 0,
            cursor: "pointer",
          }}
          aria-expanded={!collapsed}
          aria-controls="nova-ask-panel-body"
        >
          <span>{collapsed ? "Ask Nova" : "Ask Nova"}</span>
          {messages.length > 0 && (
            <span
              style={{
                color: "#64748b",
                letterSpacing: "0.02em",
                textTransform: "none",
                fontWeight: 700,
              }}
            >
              ({messages.length})
            </span>
          )}
          <span style={{ color: "#cbd5e1", fontSize: 11 }}>
            {collapsed ? "Show ▼" : "Hide ▲"}
          </span>
        </button>
        <span style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
        <span style={{ fontSize: 9, color: "#cbd5e1", letterSpacing: "0.02em" }}>
          deterministic · read-only
        </span>
      </div>

      {!collapsed && (
        <div id="nova-ask-panel-body">
      {/* ── Suggested questions (shown only when chat is empty) ───────────────── */}
      {messages.length === 0 && !loading && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 5,
            marginBottom: 12,
          }}
        >
          {SUGGESTED_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => handleSuggestedQuestion(q)}
              style={{
                fontSize: 11,
                padding: "4px 10px",
                background: "#f1f5f9",
                border: "1px solid #e2e8f0",
                borderRadius: 999,
                color: "#475569",
                cursor: "pointer",
                fontWeight: 500,
                transition: "background 0.1s, border-color 0.1s",
              }}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* ── Message thread ────────────────────────────────────────────────────── */}
      {(messages.length > 0 || loading) && (
        <div
          style={{
            display: "grid",
            gap: 10,
            marginBottom: 12,
          }}
        >
          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  maxWidth: "88%",
                  padding: "8px 12px",
                  borderRadius:
                    msg.role === "user"
                      ? "12px 12px 3px 12px"
                      : "3px 12px 12px 12px",
                  background: msg.role === "user" ? "#0f172a" : "#ffffff",
                  border:
                    msg.role === "user" ? "none" : "1px solid #e2e8f0",
                  color: msg.role === "user" ? "#f1f5f9" : "#1e293b",
                  fontSize: 13,
                  lineHeight: 1.65,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  boxShadow:
                    msg.role === "nova"
                      ? "0 1px 3px rgba(0,0,0,0.06)"
                      : "none",
                }}
              >
                {msg.text}
              </div>
              <span
                style={{
                  fontSize: 10,
                  color: "#94a3b8",
                  marginTop: 3,
                  paddingInline: 4,
                }}
              >
                {msg.role === "user" ? "You" : "Nova"}
              </span>
            </div>
          ))}

          {/* Thinking indicator */}
          {loading && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-start",
              }}
            >
              <div
                style={{
                  padding: "8px 12px",
                  borderRadius: "3px 12px 12px 12px",
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  fontSize: 12,
                  color: "#94a3b8",
                  fontStyle: "italic",
                }}
              >
                Nova is thinking…
              </div>
            </div>
          )}

          {/* Scroll anchor */}
          <div ref={bottomRef} />
        </div>
      )}

      {/* ── Input area ────────────────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          gap: 8,
          background: "#ffffff",
          border: "1.5px solid #e2e8f0",
          borderRadius: 10,
          padding: "7px 10px",
          alignItems: "flex-end",
        }}
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Nova about this job…"
          rows={1}
          style={{
            flex: 1,
            border: "none",
            outline: "none",
            resize: "none",
            fontSize: 13,
            color: "#0f172a",
            background: "transparent",
            lineHeight: 1.5,
            maxHeight: 80,
            overflowY: "auto",
            fontFamily: "inherit",
          }}
        />
        <button
          onClick={handleAsk}
          disabled={loading || !input.trim()}
          style={{
            padding: "5px 13px",
            background:
              loading || !input.trim() ? "#cbd5e1" : "#0f172a",
            color: "#ffffff",
            border: "none",
            borderRadius: 7,
            fontSize: 12,
            fontWeight: 700,
            cursor: loading || !input.trim() ? "not-allowed" : "pointer",
            flexShrink: 0,
            transition: "background 0.15s",
            letterSpacing: "0.01em",
          }}
        >
          {loading ? "…" : "Ask"}
        </button>
      </div>

      {/* Inline error — shown below input if fetch failed */}
      {error && (
        <div
          style={{
            fontSize: 11,
            color: "#dc2626",
            marginTop: 6,
            lineHeight: 1.4,
          }}
        >
          {error}
        </div>
      )}

      {/* Hint text */}
      <div style={{ fontSize: 10, color: "#cbd5e1", marginTop: 5 }}>
        Press Enter to send · Shift+Enter for new line
      </div>
        </div>
      )}
    </div>
  );
}
