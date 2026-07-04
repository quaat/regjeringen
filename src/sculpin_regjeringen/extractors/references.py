"""Deterministic reference extraction patterns."""

from __future__ import annotations

import re

REFERENCE_PATTERNS = {
    "nou": re.compile(r"\bNOU\s+(?P<year>\d{4}):\s*(?P<number>\d+)\b"),
    "proposition": re.compile(r"\bProp\.\s+(?P<number>\d+)\s*(?P<kind>L|S|LS)?\b"),
    "storting_message": re.compile(r"\bMeld\.\s+St\.\s+(?P<number>\d+)\b"),
    "eu_act": re.compile(r"\b(?:direktiv|forordning)\s+\(EU\)\s+(?P<year>\d{4})/(?P<number>\d+)\b"),
}


def find_references(text: str) -> dict[str, list[str]]:
    return {
        name: [match.group(0) for match in pattern.finditer(text)]
        for name, pattern in REFERENCE_PATTERNS.items()
    }
