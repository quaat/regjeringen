"""Runtime settings for the regjeringen.no ingestion module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CategoryUrl(BaseModel):
    """Public category entry point used for discovery."""

    name: str
    url: str


class Settings(BaseModel):
    """Configuration with conservative defaults for local development."""

    source_site: str = "regjeringen.no"
    base_url: str = "https://www.regjeringen.no/"
    robots_url: str = "https://www.regjeringen.no/robots.txt"
    sitemap_url: str = "https://www.regjeringen.no/globalassets/sitemap/sitemap.xml"
    user_agent: str = "sculpin-regjeringen-ingest/0.1 (+contact: configure-me)"
    max_concurrent_requests: int = Field(default=2, ge=1, le=3)
    request_timeout_seconds: float = Field(default=30.0, ge=1.0)
    parser_version: str = "regjeringen-parser-0.1.0"
    categories: list[CategoryUrl] = Field(
        default_factory=lambda: [
            CategoryUrl(
                name="hearing",
                url="https://www.regjeringen.no/no/dokument/hoyringar/id1763/",
            ),
            CategoryUrl(
                name="input",
                url="https://www.regjeringen.no/no/dokument/innspel/id3015054/",
            ),
            CategoryUrl(
                name="proposition",
                url="https://www.regjeringen.no/no/dokument/prop/id1753/",
            ),
            CategoryUrl(
                name="storting_message",
                url="https://www.regjeringen.no/no/dokument/meldst/id1754/",
            ),
            CategoryUrl(
                name="nou",
                url="https://www.regjeringen.no/no/dokument/nou-ar/id1767/",
            ),
        ]
    )


DEFAULT_SETTINGS = Settings()
