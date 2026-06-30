"""Render the cold-package failure matrix from scored results (plain text / markdown table)."""
from __future__ import annotations


def _conf(r) -> str:
    if getattr(r, "observed_band", None) is None:
        return "-"
    s = r.observed_band
    if r.observed_score is not None:
        s += " %.2f" % r.observed_score
    if r.observed_correction:
        s += " +corr"
    return s


def format_matrix(results) -> str:
    """A markdown table + a summary line. ``results`` is a list of ScoreResult."""
    rows = ["| fixture | expected | observed | conf | blockers | result |",
            "|---|---|---|---|---|---|"]
    for r in results:
        blockers = ", ".join(r.observed_blockers) if r.observed_blockers else "-"
        mark = "PASS" if r.passed else "FAIL"
        rows.append("| %s | %s | %s | %s | %s | %s |"
                    % (r.fixture_id, r.expected_status, r.observed_status, _conf(r), blockers, mark))
    npass = sum(1 for r in results if r.passed)
    rows.append("")
    rows.append("Summary: %d/%d passed." % (npass, len(results)))
    return "\n".join(rows)


def blocker_histogram(results) -> str:
    """Count observed blocker codes across all results (the failure-class signal for Phase 7)."""
    counts = {}
    for r in results:
        for code in r.observed_blockers:
            counts[code] = counts.get(code, 0) + 1
    if not counts:
        return "No blockers observed."
    lines = ["Observed blocker codes:"]
    for code in sorted(counts, key=lambda c: (-counts[c], c)):
        lines.append("  %3d  %s" % (counts[code], code))
    return "\n".join(lines)
