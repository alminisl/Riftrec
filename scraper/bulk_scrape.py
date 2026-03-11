"""Bulk scrape ALL decks from riftdecks.com and regenerate web data."""

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from riftbound_agg.models import CardEntry, DeckSection, Decklist, Tournament
from riftbound_agg.storage.store import save_tournament
from riftbound_agg.analysis.aggregator import aggregate, get_unique_legends

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
BASE = "https://riftdecks.com"

SECTION_MAP = {
    "legend": DeckSection.MAIN,
    "champion": DeckSection.MAIN,
    "unit": DeckSection.MAIN,
    "gear": DeckSection.MAIN,
    "spell": DeckSection.MAIN,
    "battlefields": DeckSection.BATTLEFIELDS,
    "battlefield": DeckSection.BATTLEFIELDS,
    "runes": DeckSection.RUNES,
    "rune": DeckSection.RUNES,
    "sideboard": DeckSection.SIDEBOARD,
}
SECTION_RE = re.compile(r"^([a-z]+(?:\s[a-z]+)?)\s*\(\d+\)$", re.IGNORECASE)


def fetch(url: str, retries: int = 2) -> str:
    """Fetch URL using curl."""
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(
                ["curl", "-s", "-L", "-H", f"User-Agent: {UA}",
                 "--max-time", "20", url],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=25,
            )
            if r.returncode == 0 and r.stdout and "Just a moment..." not in r.stdout[:500]:
                return r.stdout
        except subprocess.TimeoutExpired:
            pass
        if attempt < retries:
            time.sleep(2)
    return ""


def collect_deck_urls(max_pages: int = 999) -> list[str]:
    """Crawl listing pages to collect all deck URLs."""
    urls = []
    seen = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE}/riftbound-decks?metagame_id=2&page={page}"
        if page % 25 == 0 or page == 1:
            print(f"  Listing page {page}...", flush=True)

        html = fetch(url)
        if not html:
            print(f"  Failed page {page}, stopping.", flush=True)
            break

        soup = BeautifulSoup(html, "html.parser")
        found = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/riftbound-metagame/deck-" in href:
                full = href if href.startswith("http") else f"{BASE}{href}"
                if full not in seen:
                    seen.add(full)
                    urls.append(full)
                    found += 1

        if found == 0:
            print(f"  No new decks on page {page}, stopping.", flush=True)
            break

        # Delay between listing pages to avoid Cloudflare
        time.sleep(0.4)

    return urls


def parse_deck_page(html: str) -> Decklist | None:
    """Parse a deck page HTML into a Decklist."""
    soup = BeautifulSoup(html, "html.parser")
    deck_area = soup.find("div", class_="deck-content-area")
    if not deck_area:
        return None

    text = deck_area.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    cards = []
    legend_name = "Unknown"
    champion_name = "Unknown"
    section = DeckSection.MAIN
    section_key = ""
    i = 0

    while i < len(lines):
        line = lines[i]

        m = SECTION_RE.match(line)
        if m:
            section_key = m.group(1).lower()
            section = SECTION_MAP.get(section_key, DeckSection.MAIN)
            i += 1
            continue

        if line.isdigit() and i + 1 < len(lines):
            qty = int(line)
            name = lines[i + 1]
            skip = 2
            if i + 2 < len(lines) and lines[i + 2].startswith("$"):
                skip = 3
            if section_key == "legend":
                legend_name = name
            elif section_key == "champion":
                champion_name = name
            cards.append(CardEntry(name=name, quantity=qty, section=section))
            i += skip
            continue

        sm = re.match(r"^(\d+)\s+(.+)$", line)
        if sm:
            qty = int(sm.group(1))
            name = re.sub(r"\s*\$[\d.]+\s*$", "", sm.group(2).strip())
            if section_key == "legend":
                legend_name = name
            elif section_key == "champion":
                champion_name = name
            cards.append(CardEntry(name=name, quantity=qty, section=section))
            i += 1
            continue

        i += 1

    if not cards:
        return None

    # Player name from metadata
    player = "Unknown"
    meta = soup.find("div", class_=lambda c: c and "card" in c and "mt-4" in c if isinstance(c, str) else False)
    if not meta:
        for div in soup.find_all("div"):
            cls = div.get("class", [])
            if "card" in cls and "mt-4" in cls:
                meta = div
                break
    if meta:
        deck_name_el = meta.find("strong") or meta.find("h3") or meta.find("h4")
        if deck_name_el:
            player = deck_name_el.get_text(strip=True)[:100]

    return Decklist(
        player=player,
        champion=champion_name,
        legend=legend_name,
        cards=cards,
    )


def scrape_one(url: str) -> Decklist | None:
    """Fetch and parse a single deck URL."""
    html = fetch(url)
    if not html:
        return None
    try:
        return parse_deck_page(html)
    except Exception as e:
        return None


def main():
    print("=== RiftDecks Bulk Scraper ===", flush=True)
    print(f"Collecting deck URLs from listing pages...", flush=True)
    deck_urls = collect_deck_urls()
    print(f"Found {len(deck_urls)} unique deck URLs.", flush=True)

    print(f"\nScraping individual deck pages (5 concurrent)...", flush=True)
    decklists = []
    errors = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(scrape_one, url): url for url in deck_urls}
        for i, future in enumerate(as_completed(futures), 1):
            dl = future.result()
            if dl:
                decklists.append(dl)
            else:
                errors += 1

            if i % 100 == 0:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (len(deck_urls) - i) / rate if rate > 0 else 0
                print(
                    f"  {i}/{len(deck_urls)} scraped, "
                    f"{len(decklists)} ok, {errors} failed, "
                    f"{rate:.1f}/s, ETA {eta/60:.0f}m",
                    flush=True,
                )

    elapsed = time.time() - start
    print(f"\nDone scraping: {len(decklists)} decklists in {elapsed/60:.1f} min ({errors} failed)")

    # Group by legend and save as tournaments
    by_legend: dict[str, list[Decklist]] = {}
    for dl in decklists:
        key = dl.legend.strip()
        if key and key != "Unknown":
            by_legend.setdefault(key, []).append(dl)

    # Clear old riftdecks files
    data_dir = Path(__file__).parent / "data" / "tournaments"
    for f in data_dir.glob("riftdecks-*.json"):
        f.unlink()

    for legend, decks in sorted(by_legend.items()):
        slug = re.sub(r"[^a-z0-9]+", "-", legend.lower()).strip("-")
        t = Tournament(
            name=f"riftdecks-{slug}",
            url=f"{BASE}/legends/constructed/{slug}",
            date=date.today().isoformat(),
            decklists=decks,
        )
        save_tournament(t)
        print(f"  {legend}: {len(decks)} decks")

    # Regenerate web data
    print("\nRegenerating web data...", flush=True)
    from riftbound_agg.storage.store import load_all_decklists

    all_decklists = load_all_decklists()
    legends = get_unique_legends(all_decklists)

    result = {"legends": []}
    for legend in legends:
        stats = aggregate(all_decklists, legend=legend)
        filtered = [d for d in all_decklists if d.legend.strip().lower() == legend.strip().lower()]
        sections = {}
        for s in stats:
            sec = s.section.value
            sections.setdefault(sec, []).append(s.to_dict())

        result["legends"].append({
            "name": legend,
            "deck_count": len(filtered),
            "sections": sections,
        })

    result["legends"].sort(key=lambda x: -x["deck_count"])

    out = Path(__file__).parent.parent / "web" / "public" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = sum(l["deck_count"] for l in result["legends"])
    print(f"\nFinal: {len(result['legends'])} legends, {total} decklists")
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
