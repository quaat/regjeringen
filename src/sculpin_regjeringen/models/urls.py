"""URL validation adapters for Pydantic URL-bearing models."""

from __future__ import annotations

from pydantic import AnyUrl, HttpUrl, TypeAdapter

_ANY_URL_ADAPTER = TypeAdapter(AnyUrl)
_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


def any_url(value: str) -> AnyUrl:
    """Validate and return a Pydantic AnyUrl."""

    return _ANY_URL_ADAPTER.validate_python(value)


def http_url(value: str) -> HttpUrl:
    """Validate and return a Pydantic HttpUrl."""

    return _HTTP_URL_ADAPTER.validate_python(value)
