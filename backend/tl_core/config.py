"""tl_core configuration — typed, explicit, fail-closed where it matters.

No global mutable state. A :class:`Settings` snapshot is built once (from env via
:meth:`Settings.from_env` in production, or explicitly in tests/proof) and
injected into the app/services. Mirrors the monolith's default-OFF flag
semantics so behavior parity is opt-in, never accidental.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# backend/ = parent of the tl_core package; repo root = its parent.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
# The proven engine is vendored at backend/app/core/redline_pdf_first; the import
# root placed on sys.path (so ``import redline_pdf_first`` resolves) is app/core.
_ENGINE_ROOT_DEFAULT = _BACKEND_DIR / "app" / "core"
_ARTIFACT_ROOT_DEFAULT = _REPO_ROOT / "data" / "outputs" / "tl_core" / "artifacts"

_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in _TRUE


@dataclass(frozen=True)
class Settings:
    """Immutable settings snapshot. Construct via :meth:`from_env` or :meth:`for_proof`."""

    engine_root: Path
    artifact_root: Path
    sheet_offset: int = 13
    allowed_origins: Tuple[str, ...] = ()
    # Flags mirror the monolith (default OFF). Milestone-1 relies only on the
    # always-real highlight-crop render; the geometry/overlay flags are carried
    # for parity and future wiring.
    pdf_first_engine: bool = False
    render_crops: bool = True
    ap_anchored_geometry: bool = False
    pdf_redline_render: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        raw_origins = os.getenv("TRUELINE_ALLOWED_ORIGINS", "").strip()
        origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())
        return cls(
            engine_root=Path(os.getenv("TL_CORE_ENGINE_ROOT", str(_ENGINE_ROOT_DEFAULT))),
            artifact_root=Path(os.getenv("TL_CORE_ARTIFACT_ROOT", str(_ARTIFACT_ROOT_DEFAULT))),
            sheet_offset=int(os.getenv("TL_CORE_SHEET_OFFSET", "13")),
            allowed_origins=origins,
            pdf_first_engine=_flag("TRUELINE_PDF_FIRST_ENGINE"),
            ap_anchored_geometry=_flag("TRUELINE_AP_ANCHORED_GEOMETRY"),
            pdf_redline_render=_flag("TRUELINE_PDF_REDLINE_RENDER"),
        )

    @classmethod
    def for_proof(cls, artifact_root: Optional[Path] = None) -> "Settings":
        """Settings for the offline proof harness: engine ON, isolated artifact
        root, localhost CORS. Touches neither the process env nor the monolith."""
        return cls(
            engine_root=_ENGINE_ROOT_DEFAULT,
            artifact_root=artifact_root or _ARTIFACT_ROOT_DEFAULT,
            sheet_offset=13,
            allowed_origins=("http://localhost:3000", "http://127.0.0.1:8099"),
            pdf_first_engine=True,
            render_crops=True,
        )
