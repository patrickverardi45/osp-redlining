"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearPilotToken, getPilotToken, isTokenExpired } from "@/lib/pilotToken";
import { refresh } from "@/lib/authClient";
import { getAccessToken } from "@/lib/accessToken";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<"checking" | "ok">("checking");
  const redirected = useRef(false);

  useEffect(() => {
    // Auth pages are always accessible — skip gate entirely.
    if (pathname.startsWith("/auth/")) {
      setStatus("ok");
      redirected.current = false; // allow re-entry into protected pages after auth
      return;
    }

    // Always reset to "checking" on protected-path entry so a stale "ok"
    // from a prior /auth/* visit cannot bypass re-verification.
    setStatus("checking");

    if (redirected.current) return;

    let cancelled = false;

    async function boot() {
      // a. In-memory access token already present — just logged in, no reload needed.
      if (getAccessToken()) {
        setStatus("ok");
        return;
      }

      // b. Try silent refresh via httpOnly refresh cookie (real auth).
      const refreshed = await refresh();
      if (cancelled) return;
      if (refreshed) {
        setStatus("ok");
        return;
      }

      // c. Fall back to pilot token in localStorage.
      const pilotToken = getPilotToken();
      if (pilotToken) {
        if (isTokenExpired(pilotToken)) {
          clearPilotToken();
        } else {
          setStatus("ok");
          return;
        }
      }

      // d. Neither auth path succeeded — redirect to login.
      redirected.current = true;
      router.replace("/auth/login");
    }

    boot();

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (pathname.startsWith("/auth/")) return <>{children}</>;
  if (status === "checking") return null;
  return <>{children}</>;
}
