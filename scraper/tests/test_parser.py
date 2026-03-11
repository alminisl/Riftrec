from riftbound_agg.models import DeckSection
from riftbound_agg.scraper.parser import (
    detect_section,
    parse_card_line,
    parse_decklist_text,
)


def test_parse_card_line_basic():
    assert parse_card_line("4 Lightning Bolt") == (4, "Lightning Bolt")


def test_parse_card_line_with_leading_spaces():
    assert parse_card_line("  2 Mystic Shot") == (2, "Mystic Shot")


def test_parse_card_line_trailing_spaces():
    assert parse_card_line("3 Some Card   ") == (3, "Some Card")


def test_parse_card_line_no_match():
    assert parse_card_line("Main Deck") is None
    assert parse_card_line("") is None
    assert parse_card_line("---") is None


def test_detect_section_main():
    assert detect_section("Main Deck") == DeckSection.MAIN
    assert detect_section("Main") == DeckSection.MAIN
    assert detect_section("# Main Deck #") == DeckSection.MAIN


def test_detect_section_runes():
    assert detect_section("Runes") == DeckSection.RUNES
    assert detect_section("Runes:") == DeckSection.RUNES


def test_detect_section_battlefields():
    assert detect_section("Battlefields") == DeckSection.BATTLEFIELDS
    assert detect_section("Battlefield") == DeckSection.BATTLEFIELDS


def test_detect_section_sideboard():
    assert detect_section("Sideboard") == DeckSection.SIDEBOARD
    assert detect_section("Side") == DeckSection.SIDEBOARD


def test_detect_section_none():
    assert detect_section("4 Lightning Bolt") is None
    assert detect_section("Random text") is None


def test_parse_decklist_text_simple():
    text = """Main Deck
4 Lightning Bolt
3 Mystic Shot
2 Flash

Sideboard
2 Negate
1 Counterspell
"""
    cards = parse_decklist_text(text)
    assert len(cards) == 5
    assert cards[0].name == "Lightning Bolt"
    assert cards[0].quantity == 4
    assert cards[0].section == DeckSection.MAIN
    assert cards[3].name == "Negate"
    assert cards[3].section == DeckSection.SIDEBOARD


def test_parse_decklist_text_no_section_header():
    text = """4 Card A
3 Card B
"""
    cards = parse_decklist_text(text)
    assert len(cards) == 2
    assert all(c.section == DeckSection.MAIN for c in cards)


def test_parse_decklist_text_all_sections():
    text = """Main Deck
4 Card A

Runes
2 Rune X

Battlefields
1 Field Y

Sideboard
3 Side Z
"""
    cards = parse_decklist_text(text)
    sections = {c.section for c in cards}
    assert sections == {DeckSection.MAIN, DeckSection.RUNES, DeckSection.BATTLEFIELDS, DeckSection.SIDEBOARD}


def test_parse_decklist_text_empty():
    assert parse_decklist_text("") == []
    assert parse_decklist_text("\n\n\n") == []
