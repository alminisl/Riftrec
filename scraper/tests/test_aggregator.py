from riftbound_agg.analysis.aggregator import (
    aggregate,
    get_unique_champions,
    get_unique_legends,
)
from riftbound_agg.models import CardEntry, DeckSection, Decklist


def _make_decklist(champion, legend, cards):
    return Decklist(
        player="Player",
        champion=champion,
        legend=legend,
        cards=[CardEntry(name=n, quantity=q, section=s) for n, q, s in cards],
    )


def test_aggregate_basic():
    decks = [
        _make_decklist("Draven", "Garen", [
            ("Card A", 4, DeckSection.MAIN),
            ("Card B", 2, DeckSection.MAIN),
        ]),
        _make_decklist("Draven", "Garen", [
            ("Card A", 3, DeckSection.MAIN),
            ("Card C", 1, DeckSection.MAIN),
        ]),
    ]
    stats = aggregate(decks, champion="Draven")
    assert len(stats) == 3

    card_a = next(s for s in stats if s.name.lower() == "card a")
    assert card_a.deck_count == 2
    assert card_a.total_decks == 2
    assert card_a.inclusion_rate == 1.0
    assert card_a.avg_copies == 3.5


def test_aggregate_filter_by_champion():
    decks = [
        _make_decklist("Draven", "Garen", [("Card A", 4, DeckSection.MAIN)]),
        _make_decklist("Jinx", "Garen", [("Card B", 2, DeckSection.MAIN)]),
    ]
    stats = aggregate(decks, champion="Draven")
    assert len(stats) == 1
    assert stats[0].name == "Card A"


def test_aggregate_filter_by_legend():
    decks = [
        _make_decklist("Draven", "Garen", [("Card A", 4, DeckSection.MAIN)]),
        _make_decklist("Draven", "Lux", [("Card B", 2, DeckSection.MAIN)]),
    ]
    stats = aggregate(decks, legend="Garen")
    assert len(stats) == 1
    assert stats[0].name == "Card A"


def test_aggregate_filter_by_section():
    decks = [
        _make_decklist("Draven", "Garen", [
            ("Card A", 4, DeckSection.MAIN),
            ("Card B", 2, DeckSection.SIDEBOARD),
        ]),
    ]
    stats = aggregate(decks, section=DeckSection.SIDEBOARD)
    assert len(stats) == 1
    assert stats[0].name == "Card B"


def test_aggregate_empty():
    assert aggregate([], champion="Nobody") == []


def test_aggregate_case_insensitive():
    decks = [
        _make_decklist("draven", "garen", [("Card A", 4, DeckSection.MAIN)]),
    ]
    stats = aggregate(decks, champion="Draven")
    assert len(stats) == 1


def test_get_unique_champions():
    decks = [
        _make_decklist("Draven", "Garen", []),
        _make_decklist("draven", "Lux", []),
        _make_decklist("Jinx", "Garen", []),
        _make_decklist("Unknown", "Unknown", []),
    ]
    champs = get_unique_champions(decks)
    assert len(champs) == 2
    assert "Jinx" in champs


def test_get_unique_legends():
    decks = [
        _make_decklist("Draven", "Garen", []),
        _make_decklist("Jinx", "garen", []),
        _make_decklist("Jinx", "Lux", []),
    ]
    legends = get_unique_legends(decks)
    assert len(legends) == 2
