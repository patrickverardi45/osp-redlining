"use client";

import { useEffect } from "react";

export default function ErrorCapture() {
  useEffect(() => {
    function handleUnhandledRejection(event: PromiseRejectionEvent) {
      console.error("[unhandledrejection]", {
        t: "unhandled_rejection",
        reason: String(event.reason ?? "").slice(0, 300),
        ts: new Date().toISOString(),
      });
    }
    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    return () => {
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, []);

  return null;
}
