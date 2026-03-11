from __future__ import annotations

from abc import ABC, abstractmethod

from riftbound_agg.models import Tournament


class BaseScraper(ABC):
    @abstractmethod
    def scrape_tournament(self, url: str) -> Tournament:
        ...

    @abstractmethod
    def discover_tournaments(self) -> list[dict[str, str]]:
        """Return list of dicts with 'name' and 'url' keys."""
        ...
