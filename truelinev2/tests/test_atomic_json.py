"""Phase 4 hardening: atomic JSON writes for the product store.

``write_json_atomic`` serializes to a same-dir temp file, fsyncs, then ``os.replace`` — so an interrupted
write cannot corrupt a system-of-record file, and the output is byte-identical to the previous
``write_text(json.dumps(..., indent=2) + "\\n")`` form. Temp files only.
"""
from __future__ import annotations

import json

import pytest

from truelinev2.contracts.atomic_json import write_json_atomic


def test_writes_expected_json_matching_store_convention(tmp_path):
    p = tmp_path / "sub" / "record.json"
    payload = {"b": 2, "a": 1, "nested": {"x": [1, 2, 3]}}
    out = write_json_atomic(p, payload)
    assert out == p and p.is_file()
    assert p.read_text(encoding="utf-8") == json.dumps(payload, indent=2) + "\n"   # byte-identical
    assert json.loads(p.read_text(encoding="utf-8")) == payload
    assert list(p.parent.glob(".tmp-*")) == []          # no leftover temp files


def test_overwrites_existing_atomically(tmp_path):
    p = tmp_path / "r.json"
    write_json_atomic(p, {"v": 1})
    write_json_atomic(p, {"v": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}
    assert list(tmp_path.glob(".tmp-*")) == []


def test_existing_file_intact_if_serialization_fails(tmp_path):
    p = tmp_path / "r.json"
    write_json_atomic(p, {"ok": 1})
    before = p.read_text(encoding="utf-8")
    with pytest.raises(TypeError):
        write_json_atomic(p, {"bad": {1, 2, 3}})        # a set is not JSON-serializable
    assert p.read_text(encoding="utf-8") == before       # pre-existing record untouched
    assert list(tmp_path.glob(".tmp-*")) == []           # no orphan temp file


def test_creates_parents(tmp_path):
    p = tmp_path / "a" / "b" / "c" / "r.json"
    write_json_atomic(p, {"ok": True})
    assert p.is_file() and json.loads(p.read_text(encoding="utf-8")) == {"ok": True}
