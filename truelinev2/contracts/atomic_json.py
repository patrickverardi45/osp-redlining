"""Atomic JSON writes for the product store (Phase 4 hardening).

The product store is a system-of-record of one-JSON-file-per-record; a plain ``write_text`` can leave a
half-written / corrupt file if the process is interrupted mid-write. ``write_json_atomic`` serializes to a
temp file IN THE SAME DIRECTORY (so ``os.replace`` is a same-filesystem atomic rename), fsyncs, then
atomically replaces the target. On failure the temp file is cleaned up and any pre-existing target is left
intact.

Serialization matches the store convention EXACTLY — ``json.dumps(payload, indent=2)`` + a trailing
newline, utf-8 — so migrated writers are byte-identical to the previous ``write_text`` form.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path, payload: Any, *, indent: int = 2) -> Path:
    """Serialize ``payload`` to JSON and write it to ``path`` atomically (temp file + fsync + os.replace).
    Creates parent dirs. If serialization fails, ``path`` is never touched; if the temp write fails, the
    temp file is removed and an existing ``path`` is left intact. Returns the written path.

    Byte-identical to ``path.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize FIRST (before creating a temp file): a serialization error leaves the store untouched.
    text = json.dumps(payload, indent=indent) + "\n"
    # Temp file in the SAME directory so os.replace is an atomic same-filesystem rename (never cross-device).
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=path.suffix or ".json", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)                 # atomic overwrite on POSIX and Windows (same volume)
        return path
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
