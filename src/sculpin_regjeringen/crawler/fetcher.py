"""Polite HTTP fetching primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class FetchResult(BaseModel):
    request_url: str
    final_url: str
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes
    fetched_at: datetime
    redirect_chain: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class HttpxFetcher:
    user_agent: str
    timeout_seconds: float = 30.0

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def fetch(self, url: str) -> FetchResult:
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return FetchResult(
                request_url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.content,
                fetched_at=datetime.now(UTC),
                redirect_chain=[str(item.url) for item in response.history],
            )
