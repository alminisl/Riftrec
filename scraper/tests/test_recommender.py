from riftbound_agg.analysis.recommender import _tier_for, recommend
from riftbound_agg.models import CardEntry, DeckSection, Decklist


def _make_decks(n_decks, cards_per_deck):
    decks = []
    for i in range(n_decks):
        cards_for_this_deck = cards_per_deck[i] if i < len(cards_per_deck) else []
        decks.append(
            Decklist(
                player=f"Player{i}",
                champion="Draven",
                legend="Garen",
                cards=[
                    CardEntry(name=n, quantity=q, section=DeckSection.MAIN)
                    for n, q in cards_for_this_deck
                ],
            )
        )
    return decks


def test_tier_for():
    assert _tier_for(1.0) == "staple"
    assert _tier_for(0.80) == "staple"
    assert _tier_for(0.79) == "common"
    assert _tier_for(0.50) == "common"
    assert _tier_for(0.49) == "uncommon"
    assert _tier_for(0.20) == "uncommon"
    assert _tier_for(0.19) == "niche"
    assert _tier_for(0.0) == "niche"


def test_recommend_tiers():
    # 10 decks, Card A in all 10 (staple), Card B in 5 (common), Card C in 1 (niche)
    cards_per_deck = []
    for i in range(10):
        cards = [("Card A", 4)]
        if i < 5:
            cards.append(("Card B", 2))
        if i == 0:
            cards.append(("Card C", 1))
        cards_per_deck.append(cards)

    decks = _make_decks(10, cards_per_deck)
    recs = recommend(decks, champion="Draven", section=DeckSection.MAIN)

    assert len(recs["staple"]) == 1
    assert recs["staple"][0]["name"] == "Card A"
    assert len(recs["common"]) == 1
    assert recs["common"][0]["name"] == "Card B"
    assert len(recs["niche"]) == 1


def test_recommend_top_n():
    cards_per_deck = [[("Card A", 4), ("Card B", 3), ("Card C", 2)] for _ in range(5)]
    decks = _make_decks(5, cards_per_deck)
    recs = recommend(decks, champion="Draven", section=DeckSection.MAIN, top_n=2)

    total_cards = sum(len(v) for v in recs.values())
    assert total_cards == 2


def test_recommend_empty():
    recs = recommend([], champion="Nobody", section=DeckSection.MAIN)
    assert all(len(v) == 0 for v in recs.values())
