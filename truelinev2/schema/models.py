"""Canonical v2 domain models. Pure data; no engine/PDF/IO imports."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PlacementStatus(str, Enum):
    AUTO_SELECT = "AUTO_SELECT"
    REVIEW = "REVIEW"
    ABSTAIN = "ABSTAIN"


class Bore(BaseModel):
    """A normalized bore log, format-agnostic."""
    bore_id: str
    project: Optional[str] = None
    source_file: Optional[str] = None
    sheet_refs: List[int] = Field(default_factory=list)
    station_start: str
    station_end: str
    station_start_ft: float
    station_end_ft: float
    span_ft: float
    depth_min_ft: Optional[float] = None
    print_raw: Optional[str] = None


class Callout(BaseModel):
    """An authored plan-evidence callout (the unit a dialect produces)."""
    sheet: int
    page: int
    from_sta: str
    to_sta: str
    from_ft: float
    to_ft: float
    footage: float
    conduit: Optional[str] = None
    vacant: bool = False
    footage_verified: bool = False
    text: str = ""
    bbox: Optional[List[float]] = None  # page-space [x0,y0,x1,y1]
    dialect: str = "unknown"


class Artifact(BaseModel):
    name: str
    kind: str = "evidence_crop"
    sheet: Optional[int] = None
    bbox: Optional[List[float]] = None
    size_bytes: Optional[int] = None

    @property
    def url(self) -> str:
        return f"/v2/artifact/{self.name}"


class Placement(BaseModel):
    bore_id: str
    status: PlacementStatus
    tier: str
    reason: str
    sheets: List[int] = Field(default_factory=list)
    station_span: Optional[str] = None
    footage: Optional[float] = None
    footage_delta: Optional[float] = None
    start_delta: Optional[float] = None
    end_delta: Optional[float] = None
    caveats: List[str] = Field(default_factory=list)
    abstain_reason: Optional[str] = None
    matched_callouts: List[Callout] = Field(default_factory=list)
    artifacts: List[Artifact] = Field(default_factory=list)


class ReviewItem(BaseModel):
    bore: Bore
    placement: Placement


class ReviewPayload(BaseModel):
    schema_version: str = "truelinev2-review-1"
    session_id: str
    item_count: int = 0
    counts_by_status: Dict[str, int] = Field(default_factory=dict)
    items: List[ReviewItem] = Field(default_factory=list)
