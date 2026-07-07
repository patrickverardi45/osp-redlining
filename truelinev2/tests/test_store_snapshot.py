"""Phase 3 hardening: point-in-time snapshot of the served product store.

Unit tests for the snapshot helper (copies the served store, preserves nested files, best-effort on a
missing source, collision-resistant names) plus a wired-route test proving the destructive delete route
snapshots BEFORE deletion (the deleted job is recoverable from the snapshot). Temp dirs only; generic ids.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.processing_job import job_dir
from truelinev2.store import snapshot as snap_mod
from truelinev2.store.snapshot import default_snapshots_root, snapshot_store


def _seed_store(root: Path):
    job = root / "customer_projects" / "cp-aaa" / "processing_jobs" / "job-1" / "uploads"
    job.mkdir(parents=True)
    (root / "customer_projects" / "cp-aaa" / "_customer_project.json").write_text(
        '{"id":"cp-aaa"}', encoding="utf-8")
    (job / "x.bin").write_bytes(b"payload")


# --- helper unit ----------------------------------------------------------------------------------- #
def test_default_snapshots_root_is_sibling_of_store(tmp_path):
    assert default_snapshots_root(tmp_path / "product_store") == tmp_path / "product_store_snapshots"


def test_snapshot_copies_store_with_nested_files(tmp_path):
    store = tmp_path / "product_store"
    _seed_store(store)
    meta = snapshot_store(store, reason="manual", snapshots_root=tmp_path / "snaps")
    assert meta["ok"] is True and meta["error"] is None
    snap = Path(meta["snapshot_path"])
    assert snap.exists() and snap.parent == tmp_path / "snaps"
    copied = snap / "customer_projects" / "cp-aaa" / "processing_jobs" / "job-1" / "uploads" / "x.bin"
    assert copied.read_bytes() == b"payload"          # nested files preserved byte-for-byte
    assert meta["file_count"] == 2                      # _customer_project.json + x.bin
    assert meta["source"] == str(store)


def test_snapshot_names_are_collision_resistant(tmp_path):
    store = tmp_path / "product_store"
    _seed_store(store)
    a = snapshot_store(store, snapshots_root=tmp_path / "snaps")
    b = snapshot_store(store, snapshots_root=tmp_path / "snaps")
    assert a["ok"] and b["ok"] and a["snapshot_path"] != b["snapshot_path"]


def test_snapshot_missing_source_is_reported_not_raised(tmp_path):
    meta = snapshot_store(tmp_path / "nope", snapshots_root=tmp_path / "snaps")
    assert meta["ok"] is False and meta["error"] and meta["snapshot_path"] is None


def test_cli_snapshots_given_store(tmp_path, capsys):
    store = tmp_path / "product_store"
    _seed_store(store)
    rc = snap_mod.main(["--store-root", str(store), "--reason", "cli-test"])
    assert rc == 0
    meta = json.loads(capsys.readouterr().out)
    assert meta["ok"] is True and Path(meta["snapshot_path"]).exists()
    assert Path(meta["snapshot_path"]).parent == store.parent / "product_store_snapshots"


# --- wired into the destructive delete route ------------------------------------------------------- #
def _container(tmp_path, *, destructive):
    s = dataclasses.replace(
        Settings.for_proof(), artifact_root=tmp_path / "a", cards_dir=tmp_path / "c",
        db_path=tmp_path / "db.sqlite", product_pipeline_api_optin=True,
        product_store_root=tmp_path / "product_store", enable_destructive_product_routes=destructive)
    return create_app(s).state.tl2


def test_delete_route_snapshots_before_deletion(tmp_path):
    c = _container(tmp_path, destructive=True)
    ctx = require_context("cp-aaa", "sess-1")
    ppr.create_project(ppr.ProjectCreate(display_name="L"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    out = ppr.delete_processing_job("job-1", ctx=ctx, c=c)
    assert out["deleted"] is True
    snap = out["snapshot"]
    assert snap["ok"] is True and snap["snapshot_path"]
    # the snapshot (taken BEFORE deletion) still contains the now-deleted job -> recoverable
    job_in_snap = (Path(snap["snapshot_path"]) / "customer_projects" / "cp-aaa"
                   / "processing_jobs" / "job-1")
    assert job_in_snap.is_dir()
    # ...and the live store no longer has it
    assert not job_dir(tmp_path / "product_store", "cp-aaa", "job-1").exists()
