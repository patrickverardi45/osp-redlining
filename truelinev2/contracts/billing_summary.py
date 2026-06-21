"""Permanent v2 product foundation — the billing_summary server-computed model (contract-only).

ONE durable, server-authoritative billing summary per processing_job, derived from TRUSTED server-side
product state — never from client flags, UI booleans, old v1 billing state, or raw uploads. The v1 monolith
computed billing in the client (`footage × rate + exceptions` as React props; `billing.py` a placeholder —
salvage audit 5a) with no authoritative backend record. v2 fixes this: totals are computed server-side from
injected, VERSIONED cost rules over trusted inputs, and persisted as auditable, reproducible calculation
revisions.

Billing is NOT a parallel approval (contract docs/product_v2_permanent_pipeline_contract.md §6): billability
is DERIVED FROM closeout, so it can never disagree with it. There is NO "approve billing" action — the UI
cannot approve billing. A summary becomes FINAL (billable/ready) only when closeout_review is APPROVED and
no billing hard blocker exists; while closeout is not approved / missing / blocked it stays COMPUTED (a
finalization blocker), and a hard input problem makes it BLOCKED.

Trusted inputs only:
  * effective_footage = sum of `closure.drawn_ft` over DRAWN logs of the VALIDATED, sha256-verified durable
    manifest (manifest/bundle contribute only after a validated manifest handoff).
  * reviewed_bore_log freshness via the manifest handoff chain (catches a row re-reviewed after handoff).
  * itemized inputs must carry TRUSTED provenance (REVIEWED_INPUT / MANIFEST_DERIVED); a raw/unreviewed item
    raises — raw uploads can inform itemization only after passing a trust gate.
  * cost rules are injected at runtime as a VERSIONED set (no rates are ever baked into this module); each
    charge amount = quantity × the rule's unit_cost (the client never supplies a dollar amount).

Money is `Decimal` (stdlib), serialized as canonical strings, quantized ROUND_HALF_UP to the rule set's
minor units — deterministic + reproducible (identical inputs + rule version ⇒ identical totals + inputs_hash).
Recalculation appends a new audited revision when (inputs_hash, cost_rule_version) changes (the prior is
marked superseded, retained); an unchanged recompute is an idempotent revalidate that only refreshes the
live status from closeout. Contract-only: no engine execution, renderer, web/backend, AI/OCR, KMZ/KML,
export_package producer, invoicing/payment/tax, or deploy. This lane reads closeout_review but never mutates
it, and never drives the job lifecycle.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import (
    CLOSED as JOB_CLOSED,
    CLOSEOUT_REVIEW as JOB_CLOSEOUT_REVIEW,
    PLACED as JOB_PLACED,
    job_dir,
    load_job,
    validate_job_id,
)
from truelinev2.contracts.published_bundle import MANIFEST_FILENAME, load_manifest, sha256_file
from truelinev2.contracts.published_bundle_store import BUNDLES_SUBDIR
from truelinev2.contracts.manifest_handoff import (
    BUNDLE_STORE_SUBDIR,
    VALIDATION_VALIDATED,
    ManifestHandoffError,
    load_handoff,
)
from truelinev2.contracts.reviewed_bore_log import (
    ReviewedBoreLogError,
    is_engine_ready,
    load_reviewed_bore_log,
)
from truelinev2.contracts.closeout_review import (
    APPROVED as CLOSEOUT_APPROVED,
    OPEN_ENGINE_BLOCKERS as CLOSEOUT_OPEN_ENGINE_BLOCKERS,
    CloseoutNotFoundError,
    load_closeout_review,
)

BILLING_SUMMARY_RECORD_FORMAT = "trueline-billing-summary-1"
BILLING_SUMMARY_FILENAME = "_billing_summary.json"   # ONE record per job (singleton)

# Server-authoritative billing status (record level). SUPERSEDED lives only on a revision, never here.
DRAFT = "DRAFT"
COMPUTED = "COMPUTED"
BLOCKED = "BLOCKED"
FINAL = "FINAL"
BILLING_STATUSES = (DRAFT, COMPUTED, BLOCKED, FINAL)

# A job is billable only once it has (or had) a placed redline output (same range as closeout).
BILLING_ELIGIBLE_JOB_STATES = (JOB_PLACED, JOB_CLOSEOUT_REVIEW, JOB_CLOSED)

# Charge-line kinds. BASE is reserved for manifest-derived footage; itemized inputs use EXCEPTION/ADJUSTMENT.
BASE = "BASE"
EXCEPTION = "EXCEPTION"
ADJUSTMENT = "ADJUSTMENT"
CHARGE_KINDS = (BASE, EXCEPTION, ADJUSTMENT)

# Trusted itemization provenance (a raw/unreviewed item is rejected).
REVIEWED_INPUT = "REVIEWED_INPUT"
MANIFEST_DERIVED = "MANIFEST_DERIVED"
TRUSTED_ITEMIZATION_SOURCES = (REVIEWED_INPUT, MANIFEST_DERIVED)

# HARD blocker codes (any present => BLOCKED; never FINAL).
JOB_NOT_IN_BILLING_RANGE = "JOB_NOT_IN_BILLING_RANGE"
MISSING_MANIFEST = "MISSING_MANIFEST"
MISSING_ARTIFACT_BUNDLE = "MISSING_ARTIFACT_BUNDLE"
UNTRUSTED_OUTPUT = "UNTRUSTED_OUTPUT"
MANIFEST_NOT_RESOLVABLE = "MANIFEST_NOT_RESOLVABLE"
REVIEWED_BORE_LOG_NOT_READY = "REVIEWED_BORE_LOG_NOT_READY"
HARD_BLOCKER_CODES = (JOB_NOT_IN_BILLING_RANGE, MISSING_MANIFEST, MISSING_ARTIFACT_BUNDLE,
                      UNTRUSTED_OUTPUT, MANIFEST_NOT_RESOLVABLE, REVIEWED_BORE_LOG_NOT_READY)

# FINALIZATION blocker codes (allow COMPUTED, prevent FINAL — closeout owns billability).
CLOSEOUT_NOT_APPROVED = "CLOSEOUT_NOT_APPROVED"
CLOSEOUT_REVIEW_MISSING = "CLOSEOUT_REVIEW_MISSING"
FINALIZATION_BLOCKER_CODES = (CLOSEOUT_NOT_APPROVED, CLOSEOUT_REVIEW_MISSING)

# WARNING codes (recorded; never block). OPEN_ENGINE_BLOCKERS is visibility-only here — closeout owns it as
# a HARD blocker, and FINAL already requires closeout APPROVED, so billing never downgrades it.
OPEN_ENGINE_BLOCKERS = "OPEN_ENGINE_BLOCKERS"
ZERO_BILLABLE_TOTAL = "ZERO_BILLABLE_TOTAL"
EXCEPTION_WITHOUT_NOTE = "EXCEPTION_WITHOUT_NOTE"
MANIFEST_FOOTAGE_INCOMPLETE = "MANIFEST_FOOTAGE_INCOMPLETE"
REVIEWED_BORE_LOG_NOT_RESOLVABLE = "REVIEWED_BORE_LOG_NOT_RESOLVABLE"
WARNING_CODES = (OPEN_ENGINE_BLOCKERS, ZERO_BILLABLE_TOTAL, EXCEPTION_WITHOUT_NOTE,
                 MANIFEST_FOOTAGE_INCOMPLETE, REVIEWED_BORE_LOG_NOT_RESOLVABLE)


class BillingSummaryError(ValueError):
    """Base billing_summary error."""


class BillingSummaryNotFoundError(BillingSummaryError):
    """No stored billing_summary for the requested job."""


class InvalidCostRuleSetError(BillingSummaryError):
    """The injected cost rule set is missing or malformed (a caller/config error, not a state)."""


class UntrustedItemizationError(BillingSummaryError):
    """An itemized input did not carry trusted provenance (raw uploads can't become billing truth)."""


# --------------------------------------------------------------------------- #
# Money helpers — Decimal only; canonical string serialization; deterministic rounding.
# --------------------------------------------------------------------------- #
def _to_decimal(value, what) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise InvalidCostRuleSetError("%s is not a valid decimal: %r" % (what, value))


def _money(amount: Decimal, digits: int) -> str:
    """Quantize to `digits` minor units, ROUND_HALF_UP, return a canonical string."""
    return str(amount.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------- #
# Cost-rule set + itemization validation (raise on caller/config errors).
# --------------------------------------------------------------------------- #
def _validate_cost_rule_set(cost_rule_set):
    """Return (version, currency, digits, rules_by_code, base_code). Raise InvalidCostRuleSetError on any
    structural problem (no rates are baked here — the set is injected runtime data)."""
    if not isinstance(cost_rule_set, dict):
        raise InvalidCostRuleSetError("cost_rule_set must be a dict")
    version = cost_rule_set.get("version")
    if not isinstance(version, str) or not version:
        raise InvalidCostRuleSetError("cost_rule_set.version is required (non-empty string)")
    currency = cost_rule_set.get("currency")
    if not isinstance(currency, str) or not currency:
        raise InvalidCostRuleSetError("cost_rule_set.currency is required (non-empty string)")
    digits = cost_rule_set.get("minor_unit_digits", 2)
    if not isinstance(digits, int) or isinstance(digits, bool) or digits < 0 or digits > 6:
        raise InvalidCostRuleSetError("cost_rule_set.minor_unit_digits must be an int in [0, 6]")
    rules = cost_rule_set.get("rules")
    if not isinstance(rules, list) or not rules:
        raise InvalidCostRuleSetError("cost_rule_set.rules must be a non-empty list")
    by_code, base_codes = {}, []
    for r in rules:
        if not isinstance(r, dict):
            raise InvalidCostRuleSetError("each cost rule must be a dict (got %r)" % (r,))
        code, kind = r.get("code"), r.get("kind")
        if not isinstance(code, str) or not code:
            raise InvalidCostRuleSetError("a cost rule is missing a non-empty code")
        if code in by_code:
            raise InvalidCostRuleSetError("duplicate cost rule code %r" % (code,))
        if kind not in CHARGE_KINDS:
            raise InvalidCostRuleSetError("cost rule %r kind %r not in %r" % (code, kind, CHARGE_KINDS))
        _to_decimal(r.get("unit_cost"), "cost rule %r unit_cost" % code)   # parse-check
        by_code[code] = r
        if kind == BASE:
            base_codes.append(code)
    if len(base_codes) > 1:
        raise InvalidCostRuleSetError("cost_rule_set has >1 BASE rule %r (expected at most one)" % base_codes)
    return version, currency, digits, by_code, (base_codes[0] if base_codes else None)


def _validate_itemized_inputs(itemized_inputs, by_code):
    """Return the validated itemized inputs. Raise UntrustedItemizationError for untrusted provenance, and
    InvalidCostRuleSetError if an input references an unknown / BASE rule code (base is manifest-derived)."""
    out = []
    for i, it in enumerate(itemized_inputs or ()):
        if not isinstance(it, dict):
            raise UntrustedItemizationError("itemized input %d must be a dict" % i)
        if it.get("source") not in TRUSTED_ITEMIZATION_SOURCES:
            raise UntrustedItemizationError(
                "itemized input %d source %r is not trusted (allowed: %r)"
                % (i, it.get("source"), TRUSTED_ITEMIZATION_SOURCES))
        rule_code = it.get("rule_code")
        if rule_code not in by_code:
            raise InvalidCostRuleSetError("itemized input %d references unknown rule_code %r" % (i, rule_code))
        if by_code[rule_code]["kind"] == BASE:
            raise InvalidCostRuleSetError(
                "itemized input %d references BASE rule %r (base is manifest-derived, not itemized)"
                % (i, rule_code))
        _to_decimal(it.get("quantity"), "itemized input %d quantity" % i)   # parse-check
        out.append(it)
    return out


def _canonical_rules(cost_rule_set) -> dict:
    norm = [{k: (str(r.get(k)) if k == "unit_cost" else r.get(k))
             for k in ("code", "kind", "unit", "unit_cost", "label", "applies_to")}
            for r in (cost_rule_set.get("rules") or [])]
    return {"version": cost_rule_set.get("version"), "currency": cost_rule_set.get("currency"),
            "minor_unit_digits": cost_rule_set.get("minor_unit_digits", 2),
            "rules": sorted(norm, key=lambda d: str(d.get("code")))}


def _inputs_hash(inputs, version, cost_rule_set) -> str:
    payload = {
        "effective_footage": inputs["effective_footage"],
        "source_manifest_id": inputs["source_manifest_id"],
        "source_artifact_bundle_id": inputs["source_artifact_bundle_id"],
        "itemized": sorted(
            [{k: it.get(k) for k in ("rule_code", "quantity", "source", "note", "ref")}
             for it in inputs["itemized"]],
            key=lambda d: (str(d.get("rule_code")), str(d.get("ref")),
                           str(d.get("quantity")), str(d.get("note")))),
        "cost_rule_version": version,
        "cost_rule_set": _canonical_rules(cost_rule_set),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Storage (singleton per job).
# --------------------------------------------------------------------------- #
def billing_summary_path(store_root, customer_project_id, processing_job_id) -> Path:
    return job_dir(store_root, customer_project_id, processing_job_id) / BILLING_SUMMARY_FILENAME


def create_billing_summary(store_root, customer_project_id, processing_job_id, *, at, by) -> dict:
    """Create the ONE billing_summary for a job (status DRAFT, no revision yet). Verifies the job exists and
    is in-scope. Raises on a duplicate (no silent overwrite). Returns the record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    load_job(store_root, customer_project_id, processing_job_id)          # exists + isolation
    path = billing_summary_path(store_root, customer_project_id, processing_job_id)
    if path.exists():
        raise BillingSummaryError(
            "billing_summary already exists for %s/%s" % (customer_project_id, processing_job_id))
    record = {
        "record_format": BILLING_SUMMARY_RECORD_FORMAT,
        "customer_project_id": customer_project_id,
        "processing_job_id": processing_job_id,
        "status": DRAFT,
        "currency": None,
        "gate": None,
        "current_revision_id": None,
        "revisions": [],
        "audit": [{"action": "billing_summary_created", "from": None, "to": DRAFT,
                   "at": at, "by": by, "reason": None}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def load_billing_summary(store_root, customer_project_id, processing_job_id) -> dict:
    path = billing_summary_path(store_root, customer_project_id, processing_job_id)
    if not path.is_file():
        raise BillingSummaryNotFoundError(
            "no billing_summary for %s/%s" % (customer_project_id, processing_job_id))
    record = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, record.get("customer_project_id"))
    return record


def write_billing_summary(store_root, record) -> str:
    """Persist a record under its OWN (cp, job) scope (derived from the record, not ambient)."""
    cp = validate_customer_project_id(record["customer_project_id"])
    jid = validate_job_id(record["processing_job_id"])
    path = billing_summary_path(store_root, cp, jid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- #
# Trusted-state resolution + gate.
# --------------------------------------------------------------------------- #
def _effective_footage(manifest):
    """Sum closure.drawn_ft over DRAWN logs. Returns (Decimal total, incomplete?)."""
    total, incomplete = Decimal(0), False
    for lg in manifest.get("logs", []):
        if not lg.get("drawn"):
            continue
        closure = lg.get("closure")
        ft = closure.get("drawn_ft") if isinstance(closure, dict) else None
        if ft is None:
            incomplete = True
            continue
        try:
            total += Decimal(str(ft))
        except (InvalidOperation, ValueError, TypeError):
            incomplete = True
    return total, incomplete


def _resolve_manifest(store_root, cp, job_id, job, hard, checks):
    """Resolve the VALIDATED, sha256-verified durable manifest from the trusted output slots. Appends hard
    blockers/checks; returns (manifest|None, source_manifest_id, source_bundle_id, m_ref)."""
    slots = job.get("slots") or {}
    m_slot, b_slot = slots.get("redline_manifest"), slots.get("artifact_bundle")
    m_ref = (m_slot or {}).get("ref") or {}
    b_ref = (b_slot or {}).get("ref") or {}
    checks.append({"name": "redline_manifest_slot_present", "passed": bool(m_slot), "detail": ""})
    if not m_slot:
        hard.append({"code": MISSING_MANIFEST, "reason": "job has no redline_manifest output slot"})
    checks.append({"name": "artifact_bundle_slot_present", "passed": bool(b_slot), "detail": ""})
    if not b_slot:
        hard.append({"code": MISSING_ARTIFACT_BUNDLE, "reason": "job has no artifact_bundle output slot"})
    if not (m_slot and b_slot):
        return None, m_ref.get("manifest_id"), b_ref.get("bundle_id"), m_ref
    trusted = (m_ref.get("validation_status") == VALIDATION_VALIDATED
               and b_ref.get("validation_status") == VALIDATION_VALIDATED)
    checks.append({"name": "output_slots_validated", "passed": trusted, "detail": ""})
    if not trusted:
        hard.append({"code": UNTRUSTED_OUTPUT, "reason": "an output slot is not %s" % VALIDATION_VALIDATED})
        return None, m_ref.get("manifest_id"), b_ref.get("bundle_id"), m_ref
    bundle_id = b_ref.get("bundle_id")
    bundle_root = (job_dir(store_root, cp, job_id) / BUNDLE_STORE_SUBDIR / BUNDLES_SUBDIR / str(bundle_id))
    mpath = bundle_root / MANIFEST_FILENAME
    resolvable = mpath.is_file() and sha256_file(mpath) == m_ref.get("manifest_sha256")
    checks.append({"name": "stored_manifest_resolvable", "passed": resolvable, "detail": str(bundle_id)})
    if not resolvable:
        hard.append({"code": MANIFEST_NOT_RESOLVABLE,
                     "reason": "stored manifest missing or sha256 mismatch for bundle %r" % bundle_id})
        return None, m_ref.get("manifest_id"), bundle_id, m_ref
    return load_manifest(bundle_root), m_ref.get("manifest_id"), bundle_id, m_ref


def _compute_gate(store_root, cp, job_id):
    """Resolve trusted state. Returns (gate, manifest, effective_footage Decimal, source_manifest_id,
    source_bundle_id, footage_incomplete)."""
    hard, finalization, warnings, checks = [], [], [], []
    job = load_job(store_root, cp, job_id)
    in_range = job["status"] in BILLING_ELIGIBLE_JOB_STATES
    checks.append({"name": "job_in_billing_range", "passed": in_range, "detail": job["status"]})
    if not in_range:
        hard.append({"code": JOB_NOT_IN_BILLING_RANGE,
                     "reason": "job status %r not in %r" % (job["status"], BILLING_ELIGIBLE_JOB_STATES)})

    manifest, source_manifest_id, source_bundle_id, m_ref = _resolve_manifest(
        store_root, cp, job_id, job, hard, checks)

    # reviewed_bore_log freshness via the manifest handoff chain (catches post-handoff regressions).
    rbl = None
    engine_run_id = m_ref.get("source_engine_run_id")
    if engine_run_id:
        try:
            handoff = load_handoff(store_root, cp, job_id, engine_run_id)
            rbl = load_reviewed_bore_log(store_root, cp, job_id, handoff.get("reviewed_bore_log_id"))
        except (ManifestHandoffError, ReviewedBoreLogError):
            rbl = None
    if rbl is None:
        if manifest is not None:
            warnings.append({"code": REVIEWED_BORE_LOG_NOT_RESOLVABLE,
                             "reason": "could not resolve the reviewed_bore_log via the handoff chain"})
    else:
        ready = is_engine_ready(rbl)
        checks.append({"name": "reviewed_bore_log_engine_ready", "passed": ready, "detail": ""})
        if not ready:
            hard.append({"code": REVIEWED_BORE_LOG_NOT_READY,
                         "reason": "reviewed_bore_log %r is not engine-ready"
                                   % rbl.get("reviewed_bore_log_id")})

    # Closeout influence (finalization only — billing never approves itself).
    try:
        co = load_closeout_review(store_root, cp, job_id)
        closeout_status = co["status"]
        if closeout_status != CLOSEOUT_APPROVED:
            finalization.append({"code": CLOSEOUT_NOT_APPROVED,
                                 "reason": "closeout_review status is %r (FINAL requires APPROVED)"
                                           % closeout_status})
        co_gate = co.get("gate") or {}
        if any(b.get("code") == CLOSEOUT_OPEN_ENGINE_BLOCKERS for b in co_gate.get("hard_blockers", [])):
            warnings.append({"code": OPEN_ENGINE_BLOCKERS,
                             "reason": "closeout_review reports open engine/redline blockers (closeout-owned)"})
    except CloseoutNotFoundError:
        closeout_status = None
        finalization.append({"code": CLOSEOUT_REVIEW_MISSING,
                             "reason": "no closeout_review exists for this job"})

    footage, footage_incomplete = (Decimal(0), False)
    if manifest is not None:
        footage, footage_incomplete = _effective_footage(manifest)
        if footage_incomplete:
            warnings.append({"code": MANIFEST_FOOTAGE_INCOMPLETE,
                             "reason": "one or more drawn logs lack closure.drawn_ft"})

    gate = {"hard_blockers": hard, "finalization_blockers": finalization, "warnings": warnings,
            "checks": checks, "closeout_status": closeout_status}
    return gate, manifest, footage, source_manifest_id, source_bundle_id, footage_incomplete


def _build_charge_lines(footage, items, by_code, base_code, digits, warnings):
    """Deterministic charge lines: a manifest-derived BASE line (if a BASE rule exists) + one line per
    trusted itemized input. Each amount = quantity × the rule's unit_cost (clients never supply amounts)."""
    lines = []
    if base_code is not None:
        rule = by_code[base_code]
        unit_cost = _to_decimal(rule["unit_cost"], "BASE unit_cost")
        lines.append({"code": base_code, "label": rule.get("label", base_code), "kind": BASE,
                      "quantity": str(footage), "unit": rule.get("unit"), "unit_cost": str(unit_cost),
                      "amount": _money(footage * unit_cost, digits), "rule_ref": base_code,
                      "source": MANIFEST_DERIVED, "note": None})
    for it in items:
        rule = by_code[it["rule_code"]]
        qty = _to_decimal(it.get("quantity"), "itemized quantity")
        unit_cost = _to_decimal(rule["unit_cost"], "rule %r unit_cost" % it["rule_code"])
        note = it.get("note")
        if rule["kind"] == EXCEPTION and not note:
            warnings.append({"code": EXCEPTION_WITHOUT_NOTE,
                             "reason": "exception line %r has no note" % it["rule_code"]})
        lines.append({"code": it["rule_code"], "label": rule.get("label", it["rule_code"]),
                      "kind": rule["kind"], "quantity": str(qty), "unit": rule.get("unit"),
                      "unit_cost": str(unit_cost), "amount": _money(qty * unit_cost, digits),
                      "rule_ref": it["rule_code"], "source": it["source"], "note": note})
    return lines


def _totals(charge_lines, digits) -> dict:
    def s(kind):
        return sum((Decimal(cl["amount"]) for cl in charge_lines if cl["kind"] == kind), Decimal(0))
    base, exc, adj = s(BASE), s(EXCEPTION), s(ADJUSTMENT)
    return {"base_total": _money(base, digits), "exception_total": _money(exc, digits),
            "adjustment_total": _money(adj, digits), "final_total": _money(base + exc + adj, digits)}


def _current_revision(record):
    rid = record.get("current_revision_id")
    return next((r for r in record["revisions"] if r["revision_id"] == rid), None) if rid else None


def _derive_status(has_hard, has_finalization, has_revision) -> str:
    if not has_revision:
        return DRAFT
    if has_hard:
        return BLOCKED
    if has_finalization:
        return COMPUTED
    return FINAL


# --------------------------------------------------------------------------- #
# Compute — the only mutating operation (no human approval; billability follows closeout).
# --------------------------------------------------------------------------- #
def compute_billing_summary(store_root, customer_project_id, processing_job_id, *,
                            cost_rule_set, itemized_inputs=(), at, by) -> dict:
    """Recompute the billing summary from trusted server-side state + injected versioned cost rules.

    Appends a new audited calculation revision when (inputs_hash, cost_rule_version) changes (the prior is
    marked superseded, retained); otherwise revalidates idempotently (refreshes the live gate + status from
    closeout without a new revision). Derives the server-authoritative status (DRAFT/COMPUTED/BLOCKED/FINAL);
    FINAL requires closeout APPROVED and zero hard blockers. Raises InvalidCostRuleSetError /
    UntrustedItemizationError on caller/config errors. Returns the updated record."""
    version, currency, digits, by_code, base_code = _validate_cost_rule_set(cost_rule_set)
    items = _validate_itemized_inputs(itemized_inputs, by_code)
    record = load_billing_summary(store_root, customer_project_id, processing_job_id)

    gate, manifest, footage, source_manifest_id, source_bundle_id, _incomplete = _compute_gate(
        store_root, customer_project_id, processing_job_id)
    has_hard = bool(gate["hard_blockers"])

    # No trustworthy calculation while hard-blocked: record zeroed totals, never partial billing numbers.
    charge_lines = ([] if has_hard
                    else _build_charge_lines(footage, items, by_code, base_code, digits, gate["warnings"]))
    totals = _totals(charge_lines, digits)
    if not has_hard and Decimal(totals["final_total"]) == 0:
        gate["warnings"].append({"code": ZERO_BILLABLE_TOTAL, "reason": "final_total is zero"})

    inputs = {"effective_footage": str(footage if not has_hard else Decimal(0)),
              "source_manifest_id": source_manifest_id, "source_artifact_bundle_id": source_bundle_id,
              "itemized": items}
    inputs_hash = _inputs_hash(inputs, version, cost_rule_set)

    cur = _current_revision(record)
    if cur is not None and cur["inputs_hash"] == inputs_hash and cur["cost_rule_version"] == version:
        action = "revalidated"                                  # same calculation; only live state refreshed
    else:
        if cur is not None:
            cur["superseded_at"] = at
        rev_id = "rev-%d" % (len(record["revisions"]) + 1)
        record["revisions"].append({
            "revision_id": rev_id, "cost_rule_version": version, "currency": currency,
            "inputs": inputs, "charge_lines": charge_lines, "totals": totals,
            "inputs_hash": inputs_hash, "gate_at_creation": gate,
            "computed_at": at, "computed_by": by, "superseded_at": None})
        record["current_revision_id"] = rev_id
        action = "computed"

    record["currency"] = currency
    record["gate"] = gate                                       # record-level LIVE gate (drives status)
    new_status = _derive_status(has_hard, bool(gate["finalization_blockers"]), has_revision=True)
    frm = record["status"]
    record["audit"].append({
        "action": action, "from": frm, "to": new_status, "at": at, "by": by,
        "reason": "%d hard / %d finalization / %d warning"
                  % (len(gate["hard_blockers"]), len(gate["finalization_blockers"]),
                     len(gate["warnings"]))})
    record["status"] = new_status
    write_billing_summary(store_root, record)
    return record


# --------------------------------------------------------------------------- #
# Pure read-only view (no IO, no mutation) — the single value billing UI should render.
# --------------------------------------------------------------------------- #
def billing_summary_view(record) -> dict:
    """Derived, side-effect-free summary of a billing_summary record (re-runnable)."""
    gate = record.get("gate") or {}
    hard = gate.get("hard_blockers", []) or []
    final = gate.get("finalization_blockers", []) or []
    warn = gate.get("warnings", []) or []
    cur = _current_revision(record)
    status = record["status"]
    return {
        "status": status,
        "currency": record.get("currency"),
        "current_revision_id": record.get("current_revision_id"),
        "revision_count": len(record.get("revisions", [])),
        "final_total": (cur["totals"]["final_total"] if cur else None),
        "totals": (cur["totals"] if cur else None),
        "hard_blocker_codes": sorted({b["code"] for b in hard}),
        "finalization_blocker_codes": sorted({b["code"] for b in final}),
        "warning_codes": sorted({w["code"] for w in warn}),
        "is_blocked": status == BLOCKED,
        "is_final": status == FINAL,
        "is_billable": status == FINAL,
    }
