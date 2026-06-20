#!/usr/bin/env bash
# Read-only inventory of the v1 monolith (routes / components / export functions).
# STRICTLY READ-ONLY: only `grep`, `find`, `wc`. It changes no files, runs no build, touches no git.
# Usage:  bash docs/probe_v1_inventory.sh   (run from the repo root)
#
# Purpose: make the salvage-audit inventory reproducible. It does NOT execute v1 behavior; it only
# lists where v1 implements upload / map / kmz-export / closeout / billing / review surfaces, so the
# audit in docs/product_v1_workflow_salvage_audit.md can be re-derived on demand.
set -u

say() { printf '\n=== %s ===\n' "$1"; }

say "Backend FastAPI route decorators (count by file)"
grep -rEl '@(app|router|protected_router|public_router)\.(get|post|put|delete|patch)' backend 2>/dev/null \
  | while read -r f; do
      n=$(grep -cE '@(app|router|protected_router|public_router)\.(get|post|put|delete|patch)' "$f")
      printf '%5s  %s\n' "$n" "$f"
    done | sort -rn | head -40

say "Backend route paths matching product capabilities (upload/kmz/closeout/billing/export/review)"
grep -rEn '@(app|router|protected_router|public_router)\.(get|post|put|delete|patch)\("([^"]*)"' backend 2>/dev/null \
  | grep -iE 'upload|kmz|kml|closeout|lock|billing|cost|export|print|packet|review|evidence|trust|job|session' \
  | sed -E 's/^([^:]+:[0-9]+):.*\("([^"]*)".*/\2   [\1]/' | sort -u | head -60

say "Backend export / kmz / closeout / billing function defs"
grep -rEn '^\s*(async )?def .*(export|kmz|kml|closeout|billing|cost|packet|redline_segments|render_payload)' backend/app backend/main.py 2>/dev/null \
  | sed -E 's/^([^:]+:[0-9]+):\s*(async )?def ([a-zA-Z0-9_]+).*/\3   [\1]/' | sort -u | head -60

say "Web app routes (pages)"
find web/src/app -name 'page.tsx' 2>/dev/null | sort

say "Web components in the audited surfaces (map / closeout / review / export)"
find web/src/components -type f \( -iname '*map*' -o -iname '*redline*' -o -iname '*closeout*' \
  -o -iname '*packet*' -o -iname '*review*' -o -iname '*evidence*' \) 2>/dev/null | sort

say "Core modules to review for place/customer/project naming (v2 must use capability names)"
# Any module named after a place/customer/project (instead of a capability like kmz_/plan_/bore_/match_)
# must be generalized in v2. Review this list by eye. To auto-flag, pass your deployment's known tokens:
#   NAME_TOKENS='token_a|token_b' bash docs/probe_v1_inventory.sh
find backend/app/core -maxdepth 1 -type f -name '*.py' 2>/dev/null | sort
if [ -n "${NAME_TOKENS:-}" ]; then
  printf '\n-- files matching NAME_TOKENS --\n'
  grep -rilE "$NAME_TOKENS" backend/app web/src 2>/dev/null | head -20
fi

say "Done (read-only; nothing modified)"
