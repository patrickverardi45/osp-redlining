"use client";

// NovaDrawer — slide-out panel wrapper for the Nova job intelligence card.
// Provides a compact launcher button and a smooth right-side drawer.
// All Nova logic (overrides, QA flags, billing status) lives in NovaSummaryCard.
// This component only handles open/close, animation, and panel chrome.

import React, { useState, useEffect, useRef, useCallback } from "react";
import NovaSummaryCard from "@/components/NovaSummaryCard";
import type { NovaSummary, QaFlagItem, QaFlagSeverity } from "@/lib/types/nova";

// ── Types ─────────────────────────────────────────────────────────────────────

type FocusPayload = {
  issueId: string;
  source_file: string;
  group_idx: number | null;
  issue_key: string;
  severity: QaFlagSeverity;
  raw_reasons?: string[];
  item: QaFlagItem;
};

type Props = {
  summary: NovaSummary;
  onFocusIssue?: (issue: FocusPayload) => void;
  onOverrideSourcesChange?: (sourceFiles: string[]) => void;
};

// ── Status colours (mirrors NovaSummaryCard STATUS_STYLE) ─────────────────────

const STATUS_PILL: Record<string, string> = {
  Ready: "#16a34a",
  "Needs Review": "#d97706",
  Blocked: "#dc2626",
  Reviewed: "#7c3aed",
};

const STATUS_TOOLTIP: Record<string, string> = {
  Blocked: "Issues prevent reliable output.",
  "Needs Review": "Manual confirmation required.",
  Ready: "No blocking issues detected.",
  Reviewed: "Human review recorded; original engine findings remain visible.",
};

function NovaIcon({ size = 22 }: { size?: number }) {
  return (
    <span
      className="nova-icon-shell"
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <svg
        className="nova-icon-svg"
        viewBox="0 0 32 32"
        width={size}
        height={size}
        fill="none"
      >
        <circle cx="16" cy="16" r="13.2" stroke="rgba(148, 163, 184, 0.34)" strokeWidth="1" />
        <g className="nova-icon-orbits">
          <ellipse cx="16" cy="16" rx="10.8" ry="4.9" stroke="rgba(125, 211, 252, 0.78)" strokeWidth="1.15" />
          <ellipse
            cx="16"
            cy="16"
            rx="10.8"
            ry="4.9"
            stroke="rgba(196, 181, 253, 0.66)"
            strokeWidth="1.05"
            transform="rotate(62 16 16)"
          />
          <ellipse
            cx="16"
            cy="16"
            rx="10.8"
            ry="4.9"
            stroke="rgba(103, 232, 249, 0.42)"
            strokeWidth="0.95"
            transform="rotate(122 16 16)"
          />
        </g>
        <circle cx="16" cy="16" r="2.35" fill="#e0f2fe" />
        <circle cx="16" cy="16" r="1.15" fill="#38bdf8" />
        <circle cx="26.4" cy="16" r="1.45" fill="#a78bfa" />
        <circle cx="10.1" cy="6.9" r="1.15" fill="#67e8f9" />
        <circle cx="9.6" cy="24.9" r="1.15" fill="#c4b5fd" />
      </svg>
    </span>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function NovaDrawer({ summary, onFocusIssue, onOverrideSourcesChange }: Props) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const engineStatus = summary.billingReadiness.status;
  const pillColor = STATUS_PILL[engineStatus] ?? STATUS_PILL["Blocked"];

  // ── Close on Escape ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  // ── Lock body scroll while panel is open ───────────────────────────────────
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  // ── Wrap onFocusIssue to close panel so the map becomes visible ───────────
  const handleFocusIssue = useCallback((issue: FocusPayload) => {
    onFocusIssue?.(issue);
    setOpen(false);
  }, [onFocusIssue]);

  return (
    <>
      {/* ── Keyframe animations ───────────────────────────────────────────────── */}
      <style>{`
        @keyframes nova-icon-rotate {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes nova-icon-breathe {
          0%, 100% { opacity: 0.9; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.035); }
        }
        .nova-icon-shell {
          animation: nova-icon-breathe 4.8s ease-in-out infinite;
        }
        .nova-icon-orbits {
          transform-origin: 16px 16px;
          animation: nova-icon-rotate 18s linear infinite;
        }
        .nova-launcher-btn:hover {
          background: #1e293b !important;
          box-shadow: 0 2px 14px rgba(0, 0, 0, 0.22) !important;
        }
        .nova-launcher-btn:active {
          transform: scale(0.985);
        }
        .nova-panel-close:hover {
          background: rgba(255, 255, 255, 0.1) !important;
          color: #f1f5f9 !important;
        }
      `}</style>

      {/* ── Compact launcher button (replaces the full card in the billing area) ── */}
      <button
        className="nova-launcher-btn"
        onClick={() => setOpen(true)}
        aria-label="Open Nova job intelligence panel"
        title="Open Nova Assistant"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 11,
          width: "100%",
          background: "#0f172a",
          border: "1.5px solid #1e293b",
          borderRadius: 12,
          padding: "11px 13px",
          cursor: "pointer",
          transition: "background 0.15s ease, box-shadow 0.15s ease",
          boxShadow: "0 1px 4px rgba(0, 0, 0, 0.14)",
          textAlign: "left",
        }}
      >
        <NovaIcon size={22} />

        {/* Label */}
        <span
          style={{
            fontSize: 13,
            fontWeight: 800,
            color: "#f1f5f9",
            letterSpacing: "-0.01em",
            flex: 1,
          }}
        >
          Nova
        </span>

        {/* Status pill */}
        <span
          title={STATUS_TOOLTIP[engineStatus] ?? STATUS_TOOLTIP.Blocked}
          style={{
            background: pillColor,
            color: "#ffffff",
            borderRadius: 999,
            padding: "2px 9px",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.03em",
            flexShrink: 0,
          }}
        >
          {engineStatus}
        </span>

        {/* Open chevron */}
        <span style={{ fontSize: 14, color: "#64748b", flexShrink: 0, lineHeight: 1 }}>›</span>
      </button>

      {/* ── Backdrop ──────────────────────────────────────────────────────────── */}
      <div
        aria-hidden="true"
        onClick={() => setOpen(false)}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0, 0, 0, 0.30)",
          zIndex: 1998,
          opacity: open ? 1 : 0,
          pointerEvents: open ? "auto" : "none",
          transition: "opacity 0.25s ease",
        }}
      />

      {/* ── Slide-out panel ───────────────────────────────────────────────────── */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Nova Job Intelligence"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          width: 440,
          maxWidth: "92vw",
          height: "100dvh",
          zIndex: 1999,
          display: "flex",
          flexDirection: "column",
          transform: open ? "translateX(0)" : "translateX(100%)",
          transition: "transform 0.28s cubic-bezier(0.4, 0, 0.2, 1)",
          boxShadow: "-4px 0 36px rgba(0, 0, 0, 0.18)",
          borderLeft: "1px solid #1e293b",
          background: "#f8fafc",
        }}
      >
        {/* Panel header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "13px 16px",
            background: "#0f172a",
            borderBottom: "1px solid #1e293b",
            flexShrink: 0,
          }}
        >
          {/* Left: icon + title */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <NovaIcon size={24} />
            <span
              style={{
                fontSize: 14,
                fontWeight: 800,
                color: "#f1f5f9",
                letterSpacing: "-0.01em",
              }}
            >
              Nova — Job Intelligence
            </span>
          </div>

          {/* Right: persist tag + close */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 10, color: "#475569", letterSpacing: "0.02em" }}>
              review layer · persisted
            </span>
            <button
              className="nova-panel-close"
              onClick={() => setOpen(false)}
              aria-label="Close Nova panel"
              style={{
                background: "transparent",
                border: "none",
                borderRadius: 6,
                padding: "4px 7px",
                color: "#64748b",
                fontSize: 15,
                lineHeight: 1,
                cursor: "pointer",
                transition: "background 0.12s ease, color 0.12s ease",
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Panel body — scrollable */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "16px",
            minHeight: 0,
          }}
        >
          <NovaSummaryCard
            summary={summary}
            onFocusIssue={handleFocusIssue}
            onOverrideSourcesChange={onOverrideSourcesChange}
            hideHeader
          />
        </div>
      </div>
    </>
  );
}
