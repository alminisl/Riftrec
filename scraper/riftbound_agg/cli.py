from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

# Fix Windows console encoding for non-ASCII characters
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

from requests.exceptions import RequestException

from riftbound_agg.analysis.aggregator import (
    aggregate,
    get_unique_champions,
    get_unique_legends,
)
from riftbound_agg.analysis.recommender import recommend, recommend_all_sections
from riftbound_agg.models import DeckSection
from riftbound_agg.output.formatter import format_output
from riftbound_agg.scraper.official import OfficialScraper
from riftbound_agg.scraper.riftdecks import RiftDecksScraper
from riftbound_agg.storage.store import (
    list_tournaments,
    load_all_decklists,
    save_tournament,
)

ALLOWED_EXPORT_SUFFIXES = {".txt", ".csv", ".json"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riftbound_agg",
        description="Riftbound Deck Aggregator — EDHREC for Riftbound",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # scrape
    scrape_p = sub.add_parser("scrape", help="Scrape tournament decklists")
    scrape_p.add_argument("url", nargs="?", help="Tournament URL to scrape")
    scrape_p.add_argument(
        "--discover",
        action="store_true",
        help="Discover and list available tournaments",
    )
    scrape_p.add_argument(
        "--source",
        choices=["official", "riftdecks"],
        default="official",
        help="Source site to scrape from (default: official)",
    )
    scrape_p.add_argument(
        "--legend",
        type=str,
        default=None,
        help="Legend slug for riftdecks source (e.g. volibear-relentless-storm)",
    )
    scrape_p.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Max pages to scrape for riftdecks legend listing (default: 1)",
    )

    # list
    list_p = sub.add_parser("list", help="List stored data")
    list_p.add_argument(
        "what",
        choices=["champions", "legends", "tournaments"],
        help="What to list",
    )

    # recommend
    rec_p = sub.add_parser("recommend", help="Get card recommendations")
    rec_p.add_argument("name", help="Champion or legend name")
    rec_p.add_argument(
        "--legend",
        action="store_true",
        help="Treat name as a legend instead of champion",
    )
    rec_p.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        dest="fmt",
        help="Output format (default: table)",
    )
    rec_p.add_argument(
        "--section",
        choices=["main", "runes", "battlefields", "sideboard"],
        help="Filter to a specific deck section",
    )
    rec_p.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit to top N cards",
    )
    rec_p.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export output to file",
    )

    # stats
    sub.add_parser("stats", help="Show overall statistics")

    return parser


SECTION_MAP = {
    "main": DeckSection.MAIN,
    "runes": DeckSection.RUNES,
    "battlefields": DeckSection.BATTLEFIELDS,
    "sideboard": DeckSection.SIDEBOARD,
}


def cmd_scrape(args: argparse.Namespace) -> None:
    if args.source == "riftdecks":
        _cmd_scrape_riftdecks(args)
    else:
        _cmd_scrape_official(args)


def _cmd_scrape_official(args: argparse.Namespace) -> None:
    scraper = OfficialScraper()

    if args.discover:
        print("Discovering tournaments...")
        tournaments = scraper.discover_tournaments()
        if not tournaments:
            print("No tournaments found.")
            return
        for i, t in enumerate(tournaments, 1):
            print(f"  {i}. {t['name']}")
            print(f"     {t['url']}")
        return

    if not args.url:
        print("Error: provide a URL or use --discover", file=sys.stderr)
        sys.exit(1)

    print(f"Scraping: {args.url}")
    try:
        tournament = scraper.scrape_tournament(args.url)
    except ValueError as e:
        print(f"Invalid input: {e}", file=sys.stderr)
        sys.exit(1)
    except RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        sys.exit(1)

    path = save_tournament(tournament)
    print(f"Saved: {path}")
    print(f"  Tournament: {tournament.name}")
    print(f"  Date: {tournament.date}")
    print(f"  Decklists: {len(tournament.decklists)}")
    for dl in tournament.decklists:
        print(f"    - {dl.player}: {dl.champion} / {dl.legend} ({len(dl.cards)} cards)")


def _cmd_scrape_riftdecks(args: argparse.Namespace) -> None:
    from datetime import date as date_cls

    from riftbound_agg.models import Tournament

    scraper = RiftDecksScraper()

    if args.url:
        # Scrape a single deck URL
        print(f"Scraping deck from riftdecks: {args.url}")
        try:
            dl = scraper.scrape_deck(args.url)
        except ValueError as e:
            print(f"Invalid input: {e}", file=sys.stderr)
            sys.exit(1)
        except RequestException as e:
            print(f"Network error: {e}", file=sys.stderr)
            sys.exit(1)

        if not dl:
            print("Could not parse deck from page.", file=sys.stderr)
            sys.exit(1)

        tournament = Tournament(
            name=f"riftdecks-{dl.legend}",
            url=args.url,
            date=date_cls.today().isoformat(),
            decklists=[dl],
        )
        path = save_tournament(tournament)
        print(f"Saved: {path}")
        print(f"  Deck: {dl.player}: {dl.champion} / {dl.legend} ({len(dl.cards)} cards)")
        return

    if not args.legend:
        print(
            "Error: provide --legend <slug> or a deck URL when using --source riftdecks",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Scraping riftdecks legend: {args.legend} (max {args.max_pages} pages)")
    try:
        decklists = scraper.scrape_legend_decks(
            args.legend, max_pages=args.max_pages
        )
    except ValueError as e:
        print(f"Invalid input: {e}", file=sys.stderr)
        sys.exit(1)
    except RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        sys.exit(1)

    if not decklists:
        print("No decklists found.")
        return

    tournament = Tournament(
        name=f"riftdecks-{args.legend}",
        url=f"https://riftdecks.com/legends/constructed/{args.legend}",
        date=date_cls.today().isoformat(),
        decklists=decklists,
    )
    path = save_tournament(tournament)
    print(f"Saved: {path}")
    print(f"  Source: riftdecks.com")
    print(f"  Legend: {args.legend}")
    print(f"  Decklists: {len(decklists)}")
    for dl in decklists:
        print(f"    - {dl.player}: {dl.champion} / {dl.legend} ({len(dl.cards)} cards)")


def cmd_list(args: argparse.Namespace) -> None:
    decklists = load_all_decklists()

    if args.what == "tournaments":
        tournaments = list_tournaments()
        if not tournaments:
            print("No tournaments stored. Use 'scrape' to add some.")
            return
        for t in tournaments:
            print(f"  {t.name} ({t.date}) — {len(t.decklists)} decks")
            print(f"    {t.url}")
        return

    if not decklists:
        print("No decklists stored. Use 'scrape' to add some.")
        return

    if args.what == "champions":
        champions = get_unique_champions(decklists)
        print(f"Champions ({len(champions)}):")
        for c in champions:
            count = sum(1 for d in decklists if d.champion.lower() == c.lower())
            print(f"  {c} ({count} decks)")

    elif args.what == "legends":
        legends = get_unique_legends(decklists)
        print(f"Legends ({len(legends)}):")
        for lg in legends:
            count = sum(1 for d in decklists if d.legend.lower() == lg.lower())
            print(f"  {lg} ({count} decks)")


def cmd_recommend(args: argparse.Namespace) -> None:
    decklists = load_all_decklists()
    if not decklists:
        print("No decklists stored. Use 'scrape' to add some.")
        return

    champion = None if args.legend else args.name
    legend = args.name if args.legend else None
    section = SECTION_MAP.get(args.section) if args.section else None
    title = f"Recommendations for {args.name}"

    if section:
        recs = recommend(
            decklists,
            champion=champion,
            legend=legend,
            section=section,
            top_n=args.top,
        )
    else:
        recs = recommend_all_sections(
            decklists,
            champion=champion,
            legend=legend,
            top_n=args.top,
        )

    output = format_output(recs, fmt=args.fmt, title=title)

    if args.export:
        export_path = Path(args.export).resolve()
        if export_path.suffix not in ALLOWED_EXPORT_SUFFIXES:
            print(
                f"Error: export file must be one of {ALLOWED_EXPORT_SUFFIXES}",
                file=sys.stderr,
            )
            sys.exit(1)
        export_path.write_text(output)
        print(f"Exported to {export_path}")
    else:
        print(output)


def cmd_stats(args: argparse.Namespace) -> None:
    tournaments = list_tournaments()
    decklists = load_all_decklists()
    champions = get_unique_champions(decklists)
    legends = get_unique_legends(decklists)

    total_cards = set()
    for d in decklists:
        for c in d.cards:
            total_cards.add(c.name.lower())

    print("Riftbound Deck Aggregator — Statistics")
    print(f"  Tournaments:    {len(tournaments)}")
    print(f"  Decklists:      {len(decklists)}")
    print(f"  Champions:      {len(champions)}")
    print(f"  Legends:        {len(legends)}")
    print(f"  Unique cards:   {len(total_cards)}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "scrape": cmd_scrape,
        "list": cmd_list,
        "recommend": cmd_recommend,
        "stats": cmd_stats,
    }
    commands[args.command](args)
