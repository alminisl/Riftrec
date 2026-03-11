from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from riftbound_agg.models import CardEntry, DeckSection, Decklist


@dataclass
class CardStats:
    name: str
    section: DeckSection
    deck_count: int
    total_decks: int
    total_copies: int

    @property
    def inclusion_rate(self) -> float:
        if self.total_decks == 0:
            return 0.0
        return self.deck_count / self.total_decks

    @property
    def avg_copies(self) -> float:
        if self.deck_count == 0:
            return 0.0
        return self.total_copies / self.deck_count

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "section": self.section.value,
            "deck_count": self.deck_count,
            "total_decks": self.total_decks,
            "total_copies": self.total_copies,
            "inclusion_rate": round(self.inclusion_rate, 4),
            "avg_copies": round(self.avg_copies, 2),
        }


def _normalize(name: str) -> str:
    return name.strip().lower()


def _match_champion(decklist: Decklist, champion: str) -> bool:
    return _normalize(decklist.champion) == _normalize(champion)


def _match_legend(decklist: Decklist, legend: str) -> bool:
    return _normalize(decklist.legend) == _normalize(legend)


def aggregate(
    decklists: list[Decklist],
    champion: Optional[str] = None,
    legend: Optional[str] = None,
    section: Optional[DeckSection] = None,
) -> list[CardStats]:
    filtered = decklists
    if champion:
        filtered = [d for d in filtered if _match_champion(d, champion)]
    if legend:
        filtered = [d for d in filtered if _match_legend(d, legend)]

    total_decks = len(filtered)
    if total_decks == 0:
        return []

    # key = (normalized card name, section)
    card_data: dict[tuple[str, DeckSection], dict] = {}

    for deck in filtered:
        cards = deck.cards
        if section:
            cards = [c for c in cards if c.section == section]

        seen_in_deck: set[tuple[str, DeckSection]] = set()
        for card in cards:
            key = (_normalize(card.name), card.section)
            if key not in card_data:
                card_data[key] = {
                    "name": card.name,
                    "section": card.section,
                    "deck_count": 0,
                    "total_copies": 0,
                }
            card_data[key]["total_copies"] += card.quantity
            if key not in seen_in_deck:
                card_data[key]["deck_count"] += 1
                seen_in_deck.add(key)

    stats = [
        CardStats(
            name=v["name"],
            section=v["section"],
            deck_count=v["deck_count"],
            total_decks=total_decks,
            total_copies=v["total_copies"],
        )
        for v in card_data.values()
    ]

    stats.sort(key=lambda s: (-s.inclusion_rate, -s.avg_copies, s.name))
    return stats


def get_unique_champions(decklists: list[Decklist]) -> list[str]:
    seen: dict[str, str] = {}
    for d in decklists:
        key = _normalize(d.champion)
        if key and key != "unknown" and key not in seen:
            seen[key] = d.champion
    return sorted(seen.values())


def get_unique_legends(decklists: list[Decklist]) -> list[str]:
    seen: dict[str, str] = {}
    for d in decklists:
        key = _normalize(d.legend)
        if key and key != "unknown" and key not in seen:
            seen[key] = d.legend
    return sorted(seen.values())
