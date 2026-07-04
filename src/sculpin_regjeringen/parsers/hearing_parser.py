"""Hearing detail-page parser."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from sculpin_regjeringen.models.canonical import (
    Attachment,
    ContactPoint,
    DepartmentRef,
    DocumentSection,
    HearingDocument,
    OrganizationRef,
    SourceLink,
    ThemeRef,
)
from sculpin_regjeringen.models.provenance import FieldProvenance
from sculpin_regjeringen.parsers.html_common import extract_document_id, infer_language

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_ID_RE = re.compile(r"id\d+")


class HearingPageParser:
    parser_version = "regjeringen-parser-0.2.0"

    def parse(self, html: str, *, source_url: str, source_artifact_uri: str) -> HearingDocument:
        soup = BeautifulSoup(html, "html.parser")
        document_id = extract_document_id(source_url) or self._id_from_html(soup)
        if document_id is None:
            msg = f"Could not derive regjeringen.no document id from {source_url}"
            raise ValueError(msg)

        canonical_url = self._canonical_url(soup, source_url)
        title = self._text(soup.find("h1")) or self._fallback_title(soup) or document_id
        info = soup.select_one(".article-info")
        publication_date = self._parse_date(self._text(info.select_one(".date")) if info else "")
        departments = []
        if info and (owner := info.select_one(".owner")):
            label = self._text(owner).lstrip("| ").strip()
            if label:
                departments.append(DepartmentRef(label=label))
        summary = self._text(soup.select_one(".article-ingress"))
        status = self._label_value(soup, ["Status"])
        deadline = self._parse_date(
            self._label_value(soup, ["Høringsfrist", "Høyringsfrist"]) or ""
        )
        sections = self._sections(soup, source_url, source_artifact_uri)
        attachments = self._attachments(soup, document_id, source_url, source_artifact_uri)
        hearing_note_ids = [
            a.attachment_id for a in attachments if a.attachment_role == "hearing_note"
        ]
        recipients = self._recipients(soup)
        source_links = self._source_links(soup, source_url)
        themes = self._themes(soup, source_url)
        contacts = self._contacts(soup)
        hearing_letter_section_id = next(
            (
                s.section_id
                for s in sections
                if self._norm(s.heading) in {"horingsbrev", "hoyringsbrev"}
            ),
            None,
        )
        submission_url = next(
            (link.url for link in source_links if link.relation == "submission"), None
        )
        responses_url = next(
            (link.url for link in source_links if link.relation == "hearing_responses"), None
        )
        language = (soup.html.get("lang") if soup.html else None) or infer_language(source_url)

        field_values: dict[str, object] = {
            "document_id": document_id,
            "canonical_url": canonical_url,
            "document_type": "hearing",
            "title": title,
            "language": language,
            "publication_date": publication_date,
            "responsible_departments": [d.label for d in departments],
            "status": status,
            "deadline": deadline,
            "summary": summary,
            "hearing_status": status,
            "hearing_deadline": deadline,
            "hearing_letter_section_id": hearing_letter_section_id,
            "hearing_note_attachment_ids": hearing_note_ids,
            "hearing_recipients": [r.label for r in recipients],
            "submission_url": submission_url,
            "hearing_responses_url": responses_url,
            "themes": [t.label for t in themes],
            "source_links": [link.url for link in source_links],
            "contacts": [c.label for c in contacts],
        }
        provenance = [
            self._provenance(k, v, source_url=source_url, source_artifact_uri=source_artifact_uri)
            for k, v in field_values.items()
            if v not in (None, [], "")
        ]
        return HearingDocument(
            document_id=document_id,
            canonical_url=canonical_url,
            title=title,
            language=language if language in {"nb", "nn", "en", "se"} else "unknown",
            publication_date=publication_date,
            responsible_departments=departments,
            status=status,
            deadline=deadline,
            summary=summary,
            source_html_object_uri=source_artifact_uri,
            attachments=attachments,
            sections=sections,
            contacts=contacts,
            source_links=source_links,
            themes=themes,
            provenance=provenance,
            hearing_status=status,
            hearing_deadline=deadline,
            hearing_letter_section_id=hearing_letter_section_id,
            hearing_note_attachment_ids=hearing_note_ids,
            hearing_recipients=recipients,
            submission_url=submission_url,
            hearing_responses_url=responses_url,
        )

    def _sections(self, soup, source_url, uri):
        out = []
        for i, box in enumerate(soup.select(".article-body .factbox"), 1):
            h = self._text(box.select_one(".factbox-title"))
            if not h:
                continue
            sid = f"section-{i}-{self._norm(h)}"
            out.append(
                DocumentSection(
                    section_id=sid,
                    heading=h,
                    heading_path=[h],
                    provenance=[
                        self._provenance(
                            f"sections[{i - 1}]",
                            h,
                            source_url=source_url,
                            source_artifact_uri=uri,
                            selector=".factbox",
                        )
                    ],
                )
            )
        return out

    def _attachments(self, soup, document_id, source_url, uri):
        out = []
        for a in soup.select(".article-body a[href]"):
            href = a["href"]
            label = self._text(a)
            path = urlparse(href).path.lower()
            if not re.search(r"\.(pdf|docx?|xlsx?)$", path):
                continue
            url = urljoin(source_url, href)
            ext = PurePosixPath(urlparse(url).path).suffix.lower().lstrip(".") or None
            filename = PurePosixPath(urlparse(url).path).name or None
            role = (
                "hearing_note"
                if "notat" in self._norm(label + " " + (filename or ""))
                else "unknown"
            )
            aid = f"{document_id}-attachment-{len(out) + 1}"
            out.append(
                Attachment(
                    attachment_id=aid,
                    document_id=document_id,
                    source_url=url,
                    original_label=label,
                    original_filename=filename,
                    normalized_filename=filename or aid,
                    file_extension=ext,
                    media_type="application/pdf" if ext == "pdf" else None,
                    attachment_role=role,
                    provenance=[
                        self._provenance(
                            f"attachments[{len(out)}]",
                            url,
                            source_url=source_url,
                            source_artifact_uri=uri,
                            selector=".article-body a",
                        )
                    ],
                )
            )
        return out

    def _recipients(self, soup):
        box = self._factbox(soup, ["Høringsinstanser", "Høyringsinstansar"])
        if not box:
            return []
        return [
            OrganizationRef(label=t)
            for t in [self._text(p) for p in box.select(".factbox-content p")]
            if t
        ]

    def _themes(self, soup, source_url):
        return [
            ThemeRef(label=self._text(a), uri=urljoin(source_url, a["href"]))
            for a in self._links_after_heading(soup, ["Tema"])
        ]

    def _source_links(self, soup, source_url):
        links = []
        for a in soup.select(".article-body a[href]") + self._links_after_heading(
            soup, ["Relatert"]
        ):
            label = self._text(a)
            url = urljoin(source_url, a["href"])
            low = (label + url).lower()
            rel = (
                "submission"
                if "registrer_horingsuttalelse" in low or "send inn" in low
                else "hearing_responses"
                if "høringssvar" in low or "høyringssvar" in low
                else "related"
                if a in self._links_after_heading(soup, ["Relatert"])
                else None
            )
            if rel and not any(link.url == url and link.relation == rel for link in links):
                links.append(SourceLink(url=url, label=label, relation=rel))
        return links

    def _contacts(self, soup):
        contacts = []
        for a in self._links_after_heading(soup, ["Kontakt"]):
            label = self._text(a)
            if label:
                contacts.append(
                    ContactPoint(
                        label=label,
                        email=a.get("href", "").removeprefix("mailto:")
                        if a.get("href", "").startswith("mailto:")
                        else None,
                    )
                )
        return contacts

    def _links_after_heading(self, soup, headings):
        h = next((x for x in soup.find_all(["h2", "h3"]) if self._text(x) in headings), None)
        if not h:
            return []
        links = []
        for sib in h.find_all_next():
            if sib is not h and getattr(sib, "name", None) in {"h2", "h3"}:
                break
            if isinstance(sib, Tag) and sib.name == "a" and sib.get("href"):
                links.append(sib)
        return links

    def _factbox(self, soup, headings):
        for box in soup.select(".factbox"):
            if self._text(box.select_one(".factbox-title")) in headings:
                return box
        return None

    def _label_value(self, soup, labels):
        for p in soup.select(".horing-meta p"):
            text = self._text(p)
            for label in labels:
                if text.startswith(label + ":"):
                    return text.split(":", 1)[1].strip()
        return None

    def _canonical_url(self, soup, source_url):
        link = soup.find("link", rel=lambda v: v and "canonical" in v)
        return urljoin(source_url, link.get("href")) if link and link.get("href") else source_url

    def _id_from_html(self, soup):
        for val in [self._canonical_url(soup, ""), self._text(soup.find("body"))]:
            if m := _ID_RE.search(val):
                return m.group(0)
        return None

    def _parse_date(self, text):
        if m := _DATE_RE.search(text):
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return None

    def _fallback_title(self, soup):
        return self._text(soup.find("title"))

    def _text(self, node):
        return " ".join(node.get_text(" ", strip=True).split()) if node else ""

    def _norm(self, text):
        return text.lower().replace("ø", "o").replace("å", "a").replace("æ", "ae").replace(" ", "-")

    def _provenance(self, field_path, value, *, source_url, source_artifact_uri, selector=None):
        raw = str(value)
        return FieldProvenance(
            field_path=field_path,
            value_hash=f"sha256:{sha256(raw.encode()).hexdigest()}",
            extraction_method="html_selector",
            source_artifact_uri=source_artifact_uri,
            source_url=source_url,
            css_selector=selector,
            extractor_version=self.parser_version,
            extracted_at=datetime.now(UTC),
            confidence=1.0,
        )
