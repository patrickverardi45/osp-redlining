"""Point-in-time SNAPSHOT of the served product store (Phase 3 hardening).

A local, gitignored safety copy so an accidental destructive operation cannot cause irreversible loss.
NOT cloud backup, NOT a scheduler, NOT a migration — a small callable + CLI that copies the ENTIRE served
store root into a timestamped, collision-resistant snapshot directory. The snapshot targets the SERVED
store root (passed in / resolved from TL2_PRODUCT_STORE_ROOT), never a stale default.

Best-effort at a call site: ``snapshot_store`` never raises for the common cases (missing source / copy
error) — it returns ``ok=False`` + ``error`` so a caller can log-and-continue. The CLI reports failure via
a non-zero exit code.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SNAPSHOTS_DIRNAME = "product_store_snapshots"


def default_snapshots_root(store_root) -> Path:
    """Sibling of the served store root, under the same gitignored data tree:
    ``<store_root>/../product_store_snapshots/``."""
    return Path(store_root).parent / SNAPSHOTS_DIRNAME


def _snapshot_name(reason: str, when: datetime) -> str:
    """timestamp + sanitized reason + short random -> unique even for repeated same-second runs."""
    stamp = when.strftime("%Y%m%dT%H%M%S")
    tag = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in (reason or "snapshot"))[:40]
    return f"{stamp}-{tag}-{uuid.uuid4().hex[:8]}"


def snapshot_store(store_root, *, reason: str = "manual",
                   snapshots_root: Optional[Path] = None, when: Optional[datetime] = None) -> dict:
    """Copy the ENTIRE served ``store_root`` into a fresh timestamped snapshot dir.

    Returns a metadata dict: ``{ok, source, snapshot_path, reason, at, file_count, error}``. Never raises
    for missing source / copy failure -> ``ok=False`` + ``error`` (best-effort; the caller decides)."""
    src = Path(store_root)
    when = when or datetime.now(timezone.utc)
    root = Path(snapshots_root) if snapshots_root is not None else default_snapshots_root(src)
    meta = {"ok": False, "source": str(src), "snapshot_path": None, "reason": reason,
            "at": when.isoformat(), "file_count": 0, "error": None}
    if not src.is_dir():
        meta["error"] = "source store root does not exist"
        return meta
    dest = root / _snapshot_name(reason, when)
    try:
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)                 # dest must not pre-exist; the uuid suffix guarantees it
        meta["snapshot_path"] = str(dest)
        meta["file_count"] = sum(1 for p in dest.rglob("*") if p.is_file())
        meta["ok"] = True
    except Exception as exc:                        # best-effort: report, don't raise
        meta["error"] = "%s: %s" % (type(exc).__name__, exc)
    return meta


def main(argv=None) -> int:
    """CLI: snapshot the served product store on demand. Resolves the SERVED root from
    TL2_PRODUCT_STORE_ROOT (via Settings) unless --store-root overrides. Prints the metadata JSON."""
    import argparse
    import json

    from truelinev2.config import Settings

    parser = argparse.ArgumentParser(description="Snapshot the served product store (local, gitignored).")
    parser.add_argument("--reason", default="manual", help="short label recorded in the snapshot name")
    parser.add_argument("--store-root", default=None,
                        help="override the served store root (default = TL2_PRODUCT_STORE_ROOT)")
    args = parser.parse_args(argv)
    store_root = Path(args.store_root) if args.store_root else Settings.from_env().product_store_root
    meta = snapshot_store(store_root, reason=args.reason)
    print(json.dumps(meta, indent=2))
    return 0 if meta["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
