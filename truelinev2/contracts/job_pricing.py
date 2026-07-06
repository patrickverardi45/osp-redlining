"""Operator-entered job pricing (contract-only) — a per-job, OPERATOR-ENTERED rate table.

DISTINCT from the server-authoritative ``billing_summary`` (versioned, configured cost rules). Here the
operator types a cost-per-foot and exception rows PER JOB; the dollars are the operator's OWN inputs and are
explicitly UNVERIFIED — never a configured rate sheet, never invented. Boundaries (honest billing):

  * NO default / invented rates. ``cost_per_foot`` and every exception ``amount`` start BLANK (None) and
    require operator input; a blank rate yields NO base/final total (not a $0 fabrication).
  * Quantities come from the SERVER, never typed: ``footage`` is derived from the CONFIRMED reviewed
    bore-log rows' station ranges (or an explicit reviewed footage field) — never guessed map/geospatial
    coordinates. Only when no confirmed row yields a valid footage does it fall back to the validated
    manifest's drawn footage via ``billing_summary.job_effective_footage``. Both are trusted, echoed read-only.
  * Totals are computed ONLY from operator-entered rates over the server quantity:
        base_total      = footage × cost_per_foot   (only when BOTH are present)
        exception_total = Σ exception amounts
        final_total     = base_total + exception_total   (only when base_total is computable)
  * Every surface carries the ``OPERATOR_ENTERED_UNVERIFIED`` provenance + the disclaimer.

Money is ``Decimal`` (stdlib), quantized ROUND_HALF_UP to 2 places, serialized as canonical strings — the
same discipline as billing_summary, kept in a SEPARATE singleton record. Contract-only: no engine, renderer,
web/backend, AI/OCR, KMZ, invoicing/tax, or deploy. Reads the server footage; never mutates billing/closeout.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from truelinev2.contracts.billing_summary import job_effective_footage
from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.extracted_row import row_review_passes
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.reviewed_bore_log import list_reviewed_bore_logs

JOB_PRICING_RECORD_FORMAT = "trueline-operator-pricing-1"
JOB_PRICING_FILENAME = "_operator_pricing.json"        # ONE record per job (singleton)

# Provenance + disclaimer carried on every read and into the closeout PDF. The whole point: these dollars are
# the operator's own entries, NOT a configured/authoritative rate sheet.
PROVENANCE_OPERATOR_ENTERED = "OPERATOR_ENTERED_UNVERIFIED"
PRICING_DISCLAIMER = (
    "Operator-entered rates — NOT verified by a configured rate sheet. Quantities are server-computed; "
    "dollar amounts reflect the operator's own entered rates and are provisional."
)
_MONEY_DIGITS = 2
_MAX_EXCEPTIONS = 100


class JobPricingError(ValueError):
    """Invalid operator-pricing input (e.g. a negative or non-numeric amount)."""


def _q(amount: Decimal) -> str:
    return str(amount.quantize(Decimal(10) ** -_MONEY_DIGITS, rounding=ROUND_HALF_UP))


def _parse_money(value, what) -> "Decimal | None":
    """Blank/None -> None (NO fake default). Otherwise a NON-NEGATIVE decimal, or raise. Never invents a rate."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("$", "")
    if s == "":
        return None
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        raise JobPricingError("%s must be a number (got %r)" % (what, value))
    if d < 0:
        raise JobPricingError("%s must not be negative (got %r)" % (what, value))
    return d


def _normalize_exceptions(exceptions) -> list:
    """Validate operator exception rows -> [{label, amount(str|None), note(str|None)}]. A row needs a label;
    its amount is blank (None) or a non-negative number; note is optional. No defaults, no invented dollars."""
    out = []
    for raw in (exceptions or []):
        if not isinstance(raw, dict):
            raise JobPricingError("each exception must be an object")
        label = str(raw.get("label") or "").strip()
        if not label:
            raise JobPricingError("each exception needs a label")
        amount = _parse_money(raw.get("amount"), "exception amount")
        note = raw.get("note")
        note = str(note).strip() if note not in (None, "") else None
        out.append({"label": label, "amount": (_q(amount) if amount is not None else None), "note": note})
        if len(out) > _MAX_EXCEPTIONS:
            raise JobPricingError("too many exception rows (max %d)" % _MAX_EXCEPTIONS)
    return out


def job_pricing_path(store_root, customer_project_id, processing_job_id) -> Path:
    return job_dir(store_root, customer_project_id, processing_job_id) / JOB_PRICING_FILENAME


def _blank_record(customer_project_id, processing_job_id) -> dict:
    return {"record_format": JOB_PRICING_RECORD_FORMAT, "customer_project_id": customer_project_id,
            "processing_job_id": processing_job_id, "cost_per_foot": None, "exceptions": [],
            "provenance": PROVENANCE_OPERATOR_ENTERED, "updated_at": None, "updated_by": None}


def load_job_pricing(store_root, customer_project_id, processing_job_id) -> dict:
    """Load the job's operator-pricing record, or a BLANK record (no rates, no exceptions) when none is saved
    — never a fabricated default. Tenant-scoped."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    path = job_pricing_path(store_root, customer_project_id, processing_job_id)
    if not path.is_file():
        return _blank_record(customer_project_id, processing_job_id)
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, rec.get("customer_project_id"))
    return rec


def save_job_pricing(store_root, customer_project_id, processing_job_id, *, cost_per_foot, exceptions,
                     at, by) -> dict:
    """Persist the operator-entered cost-per-foot + exception rows for one job (tenant + job scoped). The job
    must exist. ``cost_per_foot`` blank/None is allowed (and stays blank — no default). Validates every amount
    is a non-negative number; rejects a negative/non-numeric input. Returns the stored record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    load_job(store_root, customer_project_id, processing_job_id)              # exists + isolation (404)
    cpf = _parse_money(cost_per_foot, "cost per foot")
    record = {"record_format": JOB_PRICING_RECORD_FORMAT, "customer_project_id": customer_project_id,
              "processing_job_id": processing_job_id,
              "cost_per_foot": (_q(cpf) if cpf is not None else None),
              "exceptions": _normalize_exceptions(exceptions),
              "provenance": PROVENANCE_OPERATOR_ENTERED, "updated_at": at, "updated_by": by}
    path = job_pricing_path(store_root, customer_project_id, processing_job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


# --------------------------------------------------------------------------- #
# Footage from CONFIRMED reviewed bore-log rows — station ranges / explicit reviewed footage. Pure; never
# guesses map/geospatial coordinates and never fabricates a length.
# --------------------------------------------------------------------------- #
# A survey station: <whole stations>+<2-digit offset feet>, e.g. "1+00"=100 ft, "10+25"=1025 ft, "0+00"=0 ft.
# Position in FEET = stations*100 + offset. The offset is exactly two digits (optionally with decimals), so it
# is < 100 by construction (standard stationing) — a bare "1", "1+5", or a 3-digit offset "1+000" is malformed.
_STATION_RE = re.compile(r"^\s*(\d+)\+(\d{2}(?:\.\d+)?)\s*$")

# Explicit reviewed footage field(s), in priority order (used before the station delta when a positive number).
_EXPLICIT_FOOTAGE_KEYS = ("footage_ft", "footage")


def parse_station_ft(value):
    """Parse a survey station like ``'1+00'`` / ``'10+25'`` / ``'0+00'`` to its position in FEET as a
    ``Decimal``, or ``None`` when missing / not a valid ``<stations>+<2-digit-feet>`` station. Pure; never
    raises. Examples: ``'1+00'`` -> 100, ``'3+00'`` -> 300, ``'10+25'`` -> 1025, ``'2+99'`` -> 299."""
    if value is None:
        return None
    m = _STATION_RE.match(str(value))
    if not m:
        return None
    return Decimal(m.group(1)) * 100 + Decimal(m.group(2))


def _clean_ft(d: Decimal) -> Decimal:
    """Integral footage -> a whole number; otherwise 2 dp (ROUND_HALF_UP). Avoids ``200.0`` / ``2E+2`` noise."""
    return (d.quantize(Decimal(1)) if d == d.to_integral_value()
            else d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _row_effective_values(row) -> dict:
    """A reviewed row's effective values: raw <- normalized-candidate <- human ``corrected_values`` (highest)."""
    eff = dict(row.get("raw") or {})
    eff.update(row.get("normalized") or {})
    corrected = (row.get("review") or {}).get("corrected_values")
    if corrected:
        eff.update(corrected)
    return eff


def row_footage(row):
    """Footage (feet) for ONE reviewed row. Returns ``(footage: Decimal|None, source: str, reason: str|None)``.

    Owner-directed rule order: an EXPLICIT reviewed footage value (``footage_ft`` / ``footage``, a positive
    number) is used FIRST; otherwise footage is the station DELTA ``end - start`` when both stations parse and
    ``end > start``. A missing / invalid range returns ``(None, ..., reason)`` so the caller can list the row
    WITHOUT zeroing the valid rows. Pure; never raises."""
    eff = _row_effective_values(row)
    for key in _EXPLICIT_FOOTAGE_KEYS:
        if eff.get(key) is not None:
            try:
                explicit = Decimal(str(eff[key]))
            except (InvalidOperation, ValueError):
                explicit = None
            if explicit is not None and explicit > 0:
                return _clean_ft(explicit), "EXPLICIT_FOOTAGE", None
            break                       # explicit present but not a positive number -> try the station delta
    start, end = parse_station_ft(eff.get("start_station")), parse_station_ft(eff.get("end_station"))
    if start is None or end is None:
        return (None, "STATION_RANGE",
                "no explicit footage and start/end station missing or unparseable "
                "(start=%r end=%r)" % (eff.get("start_station"), eff.get("end_station")))
    delta = end - start
    if delta <= 0:
        return (None, "STATION_RANGE",
                "end station is not past the start (%s -> %s = %s ft)"
                % (eff.get("start_station"), eff.get("end_station"), _clean_ft(delta)))
    return _clean_ft(delta), "STATION_DELTA", None


def reviewed_footage(store_root, customer_project_id, processing_job_id) -> dict:
    """Server-computed footage from the job's CONFIRMED/CORRECTED reviewed bore-log rows (across every
    reviewed_bore_log on the job): explicit reviewed footage first, else the station delta. VALID rows are
    summed; INVALID / missing-range rows are listed SEPARATELY and never zero the valid total. Rows that are
    not human-confirmed (UNREVIEWED / REJECTED / NEEDS_CLARIFICATION) are ignored. Read-only; invents nothing.
    Returns ``{available, total_footage(str|None), valid_rows, invalid_rows}``."""
    total, valid, invalid = Decimal(0), [], []
    for rbl in list_reviewed_bore_logs(store_root, customer_project_id, processing_job_id):
        rbl_id = rbl.get("reviewed_bore_log_id")
        for row in rbl.get("rows", []):
            if not row_review_passes(row):          # only human CONFIRMED / CORRECTED rows are billable
                continue
            ft, source, reason = row_footage(row)
            eff = _row_effective_values(row)
            ref = {"reviewed_bore_log_id": rbl_id, "row_id": row.get("row_id"),
                   "start_station": eff.get("start_station"), "end_station": eff.get("end_station")}
            if ft is None:
                invalid.append({**ref, "reason": reason})
            else:
                total += ft
                valid.append({**ref, "footage": str(ft), "source": source})
    return {"available": bool(valid),
            "total_footage": (str(_clean_ft(total)) if valid else None),
            "valid_rows": valid, "invalid_rows": invalid}


def pricing_view(store_root, customer_project_id, processing_job_id) -> dict:
    """The operator-pricing record + the SERVER footage quantity + computed totals (honest). Dollars appear
    only where the operator entered the rate; the server footage is read-only and never invented.

    Footage priority (owner-directed): the CONFIRMED reviewed bore-log rows' station ranges / explicit
    reviewed footage. ONLY when no confirmed row yields a valid footage does it fall back to the validated
    manifest's drawn length (unchanged behaviour for jobs whose rows carry no station range). Invalid /
    missing-range confirmed rows are surfaced (``footage_unavailable_rows``) and never zero the valid total."""
    record = load_job_pricing(store_root, customer_project_id, processing_job_id)

    rev = reviewed_footage(store_root, customer_project_id, processing_job_id)
    if rev["available"]:
        footage = Decimal(rev["total_footage"])
        footage_available = True
        footage_source = "REVIEWED_BORE_LOG_STATIONS"
        footage_incomplete = bool(rev["invalid_rows"])          # some confirmed rows couldn't be measured
    else:
        foot = job_effective_footage(store_root, customer_project_id, processing_job_id)
        footage = (Decimal(foot["footage"])
                   if foot.get("available") and foot.get("footage") is not None else None)
        footage_available = footage is not None
        footage_source = "DRAWN_MANIFEST" if footage_available else None
        footage_incomplete = bool(foot.get("incomplete"))

    cpf = Decimal(record["cost_per_foot"]) if record.get("cost_per_foot") is not None else None

    base_total = _q(footage * cpf) if (footage is not None and cpf is not None) else None
    exc_sum = Decimal(0)
    for e in record.get("exceptions", []):
        if e.get("amount") is not None:
            exc_sum += Decimal(e["amount"])
    exception_total = _q(exc_sum)
    final_total = _q(Decimal(base_total) + exc_sum) if base_total is not None else None

    # Honest reason when no base/final total can be shown.
    if cpf is None:
        totals_note = "Enter a cost per foot to compute the base and final totals."
    elif footage is None:
        totals_note = ("Footage is not available yet — confirm bore-log rows with a valid station range (or "
                       "an explicit footage), or place + assemble the redline.")
    else:
        totals_note = None

    return {
        "record_format": JOB_PRICING_RECORD_FORMAT,
        "provenance": PROVENANCE_OPERATOR_ENTERED,
        "disclaimer": PRICING_DISCLAIMER,
        "footage_available": footage_available,
        "footage": (str(footage) if footage is not None else None),
        "footage_incomplete": footage_incomplete,
        "footage_source": footage_source,                       # REVIEWED_BORE_LOG_STATIONS | DRAWN_MANIFEST | None
        "footage_rows": rev["valid_rows"],                      # confirmed rows summed (station / explicit)
        "footage_unavailable_rows": rev["invalid_rows"],        # confirmed rows with an invalid / missing range
        "cost_per_foot": record.get("cost_per_foot"),
        "exceptions": record.get("exceptions", []),
        "base_total": base_total,
        "exception_total": exception_total,
        "final_total": final_total,
        "totals_note": totals_note,
        "currency": "USD",
        "updated_at": record.get("updated_at"),
        "updated_by": record.get("updated_by"),
    }
