"""Deterministic parser for regjeringen.no hearing detail pages."""

from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Literal, cast
from urllib.parse import urlparse

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
from sculpin_regjeringen.parsers.html_common import (
    absolute_url,
    extract_document_id,
    infer_language,
    normalize_whitespace,
    parse_norwegian_date,
)

REGJERINGEN_BASE_URL = "https://www.regjeringen.no/"
AttachmentRole = Literal[
    "hearing_note",
    "hearing_letter",
    "main_document",
    "appendix",
    "report",
    "form",
    "unknown",
]
Language = Literal["nb", "nn", "en", "se", "unknown"]


class HearingPageParser:
    """Parse saved regjeringen.no hearing fixtures into canonical documents."""

    parser_version = "regjeringen-parser-0.3.0"

    def parse(self, html: str, *, source_url: str, source_artifact_uri: str) -> HearingDocument:
        soup = BeautifulSoup(html, "html.parser")
        canonical_url = self._canonical_url(soup, source_url)
        document_id = extract_document_id(canonical_url) or extract_document_id(source_url)
        if document_id is None:
            msg = f"Could not derive regjeringen.no document id from {source_url}"
            raise ValueError(msg)

        title = self._text(soup.select_one("h1")) or self._text(soup.select_one("title"))
        info = soup.select_one(".article-info")
        publication_date = self._publication_date(info)
        departments = self._departments(info)
        summary = self._text(soup.select_one(".article-ingress"))
        status = self._label_value(soup, ["Status"])
        deadline = parse_norwegian_date(
            self._label_value(soup, ["Høringsfrist", "Høyringsfrist"]) or ""
        )
        sections = self._sections(soup, source_url, source_artifact_uri)
        attachments = self._attachments(soup, document_id, source_url, source_artifact_uri)
        recipients = self._recipients(soup, source_url, source_artifact_uri)
        source_links = self._source_links(soup, source_url, source_artifact_uri)
        themes = self._themes(soup, source_url, source_artifact_uri)
        contacts = self._contacts(soup, source_url, source_artifact_uri)
        html_lang = str(soup.html.get("lang")) if soup.html and soup.html.get("lang") else None
        language = cast(Language, infer_language(canonical_url, html_lang=html_lang))

        hearing_note_ids = [
            attachment.attachment_id
            for attachment in attachments
            if attachment.attachment_role == "hearing_note"
        ]
        hearing_letter_section_id = next(
            (
                section.section_id
                for section in sections
                if self._normalized_key(section.heading) in {"horingsbrev", "hoyringsbrev"}
            ),
            None,
        )
        submission_url = next(
            (link.url for link in source_links if link.relation == "submission"), None
        )
        responses_url = next(
            (link.url for link in source_links if link.relation == "hearing_responses"), None
        )

        provenance = self._document_provenance(
            source_url=source_url,
            source_artifact_uri=source_artifact_uri,
            scalars={
                "document_id": document_id,
                "canonical_url": canonical_url,
                "document_type": "hearing",
                "title": title,
                "language": language,
                "publication_date": publication_date,
                "status": status,
                "deadline": deadline,
                "summary": summary,
                "hearing_status": status,
                "hearing_deadline": deadline,
                "hearing_letter_section_id": hearing_letter_section_id,
                "submission_url": submission_url,
                "hearing_responses_url": responses_url,
            },
            departments=departments,
            sections=sections,
            attachments=attachments,
            recipients=recipients,
            themes=themes,
            source_links=source_links,
            contacts=contacts,
            hearing_note_ids=hearing_note_ids,
        )

        return HearingDocument(
            document_id=document_id,
            canonical_url=canonical_url,
            title=title or document_id,
            language=language,
            publication_date=publication_date,
            responsible_departments=departments,
            status=status,
            deadline=deadline,
            summary=summary or None,
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

    def _canonical_url(self, soup: BeautifulSoup, source_url: str) -> str:
        canonical = soup.select_one('link[rel~="canonical"][href]')
        if canonical is not None:
            return absolute_url(source_url, str(canonical.get("href")))

        og_url = soup.select_one('meta[property="og:url"][content]')
        if og_url is not None:
            return absolute_url(source_url, str(og_url.get("content")))

        dc_url = soup.select_one('meta[name="DC.Identifier.URL"][content]')
        if dc_url is not None:
            return absolute_url(REGJERINGEN_BASE_URL, str(dc_url.get("content")))

        return source_url

    def _publication_date(self, info: Tag | None) -> date | None:
        if info is None:
            return None
        return parse_norwegian_date(self._text(info.select_one(".date")))

    def _departments(self, info: Tag | None) -> list[DepartmentRef]:
        if info is None:
            return []
        label = self._text(info.select_one(".owner")).lstrip("| ").strip()
        return [DepartmentRef(label=label)] if label else []

    def _sections(
        self, soup: BeautifulSoup, source_url: str, source_artifact_uri: str
    ) -> list[DocumentSection]:
        sections: list[DocumentSection] = []
        for index, box in enumerate(soup.select(".article-body .factbox")):
            if not isinstance(box, Tag):
                continue
            heading = self._text(box.select_one(".factbox-title"))
            if not heading:
                continue
            visible_text = self._text(box.select_one(".factbox-content"))
            section = DocumentSection(
                section_id=f"section-{index + 1}-{self._normalized_key(heading)}",
                heading=heading,
                heading_path=[heading],
                visible_text=visible_text or None,
                provenance=[
                    self._provenance(
                        f"sections[{index}].heading",
                        heading,
                        source_url=source_url,
                        source_artifact_uri=source_artifact_uri,
                        selector=f".article-body .factbox:nth-of-type({index + 1}) .factbox-title",
                        heading_path=[heading],
                    ),
                    self._provenance(
                        f"sections[{index}].visible_text",
                        visible_text,
                        source_url=source_url,
                        source_artifact_uri=source_artifact_uri,
                        selector=(
                            f".article-body .factbox:nth-of-type({index + 1}) .factbox-content"
                        ),
                        heading_path=[heading],
                    ),
                ],
            )
            sections.append(section)
        return sections

    def _attachments(
        self, soup: BeautifulSoup, document_id: str, source_url: str, source_artifact_uri: str
    ) -> list[Attachment]:
        attachments: list[Attachment] = []
        for link in soup.select(".article-body a[href]"):
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href"))
            url = absolute_url(source_url, href)
            extension = PurePosixPath(urlparse(url).path).suffix.lower().lstrip(".") or None
            if extension not in {"pdf", "doc", "docx", "xls", "xlsx"}:
                continue
            label = self._text(link)
            filename = PurePosixPath(urlparse(url).path).name or None
            heading = self._nearest_factbox_heading(link)
            role = self._attachment_role(
                label=label, filename=filename, extension=extension, heading=heading
            )
            index = len(attachments)
            attachment = Attachment(
                attachment_id=f"{document_id}-attachment-{index + 1}",
                document_id=document_id,
                source_url=url,
                original_label=label,
                original_filename=filename,
                normalized_filename=filename or f"{document_id}-attachment-{index + 1}",
                media_type="application/pdf" if extension == "pdf" else None,
                file_extension=extension,
                checksum_sha256=None,  # TODO: populate in downloader phase after bytes are fetched.
                object_uri=None,  # TODO: populate in downloader/object-storage phase.
                attachment_role=role,
                provenance=[
                    self._provenance(
                        f"attachments[{index}].source_url",
                        url,
                        source_url=source_url,
                        source_artifact_uri=source_artifact_uri,
                        selector=".article-body a[href]",
                        heading_path=[heading] if heading else [],
                    ),
                    self._provenance(
                        f"attachments[{index}].attachment_role",
                        role,
                        source_url=source_url,
                        source_artifact_uri=source_artifact_uri,
                        selector=".article-body .factbox a[href]",
                        heading_path=[heading] if heading else [],
                    ),
                ],
            )
            attachments.append(attachment)
        return attachments

    def _attachment_role(
        self, *, label: str, filename: str | None, extension: str | None, heading: str | None
    ) -> AttachmentRole:
        haystack = self._normalized_key(
            " ".join(part for part in [label, filename, extension, heading] if part)
        )
        if "horingsnotat" in haystack or "hoyringsnotat" in haystack:
            return "hearing_note"
        if "horingsbrev" in haystack or "hoyringsbrev" in haystack:
            return "hearing_letter"
        if "vedlegg" in haystack:
            return "appendix"
        if "skjema" in haystack or "schema" in haystack:
            return "form"
        return "unknown"

    def _recipients(
        self, soup: BeautifulSoup, source_url: str, source_artifact_uri: str
    ) -> list[OrganizationRef]:
        box = self._factbox(soup, ["Høringsinstanser", "Høyringsinstansar"])
        if box is None:
            return []
        recipients: list[OrganizationRef] = []
        for paragraph in box.select(".factbox-content p"):
            label = self._text(paragraph)
            if not label:
                continue
            recipients.append(
                OrganizationRef(
                    label=label,
                    uri=None,
                )
            )
        return recipients

    def _themes(
        self, soup: BeautifulSoup, source_url: str, source_artifact_uri: str
    ) -> list[ThemeRef]:
        return [
            ThemeRef(label=self._text(link), uri=absolute_url(source_url, str(link.get("href"))))
            for link in self._links_after_heading(soup, ["Tema"])
            if self._text(link)
        ]

    def _source_links(
        self, soup: BeautifulSoup, source_url: str, source_artifact_uri: str
    ) -> list[SourceLink]:
        del source_artifact_uri
        related_links = self._links_after_heading(soup, ["Relatert"])
        links: list[SourceLink] = []
        for link in [*soup.select(".article-body a[href]"), *related_links]:
            if not isinstance(link, Tag):
                continue
            label = self._text(link)
            url = absolute_url(source_url, str(link.get("href")))
            relation = self._link_relation(label=label, url=url, is_related=link in related_links)
            if relation is None:
                continue
            if not any(existing.url == url and existing.relation == relation for existing in links):
                links.append(SourceLink(url=url, label=label, relation=relation))
        return links

    def _link_relation(self, *, label: str, url: str, is_related: bool) -> str | None:
        key = self._normalized_key(f"{label} {url}")
        if "registrer_horingsuttalelse" in key or "send-inn" in key:
            return "submission"
        if "horingssvar" in key or "hoyringssvar" in key or "showresponse" in key:
            return "hearing_responses"
        if is_related:
            return "related"
        return None

    def _contacts(
        self, soup: BeautifulSoup, source_url: str, source_artifact_uri: str
    ) -> list[ContactPoint]:
        del source_url, source_artifact_uri
        contacts: list[ContactPoint] = []
        for link in self._links_after_heading(soup, ["Kontakt"]):
            label = self._text(link)
            if not label:
                continue
            href = str(link.get("href", ""))
            contacts.append(
                ContactPoint(
                    label=label,
                    email=href.removeprefix("mailto:") if href.startswith("mailto:") else None,
                )
            )
        return contacts

    def _document_provenance(
        self,
        *,
        source_url: str,
        source_artifact_uri: str,
        scalars: dict[str, object],
        departments: list[DepartmentRef],
        sections: list[DocumentSection],
        attachments: list[Attachment],
        recipients: list[OrganizationRef],
        themes: list[ThemeRef],
        source_links: list[SourceLink],
        contacts: list[ContactPoint],
        hearing_note_ids: list[str],
    ) -> list[FieldProvenance]:
        provenance = [
            self._provenance(
                field_path,
                value,
                source_url=source_url,
                source_artifact_uri=source_artifact_uri,
                selector=self._selector_for_field(field_path),
            )
            for field_path, value in scalars.items()
            if value not in (None, "", [])
        ]
        for index, department in enumerate(departments):
            provenance.append(
                self._provenance(
                    f"responsible_departments[{index}].label",
                    department.label,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector=".article-info .owner",
                )
            )
        for index, section in enumerate(sections):
            provenance.extend(section.provenance)
            provenance.append(
                self._provenance(
                    f"sections[{index}].section_id",
                    section.section_id,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector=".article-body .factbox",
                    heading_path=section.heading_path,
                )
            )
        for index, attachment in enumerate(attachments):
            provenance.extend(attachment.provenance)
            provenance.append(
                self._provenance(
                    f"attachments[{index}].original_label",
                    attachment.original_label,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector=".article-body a[href]",
                )
            )
        for index, recipient in enumerate(recipients):
            provenance.append(
                self._provenance(
                    f"hearing_recipients[{index}].label",
                    recipient.label,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector=".factbox-content p",
                    heading_path=["Høringsinstanser"],
                )
            )
        for index, theme in enumerate(themes):
            provenance.append(
                self._provenance(
                    f"themes[{index}].label",
                    theme.label,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector=(
                        '.content-intro-topics a[href], h2:-soup-contains("Tema") ~ * a[href]'
                    ),
                    heading_path=["Tema"],
                )
            )
            if theme.uri:
                provenance.append(
                    self._provenance(
                        f"themes[{index}].uri",
                        theme.uri,
                        source_url=source_url,
                        source_artifact_uri=source_artifact_uri,
                        selector=(
                            '.content-intro-topics a[href], h2:-soup-contains("Tema") ~ * a[href]'
                        ),
                        heading_path=["Tema"],
                    )
                )
        for index, link in enumerate(source_links):
            provenance.append(
                self._provenance(
                    f"source_links[{index}].url",
                    link.url,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector=".article-body a[href]",
                )
            )
        for index, contact in enumerate(contacts):
            provenance.append(
                self._provenance(
                    f"contacts[{index}].label",
                    contact.label,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector='h2:-soup-contains("Kontakt") ~ * a[href]',
                    heading_path=["Kontakt"],
                )
            )
        for index, attachment_id in enumerate(hearing_note_ids):
            provenance.append(
                self._provenance(
                    f"hearing_note_attachment_ids[{index}]",
                    attachment_id,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    selector=".article-body .factbox a[href]",
                    heading_path=["Høringsnotat"],
                )
            )
        return provenance

    def _selector_for_field(self, field_path: str) -> str | None:
        return {
            "document_id": 'link[rel~="canonical"], meta[property="og:url"], source_url',
            "canonical_url": (
                'link[rel~="canonical"], meta[property="og:url"], meta[name="DC.Identifier.URL"]'
            ),
            "document_type": ".article-info .type",
            "title": "h1",
            "language": "html[lang] + canonical URL path",
            "publication_date": ".article-info .date",
            "status": ".horing-meta p",
            "deadline": ".horing-meta p",
            "summary": ".article-ingress",
            "hearing_status": ".horing-meta p",
            "hearing_deadline": ".horing-meta p",
            "hearing_letter_section_id": ".article-body .factbox .factbox-title",
            "submission_url": ".article-body a[href]",
            "hearing_responses_url": ".article-body a[href]",
        }.get(field_path)

    def _links_after_heading(self, soup: BeautifulSoup, headings: list[str]) -> list[Tag]:
        heading = next(
            (
                candidate
                for candidate in soup.find_all(["h2", "h3"])
                if isinstance(candidate, Tag) and self._text(candidate) in headings
            ),
            None,
        )
        if heading is None:
            return []
        links: list[Tag] = []
        parent_links = (
            heading.parent.find_all("a", href=True) if isinstance(heading.parent, Tag) else []
        )
        for link in parent_links:
            if isinstance(link, Tag):
                links.append(link)
        for sibling in heading.find_all_next():
            if sibling is not heading and getattr(sibling, "name", None) in {"h2", "h3"}:
                break
            if isinstance(sibling, Tag) and sibling.name == "a" and sibling.get("href"):
                links.append(sibling)
        return list(dict.fromkeys(links))

    def _factbox(self, soup: BeautifulSoup, headings: list[str]) -> Tag | None:
        for box in soup.select(".factbox"):
            if isinstance(box, Tag) and self._text(box.select_one(".factbox-title")) in headings:
                return box
        return None

    def _nearest_factbox_heading(self, link: Tag) -> str | None:
        box = link.find_parent(class_="factbox")
        if not isinstance(box, Tag):
            return None
        heading = self._text(box.select_one(".factbox-title"))
        return heading or None

    def _label_value(self, soup: BeautifulSoup, labels: list[str]) -> str | None:
        for paragraph in soup.select(".horing-meta p"):
            text = self._text(paragraph)
            for label in labels:
                marker = f"{label}:"
                if text.startswith(marker):
                    return normalize_whitespace(text.removeprefix(marker))
        return None

    def _text(self, node: Tag | None) -> str:
        return normalize_whitespace(node.get_text(" ", strip=True)) if node is not None else ""

    def _normalized_key(self, text: str) -> str:
        return (
            normalize_whitespace(text)
            .lower()
            .replace("ø", "o")
            .replace("å", "a")
            .replace("æ", "ae")
            .replace(" ", "-")
            .replace("_", "-")
        )

    def _provenance(
        self,
        field_path: str,
        value: object,
        *,
        source_url: str,
        source_artifact_uri: str,
        selector: str | None = None,
        heading_path: list[str] | None = None,
    ) -> FieldProvenance:
        raw = str(value)
        return FieldProvenance(
            field_path=field_path,
            value_hash=f"sha256:{sha256(raw.encode()).hexdigest()}",
            extraction_method="html_selector",
            source_artifact_uri=source_artifact_uri,
            source_url=source_url,
            css_selector=selector,
            heading_path=heading_path or [],
            quote=raw[:500],
            extractor_version=self.parser_version,
            extracted_at=datetime.now(UTC),
            confidence=1.0,
        )
