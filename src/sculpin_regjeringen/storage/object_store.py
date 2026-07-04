"""Object storage interface for immutable raw and extracted artifacts."""

from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def put_bytes(self, key: str, body: bytes, *, content_type: str | None = None) -> str:
        """Store bytes and return an object URI."""

    def get_bytes(self, uri: str) -> bytes:
        """Load bytes from an object URI."""
