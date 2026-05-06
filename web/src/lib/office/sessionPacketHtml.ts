/**
 * Builds a standalone HTML document for printing a single field session closeout packet.
 * Pure helpers only — safe for window.open('', '_blank').document.write(html).
 */

import type { Photo, Session } from "@/lib/api";

/** Matches walk bore-log rows from `/api/walk-sessions/{id}/bore-log`. */
export type BoreLogRow = {
  station: string;
  station_ft: number;
  depth_ft: number | null;
  boc_ft: number | null;
  notes: string;
  photo_count: number;
  timestamp: string | null;
};

export type BuildSessionPacketHtmlInput = {
  jobLabel: string;
  session: Session;
  boreLogRows: BoreLogRow[];
  photos: Photo[];
  reviewerNote: string;
  reviewStatus: string;
  apiBase: string;
};

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatMaybeDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return esc(String(iso));
  return esc(d.toLocaleString());
}

function fmtNum(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return esc(String(n));
}

function normalizeBase(base: string): string {
  return String(base || "").trim().replace(/\/+$/, "");
}

function thumbnailSrc(apiBase: string, thumb: string | null): string | null {
  if (thumb == null) return null;
  const t = thumb.trim();
  if (!t) return null;
  if (t.startsWith("http://") || t.startsWith("https://")) return t;
  const root = normalizeBase(apiBase);
  const path = t.startsWith("/") ? t : `/${t}`;
  return `${root}${path}`;
}

function h2(title: string, num: string): string {
  return `<h2 style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.06em;color:#475569;margin:24px 0 8px;padding-bottom:4px;border-bottom:2px solid #e2e8f0">${esc(num)}. ${esc(title)}</h2>`;
}

function metaRow(label: string, value: string): string {
  return `<tr><td style="font-weight:600;padding:5px 10px;border:1px solid #e2e8f0;background:#f8fafc;white-space:nowrap;font-size:12px">${esc(label)}</td><td style="padding:5px 10px;border:1px solid #e2e8f0;font-size:13px">${value}</td></tr>`;
}

function checkItem(ok: boolean, label: string): string {
  return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9">
    <span style="font-size:14px;color:${ok ? "#16a34a" : "#94a3b8"}">${ok ? "✓" : "○"}</span>
    <span style="font-size:13px;color:#0f172a">${esc(label)}</span>
  </div>`;
}

/**
 * Returns a full HTML5 document string (inline CSS only) suitable for print / new window.
 */
export function buildSessionPacketHtml(input: BuildSessionPacketHtmlInput): string {
  const {
    jobLabel,
    session,
    boreLogRows,
    photos,
    reviewerNote,
    reviewStatus,
    apiBase,
  } = input;

  const generatedAt = esc(new Date().toLocaleString());
  const crew = esc(session.crew_name?.trim() || "—");
  const sid = esc(session.id);
  const sessionStatus = esc(String(session.status || "—").trim());
  const reviewLabel = esc(String(reviewStatus || "").trim() || "—");

  const stationCount = typeof session.station_count === "number" ? session.station_count : 0;
  const photoSessionCount =
    typeof session.photo_count === "number" ? session.photo_count : 0;
  const breadcrumbCount =
    typeof session.track_point_count === "number" ? session.track_point_count : 0;

  const boreRowsHtml = boreLogRows
    .map(
      (r) => `
    <tr>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${esc(String(r.station ?? ""))}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${fmtNum(r.station_ft)}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${r.depth_ft == null ? "—" : fmtNum(r.depth_ft)}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${r.boc_ft == null ? "—" : fmtNum(r.boc_ft)}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px;word-break:break-word">${esc(String(r.notes ?? ""))}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px;text-align:right">${fmtNum(r.photo_count)}</td>
      <td style="padding:5px 8px;border:1px solid #e2e8f0;font-size:11px">${r.timestamp == null ? "—" : formatMaybeDate(r.timestamp)}</td>
    </tr>`,
    )
    .join("");

  const photosHtml = photos
    .map((p) => {
      const src = thumbnailSrc(apiBase, p.thumbnail_url);
      const label = [p.station_label, p.note].filter(Boolean).join(" — ") || p.id;
      const img = src
        ? `<img src="${esc(src)}" alt="${esc(p.id)}" style="width:100%;height:120px;object-fit:cover;border-radius:6px;border:1px solid #e2e8f0;background:#f8fafc" onerror="this.style.display='none'"/>`
        : `<div style="width:100%;height:120px;border-radius:6px;border:1px dashed #cbd5e1;background:#f8fafc;display:flex;align-items:center;justify-content:center;font-size:11px;color:#94a3b8">No preview</div>`;
      return `<div style="border:1px solid #e2e8f0;border-radius:8px;padding:8px;background:#fff">
        ${img}
        <div style="margin-top:6px;font-size:10px;color:#475569;word-break:break-all;line-height:1.35">${esc(label)}</div>
        <div style="margin-top:2px;font-size:9px;color:#94a3b8">${p.uploaded_at ? formatMaybeDate(p.uploaded_at) : "—"}</div>
      </div>`;
    })
    .join("");

  const noteBlock =
    reviewerNote.trim().length > 0
      ? `<div style="background:#fafbfc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;font-size:13px;line-height:1.6;white-space:pre-wrap;color:#334155">${esc(reviewerNote.trim())}</div>`
      : `<p style="font-size:13px;color:#64748b;font-style:italic">None</p>`;

  const sessionEnded =
    String(session.status || "")
      .trim()
      .toLowerCase() === "ended";
  const stationsExist = stationCount > 0;
  const photosExist = photos.length > 0 || photoSessionCount > 0;
  const reviewedOk =
    String(reviewStatus || "")
      .trim()
      .toLowerCase() === "reviewed";

  const checklist = [
    checkItem(sessionEnded, "Session ended"),
    checkItem(stationsExist, "Stations exist"),
    checkItem(photosExist, "Photos exist"),
    checkItem(reviewedOk, "Reviewed status"),
  ].join("");

  const emptyBore =
    boreLogRows.length === 0
      ? `<p style="font-size:13px;color:#64748b">No bore log rows for this session.</p>`
      : `<table>
    <thead>
      <tr>
        <th style="text-align:left;padding:6px 8px;background:#f1f5f9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#475569;border:1px solid #e2e8f0">Station</th>
        <th style="text-align:left;padding:6px 8px;background:#f1f5f9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#475569;border:1px solid #e2e8f0">station_ft</th>
        <th style="text-align:left;padding:6px 8px;background:#f1f5f9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#475569;border:1px solid #e2e8f0">depth_ft</th>
        <th style="text-align:left;padding:6px 8px;background:#f1f5f9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#475569;border:1px solid #e2e8f0">boc_ft</th>
        <th style="text-align:left;padding:6px 8px;background:#f1f5f9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#475569;border:1px solid #e2e8f0">Notes</th>
        <th style="text-align:right;padding:6px 8px;background:#f1f5f9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#475569;border:1px solid #e2e8f0">photo_count</th>
        <th style="text-align:left;padding:6px 8px;background:#f1f5f9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#475569;border:1px solid #e2e8f0">timestamp</th>
      </tr>
    </thead>
    <tbody>${boreRowsHtml}</tbody>
  </table>`;

  const emptyPhotos =
    photos.length === 0
      ? `<p style="font-size:13px;color:#64748b">No station photos included in this packet.</p>`
      : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-top:8px">${photosHtml}</div>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Field Session Closeout — ${esc(jobLabel)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #0f172a; background: #ffffff; margin: 0; padding: 32px 40px; max-width: 980px; }
  h1 { font-size: 22px; font-weight: 900; margin: 0 0 10px; letter-spacing: -0.4px; color: #0f172a; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  th { text-align: left; }
  .meta { font-size: 12px; color: #64748b; margin-bottom: 10px; line-height: 1.55; }
  .footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #e2e8f0; font-size: 10px; color: #94a3b8; display: flex; justify-content: space-between; }
  @media print {
    body { padding: 20px 24px; background: #fff; color: #0f172a; }
    h2 { break-after: avoid; }
    table { break-inside: auto; }
    tr { break-inside: avoid; }
  }
</style>
</head>
<body>
<h1>Field Session Closeout Packet</h1>
<div class="meta">
  <strong>Job:</strong> ${esc(jobLabel)} &nbsp;|&nbsp;
  <strong>Session ID:</strong> ${sid}<br/>
  <strong>Crew:</strong> ${crew} &nbsp;|&nbsp;
  <strong>Date:</strong> ${formatMaybeDate(session.started_at)} &nbsp;|&nbsp;
  <strong>${esc("Ended")}:</strong> ${session.ended_at ? formatMaybeDate(session.ended_at) : "—"}
  <br/><strong>Generated:</strong> ${generatedAt}
</div>

${h2("Session Summary", "1")}
<table><tbody>
  ${metaRow("Job label", esc(jobLabel))}
  ${metaRow("Session ID", sid)}
  ${metaRow("Stations count", fmtNum(stationCount))}
  ${metaRow("Photos count", fmtNum(photoSessionCount))}
  ${metaRow("Breadcrumb count", fmtNum(breadcrumbCount))}
  ${metaRow("Status", sessionStatus)}
</tbody></table>

${h2("Bore Log Table", "2")}
${emptyBore}

${h2("Station Photos", "3")}
${emptyPhotos}

${h2("Reviewer Notes", "4")}
${noteBlock}

${h2("Closeout Checklist", "5")}
<div style="max-width:560px">${checklist}</div>
<div style="margin-top:8px;font-size:11px;color:#475569;line-height:1.5">
  Review status supplied: <strong>${reviewLabel}</strong>
</div>

<div class="footer">
  <span>OSP Redlining — field session packet</span>
  <span>${generatedAt}</span>
</div>
</body>
</html>`;
}
