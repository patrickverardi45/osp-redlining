"""Operator-entered job pricing (contract-only) — a per-job, OPERATOR-ENTERED rate table.

DISTINCT from the server-authoritative ``billing_summary`` (versioned, configured cost rules). Here the
operator types a cost-per-foot and exception rows PER JOB; the dollars are the operator's OWN inputs and are
explicitly UNVERIFIED — never a configured rate sheet, never invented. Boundaries (honest billing):

  * NO default / invented rates. ``cost_per_foot`` and every exception ``amount`` start BLANK (None) and
    require operator input; a blank rate yields NO base/final total (not a $0 fabrication).
  * Quantities come from the SERVER, never typed: ``footage`` is the validated manifest's drawn footage via
    ``billing_summary.job_effective_footage`` (a trusted quantity), echoed read-only.
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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from truelinev2.contracts.billing_summary import job_effective_footage
from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id

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


def pricing_view(store_root, customer_project_id, processing_job_id) -> dict:
    """The operator-pricing record + the SERVER footage quantity + computed totals (honest). Dollars appear
    only where the operator entered the rate; the server footage is read-only and never invented."""
    record = load_job_pricing(store_root, customer_project_id, processing_job_id)
    foot = job_effective_footage(store_root, customer_project_id, processing_job_id)
    footage = Decimal(foot["footage"]) if foot.get("available") and foot.get("footage") is not None else None
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
        totals_note = "Footage is not available yet (place + assemble the redline first)."
    else:
        totals_note = None

    return {
        "record_format": JOB_PRICING_RECORD_FORMAT,
        "provenance": PROVENANCE_OPERATOR_ENTERED,
        "disclaimer": PRICING_DISCLAIMER,
        "footage_available": footage is not None,
        "footage": (str(footage) if footage is not None else None),
        "footage_incomplete": bool(foot.get("incomplete")),
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
