"""Discovery records and crawler interfaces."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import AnyUrl, BaseModel, Field

SourceCategory = Literal["hearing", "input", "proposition", "storting_message", "nou"]


class DiscoveredUrl(BaseModel):
    url: AnyUrl
    canonical_candidate: AnyUrl | None = None
    source_category: SourceCategory
    source_list_url: AnyUrl
    page_number: int | None = None
    title_hint: str | None = None
    publication_date_hint: date | None = None
    department_hint: list[str] = Field(default_factory=list)
    discovered_at: datetime
    crawl_batch_id: str


class GovernmentDocumentCrawler(Protocol):
    async def discover(self, crawl_batch_id: str) -> list[DiscoveredUrl]:
        """Return category URLs that are allowed and ready for fetching."""
