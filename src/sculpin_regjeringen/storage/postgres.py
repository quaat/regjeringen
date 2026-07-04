"""Deferred PostgreSQL metadata storage adapter."""

from __future__ import annotations


class PostgresMetadataStore:
    """Placeholder for the future service-backed PostgreSQL implementation."""

    def upsert_document(self, document: object) -> None:
        raise NotImplementedError(
            "PostgreSQL persistence is deferred; use LocalJsonMetadataStore for local MVP runs."
        )
