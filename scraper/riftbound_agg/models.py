from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class DeckSection(enum.Enum):
    MAIN = "Main Deck"
    RUNES = "Runes"
    BATTLEFIELDS = "Battlefields"
    SIDEBOARD = "Sideboard"


@dataclass
class CardEntry:
    name: str
    quantity: int
    section: DeckSection = DeckSection.MAIN

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "section": self.section.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CardEntry:
        return cls(
            name=d["name"],
            quantity=d["quantity"],
            section=DeckSection(d["section"]),
        )


@dataclass
class Decklist:
    player: str
    champion: str
    legend: str
    cards: list[CardEntry] = field(default_factory=list)
    placement: Optional[str] = None

    @property
    def main_deck(self) -> list[CardEntry]:
        return [c for c in self.cards if c.section == DeckSection.MAIN]

    @property
    def runes(self) -> list[CardEntry]:
        return [c for c in self.cards if c.section == DeckSection.RUNES]

    @property
    def battlefields(self) -> list[CardEntry]:
        return [c for c in self.cards if c.section == DeckSection.BATTLEFIELDS]

    @property
    def sideboard(self) -> list[CardEntry]:
        return [c for c in self.cards if c.section == DeckSection.SIDEBOARD]

    def to_dict(self) -> dict:
        return {
            "player": self.player,
            "champion": self.champion,
            "legend": self.legend,
            "cards": [c.to_dict() for c in self.cards],
            "placement": self.placement,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Decklist:
        return cls(
            player=d["player"],
            champion=d["champion"],
            legend=d["legend"],
            cards=[CardEntry.from_dict(c) for c in d["cards"]],
            placement=d.get("placement"),
        )


@dataclass
class Tournament:
    name: str
    url: str
    date: str
    decklists: list[Decklist] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "date": self.date,
            "decklists": [dl.to_dict() for dl in self.decklists],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Tournament:
        return cls(
            name=d["name"],
            url=d["url"],
            date=d["date"],
            decklists=[Decklist.from_dict(dl) for dl in d["decklists"]],
        )
