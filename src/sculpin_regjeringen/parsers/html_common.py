"""Shared HTML parsing helpers."""

from __future__ import annotations

import re
from datetime import date
from html import unescape
from urllib.parse import urljoin

DOCUMENT_ID_RE = re.compile(r"/(id\d{4,})/?")
NORWEGIAN_DATE_RE = re.compile(r"\b(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})\b")


def extract_document_id(url: str) -> str | None:
    match = DOCUMENT_ID_RE.search(url)
    return match.group(1) if match else None


def normalize_whitespace(value: str) -> str:
    return " ".join(unescape(value).split())


def absolute_url(base_url: str, href: str) -> str:
    return urljoin(base_url, unescape(href))


def parse_norwegian_date(value: str) -> date | None:
    match = NORWEGIAN_DATE_RE.search(value)
    if match is None:
        return None
    return date(
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
    )


def infer_language(url: str, html_lang: str | None = None) -> str:
    if html_lang:
        lower = html_lang.lower()
        if lower.startswith(("nb", "no")):
            return "nb"
        if lower.startswith("nn"):
            return "nn"
        if lower.startswith("en"):
            return "en"
        if lower.startswith("se"):
            return "se"
    if "/nn/" in url:
        return "nn"
    if "/en/" in url:
        return "en"
    if "/no/" in url or "/nb/" in url:
        return "nb"
    return "unknown"
