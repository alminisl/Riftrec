"""
Bulk scrape ALL decks from riftdecks.com (deck_type=all).

Features:
- Two-phase approach: listing pages -> individual deck pages
- Resumable: saves progress to disk after each batch
- Smart rate limiting with exponential backoff
- Cloudflare bypass via FlareSolverr / browser cookies
- Incremental saves so no work is lost on crash

Usage:
    python bulk_scrape_v3.py                  # Run both phases
    python bulk_scrape_v3.py --phase listings  # Only collect deck URLs from listing pages
    python bulk_scrape_v3.py --phase details   # Only scrape individual deck pages
    python bulk_scrape_v3.py --reset           # Clear progress and start fresh
    python bulk_scrape_v3.py --delay 2.0       # Set delay between requests (default: 1.0s)
    python bulk_scrape_v3.py --workers 2       # Set concurrent workers (default: 1)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from threading import Lock

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).parent))

from riftbound_agg.models import CardEntry, DeckSection, Decklist, Tournament
from riftbound_agg.storage.store import save_tournament
from riftbound_agg.analysis.aggregator import aggregate, get_unique_legends

BASE = "https://riftdecks.com"
FLARESOLVERR = "http://localhost:8191/v1"
COOKIE_FILE = Path(__file__).parent / "cf_cookies.json"
PROGRESS_DIR = Path(__file__).parent / "data" / "scrape_progress"

# Where we store intermediate results
LISTINGS_FILE = PROGRESS_DIR / "deck_listings.json"
DETAILS_DIR = PROGRESS_DIR / "deck_details"
PROGRESS_FILE = PROGRESS_DIR / "progress.json"

SECTION_MAP = {
    "legend": DeckSection.MAIN, "champion": DeckSection.MAIN,
    "unit": DeckSection.MAIN, "gear": DeckSection.MAIN,
    "spell": DeckSection.MAIN, "battlefields": DeckSection.BATTLEFIELDS,
    "battlefield": DeckSection.BATTLEFIELDS, "runes": DeckSection.RUNES,
    "rune": DeckSection.RUNES, "sideboard": DeckSection.SIDEBOARD,
}
SECTION_RE = re.compile(r"^([a-z]+(?:\s[a-z]+)?)\s*\(\d+\)$", re.IGNORECASE)

# Rate limiting state
_request_lock = Lock()
_last_request_time = 0.0
_base_delay = 1.0


def set_base_delay(delay: float):
    global _base_delay
    _base_delay = delay


def _rate_limit():
    """Enforce minimum delay between requests."""
    global _last_request_time
    with _request_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _base_delay:
            time.sleep(_base_delay - elapsed + random.uniform(0, 0.3))
        _last_request_time = time.time()


def ensure_dirs():
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {
        "listing_page": 0,
        "total_listings": 0,
        "details_scraped": [],
        "details_failed": [],
    }


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def load_listings() -> list[dict]:
    if LISTINGS_FILE.exists():
        return json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
    return []


def save_listings(listings: list[dict]):
    LISTINGS_FILE.write_text(
        json.dumps(listings, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Cookie / fetch helpers (adapted from v2)
# ---------------------------------------------------------------------------

def get_cf_cookies_from_browser() -> tuple[str, str]:
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name=".riftdecks.com")
        cookie_str = "; ".join(f"{c.name}={c.value}" for c in cj)
        if cookie_str:
            ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36")
            print(f"  Got cookies from Chrome browser.", flush=True)
            return cookie_str, ua
    except Exception as e:
        print(f"  browser_cookie3 failed: {e}", flush=True)
    return "", ""


def get_cf_cookies() -> tuple[str, str]:
    """Get Cloudflare cookies via FlareSolverr, browser, or saved file."""
    # Try FlareSolverr first
    print("Getting Cloudflare cookies via FlareSolverr...", flush=True)
    try:
        r = requests.post(FLARESOLVERR, json={
            "cmd": "request.get",
            "url": f"{BASE}/riftbound-decks?deck_type=all",
            "maxTimeout": 60000,
        }, timeout=90)
        data = r.json()
        if data.get("status") == "ok" and "solution" in data:
            sol = data["solution"]
            cookies = sol.get("cookies", [])
            ua = sol.get("userAgent", "")
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
            print(f"  Got {len(cookies)} cookies via FlareSolverr.", flush=True)
            with open(COOKIE_FILE, "w") as f:
                json.dump({"cookies": cookie_str, "ua": ua}, f)
            return cookie_str, ua
        else:
            print(f"  FlareSolverr error: {data.get('message', 'unknown')[:100]}", flush=True)
    except Exception as e:
        print(f"  FlareSolverr unavailable: {e}", flush=True)

    # Try browser cookies
    print("Trying browser cookies...", flush=True)
    cookie_str, ua = get_cf_cookies_from_browser()
    if cookie_str:
        with open(COOKIE_FILE, "w") as f:
            json.dump({"cookies": cookie_str, "ua": ua}, f)
        return cookie_str, ua

    # Fall back to saved cookies
    if COOKIE_FILE.exists():
        print("  Using saved cookies from previous session.", flush=True)
        with open(COOKIE_FILE, "r") as f:
            saved = json.load(f)
        return saved["cookies"], saved["ua"]

    raise RuntimeError("Could not get Cloudflare cookies from any source.")


def fetch_with_cookies(url: str, cookie_str: str, ua: str, retries: int = 2) -> str:
    """Fetch URL using curl with CF cookies and rate limiting."""
    _rate_limit()
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(
                ["curl", "-s", "-L", "--max-time", "30",
                 "-H", f"User-Agent: {ua}",
                 "-H", f"Cookie: {cookie_str}",
                 "-H", "Accept: text/html,application/xhtml+xml",
                 url],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=35,
            )
            if r.returncode == 0 and r.stdout and "Just a moment..." not in r.stdout[:500]:
                return r.stdout
        except subprocess.TimeoutExpired:
            pass
        if attempt < retries:
            backoff = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(backoff)
    return ""


# ---------------------------------------------------------------------------
# Phase 1: Collect deck metadata from listing pages
# ---------------------------------------------------------------------------

def parse_listing_row(row) -> dict | None:
    """Extract deck metadata from a table row on the listing page."""
    # Find the deck link
    link = row.find("a", href=lambda h: h and "/riftbound-metagame/deck-" in h)
    if not link:
        return None

    href = link["href"]
    if not href.startswith("http"):
        href = f"{BASE}{href}"

    # Extract deck ID from URL
    deck_id_match = re.search(r"-(\d+)$", href)
    deck_id = deck_id_match.group(1) if deck_id_match else ""

    # Get all cells in the row
    cells = row.find_all("td")

    entry = {
        "url": href,
        "deck_id": deck_id,
        "deck_name": "",
        "player": "",
        "legend": "",
        "domains": "",
        "placement": "",
        "metagame": "",
        "format": "",
        "tournament": "",
        "price": "",
        "spiciness": "",
        "date": "",
    }

    # The deck name is usually the link text
    entry["deck_name"] = link.get_text(strip=True)

    # Try to extract data from data-href rows or table cells
    for cell in cells:
        text = cell.get_text(strip=True)
        # Look for price pattern
        if text.startswith("$"):
            entry["price"] = text
        # Look for percentage (spiciness)
        elif text.endswith("%") and text[:-1].replace(".", "").isdigit():
            entry["spiciness"] = text
        # Look for placement (1st, 2nd, 3rd, etc.)
        elif re.match(r"^\d+(st|nd|rd|th)$", text):
            entry["placement"] = text

    # Try to find legend from image alt text
    legend_img = row.find("img")
    if legend_img and legend_img.get("alt"):
        entry["legend"] = legend_img["alt"]

    return entry


def parse_listing_page(html: str) -> list[dict]:
    """Parse a listing page and return deck entries."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []

    # Try table rows first
    rows = soup.find_all("tr", attrs={"data-href": True})
    if rows:
        for row in rows:
            href = row.get("data-href", "")
            if "/riftbound-metagame/deck-" in href:
                if not href.startswith("http"):
                    href = f"{BASE}{href}"
                deck_id_match = re.search(r"-(\d+)$", href)
                deck_id = deck_id_match.group(1) if deck_id_match else ""

                cells = row.find_all("td")
                entry = {
                    "url": href,
                    "deck_id": deck_id,
                }

                # Extract text from all cells for metadata
                cell_texts = [c.get_text(strip=True) for c in cells]

                # Find legend from image
                legend_img = row.find("img")
                if legend_img:
                    entry["legend"] = legend_img.get("alt", "")

                # Store raw cell data for later parsing
                entry["raw_cells"] = cell_texts
                entries.append(entry)
        return entries

    # Fallback: find all deck links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/riftbound-metagame/deck-" in href:
            if not href.startswith("http"):
                href = f"{BASE}{href}"
            deck_id_match = re.search(r"-(\d+)$", href)
            deck_id = deck_id_match.group(1) if deck_id_match else ""
            entries.append({
                "url": href,
                "deck_id": deck_id,
                "deck_name": a.get_text(strip=True),
            })

    # Deduplicate by URL
    seen = set()
    unique = []
    for e in entries:
        if e["url"] not in seen:
            seen.add(e["url"])
            unique.append(e)
    return unique


def phase_listings(cookie_str: str, ua: str, max_pages: int = 5000) -> list[dict]:
    """Phase 1: Crawl listing pages to collect deck URLs and metadata."""
    progress = load_progress()
    start_page = progress["listing_page"] + 1
    all_listings = load_listings()
    seen_urls = {e["url"] for e in all_listings}

    print(f"\n=== Phase 1: Collecting deck listings ===", flush=True)
    if start_page > 1:
        print(f"  Resuming from page {start_page} ({len(all_listings)} listings so far)", flush=True)
    else:
        print(f"  Starting fresh.", flush=True)

    consecutive_empty = 0
    last_cookie_refresh = 0
    new_count = 0

    for page in range(start_page, max_pages + 1):
        url = f"{BASE}/riftbound-decks?deck_type=all&page={page}"

        if page % 10 == 0 or page == start_page:
            print(f"  Page {page}... ({len(all_listings)} total, +{new_count} new)", flush=True)

        # Refresh cookies every 200 pages proactively
        if page - last_cookie_refresh >= 200:
            try:
                cookie_str, ua = get_cf_cookies()
                last_cookie_refresh = page
                if page > start_page:
                    print(f"  Refreshed cookies at page {page}", flush=True)
            except Exception:
                pass

        html = fetch_with_cookies(url, cookie_str, ua, retries=1)

        # Detect CF block
        if html and "Just a moment" in html[:500]:
            html = ""

        if not html:
            # Try refreshing cookies
            try:
                cookie_str, ua = get_cf_cookies()
                last_cookie_refresh = page
                print(f"  Refreshed cookies at page {page} (blocked)", flush=True)
                html = fetch_with_cookies(url, cookie_str, ua, retries=2)
            except Exception:
                pass

        if not html:
            consecutive_empty += 1
            print(f"  Failed page {page} ({consecutive_empty} consecutive)", flush=True)
            if consecutive_empty >= 5:
                print(f"  5 consecutive failures, stopping.", flush=True)
                break
            continue

        consecutive_empty = 0
        entries = parse_listing_page(html)
        page_new = 0

        for entry in entries:
            if entry["url"] not in seen_urls:
                seen_urls.add(entry["url"])
                all_listings.append(entry)
                page_new += 1
                new_count += 1

        if page_new == 0:
            # Check if it's a real empty page or CF block
            soup = BeautifulSoup(html, "html.parser")
            title = soup.find("title")
            if title and "moment" in title.get_text().lower():
                try:
                    cookie_str, ua = get_cf_cookies()
                    last_cookie_refresh = page
                except Exception:
                    consecutive_empty += 1
                continue

            # If we got an actual page but no new decks, we've reached the end
            # unless all decks on this page were already seen (resume scenario)
            if len(entries) == 0:
                print(f"  No decks found on page {page}, done.", flush=True)
                break

        # Save progress every 25 pages
        if page % 25 == 0:
            progress["listing_page"] = page
            progress["total_listings"] = len(all_listings)
            save_progress(progress)
            save_listings(all_listings)

    # Final save
    progress["listing_page"] = page
    progress["total_listings"] = len(all_listings)
    save_progress(progress)
    save_listings(all_listings)

    print(f"\n  Listings complete: {len(all_listings)} total deck URLs collected.", flush=True)
    return all_listings


# ---------------------------------------------------------------------------
# Phase 2: Scrape individual deck pages for full card lists
# ---------------------------------------------------------------------------

def parse_deck_page(html: str, url: str = "") -> dict | None:
    """Parse a deck page HTML into a dict with full card list."""
    soup = BeautifulSoup(html, "html.parser")
    deck_area = soup.find("div", class_="deck-content-area")
    if not deck_area:
        return None

    text = deck_area.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    cards = []
    legend_name = "Unknown"
    champion_name = "Unknown"
    section_key = ""
    section_label = "Main Deck"
    i = 0

    while i < len(lines):
        line = lines[i]
        m = SECTION_RE.match(line)
        if m:
            section_key = m.group(1).lower()
            sec = SECTION_MAP.get(section_key, DeckSection.MAIN)
            section_label = sec.value
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
            cards.append({"name": name, "quantity": qty, "section": section_label})
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
            cards.append({"name": name, "quantity": qty, "section": section_label})
            i += 1
            continue
        i += 1

    if not cards:
        return None

    # Player name
    player = "Unknown"
    for div in soup.find_all("div"):
        cls = div.get("class", [])
        if "card" in cls and "mt-4" in cls:
            el = div.find("strong") or div.find("h3")
            if el:
                player = el.get_text(strip=True)[:100]
            break

    return {
        "url": url,
        "player": player,
        "champion": champion_name,
        "legend": legend_name,
        "cards": cards,
    }


def save_deck_detail(deck_id: str, detail: dict):
    """Save a single deck's detail to its own file."""
    path = DETAILS_DIR / f"{deck_id}.json"
    path.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")


def load_scraped_ids() -> set[str]:
    """Get set of already-scraped deck IDs."""
    scraped = set()
    if DETAILS_DIR.exists():
        for f in DETAILS_DIR.glob("*.json"):
            scraped.add(f.stem)
    return scraped


def scrape_one_deck(url: str, deck_id: str, cookie_str: str, ua: str) -> dict | None:
    """Fetch and parse a single deck page."""
    html = fetch_with_cookies(url, cookie_str, ua, retries=1)
    if not html:
        return None
    try:
        detail = parse_deck_page(html, url)
        if detail:
            detail["deck_id"] = deck_id
            save_deck_detail(deck_id, detail)
        return detail
    except Exception:
        return None


def phase_details(cookie_str: str, ua: str, max_workers: int = 1):
    """Phase 2: Scrape individual deck pages for full card lists."""
    listings = load_listings()
    if not listings:
        print("No listings found. Run phase 1 first.", flush=True)
        return

    scraped_ids = load_scraped_ids()
    to_scrape = [(e["url"], e.get("deck_id", "")) for e in listings
                 if e.get("deck_id") and e["deck_id"] not in scraped_ids]

    print(f"\n=== Phase 2: Scraping deck details ===", flush=True)
    print(f"  Total listings: {len(listings)}", flush=True)
    print(f"  Already scraped: {len(scraped_ids)}", flush=True)
    print(f"  Remaining: {len(to_scrape)}", flush=True)
    print(f"  Workers: {max_workers}, Delay: {_base_delay}s", flush=True)

    if not to_scrape:
        print("  All decks already scraped!", flush=True)
        return

    ok = 0
    fail = 0
    start = time.time()
    last_cookie_refresh = 0

    if max_workers <= 1:
        # Sequential mode - simpler, easier to manage rate limits
        for i, (url, deck_id) in enumerate(to_scrape, 1):
            # Refresh cookies every 500 decks
            if i - last_cookie_refresh >= 500:
                try:
                    cookie_str, ua = get_cf_cookies()
                    last_cookie_refresh = i
                    if i > 1:
                        print(f"  Refreshed cookies at deck {i}", flush=True)
                except Exception:
                    pass

            detail = scrape_one_deck(url, deck_id, cookie_str, ua)
            if detail:
                ok += 1
            else:
                fail += 1
                # Exponential backoff on failure
                time.sleep(min(30, (2 ** min(fail, 5)) + random.uniform(0, 2)))

            if i % 100 == 0:
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                remaining = len(to_scrape) - i
                eta_min = remaining / rate / 60 if rate > 0 else 0
                print(f"  {i}/{len(to_scrape)}: {ok} ok, {fail} fail, "
                      f"{rate:.2f}/s, ETA {eta_min:.0f}m", flush=True)

            # Reset fail counter on success
            if detail:
                fail = 0
    else:
        # Concurrent mode
        batch_size = 50
        for batch_start in range(0, len(to_scrape), batch_size):
            batch = to_scrape[batch_start:batch_start + batch_size]

            # Refresh cookies every 500 decks
            if batch_start - last_cookie_refresh >= 500:
                try:
                    cookie_str, ua = get_cf_cookies()
                    last_cookie_refresh = batch_start
                    print(f"  Refreshed cookies at deck {batch_start}", flush=True)
                except Exception:
                    pass

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(scrape_one_deck, url, did, cookie_str, ua): did
                    for url, did in batch
                }
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        ok += 1
                    else:
                        fail += 1

            total_done = batch_start + len(batch)
            if total_done % 100 <= batch_size:
                elapsed = time.time() - start
                rate = total_done / elapsed if elapsed > 0 else 0
                remaining = len(to_scrape) - total_done
                eta_min = remaining / rate / 60 if rate > 0 else 0
                print(f"  {total_done}/{len(to_scrape)}: {ok} ok, {fail} fail, "
                      f"{rate:.2f}/s, ETA {eta_min:.0f}m", flush=True)

    elapsed = time.time() - start
    print(f"\n  Details complete: {ok} scraped, {fail} failed in {elapsed/60:.1f}m", flush=True)


# ---------------------------------------------------------------------------
# Export: Combine everything into tournament files + web data
# ---------------------------------------------------------------------------

# Normalize alternate legend titles to their canonical names
LEGEND_ALIASES = {
    "Sivir, Mercenary": "Sivir, Battle Mistress",
    "Annie, Stubborn": "Annie, Dark Child",
    "Jinx, Demolitionist": "Jinx, Loose Cannon",
    "Jinx, Rebel": "Jinx, Loose Cannon",
    "Lee Sin, Centered": "Lee Sin, Blind Monk",
    "Miss Fortune, Captain": "Miss Fortune, Bounty Hunter",
    "Teemo, Scout": "Teemo, Swift Scout",
    "Reksai, Void Burrower": "Rek'Sai, Void Burrower",
}


def _normalize_legend(name: str) -> str:
    return LEGEND_ALIASES.get(name.strip(), name.strip())


def export_to_tournaments():
    """Combine scraped deck details into tournament JSON files."""
    print(f"\n=== Exporting to tournament files ===", flush=True)

    details = []
    for f in DETAILS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            details.append(d)
        except Exception:
            continue

    print(f"  Loaded {len(details)} deck details.", flush=True)

    # Group by legend
    by_legend: dict[str, list[Decklist]] = {}
    for d in details:
        cards = [CardEntry(
            name=c["name"],
            quantity=c["quantity"],
            section=DeckSection(c["section"]),
        ) for c in d.get("cards", [])]

        if not cards:
            continue

        raw_legend = d.get("legend", "Unknown")
        normalized = _normalize_legend(raw_legend)

        dl = Decklist(
            player=d.get("player", "Unknown"),
            champion=d.get("champion", "Unknown"),
            legend=normalized,
            cards=cards,
        )

        legend_key = dl.legend.strip()
        if legend_key and legend_key != "Unknown":
            by_legend.setdefault(legend_key, []).append(dl)

    # Clear old riftdecks files
    data_dir = Path(__file__).parent / "data" / "tournaments"
    data_dir.mkdir(parents=True, exist_ok=True)
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

    total = sum(len(d) for d in by_legend.values())
    print(f"\n  Exported {total} decklists across {len(by_legend)} legends.", flush=True)


def regenerate_web_data():
    """Regenerate the web data JSON file."""
    print(f"\n=== Regenerating web data ===", flush=True)
    from riftbound_agg.storage.store import load_all_decklists

    all_dl = load_all_decklists()
    legends = get_unique_legends(all_dl)

    result = {"legends": []}
    img_dir = Path(__file__).parent.parent / "web" / "public" / "images" / "legends"
    existing_imgs = {f.stem for f in img_dir.glob("*.png")} if img_dir.exists() else set()

    SLUG_OVERRIDES = {
        "Sivir, Mercenary": "sivir-battle-mistress",
        "Rek'Sai, Void Burrower": "reksai-void-burrower",
    }

    for legend in legends:
        stats = aggregate(all_dl, legend=legend)
        filtered = [d for d in all_dl if d.legend.strip().lower() == legend.strip().lower()]
        sections = {}
        for s in stats:
            sections.setdefault(s.section.value, []).append(s.to_dict())

        if legend in SLUG_OVERRIDES:
            slug = SLUG_OVERRIDES[legend]
        else:
            slug = re.sub(r"'", "", legend.lower())
            slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
            if slug not in existing_imgs:
                first = legend.split(",")[0].lower().strip()
                matches = [k for k in existing_imgs if first in k]
                if matches:
                    slug = matches[0]

        result["legends"].append({
            "name": legend,
            "slug": slug,
            "image": f"/images/legends/{slug}.png",
            "deck_count": len(filtered),
            "sections": sections,
        })

    result["legends"].sort(key=lambda x: -x["deck_count"])

    out = Path(__file__).parent.parent / "web" / "public" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = sum(l["deck_count"] for l in result["legends"])
    print(f"\n  Final: {len(result['legends'])} legends, {total} decklists")
    print(f"  Saved to {out}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bulk scrape riftdecks.com")
    parser.add_argument("--phase", choices=["listings", "details", "export"],
                        help="Run only a specific phase")
    parser.add_argument("--reset", action="store_true",
                        help="Clear all progress and start fresh")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent workers for detail scraping (default: 1)")
    parser.add_argument("--max-pages", type=int, default=5000,
                        help="Max listing pages to scrape (default: 5000)")

    args = parser.parse_args()

    set_base_delay(args.delay)
    ensure_dirs()

    if args.reset:
        import shutil
        if PROGRESS_DIR.exists():
            shutil.rmtree(PROGRESS_DIR)
        ensure_dirs()
        print("Progress cleared.", flush=True)

    print("=== RiftDecks Bulk Scraper v3 ===", flush=True)
    print(f"  Rate limit: {args.delay}s between requests", flush=True)
    print(f"  Workers: {args.workers}", flush=True)

    # Get cookies
    cookie_str, ua = get_cf_cookies()

    # Test connection
    html = fetch_with_cookies(f"{BASE}/riftbound-decks?deck_type=all", cookie_str, ua)
    if not html or "Just a moment" in html[:500]:
        print("ERROR: Cannot access riftdecks.com (cookies not working).", flush=True)
        print("Make sure FlareSolverr is running or you have valid browser cookies.", flush=True)
        return

    print("  Connection OK.\n", flush=True)

    if args.phase == "listings":
        phase_listings(cookie_str, ua, max_pages=args.max_pages)
    elif args.phase == "details":
        phase_details(cookie_str, ua, max_workers=args.workers)
    elif args.phase == "export":
        export_to_tournaments()
        regenerate_web_data()
    else:
        # Run all phases
        phase_listings(cookie_str, ua, max_pages=args.max_pages)
        # Refresh cookies before phase 2
        try:
            cookie_str, ua = get_cf_cookies()
        except Exception:
            pass
        phase_details(cookie_str, ua, max_workers=args.workers)
        export_to_tournaments()
        regenerate_web_data()


if __name__ == "__main__":
    main()
