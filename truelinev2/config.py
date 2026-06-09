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
