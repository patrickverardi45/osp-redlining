"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
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

function friendlyAdminError(detail: string | undefined): string {
  if (!detail) return "Action failed.";
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

function generateTempPassword(): string {
  const chars = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%";
  let pw = "";
  for (let i = 0; i < 12; i++) pw += chars[Math.floor(Math.random() * chars.length)];
  return pw;
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

  // Delete confirmation
  const [deleteUserTarget, setDeleteUserTarget] = useState<string | null>(null);
  const [deleteUserBusy, setDeleteUserBusy] = useState<Record<string, boolean>>({});
  const [deleteUserError, setDeleteUserError] = useState<Record<string, string>>({});
  const [deleteCompanyTarget, setDeleteCompanyTarget] = useState<string | null>(null);
  const [deleteCompanyBusy, setDeleteCompanyBusy] = useState<Record<string, boolean>>({});
  const [deleteCompanyError, setDeleteCompanyError] = useState<Record<string, string>>({});

  // Manage panel
  const [managedUserId, setManagedUserId] = useState<string | null>(null);
  const [manageDn, setManageDn] = useState("");
  const [manageDnBusy, setManageDnBusy] = useState(false);
  const [manageDnMsg, setManageDnMsg] = useState<string | null>(null);
  const [managePw, setManagePw] = useState("");
  const [managePwShow, setManagePwShow] = useState(false);
  const [manageResetBusy, setManageResetBusy] = useState(false);
  const [manageResetResult, setManageResetResult] = useState<string | null>(null);
  const [manageResetError, setManageResetError] = useState<string | null>(null);
  const [manageCopied, setManageCopied] = useState(false);
  const [manageLifeBusy, setManageLifeBusy] = useState(false);
  const managePwRef = useRef<HTMLInputElement>(null);

  // Auth gate
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
      if (!uRes.ok || !cRes.ok) { setLoadError("Failed to load admin data."); return; }
      const [uData, cData] = await Promise.all([uRes.json(), cRes.json()]);
      setUsers(uData);
      setCompanies(cData);
      setCuCompany((prev) => prev || (cData.length > 0 ? cData[0].id : ""));
    } catch { setLoadError("Network error — could not reach the server."); }
  }, []);

  useEffect(() => { if (ready) loadData(); }, [ready, loadData]);
  useEffect(() => { if (!isOwner && callerCompanyId) setCuCompany(callerCompanyId); }, [isOwner, callerCompanyId]);

  // ── Open / close Manage panel ─────────────────────────────────────────────
  const openManage = useCallback((user: AdminUser) => {
    setManagedUserId(user.id);
    setManageDn(user.display_name ?? "");
    setManageDnMsg(null);
    setManagePw("");
    setManagePwShow(false);
    setManageResetResult(null);
    setManageResetError(null);
    setManageCopied(false);
    setDeleteUserTarget(null);
  }, []);

  const closeManage = useCallback(() => {
    setManagedUserId(null);
    setManageResetResult(null);
  }, []);

  // ── Save display name ─────────────────────────────────────────────────────
  const handleSaveDisplayName = useCallback(async (userId: string) => {
    setManageDnBusy(true);
    setManageDnMsg(null);
    try {
      const res = await apiFetch(`/api/admin/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: manageDn.trim() || null }),
      });
      if (res.ok) {
        setManageDnMsg("Saved.");
        loadData();
      } else {
        const data = await res.json().catch(() => ({}));
        setManageDnMsg(data.detail ?? "Save failed.");
      }
    } catch { setManageDnMsg("Network error."); }
    finally { setManageDnBusy(false); }
  }, [manageDn, loadData]);

  // ── Reset password (Manage panel) ─────────────────────────────────────────
  const handleManageReset = useCallback(async (userId: string) => {
    if (managePw.length < 8) return;
    setManageResetBusy(true);
    setManageResetResult(null);
    setManageResetError(null);
    const pwToSet = managePw;
    try {
      const res = await apiFetch(`/api/admin/users/${userId}/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: pwToSet }),
      });
      if (res.ok) {
        setManageResetResult(pwToSet);
        setManagePw("");
        setManagePwShow(false);
      } else {
        const data = await res.json().catch(() => ({}));
        setManageResetError(data.detail ?? "Reset failed.");
      }
    } catch { setManageResetError("Network error."); }
    finally { setManageResetBusy(false); }
  }, [managePw]);

  // ── Copy to clipboard ─────────────────────────────────────────────────────
  const handleCopy = useCallback((text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setManageCopied(true);
      setTimeout(() => setManageCopied(false), 2000);
    }).catch(() => {});
  }, []);

  // ── Disable / Enable (Manage panel) ──────────────────────────────────────
  const handleManageLifecycle = useCallback(async (userId: string, action: "disable" | "enable") => {
    setManageLifeBusy(true);
    try {
      const res = await apiFetch(`/api/admin/users/${userId}/${action}`, { method: "POST" });
      if (res.ok) loadData();
    } catch { /* silent */ }
    finally { setManageLifeBusy(false); }
  }, [loadData]);

  // ── Create User ───────────────────────────────────────────────────────────
  const handleCreateUser = useCallback(async (e: React.FormEvent) => {
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
  }, [cuEmail, cuDisplay, cuPassword, cuCompany, cuRole, callerCompanyId, isOwner, loadData]);

  // ── Create Company ────────────────────────────────────────────────────────
  const handleCreateCompany = useCallback(async (e: React.FormEvent) => {
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
  }, [ccName, loadData]);

  // ── Delete User ───────────────────────────────────────────────────────────
  const handleDeleteUser = useCallback(async (userId: string) => {
    setDeleteUserBusy((p) => ({ ...p, [userId]: true }));
    setDeleteUserError((p) => ({ ...p, [userId]: "" }));
    try {
      const res = await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
      if (res.ok) { setDeleteUserTarget(null); closeManage(); loadData(); }
      else {
        const data = await res.json().catch(() => ({}));
        setDeleteUserError((p) => ({ ...p, [userId]: friendlyAdminError(data.detail) }));
      }
    } catch { setDeleteUserError((p) => ({ ...p, [userId]: "Network error." })); }
    finally { setDeleteUserBusy((p) => ({ ...p, [userId]: false })); }
  }, [loadData, closeManage]);

  // ── Delete Company ────────────────────────────────────────────────────────
  const handleDeleteCompany = useCallback(async (companyId: string) => {
    setDeleteCompanyBusy((p) => ({ ...p, [companyId]: true }));
    setDeleteCompanyError((p) => ({ ...p, [companyId]: "" }));
    try {
      const res = await apiFetch(`/api/admin/companies/${companyId}`, { method: "DELETE" });
      if (res.ok) { setDeleteCompanyTarget(null); loadData(); }
      else {
        const data = await res.json().catch(() => ({}));
        setDeleteCompanyError((p) => ({ ...p, [companyId]: friendlyAdminError(data.detail) }));
      }
    } catch { setDeleteCompanyError((p) => ({ ...p, [companyId]: "Network error." })); }
    finally { setDeleteCompanyBusy((p) => ({ ...p, [companyId]: false })); }
  }, [loadData]);

  if (!ready) return null;

  const availableRoles = isOwner ? ROLES : ROLES.filter((r) => r !== "owner");

  // ── render ────────────────────────────────────────────────────────────────
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
                {isOwner ? "Create and manage users, companies, and role assignments." : "Manage users within your company."}
              </p>
            </div>
            <Link href="/projects" className="tl-btn tl-btn-ghost" style={{ whiteSpace: "nowrap" }}>← Projects</Link>
          </div>
        </header>

        {loadError && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "#2a1212", border: "1px solid #7f1d1d", color: "#fca5a5", fontSize: 13, marginBottom: 20 }}>
            {loadError}
          </div>
        )}

        {/* ── Companies (owners only) ─────────────────────────────────────── */}
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
                            <span style={{ fontSize: 12, color: "#fca5a5" }}>Delete <strong>{c.name}</strong>? Cannot be undone.</span>
                            {deleteCompanyError[c.id] && <span style={{ fontSize: 11, color: "#fca5a5" }}>{deleteCompanyError[c.id]}</span>}
                            <div style={{ display: "flex", gap: 6 }}>
                              <button className="tl-btn tl-btn-ghost" style={{ fontSize: 12, padding: "4px 10px", color: "#fca5a5", borderColor: "#7f1d1d" }} disabled={deleteCompanyBusy[c.id]} onClick={() => handleDeleteCompany(c.id)}>
                                {deleteCompanyBusy[c.id] ? "Deleting…" : "Yes, delete"}
                              </button>
                              <button className="tl-btn tl-btn-ghost" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { setDeleteCompanyTarget(null); setDeleteCompanyError((p) => ({ ...p, [c.id]: "" })); }}>Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <button className="tl-btn tl-btn-ghost" style={{ fontSize: 12, padding: "4px 10px", color: "#fca5a5", borderColor: "#7f1d1d" }} onClick={() => setDeleteCompanyTarget(c.id)}>Delete</button>
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
              <div><button type="submit" className="tl-btn tl-btn-primary" disabled={ccBusy}>{ccBusy ? "Creating…" : "Create Company"}</button></div>
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
                    const isManaged = managedUserId === u.id;

                    return (
                      <Fragment key={u.id}>
                        {/* ── Main row ── */}
                        <tr style={{ opacity: u.disabled_at ? 0.65 : 1, background: isManaged ? "rgba(255,255,255,0.03)" : undefined }}>
                          <td style={cellStyle}>{u.email}{isSelf && <span style={{ marginLeft: 6, fontSize: 11, color: "var(--tl-text-muted)", fontStyle: "italic" }}>(you)</span>}</td>
                          <td style={cellStyle}>{u.display_name ?? <span style={{ color: "var(--tl-text-muted)" }}>—</span>}</td>
                          <td style={cellStyle}>
                            {u.memberships.length === 0 ? (
                              <span style={{ color: "var(--tl-text-muted)" }}>Unassigned</span>
                            ) : u.memberships.map((m) => (
                              <div key={m.membership_id} style={{ lineHeight: 1.6 }}>
                                <span style={{ fontWeight: 500 }}>{m.company_name}</span>
                                <span style={{ color: "var(--tl-text-muted)", marginLeft: 6, fontSize: 12 }}>{m.role}</span>
                              </div>
                            ))}
                          </td>
                          <td style={cellStyle}>
                            {u.disabled_at ? (
                              <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, background: "#450a0a", border: "1px solid #7f1d1d", color: "#fca5a5", fontSize: 11, fontWeight: 600 }}>Disabled</span>
                            ) : (
                              <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, background: "#052e16", border: "1px solid #166534", color: "#86efac", fontSize: 11, fontWeight: 600 }}>Active</span>
                            )}
                          </td>
                          <td style={cellStyle}>
                            {deleteUserTarget === u.id ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 220 }}>
                                <span style={{ fontSize: 12, color: "#fca5a5" }}>
                                  Delete <strong>{u.email}</strong>?<br />
                                  <span style={{ fontSize: 11, opacity: 0.8 }}>Removes user, memberships, and sessions. Cannot be undone.</span>
                                </span>
                                {deleteUserError[u.id] && <span style={{ fontSize: 11, color: "#fca5a5" }}>{deleteUserError[u.id]}</span>}
                                <div style={{ display: "flex", gap: 6 }}>
                                  <button className="tl-btn tl-btn-ghost" style={{ fontSize: 12, padding: "4px 10px", color: "#fca5a5", borderColor: "#7f1d1d" }} disabled={deleteUserBusy[u.id]} onClick={() => handleDeleteUser(u.id)}>
                                    {deleteUserBusy[u.id] ? "Deleting…" : "Yes, delete"}
                                  </button>
                                  <button className="tl-btn tl-btn-ghost" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { setDeleteUserTarget(null); setDeleteUserError((p) => ({ ...p, [u.id]: "" })); }}>Cancel</button>
                                </div>
                              </div>
                            ) : (
                              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                <button
                                  className="tl-btn tl-btn-ghost"
                                  style={{ fontSize: 12, padding: "4px 12px" }}
                                  onClick={() => isManaged ? closeManage() : openManage(u)}
                                >
                                  {isManaged ? "Close" : "Manage"}
                                </button>
                                {canDelete && (
                                  <button
                                    className="tl-btn tl-btn-ghost"
                                    style={{ fontSize: 11, padding: "3px 8px", color: "#fca5a5", borderColor: "#7f1d1d", marginTop: 2 }}
                                    onClick={() => { closeManage(); setDeleteUserTarget(u.id); }}
                                  >
                                    Delete
                                  </button>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>

                        {/* ── Manage panel row ── */}
                        {isManaged && (
                          <tr>
                            <td colSpan={5} style={{ padding: "0 0 16px 0", borderBottom: "1px solid var(--tl-border)" }}>
                              <ManagePanel
                                user={u}
                                companies={companies}
                                isSelf={isSelf}
                                manageDn={manageDn}
                                manageDnBusy={manageDnBusy}
                                manageDnMsg={manageDnMsg}
                                managePw={managePw}
                                managePwShow={managePwShow}
                                managePwRef={managePwRef}
                                manageResetBusy={manageResetBusy}
                                manageResetResult={manageResetResult}
                                manageResetError={manageResetError}
                                manageCopied={manageCopied}
                                manageLifeBusy={manageLifeBusy}
                                onDnChange={setManageDn}
                                onSaveDn={() => handleSaveDisplayName(u.id)}
                                onPwChange={setManagePw}
                                onPwShowToggle={() => setManagePwShow((v) => !v)}
                                onGenerate={() => setManagePw(generateTempPassword())}
                                onReset={() => handleManageReset(u.id)}
                                onCopy={() => handleCopy(manageResetResult ?? "")}
                                onLifecycle={(action) => handleManageLifecycle(u.id, action)}
                                onClose={closeManage}
                              />
                            </td>
                          </tr>
                        )}
                      </Fragment>
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
                  <button type="button" aria-label={cuShowPassword ? "Hide password" : "Show password"} onClick={() => setCuShowPassword((v) => !v)} style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", padding: 2, color: "var(--tl-text-muted)", display: "flex", alignItems: "center" }}>
                    <EyeIcon open={cuShowPassword} />
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
                  <input type="text" readOnly value={companies.find((c) => c.id === callerCompanyId)?.name ?? "—"} style={{ ...inputStyle, color: "var(--tl-text-muted)", cursor: "default" }} />
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

// ---------------------------------------------------------------------------
// ManagePanel — inline expanded user management card
// ---------------------------------------------------------------------------

type ManagePanelProps = {
  user: AdminUser;
  companies: Company[];
  isSelf: boolean;
  manageDn: string;
  manageDnBusy: boolean;
  manageDnMsg: string | null;
  managePw: string;
  managePwShow: boolean;
  managePwRef: React.RefObject<HTMLInputElement | null>;
  manageResetBusy: boolean;
  manageResetResult: string | null;
  manageResetError: string | null;
  manageCopied: boolean;
  manageLifeBusy: boolean;
  onDnChange: (v: string) => void;
  onSaveDn: () => void;
  onPwChange: (v: string) => void;
  onPwShowToggle: () => void;
  onGenerate: () => void;
  onReset: () => void;
  onCopy: () => void;
  onLifecycle: (action: "disable" | "enable") => void;
  onClose: () => void;
};

const panelInput: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 6,
  border: "1px solid var(--tl-border)",
  background: "var(--tl-bg)",
  color: "var(--tl-text)",
  fontSize: 13,
  boxSizing: "border-box",
};

function ManagePanel({
  user, companies, isSelf,
  manageDn, manageDnBusy, manageDnMsg,
  managePw, managePwShow, managePwRef,
  manageResetBusy, manageResetResult, manageResetError, manageCopied,
  manageLifeBusy,
  onDnChange, onSaveDn, onPwChange, onPwShowToggle, onGenerate,
  onReset, onCopy, onLifecycle, onClose,
}: ManagePanelProps) {
  const primaryMembership = user.memberships[0];

  return (
    <div style={{
      margin: "0 10px 0 10px",
      padding: "16px 18px",
      borderRadius: "0 0 8px 8px",
      background: "var(--tl-bg-raised, rgba(255,255,255,0.04))",
      border: "1px solid var(--tl-border)",
      borderTop: "none",
      display: "flex",
      flexDirection: "column",
      gap: 18,
    }}>

      {/* ── User info ── */}
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ minWidth: 180 }}>
          <div style={{ fontSize: 11, color: "var(--tl-text-muted)", marginBottom: 2 }}>Email</div>
          <div style={{ fontSize: 13, fontFamily: "monospace" }}>{user.email}</div>
        </div>
        {primaryMembership && (
          <div style={{ minWidth: 140 }}>
            <div style={{ fontSize: 11, color: "var(--tl-text-muted)", marginBottom: 2 }}>Company</div>
            <div style={{ fontSize: 13 }}>{primaryMembership.company_name}</div>
          </div>
        )}
        {primaryMembership && (
          <div style={{ minWidth: 80 }}>
            <div style={{ fontSize: 11, color: "var(--tl-text-muted)", marginBottom: 2 }}>Role</div>
            <div style={{ fontSize: 13 }}>{primaryMembership.role}</div>
          </div>
        )}
        <div style={{ minWidth: 80 }}>
          <div style={{ fontSize: 11, color: "var(--tl-text-muted)", marginBottom: 2 }}>Status</div>
          {user.disabled_at ? (
            <span style={{ padding: "2px 8px", borderRadius: 4, background: "#450a0a", border: "1px solid #7f1d1d", color: "#fca5a5", fontSize: 11, fontWeight: 600 }}>Disabled</span>
          ) : (
            <span style={{ padding: "2px 8px", borderRadius: 4, background: "#052e16", border: "1px solid #166534", color: "#86efac", fontSize: 11, fontWeight: 600 }}>Active</span>
          )}
        </div>
      </div>

      {/* ── Edit display name ── */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--tl-text)", marginBottom: 6 }}>Display Name</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="text"
            value={manageDn}
            onChange={(e) => onDnChange(e.target.value)}
            placeholder="e.g. Mario Hernandez"
            style={{ ...panelInput, flex: "1 1 200px", maxWidth: 300 }}
          />
          <button
            className="tl-btn tl-btn-ghost"
            style={{ fontSize: 12, padding: "5px 12px" }}
            disabled={manageDnBusy}
            onClick={onSaveDn}
          >
            {manageDnBusy ? "Saving…" : "Save"}
          </button>
        </div>
        {manageDnMsg && (
          <p style={{ margin: "4px 0 0", fontSize: 12, color: manageDnMsg === "Saved." ? "#86efac" : "#fca5a5" }}>{manageDnMsg}</p>
        )}
      </div>

      {/* ── Password section ── */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--tl-text)", marginBottom: 4 }}>Password Reset</div>
        <p style={{ margin: "0 0 8px", fontSize: 12, color: "var(--tl-text-muted)" }}>
          Existing passwords cannot be viewed — they are stored as one-way hashes. Reset to issue a new temporary password.
        </p>

        {manageResetResult ? (
          /* ── Success: reveal new temp password ── */
          <div style={{ padding: "12px 14px", borderRadius: 8, background: "#052e16", border: "1px solid #166534", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 12, color: "#86efac", fontWeight: 600 }}>Password updated. Share this with the user:</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <code style={{ flex: 1, fontSize: 14, letterSpacing: "0.05em", background: "rgba(0,0,0,0.3)", padding: "6px 10px", borderRadius: 4, color: "#d1fae5", userSelect: "all" }}>
                {manageResetResult}
              </code>
              <button
                className="tl-btn tl-btn-ghost"
                style={{ fontSize: 12, padding: "5px 12px", color: manageCopied ? "#86efac" : undefined }}
                onClick={onCopy}
              >
                {manageCopied ? "Copied!" : "Copy"}
              </button>
            </div>
            <p style={{ margin: 0, fontSize: 11, color: "#6ee7b7", opacity: 0.8 }}>
              Store this now — it will not be shown again after you leave this panel.
            </p>
          </div>
        ) : (
          /* ── Input + actions ── */
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ position: "relative", flex: "1 1 200px", maxWidth: 300 }}>
                <input
                  ref={managePwRef}
                  type={managePwShow ? "text" : "password"}
                  placeholder="New password (min 8 chars)"
                  value={managePw}
                  onChange={(e) => onPwChange(e.target.value)}
                  style={{ ...panelInput, width: "100%", paddingRight: 34 }}
                />
                <button
                  type="button"
                  aria-label={managePwShow ? "Hide password" : "Show password"}
                  onClick={onPwShowToggle}
                  style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", padding: 2, color: "var(--tl-text-muted)", display: "flex", alignItems: "center" }}
                >
                  <EyeIcon open={managePwShow} />
                </button>
              </div>
              <button
                className="tl-btn tl-btn-ghost"
                style={{ fontSize: 12, padding: "5px 12px" }}
                onClick={onGenerate}
                type="button"
              >
                Generate
              </button>
              <button
                className="tl-btn tl-btn-primary"
                style={{ fontSize: 12, padding: "5px 14px" }}
                disabled={manageResetBusy || managePw.length < 8}
                onClick={onReset}
                type="button"
              >
                {manageResetBusy ? "Resetting…" : "Reset Password"}
              </button>
            </div>
            {manageResetError && <p style={{ margin: 0, fontSize: 12, color: "#fca5a5" }}>{manageResetError}</p>}
          </div>
        )}
      </div>

      {/* ── Lifecycle ── */}
      {!isSelf && (
        <div style={{ paddingTop: 12, borderTop: "1px solid var(--tl-border)", display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "var(--tl-text-muted)", marginRight: 4 }}>Account status:</span>
          {user.disabled_at ? (
            <button
              className="tl-btn tl-btn-ghost"
              style={{ fontSize: 12, padding: "4px 12px", color: "#86efac", borderColor: "#166534" }}
              disabled={manageLifeBusy}
              onClick={() => onLifecycle("enable")}
            >
              {manageLifeBusy ? "…" : "Enable account"}
            </button>
          ) : (
            <button
              className="tl-btn tl-btn-ghost"
              style={{ fontSize: 12, padding: "4px 12px", color: "#fca5a5", borderColor: "#7f1d1d" }}
              disabled={manageLifeBusy}
              onClick={() => onLifecycle("disable")}
            >
              {manageLifeBusy ? "…" : "Disable account"}
            </button>
          )}
        </div>
      )}

      {/* ── Close ── */}
      <div>
        <button className="tl-btn tl-btn-ghost" style={{ fontSize: 12, padding: "4px 12px" }} onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EyeIcon — shared password show/hide icon
// ---------------------------------------------------------------------------

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
        <line x1="1" y1="1" x2="23" y2="23" />
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}
