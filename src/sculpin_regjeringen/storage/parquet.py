"""Analytical dataset export placeholder."""

from __future__ import annotations


class ParquetExporter:
    def write_documents(self, documents: list[object], output_dir: str) -> None:
        raise NotImplementedError("Parquet export is optional after the MVP.")
