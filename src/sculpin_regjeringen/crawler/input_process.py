"""Input process category discovery placeholder."""

from __future__ import annotations


class InputCrawler:
    async def discover(self, crawl_batch_id: str) -> list[object]:
        raise NotImplementedError("Input process discovery is planned after the hearing MVP.")
