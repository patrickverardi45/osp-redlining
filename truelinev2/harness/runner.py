"""Provision a fixture into a transient store and run the REAL product redline decision (registry=None).

The sequence mirrors the product proof seed exactly: create the customer project + job, upload each file,
then (if a bore-log is present) stand up the reviewed-bore-log review gate to engine-ready (rows added ->
reviewed CONFIRMED -> one confirmed SEPARATE_BORE group). Finally it calls ``run_product_redline`` with
``registry=None`` so the recognized-corpus shortcut is impossible — the decision reflects the engine's true
cold-package behavior. Returns the decision dict unchanged (the scorer reads it).

Identity ids (tenant/job/rbl) are DERIVED at runtime from the fixture id and passed explicitly — never
defaulted in a signature (the naming-guard invariant).
"""
from __future__ import annotations

import re

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.product_workflow import run_product_redline

# Fixed, deterministic stamps (a harness run is reproducible; not identity, not a real name).
_AT = "2026-01-01T00:00:00Z"
_BY = "cold-package-harness"
_RBL = "rbl-main"
_GROUP = "g-1"
_ID_OK = re.compile(r"[^a-z0-9_-]+")

# A CONFIGURED-but-empty registry: a registry IS wired on this run, the package just isn't in it — the
# realistic cold-package recognition state (yields UPLOADED_CORPUS_NOT_RECOGNIZED, not the operational
# NOT_CONFIGURED gap). It contains ZERO corpora, so Path A (recognized deterministic) can never fire — the
# decision reflects the engine's true cold-package behavior, never a memorized render.
_COLD_REGISTRY = {"corpora": [], "configured": True}


def _ids_for(fixture_id):
    """Derive a valid (tenant, job) id pair from a fixture id (^[a-z0-9][a-z0-9_-]{0,62}$)."""
    slug = _ID_OK.sub("-", fixture_id.lower()).strip("-_") or "fixture"
    tenant = ("cph-" + slug)[:63].rstrip("-_")
    job = ("job-" + slug)[:63].rstrip("-_")
    return tenant, job


def provision_and_run(store_root, fixture, *, at=_AT, by=_BY) -> dict:
    """Provision ``fixture`` into ``store_root`` and return the cold-path redline decision (registry=None)."""
    tenant, job = _ids_for(fixture.fixture_id)
    create_customer_project(store_root, tenant, "Cold-package fixture %s" % fixture.fixture_id, at)
    create_job(store_root, tenant, job, at, by)

    bore_upload_id = None
    for u in fixture.uploads:
        rec = accept_upload(store_root, tenant, job, kind=u.kind, filename=u.filename,
                            content=u.read_bytes(), stored_at=at)
        if u.kind == "BORE_LOG":
            bore_upload_id = rec["upload_id"]

    # Stand up the reviewed-bore-log review gate to engine-ready (the human sign-off the engine requires
    # before it will attempt placement). Without this an abstain would be NO_ENGINE_READY_REVIEWED_BORE_LOG
    # (a gate state) rather than the engine's real geometry verdict.
    if bore_upload_id is not None and fixture.bore_rows:
        create_reviewed_bore_log(store_root, tenant, job, bore_upload_id, _RBL, at=at, by=by)
        rows = [new_extracted_row(r["row_id"], bore_upload_id, raw=r["raw"], normalized=r["normalized"],
                                  extraction_method=MANUAL_ENTRY, at=at, by=by)
                for r in fixture.bore_rows]
        add_extracted_rows(store_root, tenant, job, _RBL, rows, at=at, by=by)
        row_ids = [r["row_id"] for r in fixture.bore_rows]
        for rid in row_ids:
            review_row_in_log(store_root, tenant, job, _RBL, rid, CONFIRMED, at=at, by=by)
        define_segment_group(store_root, tenant, job, _RBL, _GROUP, row_ids, SEPARATE_BORE, at=at, by=by)
        set_grouping_status(store_root, tenant, job, _RBL, _GROUP, GROUPING_CONFIRMED, at=at, by=by)

    # An empty (configured) registry forces Path B (uploaded engine) or Path C (abstain); Path A cannot fire.
    return run_product_redline(store_root, tenant, job, registry=_COLD_REGISTRY, at=at, by=by)
