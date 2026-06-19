"""Phase-2C registry integrity test (static; no render, no engine import).

Locks: the canonical render registry covers EXACTLY the 13 ALREADY_DRAWN logs (cross-checked
against the committed manifest's drawn_lane truth), includes log50, maps each log to exactly
one entrypoint with a known render status, and every entrypoint resolves to an existing proof
module file. It runs no renders and imports no engine module (the registry module's top-level
imports are stdlib only; proof modules load lazily only when rendering).
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.proof.run_already_drawn13_canonical_render_registry import (
    REGISTRY,
    _module_file,
)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
EXAMPLE = CONTRACTS / "examples" / "brenham_50_of_58_redline_manifest.example.json"
ALREADY_DRAWN = {
    lg["log_id"]
    for lg in json.loads(EXAMPLE.read_text(encoding="utf-8"))["logs"]
    if lg.get("drawn_lane") == "ALREADY_DRAWN"
}


def test_registry_covers_exactly_the_13_already_drawn():
    assert len(REGISTRY) == 13
    assert set(REGISTRY) == ALREADY_DRAWN


def test_log50_explicitly_included():
    assert "log50" in REGISTRY  # Phase 2B found it standalone, not in the old diagnostic registry


def test_one_entrypoint_per_log_with_known_status():
    for log, (module, status, note) in REGISTRY.items():
        assert isinstance(module, str) and module.startswith("truelinev2.proof."), log
        assert status in ("FULL", "PARTIAL"), log
        assert note.strip(), log


def test_every_entrypoint_module_file_exists():
    for log, (module, _status, _note) in REGISTRY.items():
        assert _module_file(module).is_file(), "%s -> %s" % (log, module)


def test_entrypoints_are_distinct_per_log():
    modules = [m for (m, _s, _n) in REGISTRY.values()]
    assert len(set(modules)) == len(modules)  # one canonical path each, no shared collection
