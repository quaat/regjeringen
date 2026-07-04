"""Human validation review queue scaffold."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ReviewStatus = Literal["proposed", "approved", "rejected", "merged"]


class ReviewItem(BaseModel):
    item_id: str
    item_type: str
    source_span_id: str
    proposed_value: str
    status: ReviewStatus = "proposed"
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewer: str | None = None
