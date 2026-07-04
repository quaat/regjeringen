"""Attachment link parsing and role classification scaffold."""

from __future__ import annotations

from pathlib import PurePosixPath


def _fold_norwegian(value: str) -> str:
    return (
        value.casefold()
        .replace("\u00e6", "ae")
        .replace("\u00f8", "o")
        .replace("\u00e5", "a")
    )


def classify_attachment_role(label: str, href: str) -> str:
    text = _fold_norwegian(f"{label} {PurePosixPath(href).name}")
    if "horingsnotat" in text or "hoyringsnotat" in text:
        return "hearing_note"
    if "horingsbrev" in text or "hoyringsbrev" in text:
        return "hearing_letter"
    if "vedlegg" in text or "appendiks" in text:
        return "appendix"
    if "rapport" in text:
        return "report"
    if "skjema" in text or "form" in text:
        return "form"
    if "pdf" in text:
        return "main_document"
    return "unknown"
