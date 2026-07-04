
from sculpin_regjeringen.crawler.detail_audit import inspect_detail_page
from sculpin_regjeringen.crawler.hearing import parse_hearing_listing_page
from sculpin_regjeringen.crawler.robots import CrawlPolicy, build_robots_parser
from sculpin_regjeringen.crawler.source_audit import (
    CategoryAudit,
    SourceAuditResult,
    render_markdown_report,
)


def test_crawl_policy_blocks_disallowed_filter_queries_but_allows_page() -> None:
    robots = build_robots_parser(
        "https://www.regjeringen.no/robots.txt",
        "\n".join(
            [
                "User-agent: *",
                "Disallow: /api/*",
                "Disallow: /*/?pageRef",
                "Disallow: /*/?sortby",
            ]
        ),
    )
    policy = CrawlPolicy(robots=robots, user_agent="test-agent")

    assert policy.is_allowed("https://www.regjeringen.no/no/dokument/hoyringar/id1763/?page=2")
    assert not policy.is_allowed(
        "https://www.regjeringen.no/no/dokument/hoyringar/id1763/?sortby=1"
    )
    assert not policy.is_allowed("https://www.regjeringen.no/api/search")


def test_parse_hearing_listing_page_extracts_items_and_pagination() -> None:
    html = """
    <html><head>
      <link rel="next" href="https://www.regjeringen.no/no/dokument/hoyringar/id1763/?page=2">
    </head><body>
      <p class="count">Viser 1-2 av 6960 treff.</p>
      <ul class="listing">
        <li class="listItem">
          <h2 class="title">
            <a href="/no/dokumenter/example/id3168525/" data-nav=searchResultItem>
              Høyring - eksempel
            </a>
          </h2>
          <div class="info">
            <span class="date">03.07.2026</span>
            <span class="type">Høyring</span>
            <span class="department">Finansdepartementet, Energidepartementet</span>
          </div>
          <p class="excerpts">Kort ingress.</p>
          <p class="event-details">
            <span class="event-details">Høyringsfrist: 14.08.2026</span>
            <span class="event-details-open">Status: På høyring</span>
          </p>
        </li>
      </ul>
      <ul class="pagination"><li class="current_0"><span>Side 1 av 348</span></li></ul>
    </body></html>
    """

    listing = parse_hearing_listing_page(
        html,
        page_url="https://www.regjeringen.no/no/dokument/hoyringar/id1763/",
        crawl_batch_id="batch-1",
    )

    assert listing.total_results == 6960
    assert listing.total_pages == 348
    assert listing.next_page_url == "https://www.regjeringen.no/no/dokument/hoyringar/id1763/?page=2"
    assert len(listing.items) == 1
    item = listing.items[0]
    assert item.document_id == "id3168525"
    assert item.document_type_hint == "Høyring"
    assert item.deadline_hint and item.deadline_hint.isoformat() == "2026-08-14"
    assert item.status_hint == "På høyring"
    assert item.discovered_url.department_hint == ["Finansdepartementet", "Energidepartementet"]


def test_inspect_detail_page_extracts_source_audit_signals() -> None:
    html = """
    <html lang="nb"><head>
      <meta property="og:url" content="https://www.regjeringen.no/no/dokumenter/example/id3168525/">
      <meta name="last-modified" content="Fri, 03 Jul 2026 12:00:00 GMT">
      <script type="application/ld+json">{"@type": "WebPage"}</script>
    </head><body>
      <h1>Høring - eksempel</h1>
      <h2>Høringsbrev</h2>
      <h2>Høringsnotat</h2>
      <a href="/contentassets/example/horingsnotat.pdf">Høringsnotat (PDF)</a>
      <a href="/no/dokumenter/example/id3168525/?showresponse=true">Høringssvar</a>
    </body></html>
    """

    audit = inspect_detail_page(
        html,
        source_url="https://www.regjeringen.no/no/dokumenter/example/id3168525/",
    )

    assert audit.document_id == "id3168525"
    assert audit.html_lang == "nb"
    assert audit.title == "Høring - eksempel"
    assert audit.has_hearing_letter
    assert audit.has_hearing_note
    assert audit.has_responses_link
    assert len(audit.attachments) == 1
    assert audit.json_ld_blocks == 1


def test_render_markdown_report_includes_pending_categories() -> None:
    result = SourceAuditResult(
        crawl_batch_id="batch-1",
        generated_at="2026-07-03T20:00:00Z",
        robots_url="https://www.regjeringen.no/robots.txt",
        sitemap_urls=["https://www.regjeringen.no/globalassets/sitemap/sitemap.xml"],
        disallowed_patterns=["/api/*"],
        categories=[
            CategoryAudit(category="hearing", status="implemented", discovered_urls=1),
            CategoryAudit(category="nou", status="pending"),
        ],
    )

    report = render_markdown_report(result)

    assert "### hearing" in report
    assert "### nou" in report
    assert "Status: `pending`" in report


def test_settings_reject_invalid_urls() -> None:
    from pydantic import ValidationError

    from sculpin_regjeringen.config import CategoryUrl, Settings

    try:
        CategoryUrl(name="bad", url="not a url")
    except ValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("CategoryUrl accepted an invalid URL")

    try:
        Settings(base_url="ftp://example.com")
    except ValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Settings accepted a non-HTTP base URL")


def test_discovered_url_rejects_invalid_url() -> None:
    from datetime import UTC, datetime

    from pydantic import ValidationError

    from sculpin_regjeringen.crawler.discovery import DiscoveredUrl

    try:
        DiscoveredUrl(
            url="not a url",
            source_category="hearing",
            source_list_url="https://www.regjeringen.no/no/dokument/hoyringar/id1763/",
            discovered_at=datetime.now(UTC),
            crawl_batch_id="batch",
        )
    except ValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("DiscoveredUrl accepted an invalid URL")
