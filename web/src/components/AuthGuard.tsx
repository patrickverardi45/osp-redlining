"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearPilotToken, getPilotToken, isTokenExpired } from "@/lib/pilotToken";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<"checking" | "ok">("checking");
  const redirected = useRef(false);

  useEffect(() => {
    if (pathname.startsWith("/auth/")) {
      setStatus("ok");
      return;
    }
    if (redirected.current) return;
    const token = getPilotToken();
    if (!token) {
      redirected.current = true;
      router.replace("/auth/token");
      return;
    }
    if (isTokenExpired(token)) {
      clearPilotToken();
      redirected.current = true;
      router.replace("/auth/token");
      return;
    }
    setStatus("ok");
  }, [pathname, router]);

  if (pathname.startsWith("/auth/")) return <>{children}</>;
  if (status === "checking") return null;
  return <>{children}</>;
}
