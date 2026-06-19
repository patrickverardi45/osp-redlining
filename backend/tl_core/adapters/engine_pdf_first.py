"""Reuse-by-import adapter for the proven PDF-first engine.

Imports the vendored, decoupled ``redline_pdf_first`` package (verified free of
``STATE`` / ``main`` / ``_session_scope`` / FastAPI coupling — Stream-2) lazily
and import-isolated, exactly like the reference shim ``app/core/pdf_first_adapter.py``:
the engine root is placed on ``sys.path`` so the package's internal absolute
imports (``from redline_pdf_first.pdf import ...``) resolve. Importing THIS module
never imports ``fitz`` and never imports ``main``. Nothing raises into the caller.

It translates the engine's frozen :class:`EngineResult` contract into tl_core
domain types and carries the absolute render PNG paths on each ref's
``source_path`` so the service can ingest them into the tenant-scoped store.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..domain.redline import ArtifactRef, Placement, RedlineResult

# Tier -> surface mapping mirrors the engine contract + reference adapter.
_SURFACE_BY_TIER: Dict[str, str] = {
    "AUTO_SELECT": "placement",
    "AUTO_PLACED_REQUIRES_APPROVAL": "review",
    "SHARED_SEGMENT_REVIEW": "review",
    "MULTI_LOG_SEGMENT_REVIEW": "review",
    "CONTINUATION_REVIEW": "review",
    "FAIL_SAFE": "fail_safe",
}


class PdfFirstEngine:
    """:class:`RedlineEnginePort` implementation backed by the reused package."""

    def __init__(self, engine_root: Path, sheet_offset: int = 13,
                 render_crops: bool = True, out_dir: Optional[Path] = None):
        self._engine_root = str(Path(engine_root))
        self._sheet_offset = sheet_offset
        self._render_crops = render_crops
        self._out_dir = str(out_dir) if out_dir else None
        self._eng: Any = None
        self._err: Optional[str] = None

    # -- lazy, import-isolated engine load (never raises) ---------------------
    def _load(self) -> Tuple[Any, Optional[str]]:
        if self._eng is not None or self._err is not None:
            return self._eng, self._err
        try:
            if self._engine_root and self._engine_root not in sys.path:
                sys.path.insert(0, self._engine_root)
            import redline_pdf_first as eng  # decoupled; lazy keeps fitz out of import
            self._eng = eng
        except Exception as exc:  # missing/broken engine must not crash the caller
            self._err = f"{type(exc).__name__}: {exc}"
        return self._eng, self._err

    def available(self) -> bool:
        eng, _ = self._load()
        return eng is not None

    def run(self, bore_log_path: str, plan_pdf_path: str) -> RedlineResult:
        eng, err = self._load()
        if eng is None:
            return RedlineResult(job_id="", status="ERROR",
                                 source_file=os.path.basename(bore_log_path),
                                 warnings=[f"engine unavailable: {err}"])
        try:
            result = eng.select_redline(bore_log_path, plan_pdf_path,
                                        sheet_offset=self._sheet_offset)
            if self._render_crops:
                from redline_pdf_first.render import crop_renderer
                out_dir = self._out_dir or os.path.join(
                    os.path.dirname(os.path.abspath(plan_pdf_path)), "_tl_core_cards")
                os.makedirs(out_dir, exist_ok=True)
                crop_renderer.render_and_attach(result, plan_pdf_path,
                                                out_dir=out_dir,
                                                sheet_offset=self._sheet_offset)
            return self._to_domain(result, bore_log_path)
        except Exception as exc:  # mirror engine no-raise contract
            return RedlineResult(job_id="", status="ERROR",
                                 source_file=os.path.basename(bore_log_path),
                                 warnings=[f"engine run failed: {type(exc).__name__}: {exc}"])

    # -- translation: frozen EngineResult contract -> tl_core domain ----------
    def _to_domain(self, result: Any, bore_log_path: str) -> RedlineResult:
        arts_by_seg = self._artifacts_by_segment(result)
        placements = [self._seg_to_placement(s, "placement", arts_by_seg)
                      for s in getattr(result, "selected_segments", []) or []]
        reviews = [self._seg_to_placement(s, "review", arts_by_seg)
                   for s in getattr(result, "review_items", []) or []]
        fails = [self._failsafe_to_placement(f)
                 for f in getattr(result, "fail_safe_items", []) or []]
        source = getattr(result, "source", {}) or {}
        return RedlineResult(
            job_id=getattr(result, "job_id", ""),
            status=getattr(result, "status", "ERROR"),
            source_file=source.get("bore_log") or os.path.basename(bore_log_path),
            placements=placements,
            review_items=reviews,
            fail_safe=fails,
            warnings=list(getattr(result, "warnings", []) or []),
        )

    def _artifacts_by_segment(self, result: Any) -> Dict[str, List[Tuple[str, str, str]]]:
        """Collect (basename, abspath, kind) per segment from render_artifacts.
        crop_renderer sets ``art.ref`` (first PNG) and
        ``art.payload['render_artifact_ref']`` (all PNGs, absolute)."""
        out: Dict[str, List[Tuple[str, str, str]]] = {}
        for art in getattr(result, "render_artifacts", []) or []:
            seg_id = getattr(art, "segment_id", None)
            if not seg_id:
                continue
            payload = getattr(art, "payload", {}) or {}
            ref_list = payload.get("render_artifact_ref")
            if not ref_list:
                ref = getattr(art, "ref", None)
                ref_list = [ref] if ref else []
            kind = getattr(art, "kind", "evidence_card")
            for path in ref_list:
                if path and os.path.isfile(path):
                    out.setdefault(seg_id, []).append((os.path.basename(path), path, kind))
        return out

    def _seg_to_placement(self, seg: Any, default_surface: str,
                          arts_by_seg: Dict[str, List[Tuple[str, str, str]]]) -> Placement:
        tier = getattr(seg, "tier", "")
        span = getattr(seg, "station_span", None)
        seg_id = getattr(seg, "segment_id", "")
        placement = getattr(seg, "placement", None)
        refs = [ArtifactRef(name=n, kind=k, segment_id=seg_id, source_path=p)
                for (n, p, k) in arts_by_seg.get(seg_id, [])]
        return Placement(
            segment_id=seg_id,
            log_ids=list(getattr(seg, "log_ids", []) or []),
            tier=tier,
            surface=_SURFACE_BY_TIER.get(tier, default_surface),
            sheets=list(getattr(seg, "sheets", []) or []),
            station_start=getattr(span, "start", None) if span else None,
            station_end=getattr(span, "end", None) if span else None,
            footage=getattr(seg, "footage", None),
            geometry_status=getattr(placement, "geometry_status", None) if placement else None,
            artifacts=refs,
        )

    def _failsafe_to_placement(self, fs: Any) -> Placement:
        return Placement(
            segment_id="",
            log_ids=list(getattr(fs, "log_ids", []) or []),
            tier=getattr(fs, "tier", "FAIL_SAFE"),
            surface="fail_safe",
        )
