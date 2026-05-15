"use client";

import { useRouter } from "next/navigation";
import { logout } from "@/lib/authClient";
import { clearPilotToken } from "@/lib/pilotToken";

function clearWorkspaceLocalStorage(): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.removeItem("trueline_projects");
  window.localStorage.removeItem("osp_session_id");
  const prefixes = ["osp_session_id:", "osp_project_planned_footage:"];
  const toRemove: string[] = [];
  for (let i = 0; i < window.localStorage.length; i++) {
    const key = window.localStorage.key(i);
    if (key && prefixes.some((p) => key.startsWith(p))) toRemove.push(key);
  }
  toRemove.forEach((key) => window.localStorage.removeItem(key));
}

export default function LogoutButton() {
  const router = useRouter();

  async function handleLogout() {
    clearPilotToken();
    await logout();
    clearWorkspaceLocalStorage();
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
