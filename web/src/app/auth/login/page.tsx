"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/authClient";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
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
          maxWidth: "400px",
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
            TrueLine
          </h1>
          <p
            style={{
              margin: "0.5rem 0 0",
              fontSize: "0.875rem",
              color: "#7a8fa6",
              lineHeight: 1.5,
            }}
          >
            Sign in to your account.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <label
              htmlFor="email"
              style={{ fontSize: "0.8125rem", color: "#7a8fa6", fontWeight: 500 }}
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => { setEmail(e.target.value); setError(null); }}
              style={{
                background: "#0b0f17",
                border: `1px solid ${error ? "#e05252" : "#1e2a3a"}`,
                borderRadius: "8px",
                color: "#e6ecf5",
                fontSize: "0.9rem",
                padding: "0.625rem 0.75rem",
                outline: "none",
                width: "100%",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <label
              htmlFor="password"
              style={{ fontSize: "0.8125rem", color: "#7a8fa6", fontWeight: 500 }}
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(null); }}
              style={{
                background: "#0b0f17",
                border: `1px solid ${error ? "#e05252" : "#1e2a3a"}`,
                borderRadius: "8px",
                color: "#e6ecf5",
                fontSize: "0.9rem",
                padding: "0.625rem 0.75rem",
                outline: "none",
                width: "100%",
                boxSizing: "border-box",
              }}
            />
          </div>

          {error && (
            <p
              role="alert"
              style={{ margin: 0, fontSize: "0.8125rem", color: "#e05252" }}
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              background: loading ? "#1a3a7a" : "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              padding: "0.625rem 1rem",
              fontSize: "0.9375rem",
              fontWeight: 600,
              cursor: loading ? "default" : "pointer",
              width: "100%",
              marginTop: "0.25rem",
            }}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
