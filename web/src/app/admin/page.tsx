"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/apiFetch";
import { me } from "@/lib/authClient";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Company = { id: string; slug: string; name: string };

type Membership = {
  membership_id: string;
  company_id: string;
  company_slug: string;
  company_name: string;
  role: string;
};

type AdminUser = {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
  memberships: Membership[];
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ROLES = ["owner", "admin", "member"] as const;

const inputStyle: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 6,
  border: "1px solid var(--tl-border)",
  background: "var(--tl-bg)",
  color: "var(--tl-text)",
  fontSize: 14,
  width: "100%",
  boxSizing: "border-box",
};

const cellStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderBottom: "1px solid var(--tl-border)",
  fontSize: 13,
  verticalAlign: "top",
};

const thStyle: React.CSSProperties = {
  ...cellStyle,
  fontWeight: 600,
  color: "var(--tl-text-muted)",
  fontSize: 12,
  textAlign: "left",
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Create user form
  const [cuEmail, setCuEmail] = useState("");
  const [cuDisplay, setCuDisplay] = useState("");
  const [cuPassword, setCuPassword] = useState("");
  const [cuCompany, setCuCompany] = useState("");
  const [cuRole, setCuRole] = useState<string>("member");
  const [cuBusy, setCuBusy] = useState(false);
  const [cuError, setCuError] = useState<string | null>(null);
  const [cuSuccess, setCuSuccess] = useState<string | null>(null);
  const [cuShowPassword, setCuShowPassword] = useState(false);

  // Create company form
  const [ccName, setCcName] = useState("");
  const [ccBusy, setCcBusy] = useState(false);
  const [ccError, setCcError] = useState<string | null>(null);
  const [ccSuccess, setCcSuccess] = useState<string | null>(null);

  // Reset password state keyed by user_id
  const [resetTarget, setResetTarget] = useState<string | null>(null);
  const [resetPw, setResetPw] = useState("");
  const [resetBusy, setResetBusy] = useState(false);
  const [resetMsg, setResetMsg] = useState<Record<string, string>>({});

  // Auth gate — only owner/admin may access this page
  useEffect(() => {
    me().then((user) => {
      if (!user || !["owner", "admin"].includes(user.role)) {
        router.replace("/projects");
        return;
      }
      setReady(true);
    });
  }, [router]);

  const loadData = useCallback(async () => {
    setLoadError(null);
    try {
      const [uRes, cRes] = await Promise.all([
        apiFetch("/api/admin/users"),
        apiFetch("/api/admin/companies"),
      ]);
      if (!uRes.ok || !cRes.ok) {
        setLoadError("Failed to load admin data. Are you logged in as owner?");
        return;
      }
      const [uData, cData] = await Promise.all([uRes.json(), cRes.json()]);
      setUsers(uData);
      setCompanies(cData);
      if (!cuCompany && cData.length > 0) setCuCompany(cData[0].id);
    } catch {
      setLoadError("Network error — could not reach the server.");
    }
  }, [cuCompany]);

  useEffect(() => {
    if (ready) loadData();
  }, [ready, loadData]);

  // ── Create User ──────────────────────────────────────────────────────────
  const handleCreateUser = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setCuError(null);
      setCuSuccess(null);
      if (!cuCompany) { setCuError("Select a company first."); return; }
      setCuBusy(true);
      try {
        const createRes = await apiFetch("/api/admin/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: cuEmail, password: cuPassword, display_name: cuDisplay || null }),
        });
        const createData = await createRes.json();
        if (!createRes.ok) { setCuError(createData.detail ?? "Create failed."); return; }

        const assignRes = await apiFetch(`/api/admin/users/${createData.id}/assign`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_id: cuCompany, role: cuRole }),
        });
        if (!assignRes.ok) {
          const d = await assignRes.json();
          setCuError(`User created but assign failed: ${d.detail ?? "unknown error"}`);
          return;
        }
        setCuSuccess(`Created ${cuEmail} — temp password set. Share credentials securely.`);
        setCuEmail(""); setCuDisplay(""); setCuPassword(""); setCuRole("member");
        loadData();
      } catch {
        setCuError("Network error.");
      } finally {
        setCuBusy(false);
      }
    },
    [cuEmail, cuDisplay, cuPassword, cuCompany, cuRole, loadData],
  );

  // ── Create Company ───────────────────────────────────────────────────────
  const handleCreateCompany = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setCcError(null);
      setCcSuccess(null);
      setCcBusy(true);
      try {
        const res = await apiFetch("/api/admin/companies", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: ccName }),
        });
        const data = await res.json();
        if (!res.ok) { setCcError(data.detail ?? "Create failed."); return; }
        setCcSuccess(`Company "${data.name}" created (slug: ${data.slug}).`);
        setCcName("");
        loadData();
      } catch {
        setCcError("Network error.");
      } finally {
        setCcBusy(false);
      }
    },
    [ccName, loadData],
  );

  // ── Reset Password ───────────────────────────────────────────────────────
  const handleResetPassword = useCallback(
    async (userId: string) => {
      setResetBusy(true);
      setResetMsg((prev) => ({ ...prev, [userId]: "" }));
      try {
        const res = await apiFetch(`/api/admin/users/${userId}/reset-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_password: resetPw }),
        });
        const data = await res.json();
        if (!res.ok) {
          setResetMsg((prev) => ({ ...prev, [userId]: `Error: ${data.detail ?? "failed"}` }));
        } else {
          setResetMsg((prev) => ({ ...prev, [userId]: "Password updated." }));
          setResetTarget(null);
          setResetPw("");
        }
      } catch {
        setResetMsg((prev) => ({ ...prev, [userId]: "Network error." }));
      } finally {
        setResetBusy(false);
      }
    },
    [resetPw],
  );

  if (!ready) return null;

  return (
    <main className="tl-page">
      <div className="tl-page-inner">

        {/* Header */}
        <header style={{ marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
            <div>
              <div className="tl-eyebrow">Administration</div>
              <h1 className="tl-h1">User Management</h1>
              <p className="tl-subtle" style={{ margin: 0 }}>
                Create and manage users, companies, and role assignments.
              </p>
            </div>
            <Link href="/projects" className="tl-btn tl-btn-ghost" style={{ whiteSpace: "nowrap" }}>
              ← Projects
            </Link>
          </div>
        </header>

        {loadError && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "#2a1212", border: "1px solid #7f1d1d", color: "#fca5a5", fontSize: 13, marginBottom: 20 }}>
            {loadError}
          </div>
        )}

        {/* ── Companies ───────────────────────────────────────────────────── */}
        <section className="tl-card tl-card-padded" style={{ marginBottom: 20 }}>
          <h2 className="tl-h2" style={{ marginBottom: 14 }}>Companies</h2>
          {companies.length === 0 ? (
            <p className="tl-subtle" style={{ marginBottom: 14 }}>No companies yet.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 20 }}>
              <thead>
                <tr>
                  <th style={thStyle}>Name</th>
                  <th style={thStyle}>Slug</th>
                  <th style={thStyle}>ID</th>
                </tr>
              </thead>
              <tbody>
                {companies.map((c) => (
                  <tr key={c.id}>
                    <td style={cellStyle}>{c.name}</td>
                    <td style={cellStyle}>{c.slug}</td>
                    <td style={{ ...cellStyle, fontFamily: "monospace", fontSize: 11, color: "var(--tl-text-muted)" }}>{c.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10, color: "var(--tl-text)" }}>Create Company</h3>
          <form onSubmit={handleCreateCompany} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 200px", display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Company Name *</label>
                <input type="text" required value={ccName} onChange={(e) => setCcName(e.target.value)} style={inputStyle} placeholder="Acme Corp" />
              </div>
            </div>
            {ccError && <p style={{ margin: 0, fontSize: 13, color: "#fca5a5" }}>{ccError}</p>}
            {ccSuccess && <p style={{ margin: 0, fontSize: 13, color: "#86efac" }}>{ccSuccess}</p>}
            <div>
              <button type="submit" className="tl-btn tl-btn-primary" disabled={ccBusy}>
                {ccBusy ? "Creating…" : "Create Company"}
              </button>
            </div>
          </form>
        </section>

        {/* ── Users table ─────────────────────────────────────────────────── */}
        <section className="tl-card tl-card-padded" style={{ marginBottom: 20 }}>
          <h2 className="tl-h2" style={{ marginBottom: 14 }}>Users</h2>
          {users.length === 0 ? (
            <p className="tl-subtle" style={{ margin: 0 }}>No users yet.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Email</th>
                    <th style={thStyle}>Display name</th>
                    <th style={thStyle}>Company / Role</th>
                    <th style={thStyle}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td style={cellStyle}>{u.email}</td>
                      <td style={cellStyle}>{u.display_name ?? <span style={{ color: "var(--tl-text-muted)" }}>—</span>}</td>
                      <td style={cellStyle}>
                        {u.memberships.length === 0 ? (
                          <span style={{ color: "var(--tl-text-muted)" }}>Unassigned</span>
                        ) : (
                          u.memberships.map((m) => (
                            <div key={m.membership_id} style={{ lineHeight: 1.6 }}>
                              <span style={{ fontWeight: 500 }}>{m.company_name}</span>
                              <span style={{ color: "var(--tl-text-muted)", marginLeft: 6, fontSize: 12 }}>{m.role}</span>
                            </div>
                          ))
                        )}
                      </td>
                      <td style={cellStyle}>
                        {resetTarget === u.id ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 220 }}>
                            <input
                              type="password"
                              placeholder="New password (min 8 chars)"
                              value={resetPw}
                              onChange={(e) => setResetPw(e.target.value)}
                              style={{ ...inputStyle, width: "auto" }}
                              autoFocus
                            />
                            <div style={{ display: "flex", gap: 6 }}>
                              <button
                                className="tl-btn tl-btn-primary"
                                style={{ fontSize: 12, padding: "4px 10px" }}
                                disabled={resetBusy || resetPw.length < 8}
                                onClick={() => handleResetPassword(u.id)}
                              >
                                {resetBusy ? "Saving…" : "Save"}
                              </button>
                              <button
                                className="tl-btn tl-btn-ghost"
                                style={{ fontSize: 12, padding: "4px 10px" }}
                                onClick={() => { setResetTarget(null); setResetPw(""); }}
                              >
                                Cancel
                              </button>
                            </div>
                            {resetMsg[u.id] && (
                              <span style={{ fontSize: 12, color: resetMsg[u.id].startsWith("Error") ? "#fca5a5" : "#86efac" }}>
                                {resetMsg[u.id]}
                              </span>
                            )}
                          </div>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <button
                              className="tl-btn tl-btn-ghost"
                              style={{ fontSize: 12, padding: "4px 10px" }}
                              onClick={() => { setResetTarget(u.id); setResetPw(""); setResetMsg((p) => ({ ...p, [u.id]: "" })); }}
                            >
                              Reset password
                            </button>
                            {resetMsg[u.id] && (
                              <span style={{ fontSize: 12, color: "#86efac" }}>{resetMsg[u.id]}</span>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Create User ─────────────────────────────────────────────────── */}
        <section className="tl-card tl-card-padded" style={{ marginBottom: 20 }}>
          <h2 className="tl-h2" style={{ marginBottom: 14 }}>Create User</h2>
          <form onSubmit={handleCreateUser} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 200px", display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Email *</label>
                <input type="email" required value={cuEmail} onChange={(e) => setCuEmail(e.target.value)} style={inputStyle} placeholder="user@company.com" />
              </div>
              <div style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Display name</label>
                <input type="text" value={cuDisplay} onChange={(e) => setCuDisplay(e.target.value)} style={inputStyle} placeholder="Mario Hernandez" />
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 180px", display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Temporary password *</label>
                <div style={{ position: "relative" }}>
                  <input type={cuShowPassword ? "text" : "password"} required minLength={8} value={cuPassword} onChange={(e) => setCuPassword(e.target.value)} style={{ ...inputStyle, paddingRight: 34 }} placeholder="Min 8 characters" />
                  <button
                    type="button"
                    aria-label={cuShowPassword ? "Hide password" : "Show password"}
                    onClick={() => setCuShowPassword((v) => !v)}
                    style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", padding: 2, color: "var(--tl-text-muted)", display: "flex", alignItems: "center" }}
                  >
                    {cuShowPassword ? (
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
              <div style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Company *</label>
                <select value={cuCompany} onChange={(e) => setCuCompany(e.target.value)} required style={inputStyle}>
                  {companies.length === 0 && <option value="">— no companies yet —</option>}
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div style={{ flex: "0 1 120px", display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Role</label>
                <select value={cuRole} onChange={(e) => setCuRole(e.target.value)} style={inputStyle}>
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>
            {cuError && <p style={{ margin: 0, fontSize: 13, color: "#fca5a5" }}>{cuError}</p>}
            {cuSuccess && <p style={{ margin: 0, fontSize: 13, color: "#86efac" }}>{cuSuccess}</p>}
            <div>
              <button type="submit" className="tl-btn tl-btn-primary" disabled={cuBusy || companies.length === 0}>
                {cuBusy ? "Creating…" : "Create User"}
              </button>
            </div>
          </form>
        </section>


      </div>
    </main>
  );
}
