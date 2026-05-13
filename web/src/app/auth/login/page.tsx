"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/authClient";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.push("/projects");
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
            <div style={{ position: "relative" }}>
              <input
                id="password"
                type={showPassword ? "text" : "password"}
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
                  padding: "0.625rem 2.25rem 0.625rem 0.75rem",
                  outline: "none",
                  width: "100%",
                  boxSizing: "border-box",
                }}
              />
              <button
                type="button"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((v) => !v)}
                style={{
                  position: "absolute",
                  right: "0.625rem",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  padding: "2px",
                  color: "#7a8fa6",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                {showPassword ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
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

        <p style={{ margin: 0, textAlign: "center", fontSize: "0.8125rem", color: "#7a8fa6" }}>
          Have a pilot access token?{" "}
          <Link href="/auth/token" style={{ color: "#60a5fa", textDecoration: "none" }}>
            Enter it here.
          </Link>
        </p>
      </div>
    </div>
  );
}
