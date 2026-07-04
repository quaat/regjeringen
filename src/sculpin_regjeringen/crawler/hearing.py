"""Hearing category discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from sculpin_regjeringen.config import DEFAULT_SETTINGS
from sculpin_regjeringen.crawler.discovery import DiscoveredUrl
from sculpin_regjeringen.crawler.fetcher import HttpxFetcher
from sculpin_regjeringen.crawler.robots import CrawlPolicy
from sculpin_regjeringen.parsers.html_common import (
    absolute_url,
    extract_document_id,
    normalize_whitespace,
    parse_norwegian_date,
)


class HearingListingItem(BaseModel):
    discovered_url: DiscoveredUrl
    document_id: str | None = None
    document_type_hint: str | None = None
    summary_hint: str | None = None
    deadline_hint: date | None = None
    status_hint: str | None = None


class HearingListingPage(BaseModel):
    page_url: str
    page_number: int
    total_pages: int | None = None
    total_results: int | None = None
    next_page_url: str | None = None
    items: list[HearingListingItem] = Field(default_factory=list)


@dataclass(slots=True)
class HearingCrawler:
    category_url: str = str(DEFAULT_SETTINGS.categories[0].url)
    fetcher: HttpxFetcher | None = None
    crawl_policy: CrawlPolicy | None = None
    max_listing_pages: int = 1

    async def discover(self, crawl_batch_id: str) -> list[DiscoveredUrl]:
        """Discover hearing detail URLs from allowed public sources."""

        if self.fetcher is None:
            msg = "HearingCrawler requires a fetcher for live discovery."
            raise ValueError(msg)
        discovered: list[DiscoveredUrl] = []
        page_url: str | None = self.category_url
        pages_seen = 0

        while page_url and pages_seen < self.max_listing_pages:
            if self.crawl_policy is not None and not self.crawl_policy.is_allowed(page_url):
                break

            result = await self.fetcher.fetch(page_url)
            listing = parse_hearing_listing_page(
                result.body.decode("utf-8", errors="replace"),
                page_url=result.final_url,
                crawl_batch_id=crawl_batch_id,
            )
            discovered.extend(item.discovered_url for item in listing.items)
            page_url = listing.next_page_url
            pages_seen += 1

        return discovered


def parse_hearing_listing_page(
    html: str,
    *,
    page_url: str,
    crawl_batch_id: str,
) -> HearingListingPage:
    soup = BeautifulSoup(html, "html.parser")
    page_number = _page_number_from_url(page_url)
    parsed_at = datetime.now(UTC)
    items: list[HearingListingItem] = []

    for node in soup.select("ul.listing li.listItem"):
        link = node.select_one('a[data-nav="searchResultItem"], a[data-nav=searchResultItem]')
        if link is None or not link.get("href"):
            continue

        detail_url = absolute_url(page_url, str(link["href"]))
        title = normalize_whitespace(link.get_text(" ", strip=True))
        department_text = _select_text(node, ".department")
        departments = _split_departments(department_text)
        date_hint = parse_norwegian_date(_select_text(node, ".date"))
        detail_text = normalize_whitespace(node.get_text(" ", strip=True))
        deadline_hint = _extract_labeled_date(detail_text, ("Høringsfrist", "Høyringsfrist"))
        status_hint = _extract_status(detail_text)

        discovered = DiscoveredUrl(
            url=detail_url,
            canonical_candidate=detail_url,
            source_category="hearing",
            source_list_url=page_url,
            page_number=page_number,
            title_hint=title or None,
            publication_date_hint=date_hint,
            department_hint=departments,
            discovered_at=parsed_at,
            crawl_batch_id=crawl_batch_id,
        )
        items.append(
            HearingListingItem(
                discovered_url=discovered,
                document_id=extract_document_id(detail_url),
                document_type_hint=_select_text(node, ".type") or None,
                summary_hint=_select_text(node, ".excerpts") or None,
                deadline_hint=deadline_hint,
                status_hint=status_hint,
            )
        )

    return HearingListingPage(
        page_url=page_url,
        page_number=page_number,
        total_pages=_extract_total_pages(soup),
        total_results=_extract_total_results(soup),
        next_page_url=_extract_next_page_url(soup, page_url),
        items=items,
    )


def _page_number_from_url(url: str) -> int:
    raw_page = parse_qs(urlparse(url).query).get("page", ["1"])[0]
    try:
        return max(int(raw_page), 1)
    except ValueError:
        return 1


def _select_text(node: BeautifulSoup, selector: str) -> str:
    selected = node.select_one(selector)
    if selected is None:
        return ""
    return normalize_whitespace(selected.get_text(" ", strip=True))


def _split_departments(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _extract_labeled_date(text: str, labels: tuple[str, ...]) -> date | None:
    for label in labels:
        marker = f"{label}:"
        if marker in text:
            return parse_norwegian_date(text[text.index(marker) + len(marker) :])
    return None


def _extract_status(text: str) -> str | None:
    marker = "Status:"
    if marker not in text:
        return None
    status = text[text.index(marker) + len(marker) :].strip()
    return status or None


def _extract_total_pages(soup: BeautifulSoup) -> int | None:
    pagination = soup.select_one("ul.pagination")
    if pagination is None:
        return None
    text = normalize_whitespace(pagination.get_text(" ", strip=True))
    match = re.search(r"\b(?:av|of)\s+(\d+)\b", text)
    return int(match.group(1)) if match else None


def _extract_total_results(soup: BeautifulSoup) -> int | None:
    count = soup.select_one("p.count")
    if count is None:
        return None
    text = normalize_whitespace(count.get_text(" ", strip=True)).replace("\u00a0", " ")
    match = re.search(r"\bav\s+([\d\s]+)\s+treff\b", text)
    if match is None:
        return None
    return int(match.group(1).replace(" ", ""))


def _extract_next_page_url(soup: BeautifulSoup, page_url: str) -> str | None:
    link = soup.select_one('link[rel="next"]')
    if link is None:
        link = soup.select_one("ul.pagination li.next:not(.disabled) a[href]")
    href = link.get("href") if link is not None else None
    return absolute_url(page_url, str(href)) if href else None
