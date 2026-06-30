"""Score a cold-path decision against a fixture's expected outcome.

Scoring is on PATH + BLOCKER CODES, not path alone:

  * PASS  — observed path == expected status, AND (for an expected ABSTAIN with declared expected_blockers)
            every expected blocker code is present in the observed blockers. A correct ABSTAIN with the
            right named blocker is a PASS — an honest 'I cannot place this, here is exactly why' is the goal,
            not a failure.
  * FAIL  — observed path != expected status (e.g. expected REVIEW but abstained; or expected ABSTAIN but
            the engine placed a candidate where it should have abstained — an over-placement), or an
            expected blocker code is missing.

The observed blocker codes are always reported (even when expected_blockers is empty for the first baseline),
so they can be tightened into expectations once observed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreResult:
    fixture_id: str
    expected_status: str
    observed_status: str
    observed_blockers: tuple     # tuple[str, ...] of blocker codes (source:code)
    expected_blockers: tuple
    passed: bool
    detail: str


def _blocker_codes(decision) -> tuple:
    out = []
    for b in decision.get("blockers", []) or []:
        code = b.get("code")
        source = b.get("source")
        out.append("%s:%s" % (source, code) if source else str(code))
    return tuple(out)


def score(decision, fixture) -> ScoreResult:
    observed_status = decision.get("path")
    observed = _blocker_codes(decision)
    # Compare expected blocker codes by their bare code (ignore the source tag for the expectation).
    observed_bare = {c.split(":", 1)[-1] for c in observed}

    if observed_status != fixture.expected_status:
        detail = "path mismatch: expected %s, observed %s" % (fixture.expected_status, observed_status)
        return ScoreResult(fixture.fixture_id, fixture.expected_status, observed_status, observed,
                           fixture.expected_blockers, False, detail)

    missing = [b for b in fixture.expected_blockers if b not in observed_bare]
    if missing:
        detail = "path ok (%s) but missing expected blocker(s): %r" % (observed_status, missing)
        return ScoreResult(fixture.fixture_id, fixture.expected_status, observed_status, observed,
                           fixture.expected_blockers, False, detail)

    detail = "ok (%s)" % observed_status
    return ScoreResult(fixture.fixture_id, fixture.expected_status, observed_status, observed,
                       fixture.expected_blockers, True, detail)
