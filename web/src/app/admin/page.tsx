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
  disabled_at: string | null;
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

const dangerDivider: React.CSSProperties = {
  marginTop: 6,
  paddingTop: 6,
  borderTop: "1px solid #3f1515",
};

function friendlyAdminError(detail: string | undefined): string {
  if (!detail) return "Delete failed.";
  if (detail.startsWith("company_has_users"))
    return "This company still has users. Remove or delete all users from the company first.";
  if (detail.startsWith("company_has_projects"))
    return "This company still has projects in the database. Remove all projects first.";
  if (detail === "cannot_delete_self") return "You cannot delete your own account.";
  if (detail === "not_in_your_company") return "That user is not in your company.";
  if (detail === "admin_cannot_delete_owner_user") return "Admins cannot delete owner-role users.";
  if (detail === "owner_required") return "Only platform owners can perform this action.";
  if (detail === "company_not_found") return "Company not found.";
  if (detail === "user_not_found") return "User not found.";
  return detail;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [callerId, setCallerId] = useState<string>("");
  const [callerRole, setCallerRole] = useState<string>("member");
  const [callerCompanyId, setCallerCompanyId] = useState<string>("");

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

  // Disable/enable busy keyed by user_id
  const [lifeBusy, setLifeBusy] = useState<Record<string, boolean>>({});

  // Delete confirmation targets
  const [deleteUserTarget, setDeleteUserTarget] = useState<string | null>(null);
  const [deleteUserBusy, setDeleteUserBusy] = useState<Record<string, boolean>>({});
  const [deleteUserError, setDeleteUserError] = useState<Record<string, string>>({});
  const [deleteCompanyTarget, setDeleteCompanyTarget] = useState<string | null>(null);
  const [deleteCompanyBusy, setDeleteCompanyBusy] = useState<Record<string, boolean>>({});
  const [deleteCompanyError, setDeleteCompanyError] = useState<Record<string, string>>({});

  // Auth gate — only owner/admin may access this page
  useEffect(() => {
    me().then((user) => {
      if (!user || !["owner", "admin"].includes(user.role)) {
        router.replace("/projects");
        return;
      }
      setCallerId(user.id);
      setCallerRole(user.role);
      setCallerCompanyId(user.company_id);
      setReady(true);
    });
  }, [router]);

  const isOwner = callerRole === "owner";

  const loadData = useCallback(async () => {
    setLoadError(null);
    try {
      const [uRes, cRes] = await Promise.all([
        apiFetch("/api/admin/users"),
        apiFetch("/api/admin/companies"),
      ]);
      if (!uRes.ok || !cRes.ok) {
        setLoadError("Failed to load admin data.");
        return;
      }
      const [uData, cData] = await Promise.all([uRes.json(), cRes.json()]);
      setUsers(uData);
      setCompanies(cData);
      setCuCompany((prev) => {
        if (prev) return prev;
        return cData.length > 0 ? cData[0].id : "";
      });
    } catch {
      setLoadError("Network error — could not reach the server.");
    }
  }, []);

  useEffect(() => {
    if (ready) loadData();
  }, [ready, loadData]);

  useEffect(() => {
    if (!isOwner && callerCompanyId) setCuCompany(callerCompanyId);
  }, [isOwner, callerCompanyId]);

  // ── Create User ──────────────────────────────────────────────────────────
  const handleCreateUser = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setCuError(null); setCuSuccess(null);
      const effectiveCompany = isOwner ? cuCompany : callerCompanyId;
      if (!effectiveCompany) { setCuError("No company available."); return; }
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
          body: JSON.stringify({ company_id: effectiveCompany, role: cuRole }),
        });
        if (!assignRes.ok) {
          const d = await assignRes.json();
          setCuError(`User created but assign failed: ${d.detail ?? "unknown error"}`);
          return;
        }
        setCuSuccess(`Created ${cuEmail} — temp password set. Share credentials securely.`);
        setCuEmail(""); setCuDisplay(""); setCuPassword(""); setCuRole("member");
        loadData();
      } catch { setCuError("Network error."); }
      finally { setCuBusy(false); }
    },
    [cuEmail, cuDisplay, cuPassword, cuCompany, cuRole, callerCompanyId, isOwner, loadData],
  );

  // ── Create Company ───────────────────────────────────────────────────────
  const handleCreateCompany = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setCcError(null); setCcSuccess(null); setCcBusy(true);
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
      } catch { setCcError("Network error."); }
      finally { setCcBusy(false); }
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
          setResetTarget(null); setResetPw("");
        }
      } catch {
        setResetMsg((prev) => ({ ...prev, [userId]: "Network error." }));
      } finally { setResetBusy(false); }
    },
    [resetPw],
  );

  // ── Disable / Enable ─────────────────────────────────────────────────────
  const handleLifecycle = useCallback(
    async (userId: string, action: "disable" | "enable") => {
      setLifeBusy((prev) => ({ ...prev, [userId]: true }));
      try {
        const res = await apiFetch(`/api/admin/users/${userId}/${action}`, { method: "POST" });
        if (res.ok) loadData();
      } catch { /* silent */ }
      finally { setLifeBusy((prev) => ({ ...prev, [userId]: false })); }
    },
    [loadData],
  );

  // ── Delete User ──────────────────────────────────────────────────────────
  const handleDeleteUser = useCallback(
    async (userId: string) => {
      setDeleteUserBusy((prev) => ({ ...prev, [userId]: true }));
      setDeleteUserError((prev) => ({ ...prev, [userId]: "" }));
      try {
        const res = await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
        if (res.ok) {
          setDeleteUserTarget(null);
          loadData();
        } else {
          const data = await res.json().catch(() => ({}));
          setDeleteUserError((prev) => ({ ...prev, [userId]: friendlyAdminError(data.detail) }));
        }
      } catch {
        setDeleteUserError((prev) => ({ ...prev, [userId]: "Network error." }));
      } finally {
        setDeleteUserBusy((prev) => ({ ...prev, [userId]: false }));
      }
    },
    [loadData],
  );

  // ── Delete Company ───────────────────────────────────────────────────────
  const handleDeleteCompany = useCallback(
    async (companyId: string) => {
      setDeleteCompanyBusy((prev) => ({ ...prev, [companyId]: true }));
      setDeleteCompanyError((prev) => ({ ...prev, [companyId]: "" }));
      try {
        const res = await apiFetch(`/api/admin/companies/${companyId}`, { method: "DELETE" });
        if (res.ok) {
          setDeleteCompanyTarget(null);
          loadData();
        } else {
          const data = await res.json().catch(() => ({}));
          setDeleteCompanyError((prev) => ({ ...prev, [companyId]: friendlyAdminError(data.detail) }));
        }
      } catch {
        setDeleteCompanyError((prev) => ({ ...prev, [companyId]: "Network error." }));
      } finally {
        setDeleteCompanyBusy((prev) => ({ ...prev, [companyId]: false }));
      }
    },
    [loadData],
  );

  if (!ready) return null;

  const availableRoles = isOwner ? ROLES : ROLES.filter((r) => r !== "owner");

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
                {isOwner
                  ? "Create and manage users, companies, and role assignments."
                  : "Manage users within your company."}
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

        {/* ── Companies (owners only) ──────────────────────────────────────── */}
        {isOwner && (
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
                    <th style={thStyle}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {companies.map((c) => (
                    <tr key={c.id}>
                      <td style={cellStyle}>{c.name}</td>
                      <td style={cellStyle}>{c.slug}</td>
                      <td style={{ ...cellStyle, fontFamily: "monospace", fontSize: 11, color: "var(--tl-text-muted)" }}>{c.id}</td>
                      <td style={cellStyle}>
                        {deleteCompanyTarget === c.id ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            <span style={{ fontSize: 12, color: "#fca5a5" }}>
                              Delete <strong>{c.name}</strong>? This cannot be undone.
                            </span>
                            {deleteCompanyError[c.id] && (
                              <span style={{ fontSize: 11, color: "#fca5a5" }}>{deleteCompanyError[c.id]}</span>
                            )}
                            <div style={{ display: "flex", gap: 6 }}>
                              <button
                                className="tl-btn tl-btn-ghost"
                                style={{ fontSize: 12, padding: "4px 10px", color: "#fca5a5", borderColor: "#7f1d1d" }}
                                disabled={deleteCompanyBusy[c.id]}
                                onClick={() => handleDeleteCompany(c.id)}
                              >
                                {deleteCompanyBusy[c.id] ? "Deleting…" : "Yes, delete"}
                              </button>
                              <button
                                className="tl-btn tl-btn-ghost"
                                style={{ fontSize: 12, padding: "4px 10px" }}
                                onClick={() => { setDeleteCompanyTarget(null); setDeleteCompanyError((p) => ({ ...p, [c.id]: "" })); }}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            className="tl-btn tl-btn-ghost"
                            style={{ fontSize: 12, padding: "4px 10px", color: "#fca5a5", borderColor: "#7f1d1d" }}
                            onClick={() => setDeleteCompanyTarget(c.id)}
                          >
                            Delete
                          </button>
                        )}
                      </td>
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
        )}

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
                    <th style={thStyle}>Status</th>
                    <th style={thStyle}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const isSelf = u.id === callerId;
                    const isTargetOwner = u.memberships.some((m) => m.role === "owner");
                    const canDelete = !isSelf && (isOwner || !isTargetOwner);
                    return (
                      <tr key={u.id} style={{ opacity: u.disabled_at ? 0.6 : 1 }}>
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
                          {u.disabled_at ? (
                            <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, background: "#450a0a", border: "1px solid #7f1d1d", color: "#fca5a5", fontSize: 11, fontWeight: 600 }}>
                              Disabled
                            </span>
                          ) : (
                            <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, background: "#052e16", border: "1px solid #166534", color: "#86efac", fontSize: 11, fontWeight: 600 }}>
                              Active
                            </span>
                          )}
                        </td>
                        <td style={cellStyle}>
                          {deleteUserTarget === u.id ? (
                            <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 220 }}>
                              <span style={{ fontSize: 12, color: "#fca5a5" }}>
                                Delete <strong>{u.email}</strong>?<br />
                                <span style={{ fontSize: 11, opacity: 0.8 }}>Removes user, memberships, and sessions. Cannot be undone.</span>
                              </span>
                              {deleteUserError[u.id] && (
                                <span style={{ fontSize: 11, color: "#fca5a5" }}>{deleteUserError[u.id]}</span>
                              )}
                              <div style={{ display: "flex", gap: 6 }}>
                                <button
                                  className="tl-btn tl-btn-ghost"
                                  style={{ fontSize: 12, padding: "4px 10px", color: "#fca5a5", borderColor: "#7f1d1d" }}
                                  disabled={deleteUserBusy[u.id]}
                                  onClick={() => handleDeleteUser(u.id)}
                                >
                                  {deleteUserBusy[u.id] ? "Deleting…" : "Yes, delete"}
                                </button>
                                <button
                                  className="tl-btn tl-btn-ghost"
                                  style={{ fontSize: 12, padding: "4px 10px" }}
                                  onClick={() => { setDeleteUserTarget(null); setDeleteUserError((p) => ({ ...p, [u.id]: "" })); }}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              {/* Normal actions */}
                              {resetTarget === u.id ? (
                                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
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
                                <>
                                  <button
                                    className="tl-btn tl-btn-ghost"
                                    style={{ fontSize: 12, padding: "4px 10px" }}
                                    onClick={() => { setResetTarget(u.id); setResetPw(""); setResetMsg((p) => ({ ...p, [u.id]: "" })); }}
                                  >
                                    Reset password
                                  </button>
                                  {u.disabled_at ? (
                                    <button
                                      className="tl-btn tl-btn-ghost"
                                      style={{ fontSize: 12, padding: "4px 10px", color: "#86efac", borderColor: "#166534" }}
                                      disabled={lifeBusy[u.id]}
                                      onClick={() => handleLifecycle(u.id, "enable")}
                                    >
                                      {lifeBusy[u.id] ? "…" : "Enable"}
                                    </button>
                                  ) : (
                                    <button
                                      className="tl-btn tl-btn-ghost"
                                      style={{ fontSize: 12, padding: "4px 10px", color: "#fca5a5", borderColor: "#7f1d1d" }}
                                      disabled={lifeBusy[u.id]}
                                      onClick={() => handleLifecycle(u.id, "disable")}
                                    >
                                      {lifeBusy[u.id] ? "…" : "Disable"}
                                    </button>
                                  )}
                                  {resetMsg[u.id] && (
                                    <span style={{ fontSize: 12, color: "#86efac" }}>{resetMsg[u.id]}</span>
                                  )}
                                </>
                              )}

                              {/* Danger zone — visually separated */}
                              {canDelete && (
                                <div style={dangerDivider}>
                                  <button
                                    className="tl-btn tl-btn-ghost"
                                    style={{ fontSize: 11, padding: "3px 8px", color: "#fca5a5", borderColor: "#7f1d1d" }}
                                    onClick={() => { setResetTarget(null); setDeleteUserTarget(u.id); }}
                                  >
                                    Delete user
                                  </button>
                                </div>
                              )}
                              {isSelf && (
                                <span style={{ fontSize: 11, color: "var(--tl-text-muted)", fontStyle: "italic" }}>
                                  (you)
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
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

              {isOwner ? (
                <div style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Company *</label>
                  <select value={cuCompany} onChange={(e) => setCuCompany(e.target.value)} required style={inputStyle}>
                    {companies.length === 0 && <option value="">— no companies yet —</option>}
                    {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
              ) : (
                <div style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Company</label>
                  <input
                    type="text"
                    readOnly
                    value={companies.find((c) => c.id === callerCompanyId)?.name ?? "—"}
                    style={{ ...inputStyle, color: "var(--tl-text-muted)", cursor: "default" }}
                  />
                </div>
              )}

              <div style={{ flex: "0 1 120px", display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 12, color: "var(--tl-text-muted)" }}>Role</label>
                <select value={cuRole} onChange={(e) => setCuRole(e.target.value)} style={inputStyle}>
                  {availableRoles.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>
            {cuError && <p style={{ margin: 0, fontSize: 13, color: "#fca5a5" }}>{cuError}</p>}
            {cuSuccess && <p style={{ margin: 0, fontSize: 13, color: "#86efac" }}>{cuSuccess}</p>}
            <div>
              <button type="submit" className="tl-btn tl-btn-primary" disabled={cuBusy || (isOwner && companies.length === 0)}>
                {cuBusy ? "Creating…" : "Create User"}
              </button>
            </div>
          </form>
        </section>

      </div>
    </main>
  );
}
