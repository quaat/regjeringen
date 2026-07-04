"""Robots-aware source audit and fixture capture."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sculpin_regjeringen.config import DEFAULT_SETTINGS, Settings
from sculpin_regjeringen.crawler.detail_audit import DetailPageAudit, inspect_detail_page
from sculpin_regjeringen.crawler.fetcher import FetchResult, HttpxFetcher
from sculpin_regjeringen.crawler.hearing import HearingListingItem, parse_hearing_listing_page
from sculpin_regjeringen.crawler.robots import CrawlPolicy, build_robots_parser


@dataclass(slots=True)
class SourceAuditOptions:
    categories: list[str]
    sample_size: int
    output: Path
    fixture_root: Path = Path("tests/fixtures/regjeringen")
    max_listing_pages: int = 1
    fetch_details: bool = True
    settings: Settings = field(default_factory=lambda: DEFAULT_SETTINGS)


class SavedFixture(BaseModel):
    url: str
    path: str
    sha256: str
    status_code: int


class CategoryAudit(BaseModel):
    category: str
    status: str
    listing_pages_fetched: int = 0
    discovered_urls: int = 0
    fixtures_saved: list[SavedFixture] = Field(default_factory=list)
    listing_items: list[dict[str, Any]] = Field(default_factory=list)
    detail_pages: list[DetailPageAudit] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SourceAuditResult(BaseModel):
    crawl_batch_id: str
    generated_at: datetime
    robots_url: str
    sitemap_urls: list[str] = Field(default_factory=list)
    disallowed_patterns: list[str] = Field(default_factory=list)
    categories: list[CategoryAudit] = Field(default_factory=list)


async def run_source_audit(options: SourceAuditOptions) -> SourceAuditResult:
    fetcher = HttpxFetcher(
        user_agent=options.settings.user_agent,
        timeout_seconds=options.settings.request_timeout_seconds,
    )
    crawl_batch_id = f"source-audit-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    robots_result = await fetcher.fetch(str(options.settings.robots_url))
    robots_text = robots_result.body.decode("utf-8", errors="replace")
    robots_parser = build_robots_parser(str(options.settings.robots_url), robots_text)
    policy = CrawlPolicy(robots=robots_parser, user_agent=options.settings.user_agent)
    result = SourceAuditResult(
        crawl_batch_id=crawl_batch_id,
        generated_at=datetime.now(UTC),
        robots_url=str(options.settings.robots_url),
        sitemap_urls=_extract_sitemaps(robots_text),
        disallowed_patterns=_extract_disallows(robots_text),
    )

    _write_fetch_artifact(
        options.fixture_root / "_source_audit" / "robots.txt",
        robots_result,
    )

    for category in options.categories:
        normalized = _normalize_category(category)
        if normalized != "hearing":
            result.categories.append(
                CategoryAudit(
                    category=normalized,
                    status="pending",
                    notes=["Only hearing source audit is implemented in the first milestone."],
                )
            )
            continue
        result.categories.append(
            await _audit_hearings(
                fetcher=fetcher,
                policy=policy,
                options=options,
                crawl_batch_id=crawl_batch_id,
            )
        )

    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(render_markdown_report(result), encoding="utf-8")
    manifest_path = options.output.with_suffix(".json")
    manifest_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def run_source_audit_sync(options: SourceAuditOptions) -> SourceAuditResult:
    return asyncio.run(run_source_audit(options))


async def _audit_hearings(
    *,
    fetcher: HttpxFetcher,
    policy: CrawlPolicy,
    options: SourceAuditOptions,
    crawl_batch_id: str,
) -> CategoryAudit:
    audit = CategoryAudit(category="hearing", status="implemented")
    category_url = str(options.settings.categories[0].url)
    page_url: str | None = category_url
    listing_items: list[HearingListingItem] = []

    while page_url and audit.listing_pages_fetched < options.max_listing_pages:
        if not policy.is_allowed(page_url):
            audit.notes.append(f"Skipped disallowed listing URL: {page_url}")
            break
        listing_fetch = await fetcher.fetch(page_url)
        listing_number = audit.listing_pages_fetched + 1
        listing_path = (
            options.fixture_root / "hearings" / "_listing" / f"page-{listing_number:03d}.html"
        )
        audit.fixtures_saved.append(_write_fetch_artifact(listing_path, listing_fetch))
        listing = parse_hearing_listing_page(
            listing_fetch.body.decode("utf-8", errors="replace"),
            page_url=listing_fetch.final_url,
            crawl_batch_id=crawl_batch_id,
        )
        audit.listing_pages_fetched += 1
        listing_items.extend(listing.items)
        page_url = listing.next_page_url
        audit.notes.append(
            f"Listing page {listing.page_number}: {len(listing.items)} items; "
            f"total_results={listing.total_results}; total_pages={listing.total_pages}"
        )

    selected_items = listing_items[: options.sample_size]
    audit.discovered_urls = len(listing_items)
    audit.listing_items = [_listing_item_summary(item) for item in selected_items]

    if not options.fetch_details:
        return audit

    for item in selected_items:
        detail_url = str(item.discovered_url.url)
        if not policy.is_allowed(detail_url):
            audit.notes.append(f"Skipped disallowed detail URL: {detail_url}")
            continue
        detail_fetch = await fetcher.fetch(detail_url)
        document_id = item.document_id or "unknown-document"
        detail_path = options.fixture_root / "hearings" / document_id / "page.html"
        audit.fixtures_saved.append(_write_fetch_artifact(detail_path, detail_fetch))
        detail_audit = inspect_detail_page(
            detail_fetch.body.decode("utf-8", errors="replace"),
            source_url=detail_fetch.final_url,
        )
        audit.detail_pages.append(detail_audit)

    return audit


def render_markdown_report(result: SourceAuditResult) -> str:
    lines = [
        "# Source Audit",
        "",
        f"- Crawl batch: `{result.crawl_batch_id}`",
        f"- Generated: `{result.generated_at.isoformat()}`",
        f"- Robots: `{result.robots_url}`",
        f"- Sitemaps: {', '.join(f'`{url}`' for url in result.sitemap_urls) or 'none found'}",
        f"- Disallow rules: {len(result.disallowed_patterns)}",
        "",
        "## Categories",
        "",
    ]
    for category in result.categories:
        lines.extend(
            [
                f"### {category.category}",
                "",
                f"- Status: `{category.status}`",
                f"- Listing pages fetched: {category.listing_pages_fetched}",
                f"- Discovered URLs: {category.discovered_urls}",
                f"- Fixtures saved: {len(category.fixtures_saved)}",
            ]
        )
        if category.notes:
            lines.append("- Notes:")
            lines.extend(f"  - {note}" for note in category.notes)
        lines.extend(["", "#### Listing Field Coverage", ""])
        lines.extend(_coverage_table(category.listing_items))
        if category.detail_pages:
            lines.extend(["", "#### Detail Field Coverage", ""])
            lines.extend(_detail_coverage_table(category.detail_pages))
            lines.extend(["", "#### Detail Headings Observed", ""])
            for page in category.detail_pages:
                lines.append(f"- `{page.document_id}`: {', '.join(page.headings[:8]) or 'none'}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _coverage_table(rows: list[dict[str, Any]]) -> list[str]:
    fields = [
        "url",
        "document_id",
        "title",
        "publication_date",
        "departments",
        "document_type",
        "deadline",
        "status",
        "summary",
    ]
    return _field_coverage_table(rows, fields)


def _detail_coverage_table(rows: list[DetailPageAudit]) -> list[str]:
    dict_rows = [
        {
            "title": row.title,
            "document_id": row.document_id,
            "language": row.html_lang,
            "canonical_url": row.canonical_url,
            "last_modified": row.meta_last_modified,
            "headings": row.headings,
            "attachments": row.attachments,
            "hearing_letter": row.has_hearing_letter,
            "hearing_note": row.has_hearing_note,
            "responses_link": row.has_responses_link,
            "json_ld": row.json_ld_blocks,
        }
        for row in rows
    ]
    return _field_coverage_table(
        dict_rows,
        [
            "title",
            "document_id",
            "language",
            "canonical_url",
            "last_modified",
            "headings",
            "attachments",
            "hearing_letter",
            "hearing_note",
            "responses_link",
            "json_ld",
        ],
    )


def _field_coverage_table(rows: list[dict[str, Any]], fields: list[str]) -> list[str]:
    lines = ["| Field | Present | Total | Coverage |", "| --- | ---: | ---: | ---: |"]
    total = len(rows)
    for field_name in fields:
        present = sum(1 for row in rows if _has_value(row.get(field_name)))
        coverage = f"{(present / total * 100):.1f}%" if total else "n/a"
        lines.append(f"| `{field_name}` | {present} | {total} | {coverage} |")
    return lines


def _write_fetch_artifact(path: Path, result: FetchResult) -> SavedFixture:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.body)
    digest = sha256(result.body).hexdigest()
    metadata = {
        "request_url": result.request_url,
        "final_url": result.final_url,
        "status_code": result.status_code,
        "headers": result.headers,
        "fetched_at": result.fetched_at.isoformat(),
        "redirect_chain": result.redirect_chain,
        "sha256": digest,
    }
    path.with_suffix(path.suffix + ".fetch.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return SavedFixture(
        url=result.final_url,
        path=str(path),
        sha256=f"sha256:{digest}",
        status_code=result.status_code,
    )


def _listing_item_summary(item: HearingListingItem) -> dict[str, Any]:
    return {
        "url": str(item.discovered_url.url),
        "document_id": item.document_id,
        "title": item.discovered_url.title_hint,
        "publication_date": (
            item.discovered_url.publication_date_hint.isoformat()
            if item.discovered_url.publication_date_hint
            else None
        ),
        "departments": item.discovered_url.department_hint,
        "document_type": item.document_type_hint,
        "deadline": item.deadline_hint.isoformat() if item.deadline_hint else None,
        "status": item.status_hint,
        "summary": item.summary_hint,
    }


def _extract_sitemaps(robots_text: str) -> list[str]:
    return [
        line.split(":", 1)[1].strip()
        for line in robots_text.splitlines()
        if line.casefold().startswith("sitemap:")
    ]


def _extract_disallows(robots_text: str) -> list[str]:
    return [
        line.split(":", 1)[1].strip()
        for line in robots_text.splitlines()
        if line.casefold().startswith("disallow:")
    ]


def _normalize_category(category: str) -> str:
    normalized = category.strip().casefold().replace("-", "_")
    aliases = {
        "høring": "hearing",
        "høyring": "hearing",
        "horing": "hearing",
        "hoyring": "hearing",
        "storting_message": "storting_message",
        "stortingmessage": "storting_message",
    }
    return aliases.get(normalized, normalized)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True
