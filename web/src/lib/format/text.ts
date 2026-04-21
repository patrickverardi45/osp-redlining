// Generic formatting and display helpers.
// Moved verbatim from components/RedlineMap.tsx as part of Phase 1 extraction.
// No behavior changes.

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}

export function cleanDisplayText(value: unknown): string {
  const raw = String(value ?? "").trim();
  if (!raw) return "--";
  const lower = raw.toLowerCase();
  if (lower === "nan" || lower === "null" || lower === "undefined") return "--";
  return raw;
}

export function formatDisplayDate(value: string | null | undefined): string {
  const raw = String(value || "").trim();
  if (!raw) return "--";
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];
  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) {
    const year = parsed.getFullYear();
    const month = String(parsed.getMonth() + 1).padStart(2, "0");
    const day = String(parsed.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  return raw.replace(/\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?$/, "");
}
