// Currency formatting helper.
// Moved verbatim from components/RedlineMap.tsx as part of Phase 1 extraction.
// No behavior changes. Isolated from text.ts so future currency/locale work has a home.

export function toMoney(value: number): string {
  return `$${value.toFixed(2)}`;
}
