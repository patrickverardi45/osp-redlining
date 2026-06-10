"""Typed settings for TrueLine v2. No global mutable state; constructed once and
injected. Fail-closed CORS in the app factory."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# truelinev2/config.py -> truelinev2/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUT = _REPO_ROOT / "data" / "outputs" / "truelinev2"


@dataclass(frozen=True)
class Settings:
    artifact_root: Path
    cards_dir: Path
    db_path: Path
    sheet_offset: int = 13
    render_zoom: float = 3.5
    allowed_origins: Tuple[str, ...] = ()
    # M8.2l: reset-vs-continuous collision gate. DEFAULT OFF -- the gate is consulted
    # only when this is explicitly True (opt-in test); OFF is byte-identical default.
    reset_collision_optin: bool = False
    # M8.4: frame-aware continuation retry (safe HIGH edges, abstain-fill, REVIEW-cap).
    # DEFAULT OFF -- OFF is byte-identical default behavior.
    frame_continuation_optin: bool = False
    # M8.5: reverse endpoint anchor retry (end-station backsolve, abstain-fill,
    # REVIEW-cap, uniqueness-mandatory). DEFAULT OFF -- OFF is byte-identical.
    reverse_endpoint_optin: bool = False
    # M8.8: station-axis interval containment retry (tick-ladder path-walk,
    # abstain-fill, REVIEW-cap). DEFAULT OFF -- OFF is byte-identical.
    station_axis_interval_optin: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        raw = os.getenv("TL2_ALLOWED_ORIGINS", "").strip()
        origins = tuple(o.strip() for o in raw.split(",") if o.strip())
        return cls(
            artifact_root=Path(os.getenv("TL2_ARTIFACT_ROOT", str(_OUT / "artifacts"))),
            cards_dir=Path(os.getenv("TL2_CARDS_DIR", str(_OUT / "_cards"))),
            db_path=Path(os.getenv("TL2_DB_PATH", str(_OUT / "truelinev2.db"))),
            sheet_offset=int(os.getenv("TL2_SHEET_OFFSET", "13")),
            allowed_origins=origins,
            reset_collision_optin=os.getenv("TL2_RESET_COLLISION_OPTIN", "0") == "1",
            frame_continuation_optin=os.getenv("TL2_FRAME_AWARE_CONTINUATION_OPTIN", "0") == "1",
            reverse_endpoint_optin=os.getenv("TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN", "0") == "1",
            station_axis_interval_optin=os.getenv("TL2_STATION_AXIS_INTERVAL_OPTIN", "0") == "1",
        )

    @classmethod
    def for_proof(cls) -> "Settings":
        return cls(
            artifact_root=_OUT / "artifacts",
            cards_dir=_OUT / "_cards",
            db_path=_OUT / "truelinev2.db",
            sheet_offset=13,
            allowed_origins=("http://localhost:3000", "http://127.0.0.1:8100"),
        )
