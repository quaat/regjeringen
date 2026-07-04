"""Lightweight detail-page inspection for source audits."""

from __future__ import annotations

from collections.abc import Iterable

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from sculpin_regjeringen.parsers.html_common import (
    absolute_url,
    extract_document_id,
    normalize_whitespace,
)

ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")


class DetailLink(BaseModel):
    label: str
    url: str


class DetailPageAudit(BaseModel):
    source_url: str
    document_id: str | None
    html_lang: str | None = None
    title: str | None = None
    canonical_url: str | None = None
    meta_last_modified: str | None = None
    headings: list[str] = Field(default_factory=list)
    attachments: list[DetailLink] = Field(default_factory=list)
    response_links: list[DetailLink] = Field(default_factory=list)
    related_links: list[DetailLink] = Field(default_factory=list)
    json_ld_blocks: int = 0

    @property
    def has_hearing_letter(self) -> bool:
        return _contains_any(self.headings, ("høringsbrev", "høyringsbrev"))

    @property
    def has_hearing_note(self) -> bool:
        heading_match = _contains_any(self.headings, ("høringsnotat", "høyringsnotat"))
        attachment_match = _contains_any(
            (link.label for link in self.attachments),
            ("høringsnotat",),
        )
        return heading_match or attachment_match

    @property
    def has_responses_link(self) -> bool:
        return bool(self.response_links)


def inspect_detail_page(html: str, *, source_url: str) -> DetailPageAudit:
    soup = BeautifulSoup(html, "html.parser")
    html_node = soup.select_one("html")
    h1 = soup.select_one("h1")
    canonical_url = _meta_content(soup, "property", "og:url") or _link_href(soup, "canonical")
    headings = [
        normalize_whitespace(node.get_text(" ", strip=True))
        for node in soup.select("h2, h3")
        if normalize_whitespace(node.get_text(" ", strip=True))
    ]

    return DetailPageAudit(
        source_url=source_url,
        document_id=extract_document_id(source_url),
        html_lang=str(html_node.get("lang")) if html_node and html_node.get("lang") else None,
        title=normalize_whitespace(h1.get_text(" ", strip=True)) if h1 else None,
        canonical_url=canonical_url,
        meta_last_modified=_meta_content(soup, "name", "last-modified"),
        headings=headings,
        attachments=_extract_attachment_links(soup, source_url),
        response_links=_extract_keyword_links(soup, source_url, ("høringssvar", "høyringssvar")),
        related_links=_extract_keyword_links(soup, source_url, ("relatert", "videre behandling")),
        json_ld_blocks=len(soup.select('script[type="application/ld+json"]')),
    )


def _meta_content(soup: BeautifulSoup, attribute: str, value: str) -> str | None:
    node = soup.select_one(f'meta[{attribute}="{value}"]')
    return str(node.get("content")) if node and node.get("content") else None


def _link_href(soup: BeautifulSoup, rel: str) -> str | None:
    node = soup.select_one(f'link[rel="{rel}"]')
    return str(node.get("href")) if node and node.get("href") else None


def _extract_attachment_links(soup: BeautifulSoup, source_url: str) -> list[DetailLink]:
    links: list[DetailLink] = []
    for link in soup.select("a[href]"):
        href = str(link["href"])
        lower_href = href.casefold().split("?", 1)[0]
        label = normalize_whitespace(link.get_text(" ", strip=True))
        lower_label = label.casefold()
        if lower_href.endswith(ATTACHMENT_EXTENSIONS) or any(
            extension.strip(".") in lower_label for extension in ATTACHMENT_EXTENSIONS
        ):
            links.append(DetailLink(label=label, url=absolute_url(source_url, href)))
    return _deduplicate_links(links)


def _extract_keyword_links(
    soup: BeautifulSoup,
    source_url: str,
    keywords: tuple[str, ...],
) -> list[DetailLink]:
    links: list[DetailLink] = []
    for link in soup.select("a[href]"):
        label = normalize_whitespace(link.get_text(" ", strip=True))
        href = str(link["href"])
        haystack = f"{label} {href}".casefold()
        if any(keyword in haystack for keyword in keywords):
            links.append(DetailLink(label=label, url=absolute_url(source_url, href)))
    return _deduplicate_links(links)


def _deduplicate_links(links: Iterable[DetailLink]) -> list[DetailLink]:
    seen: set[tuple[str, str]] = set()
    deduped: list[DetailLink] = []
    for link in links:
        key = (link.label, link.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped


def _contains_any(values: Iterable[str], needles: tuple[str, ...]) -> bool:
    return any(any(needle in value.casefold() for needle in needles) for value in values)
