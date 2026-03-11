"""Scrape all 28 legends from riftdecks.com and regenerate web data JSON."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

from riftbound_agg.scraper.riftdecks import RiftDecksScraper
from riftbound_agg.storage.store import save_tournament, load_all_decklists
from riftbound_agg.models import Tournament, DeckSection
from riftbound_agg.analysis.aggregator import aggregate, get_unique_legends

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

LEGEND_SLUGS = [
    "draven-glorious-executioner",
    "irelia-blade-dancer",
    "kaisa-daughter-of-the-void",
    "fiora-grand-duelist",
    "viktor-herald-of-the-arcane",
    "ezreal-prodigal-explorer",
    "azir-emperor-of-the-sands",
    "ornn-fire-below-the-mountain",
    "master-yi-wuju-bladesman",
    "sivir-battle-mistress",
    "lucian-purifier",
    "reksai-void-burrower",
    "annie-dark-child",
    "rumble-mechanized-menace",
    "jax-grandmaster-at-arms",
    "sett-the-boss",
    "renata-glasc-chem-baroness",
    "ahri-nine-tailed-fox",
    "lux-lady-of-luminosity",
    "yasuo-unforgiven",
    "miss-fortune-bounty-hunter",
    "jinx-loose-cannon",
    "teemo-swift-scout",
    "darius-hand-of-noxus",
    "leona-radiant-dawn",
    "lee-sin-blind-monk",
    "volibear-relentless-storm",
    "garen-might-of-demacia",
]

MAX_PAGES = 3
WEB_DATA_PATH = Path("F:/Projects/riftrec/web/public/data.json")

today = date.today().isoformat()


def main() -> None:
    scraper = RiftDecksScraper()
    total_decklists = 0

    print(f"\n{'='*60}")
    print(f"Scraping {len(LEGEND_SLUGS)} legends from riftdecks.com")
    print(f"Date: {today}  |  Max pages per legend: {MAX_PAGES}")
    print(f"{'='*60}\n")

    for i, slug in enumerate(LEGEND_SLUGS, 1):
        print(f"[{i}/{len(LEGEND_SLUGS)}] Scraping {slug} ...")
        decks = scraper.scrape_legend_decks(slug, max_pages=MAX_PAGES)

        tournament = Tournament(
            name=f"riftdecks-{slug}",
            url=f"https://riftdecks.com/legends/constructed/{slug}",
            date=today,
            decklists=decks,
        )
        save_tournament(tournament)

        deck_count = len(decks)
        total_decklists += deck_count
        print(f"    -> {slug}: {deck_count} decks found")

    # --- Regenerate web data JSON ---
    print(f"\n{'='*60}")
    print("Regenerating web data JSON ...")
    print(f"{'='*60}\n")

    all_decklists = load_all_decklists()
    legends = get_unique_legends(all_decklists)

    legend_entries = []
    for legend_name in legends:
        stats = aggregate(all_decklists, legend=legend_name)
        if not stats:
            continue

        # Group cards by section
        sections: dict[str, list[dict]] = {}
        for s in stats:
            sec_name = s.section.value
            if sec_name not in sections:
                sections[sec_name] = []
            sections[sec_name].append(s.to_dict())

        deck_count = stats[0].total_decks if stats else 0
        legend_entries.append({
            "name": legend_name,
            "deck_count": deck_count,
            "sections": sections,
        })

    # Sort by deck_count descending
    legend_entries.sort(key=lambda x: -x["deck_count"])

    output = {"legends": legend_entries}

    WEB_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_DATA_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Saved web data to {WEB_DATA_PATH}")
    print(f"\n{'='*60}")
    print(f"DONE  |  Legends: {len(legend_entries)}  |  Total decklists: {len(all_decklists)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
