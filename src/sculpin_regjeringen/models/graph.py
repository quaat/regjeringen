"""Graph export payload models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GraphNamespace(BaseModel):
    prefix: str
    iri: str


class Triple(BaseModel):
    subject: str
    predicate: str
    object: str
    object_type: Literal["iri", "literal"] = "iri"
    datatype: str | None = None
    language: str | None = None


class GraphExport(BaseModel):
    document_id: str
    namespaces: list[GraphNamespace] = Field(default_factory=list)
    triples: list[Triple] = Field(default_factory=list)
