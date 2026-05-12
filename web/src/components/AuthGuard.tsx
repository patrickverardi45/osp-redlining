"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearPilotToken, getPilotToken, isTokenExpired } from "@/lib/pilotToken";
import { refresh } from "@/lib/authClient";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<"checking" | "ok">("checking");
  const redirected = useRef(false);

  useEffect(() => {
    // Auth pages are always accessible — skip gate entirely.
    if (pathname.startsWith("/auth/")) {
      setStatus("ok");
      return;
    }
    if (redirected.current) return;

    let cancelled = false;

    async function boot() {
      // a. Try silent refresh via httpOnly refresh cookie (real auth).
      const refreshed = await refresh();
      if (cancelled) return;
      if (refreshed) {
        setStatus("ok");
        return;
      }

      // b. Fall back to pilot token in localStorage.
      const pilotToken = getPilotToken();
      if (pilotToken) {
        if (isTokenExpired(pilotToken)) {
          clearPilotToken();
        } else {
          setStatus("ok");
          return;
        }
      }

      // c. Neither auth path succeeded — redirect to login.
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
