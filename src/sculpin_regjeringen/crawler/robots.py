"""Robots and URL policy helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlparse
from urllib.robotparser import RobotFileParser

DISALLOWED_PATH_PREFIXES = (
    "/api/",
    "/no/api/",
    "/nb/api/",
    "/nn/api/",
    "/se/api/",
    "/en/api/",
    "/no/dokumentarkiv/",
    "/en/historical-archive/",
    "/se/dokumeantavuorka/",
)

DISALLOWED_QUERY_KEYS = {
    "documenttype",
    "topic",
    "ownerid",
    "from",
    "to",
    "government",
    "utid",
    "sesjon",
    "type",
    "law",
    "county",
    "term",
    "sortby",
    "sort",
    "expand",
    "querystring",
    "isfilteropen",
    "pageRef",
    "reg_oss",
    "tema",
    "q",
    "bq",
    "uid",
    "docid",
    "personid",
    "eventId",
    "cedit",
    "consterm",
}


@dataclass(slots=True)
class CrawlPolicy:
    robots: RobotFileParser
    user_agent: str
    disallowed_query_keys: set[str] = field(default_factory=lambda: set(DISALLOWED_QUERY_KEYS))
    disallowed_path_prefixes: tuple[str, ...] = DISALLOWED_PATH_PREFIXES

    def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.path.startswith(self.disallowed_path_prefixes):
            return False
        query_keys = {key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
        if query_keys & self.disallowed_query_keys:
            return False
        return self.robots.can_fetch(self.user_agent, url)


def build_robots_parser(robots_url: str, robots_text: str) -> RobotFileParser:
    parser = RobotFileParser(robots_url)
    parser.parse(robots_text.splitlines())
    return parser
