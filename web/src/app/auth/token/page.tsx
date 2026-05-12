"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { looksLikeJwt, savePilotToken, clearPilotToken } from "@/lib/pilotToken";

export default function PilotTokenGatePage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cleared, setCleared] = useState(false);

  function handleSave() {
    setError(null);
    setCleared(false);
    const trimmed = token.trim();
    if (!trimmed) {
      setError("Please paste your pilot access token.");
      return;
    }
    if (!looksLikeJwt(trimmed)) {
      setError("Token shape is invalid. Expected a JWT (three dot-separated segments).");
      return;
    }
    savePilotToken(trimmed);
    router.push("/");
  }

  function handleClear() {
    clearPilotToken();
    setToken("");
    setError(null);
    setCleared(true);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0b0f17",
        color: "#e6ecf5",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "system-ui, sans-serif",
        padding: "1.5rem",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "480px",
          background: "#141924",
          border: "1px solid #1e2a3a",
          borderRadius: "12px",
          padding: "2rem",
          display: "flex",
          flexDirection: "column",
          gap: "1.25rem",
        }}
      >
        <div>
          <h1
            style={{
              margin: 0,
              fontSize: "1.25rem",
              fontWeight: 600,
              color: "#e6ecf5",
              letterSpacing: "-0.01em",
            }}
          >
            TrueLine Pilot Access
          </h1>
          <p
            style={{
              margin: "0.5rem 0 0",
              fontSize: "0.875rem",
              color: "#7a8fa6",
              lineHeight: 1.5,
            }}
          >
            Paste your pilot access token to continue.
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <label
            htmlFor="pilot-token-input"
            style={{ fontSize: "0.8125rem", color: "#7a8fa6", fontWeight: 500 }}
          >
            Access token
          </label>
          <textarea
            id="pilot-token-input"
            value={token}
            onChange={(e) => {
              setToken(e.target.value);
              setError(null);
              setCleared(false);
            }}
            placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            rows={4}
            style={{
              width: "100%",
              background: "#0b0f17",
              border: `1px solid ${error ? "#e05252" : "#1e2a3a"}`,
              borderRadius: "8px",
              color: "#e6ecf5",
              fontSize: "0.8125rem",
              fontFamily: "monospace",
              padding: "0.625rem 0.75rem",
              resize: "vertical",
              outline: "none",
              boxSizing: "border-box",
            }}
          />
          {error && (
            <p
              role="alert"
              style={{
                margin: 0,
                fontSize: "0.8125rem",
                color: "#e05252",
              }}
            >
              {error}
            </p>
          )}
          {cleared && (
            <p
              style={{
                margin: 0,
                fontSize: "0.8125rem",
                color: "#7a8fa6",
              }}
            >
              Saved token cleared.
            </p>
          )}
        </div>

        <button
          onClick={handleSave}
          style={{
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            padding: "0.625rem 1rem",
            fontSize: "0.9375rem",
            fontWeight: 600,
            cursor: "pointer",
            width: "100%",
          }}
        >
          Save pilot token
        </button>

        <button
          onClick={handleClear}
          style={{
            background: "transparent",
            color: "#7a8fa6",
            border: "none",
            padding: "0.25rem 0",
            fontSize: "0.8125rem",
            cursor: "pointer",
            textDecoration: "underline",
            textAlign: "left",
          }}
        >
          Clear saved token
        </button>
      </div>
    </div>
  );
}
