/**
 * PDF Plan Mode Step 3C — Excel bore-log import.
 *
 * Pure module: takes File objects, returns parsed bore-log row specs that
 * mirror the existing Step 3B BoreLogRow shape (sans row_id + created_at,
 * which the caller assigns).  No DOM, no React, no localStorage — the
 * caller wires the result into the existing Step 3B append flow.
 *
 * Canonical Excel schema (verified against 71-file Brenham corpus):
 *   row 1:  station | depth | boc | date | crew | print | notes
 *   row N:  '12+22' | 4.2   | 9   | <Date>| 'tx1-1' | '18,19' | '<note>'
 *
 * Cardinality: 1 workbook = 1 continuous bore = 1 Step 3B row.
 *   start_label = first row's station (preserves Excel row order, including
 *                 intentional descending bore_log55-style files)
 *   end_label   = last  row's station
 *   depth       = max numeric depth across point readings (conservative
 *                 for buried-infrastructure clearance)
 *   boc         = max numeric BOC across point readings
 *   crew/date/print = preserved (verified uniform per file in 71/71)
 *   notes       = concatenation of per-row non-empty notes + auto-summary
 *
 * Import metadata (point readings, filename, sheet name, print, etc.) is
 * stashed on the row's `import_metadata` field; the existing Step 3B
 * generate handler merges it into `source_metadata` on each POSTed segment.
 *
 * SECURITY NOTE: this module accepts operator-curated `.xlsx` files only.
 * It is NOT called on remote/untrusted input.  See ship report for the
 * xlsx@0.18.5 vulnerability acceptance.
 */

import * as XLSX from "xlsx";
import type { BoreLogRow } from "./types/pdfPlan";

// ───────────────────────────────────────────────────────────────────────────
// Constants
// ───────────────────────────────────────────────────────────────────────────

const CANONICAL_HEADER: readonly string[] = [
  "station",
  "depth",
  "boc",
  "date",
  "crew",
  "print",
  "notes",
] as const;

const QUARANTINE_FOLDER = "combined_originals_DO_NOT_IMPORT";

// ───────────────────────────────────────────────────────────────────────────
// Public types
// ───────────────────────────────────────────────────────────────────────────

/** Per-row reading captured from the Excel — preserved verbatim in the
 *  segment's `source_metadata.point_readings` (JSON-stringified) so the
 *  full bore profile is auditable post-generation. */
export type ImportedPointReading = {
  station: string;
  depth: number | string | null;
  boc: number | string | null;
  date: string | null;
  crew: string | null;
  print: string | null;
  notes: string | null;
};

/** Outcome of importing a single file.  Batch importers return one per file. */
export type ImportFileOutcome =
  | {
      kind: "ok";
      filename: string;
      /** Caller assigns row_id + created_at and appends to localStorage. */
      row_spec: Omit<BoreLogRow, "row_id" | "created_at">;
    }
  | { kind: "skipped"; filename: string; reason: string }
  | { kind: "error"; filename: string; reason: string };

// ───────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────

/** Strip extension, return file stem (e.g. "bore_log2.xlsx" → "bore_log2"). */
export function fileStem(filename: string): string {
  const lastSlash = Math.max(filename.lastIndexOf("/"), filename.lastIndexOf("\\"));
  const base = lastSlash >= 0 ? filename.slice(lastSlash + 1) : filename;
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

/** Does the file's webkitRelativePath (or name) contain the quarantine folder? */
export function isQuarantinedPath(pathOrName: string): boolean {
  return pathOrName.includes(QUARANTINE_FOLDER);
}

/** Normalize a header cell to canonical lowercase trimmed form. */
function normalizeHeaderCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v).trim().toLowerCase();
}

/** Coerce any cell to a trimmed string (or null for blank). */
function cellToString(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") {
    const t = v.trim();
    return t === "" ? null : t;
  }
  if (v instanceof Date) {
    // ISO date (YYYY-MM-DD) — consistent with how Step 3B row.date displays.
    const y = v.getUTCFullYear();
    const m = String(v.getUTCMonth() + 1).padStart(2, "0");
    const d = String(v.getUTCDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  return String(v);
}

/** Try to parse a cell as a finite number; return null if not numeric.
 *  Accepts native numbers or numeric strings like "4.2", "36". */
function cellToNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const trimmed = v.trim();
    if (trimmed === "") return null;
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/** Strip optional "STA " / "STA. " prefix from station labels.
 *  Returns the cleaned label; caller's parseStationLabel does the ft conversion. */
export function stripStationPrefix(label: string): string {
  return label.replace(/^STA\.?\s+/i, "").trim();
}

/** True iff a row's seven cells are all null/empty (blank row to skip). */
function isBlankRow(cells: ReadonlyArray<unknown>): boolean {
  for (const c of cells) {
    if (c !== null && c !== undefined && String(c).trim() !== "") return false;
  }
  return true;
}

// ───────────────────────────────────────────────────────────────────────────
// Parser
// ───────────────────────────────────────────────────────────────────────────

/** Parse an in-memory ArrayBuffer (xlsx file bytes) into a row spec.
 *  Exported separately from `importBoreLogExcel` so tests can drive it
 *  without constructing File objects. */
export function parseXlsxBuffer(
  buffer: ArrayBuffer,
  filename: string,
): ImportFileOutcome {
  let wb: XLSX.WorkBook;
  try {
    wb = XLSX.read(buffer, { type: "array", cellDates: true });
  } catch (err) {
    return {
      kind: "error",
      filename,
      reason: `Failed to read workbook: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
  if (!wb.SheetNames || wb.SheetNames.length === 0) {
    return { kind: "error", filename, reason: "Workbook has no sheets." };
  }
  const sheetName = wb.SheetNames[0];
  const ws = wb.Sheets[sheetName];
  if (!ws) {
    return { kind: "error", filename, reason: `Sheet "${sheetName}" not found.` };
  }

  // sheet_to_json with header:1 returns row-arrays of cell values in order.
  //   defval: null  → blank cells are null (not undefined) so column indexing stays stable.
  //   blankrows:false → drop fully-blank rows server-side.
  //   raw: true     → read cell.v (typed): Excel numbers come as JS numbers,
  //                   text comes as strings, AND with cellDates:true above,
  //                   date cells come as JS Date objects (which our
  //                   cellToString helper formats to ISO YYYY-MM-DD).
  //                   Using raw:false would force xlsx's display formatting,
  //                   yielding locale-dependent strings like "11/21/25".
  const matrix: unknown[][] = XLSX.utils.sheet_to_json(ws, {
    header: 1,
    defval: null,
    blankrows: false,
    raw: true,
  });

  if (matrix.length < 1) {
    return { kind: "error", filename, reason: "Sheet has no rows." };
  }

  // ──── Header validation ──────────────────────────────────────────────
  const header = (matrix[0] ?? []).slice(0, 7).map(normalizeHeaderCell);
  if (header.length < 7) {
    return {
      kind: "error",
      filename,
      reason: `Header row has ${header.length} columns; expected 7 (${CANONICAL_HEADER.join("|")}).`,
    };
  }
  for (let i = 0; i < 7; i += 1) {
    if (header[i] !== CANONICAL_HEADER[i]) {
      return {
        kind: "error",
        filename,
        reason: `Header column ${i + 1} is "${header[i] || "(blank)"}"; expected "${CANONICAL_HEADER[i]}".`,
      };
    }
  }

  // ──── Data row scan ──────────────────────────────────────────────────
  // sheet_to_json already strips blank rows internally (blankrows:false)
  // but defensively filter again in case a row has all-null cells.
  const dataRows: unknown[][] = [];
  for (let i = 1; i < matrix.length; i += 1) {
    const row = matrix[i] ?? [];
    if (isBlankRow(row.slice(0, 7))) continue;
    dataRows.push(row);
  }
  if (dataRows.length === 0) {
    return { kind: "error", filename, reason: "Sheet has header but zero data rows." };
  }

  // ──── Per-row extraction ─────────────────────────────────────────────
  const readings: ImportedPointReading[] = [];
  for (const r of dataRows) {
    const stationRaw = cellToString(r[0]);
    if (stationRaw === null) {
      // A row with no station is useless for segment math — skip silently.
      continue;
    }
    readings.push({
      station: stationRaw,
      depth: cellToNumber(r[1]) ?? cellToString(r[1]),
      boc: cellToNumber(r[2]) ?? cellToString(r[2]),
      date: cellToString(r[3]),
      crew: cellToString(r[4]),
      print: cellToString(r[5]),
      notes: cellToString(r[6]),
    });
  }
  if (readings.length === 0) {
    return { kind: "error", filename, reason: "No rows had a parseable station value." };
  }

  // ──── Aggregation: 1 workbook = 1 row spec ───────────────────────────
  const stem = fileStem(filename);
  const startLabel = stripStationPrefix(readings[0].station);
  const endLabel = stripStationPrefix(readings[readings.length - 1].station);

  // Depth/BOC: max of numeric values across all readings (null if none numeric)
  let maxDepth: number | null = null;
  let maxBoc: number | null = null;
  for (const r of readings) {
    if (typeof r.depth === "number") {
      maxDepth = maxDepth === null ? r.depth : Math.max(maxDepth, r.depth);
    }
    if (typeof r.boc === "number") {
      maxBoc = maxBoc === null ? r.boc : Math.max(maxBoc, r.boc);
    }
  }

  // Crew/date/print: first non-null wins (verified uniform across the corpus,
  // but we don't assert it — operator can edit inline if needed).
  const firstNonNull = (field: keyof ImportedPointReading): string | null => {
    for (const r of readings) {
      const v = r[field];
      if (typeof v === "string" && v !== "") return v;
    }
    return null;
  };
  const crew = firstNonNull("crew");
  const date = firstNonNull("date");
  const print = firstNonNull("print");

  // Notes: concatenate all per-row notes (deduped) + auto-summary line.
  const noteFragments: string[] = [];
  const seen = new Set<string>();
  for (const r of readings) {
    if (typeof r.notes === "string" && r.notes !== "" && !seen.has(r.notes)) {
      seen.add(r.notes);
      noteFragments.push(r.notes);
    }
  }
  const summaryParts: string[] = [`${readings.length} point reading${readings.length === 1 ? "" : "s"}`];
  if (maxDepth !== null) summaryParts.push(`max depth ${maxDepth}`);
  if (maxBoc !== null) summaryParts.push(`max BOC ${maxBoc}`);
  const summary = `[Imported from ${stem}.xlsx: ${summaryParts.join(", ")}]`;
  const noteCombined = [...noteFragments, summary].join(" | ");

  // Import metadata: stashed on the row, merged into source_metadata at
  // generate time.  All values are strings per the source_metadata schema
  // constraint (Record<string, string>).  point_readings is JSON-stringified.
  const importMetadata: Record<string, string> = {
    import_kind: "xlsx",
    filename,
    sheet_name: sheetName,
    point_count: String(readings.length),
    imported_at: new Date().toISOString(),
    point_readings: JSON.stringify(readings),
  };
  if (print !== null) importMetadata.print = print;

  return {
    kind: "ok",
    filename,
    row_spec: {
      label: stem,
      start_label: startLabel,
      end_label: endLabel,
      depth: maxDepth !== null ? String(maxDepth) : undefined,
      boc: maxBoc !== null ? String(maxBoc) : undefined,
      crew: crew ?? undefined,
      date: date ?? undefined,
      notes: noteCombined,
      import_metadata: importMetadata,
    },
  };
}

// ───────────────────────────────────────────────────────────────────────────
// File-level API
// ───────────────────────────────────────────────────────────────────────────

/** Browser-only: read a File and parse it. */
export async function importBoreLogExcel(file: File): Promise<ImportFileOutcome> {
  // Defensive path check — webkitRelativePath is populated when the user
  // selects via a directory picker; for normal file pickers it's empty,
  // so we also check the bare filename.
  const fileWithPath = file as File & { webkitRelativePath?: string };
  const path = fileWithPath.webkitRelativePath || file.name;
  if (isQuarantinedPath(path)) {
    return {
      kind: "skipped",
      filename: file.name,
      reason: `File is inside ${QUARANTINE_FOLDER} (multi-segment originals — pre-split files should be imported instead).`,
    };
  }
  const lowerName = file.name.toLowerCase();
  if (!lowerName.endsWith(".xlsx")) {
    return {
      kind: "skipped",
      filename: file.name,
      reason: `File is not .xlsx (got "${file.name}").`,
    };
  }
  let buffer: ArrayBuffer;
  try {
    buffer = await file.arrayBuffer();
  } catch (err) {
    return {
      kind: "error",
      filename: file.name,
      reason: `Failed to read file bytes: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
  return parseXlsxBuffer(buffer, file.name);
}

/** Import a batch of files, returning one outcome per file (order preserved). */
export async function importBoreLogExcelBatch(
  files: ReadonlyArray<File>,
): Promise<ImportFileOutcome[]> {
  const out: ImportFileOutcome[] = [];
  for (const f of files) {
    // Sequential to keep memory steady; xlsx parsing is sync-CPU-bound
    // and benefits little from parallel awaits in browsers.
    out.push(await importBoreLogExcel(f));
  }
  return out;
}
