"use client";

import { useRouter } from "next/navigation";
import { logout } from "@/lib/authClient";
import { clearPilotToken } from "@/lib/pilotToken";

export default function LogoutButton() {
  const router = useRouter();

  async function handleLogout() {
    clearPilotToken();
    await logout();
    router.replace("/auth/login");
  }

  return (
    <button
      type="button"
      onClick={handleLogout}
      className="tl-btn tl-btn-ghost"
      style={{ fontSize: 12, padding: "6px 12px" }}
    >
      Log out
    </button>
  );
}
