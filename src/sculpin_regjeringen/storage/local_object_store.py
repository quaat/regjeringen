"""Filesystem-backed immutable object store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from sculpin_regjeringen.storage.object_store import ObjectStore


@dataclass(frozen=True, slots=True)
class StoredObject:
    uri: str
    checksum_sha256: str
    size_bytes: int
    content_type: str | None


class LocalObjectStore(ObjectStore):
    """Content-addressed local object storage using SHA-256."""

    def __init__(self, root: Path, *, uri_root: str | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.uri_root = uri_root.rstrip("/") if uri_root else self.root.resolve().as_uri()

    def put_bytes(self, key: str, body: bytes, *, content_type: str | None = None) -> str:
        return self.put_object(key, body, content_type=content_type).uri

    def put_object(self, key: str, body: bytes, *, content_type: str | None = None) -> StoredObject:
        checksum = sha256(body).hexdigest()
        relative_path = self._relative_path(checksum, key)
        object_path = self.root / relative_path
        metadata_path = object_path.with_suffix(object_path.suffix + ".metadata.json")
        object_path.parent.mkdir(parents=True, exist_ok=True)
        if not object_path.exists():
            object_path.write_bytes(body)
        metadata = {
            "key": key,
            "checksum_sha256": checksum,
            "size_bytes": len(body),
            "content_type": content_type,
            "stored_at": datetime.now(UTC).isoformat(),
        }
        if not metadata_path.exists():
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        return StoredObject(
            uri=f"{self.uri_root}/{relative_path.as_posix()}",
            checksum_sha256=checksum,
            size_bytes=len(body),
            content_type=content_type,
        )

    def get_bytes(self, uri: str) -> bytes:
        parsed = urlparse(uri)
        if parsed.scheme == "file":
            return Path(parsed.path).read_bytes()
        prefix = f"{self.uri_root}/"
        if not uri.startswith(prefix):
            msg = f"URI is outside this object store: {uri}"
            raise ValueError(msg)
        return (self.root / uri.removeprefix(prefix)).read_bytes()

    def _relative_path(self, checksum: str, key: str) -> Path:
        suffix = Path(key).suffix or ".bin"
        return Path("sha256") / checksum[:2] / checksum[2:4] / f"{checksum}{suffix}"
