from __future__ import annotations

import re

from riftbound_agg.models import CardEntry, DeckSection

CARD_LINE_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")

SECTION_HEADERS: dict[str, DeckSection] = {
    "main deck": DeckSection.MAIN,
    "main": DeckSection.MAIN,
    "runes": DeckSection.RUNES,
    "rune pool": DeckSection.RUNES,
    "battlefields": DeckSection.BATTLEFIELDS,
    "battlefield": DeckSection.BATTLEFIELDS,
    "sideboard": DeckSection.SIDEBOARD,
    "side": DeckSection.SIDEBOARD,
}


def detect_section(line: str) -> DeckSection | None:
    cleaned = re.sub(r"[:\-#*]", "", line).strip().lower()
    return SECTION_HEADERS.get(cleaned)


def parse_card_line(line: str) -> tuple[int, str] | None:
    m = CARD_LINE_RE.match(line)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None


def parse_decklist_text(text: str) -> list[CardEntry]:
    cards: list[CardEntry] = []
    current_section = DeckSection.MAIN

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        section = detect_section(stripped)
        if section is not None:
            current_section = section
            continue

        parsed = parse_card_line(stripped)
        if parsed:
            qty, name = parsed
            cards.append(CardEntry(name=name, quantity=qty, section=current_section))

    return cards
