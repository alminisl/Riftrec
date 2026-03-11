from __future__ import annotations

from typing import Optional

from riftbound_agg.analysis.aggregator import CardStats, aggregate
from riftbound_agg.models import DeckSection, Decklist


TIERS = {
    "staple": (0.80, 1.01),
    "common": (0.50, 0.80),
    "uncommon": (0.20, 0.50),
    "niche": (0.0, 0.20),
}


def _tier_for(rate: float) -> str:
    for tier, (low, high) in TIERS.items():
        if low <= rate < high:
            return tier
    return "niche"


def recommend(
    decklists: list[Decklist],
    champion: Optional[str] = None,
    legend: Optional[str] = None,
    section: Optional[DeckSection] = None,
    top_n: Optional[int] = None,
) -> dict[str, list[dict]]:
    stats = aggregate(decklists, champion=champion, legend=legend, section=section)

    if top_n is not None:
        stats = stats[:top_n]

    result: dict[str, list[dict]] = {
        "staple": [],
        "common": [],
        "uncommon": [],
        "niche": [],
    }

    for s in stats:
        tier = _tier_for(s.inclusion_rate)
        result[tier].append(s.to_dict())

    return result


def recommend_all_sections(
    decklists: list[Decklist],
    champion: Optional[str] = None,
    legend: Optional[str] = None,
    top_n: Optional[int] = None,
) -> dict[str, dict[str, list[dict]]]:
    output: dict[str, dict[str, list[dict]]] = {}
    for sec in DeckSection:
        recs = recommend(
            decklists, champion=champion, legend=legend, section=sec, top_n=top_n
        )
        if any(recs.values()):
            output[sec.value] = recs
    return output
