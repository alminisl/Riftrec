"""Bulk scrape ALL decks from riftdecks.com via FlareSolverr + cookies."""

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
import requests

sys.path.insert(0, str(Path(__file__).parent))

from riftbound_agg.models import CardEntry, DeckSection, Decklist, Tournament
from riftbound_agg.storage.store import save_tournament
from riftbound_agg.analysis.aggregator import aggregate, get_unique_legends

BASE = "https://riftdecks.com"
FLARESOLVERR = "http://localhost:8191/v1"
COOKIE_FILE = Path(__file__).parent / "cf_cookies.json"

SECTION_MAP = {
    "legend": DeckSection.MAIN, "champion": DeckSection.MAIN,
    "unit": DeckSection.MAIN, "gear": DeckSection.MAIN,
    "spell": DeckSection.MAIN, "battlefields": DeckSection.BATTLEFIELDS,
    "battlefield": DeckSection.BATTLEFIELDS, "runes": DeckSection.RUNES,
    "rune": DeckSection.RUNES, "sideboard": DeckSection.SIDEBOARD,
}
SECTION_RE = re.compile(r"^([a-z]+(?:\s[a-z]+)?)\s*\(\d+\)$", re.IGNORECASE)


def get_cf_cookies_from_browser() -> tuple[str, str]:
    """Try to extract Cloudflare cookies from browser cookie stores."""
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name=".riftdecks.com")
        cookie_str = "; ".join(f"{c.name}={c.value}" for c in cj)
        if cookie_str:
            ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36")
            print(f"Got cookies from Chrome browser.", flush=True)
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
            "url": f"{BASE}/riftbound-decks?metagame_id=2",
            "maxTimeout": 60000,
        }, timeout=90)
        data = r.json()
        if data.get("status") == "ok" and "solution" in data:
            sol = data["solution"]
            cookies = sol.get("cookies", [])
            ua = sol.get("userAgent", "")
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
            print(f"Got {len(cookies)} cookies, UA: {ua[:60]}...", flush=True)
            with open(COOKIE_FILE, "w") as f:
                json.dump({"cookies": cookie_str, "ua": ua}, f)
            return cookie_str, ua
        else:
            print(f"  FlareSolverr error: {data.get('message', 'unknown')[:100]}", flush=True)
    except Exception as e:
        print(f"  FlareSolverr failed: {e}", flush=True)

    # Try browser cookies
    print("Trying browser cookies...", flush=True)
    cookie_str, ua = get_cf_cookies_from_browser()
    if cookie_str:
        with open(COOKIE_FILE, "w") as f:
            json.dump({"cookies": cookie_str, "ua": ua}, f)
        return cookie_str, ua

    # Fall back to saved cookies
    if COOKIE_FILE.exists():
        print("Using saved cookies from previous session...", flush=True)
        with open(COOKIE_FILE, "r") as f:
            saved = json.load(f)
        return saved["cookies"], saved["ua"]

    raise RuntimeError("Could not get Cloudflare cookies from any source.")


def fetch_with_cookies(url: str, cookie_str: str, ua: str, retries: int = 2) -> str:
    """Fetch URL using curl with CF cookies."""
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(
                ["curl", "-s", "-L", "--max-time", "20",
                 "-H", f"User-Agent: {ua}",
                 "-H", f"Cookie: {cookie_str}",
                 "-H", "Accept: text/html,application/xhtml+xml",
                 url],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=25,
            )
            if r.returncode == 0 and r.stdout and "Just a moment..." not in r.stdout[:500]:
                return r.stdout
        except subprocess.TimeoutExpired:
            pass
        if attempt < retries:
            time.sleep(1)
    return ""


def fetch_via_flaresolverr(url: str) -> str:
    """Fallback: fetch via FlareSolverr directly."""
    try:
        r = requests.post(FLARESOLVERR, json={
            "cmd": "request.get", "url": url, "maxTimeout": 30000,
        }, timeout=45)
        data = r.json()
        return data.get("solution", {}).get("response", "")
    except Exception:
        return ""


def collect_deck_urls(cookie_str: str, ua: str) -> tuple[list[str], str, str]:
    """Crawl listing pages to collect all deck URLs.

    Returns (urls, cookie_str, ua) — cookies may be refreshed mid-run.
    """
    urls = []
    seen = set()
    consecutive_empty = 0
    last_refresh = 0

    for page in range(1, 2000):
        url = f"{BASE}/riftbound-decks?metagame_id=2&page={page}"
        if page % 25 == 0 or page == 1:
            print(f"  Listing page {page}... ({len(urls)} URLs so far)", flush=True)

        # Proactively refresh cookies every 150 pages
        if page - last_refresh >= 150:
            try:
                cookie_str, ua = get_cf_cookies()
                last_refresh = page
                print(f"  Refreshed cookies at page {page}", flush=True)
            except Exception:
                pass

        html = fetch_with_cookies(url, cookie_str, ua, retries=1)

        # Detect Cloudflare block (got HTML but it's the challenge page)
        if html and "Just a moment" in html[:500]:
            html = ""

        if not html:
            # Refresh cookies via FlareSolverr and retry
            try:
                cookie_str, ua = get_cf_cookies()
                last_refresh = page
                print(f"  Cookies expired, refreshed at page {page}", flush=True)
                html = fetch_with_cookies(url, cookie_str, ua, retries=1)
            except Exception:
                pass

        if not html:
            consecutive_empty += 1
            if consecutive_empty >= 5:
                print(f"  5 consecutive failures at page {page}, stopping.", flush=True)
                break
            continue

        consecutive_empty = 0
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
            # Might be end of data OR a blocked page — check title
            title = soup.find("title")
            if title and "moment" in title.get_text().lower():
                # Cloudflare page, not end of data — refresh and retry
                try:
                    cookie_str, ua = get_cf_cookies()
                    last_refresh = page
                    print(f"  Cloudflare block detected, refreshed at page {page}", flush=True)
                except Exception:
                    consecutive_empty += 1
                continue
            # Real end of data
            print(f"  No more decks at page {page}, done.", flush=True)
            break

        time.sleep(0.3)

    return urls, cookie_str, ua


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

    player = "Unknown"
    for div in soup.find_all("div"):
        cls = div.get("class", [])
        if "card" in cls and "mt-4" in cls:
            el = div.find("strong") or div.find("h3")
            if el:
                player = el.get_text(strip=True)[:100]
            break

    return Decklist(player=player, champion=champion_name, legend=legend_name, cards=cards)


def scrape_one(args: tuple[str, str, str]) -> Decklist | None:
    url, cookie_str, ua = args
    html = fetch_with_cookies(url, cookie_str, ua, retries=1)
    if not html:
        return None
    try:
        return parse_deck_page(html)
    except Exception:
        return None


def download_card_images(cookie_str: str, ua: str):
    """Download all card images locally."""
    print("\nDownloading card images...", flush=True)
    img_dir = Path(__file__).parent.parent / "web" / "public" / "images" / "cards"
    img_dir.mkdir(parents=True, exist_ok=True)

    # Load card mapping
    cards_file = Path(__file__).parent.parent / "web" / "public" / "cards.json"
    if not cards_file.exists():
        print("  No cards.json found, skipping.", flush=True)
        return

    with open(cards_file, "r", encoding="utf-8") as f:
        cards = json.load(f)

    local_mapping = {}
    downloaded = 0
    skipped = 0

    for name, remote_url in cards.items():
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        local_path = img_dir / f"{slug}.png"
        local_web_path = f"/images/cards/{slug}.png"

        if local_path.exists() and local_path.stat().st_size > 0:
            local_mapping[name] = local_web_path
            skipped += 1
            continue

        try:
            subprocess.run(
                ["curl", "-s", "-L", "--max-time", "10",
                 "-H", f"User-Agent: {ua}",
                 "-H", f"Cookie: {cookie_str}",
                 "-o", str(local_path), remote_url],
                capture_output=True, timeout=15,
            )
            if local_path.exists() and local_path.stat().st_size > 1000:
                local_mapping[name] = local_web_path
                downloaded += 1
            else:
                local_mapping[name] = remote_url  # fallback to remote
                if local_path.exists():
                    local_path.unlink()
        except Exception:
            local_mapping[name] = remote_url

        if (downloaded + skipped) % 50 == 0:
            print(f"  {downloaded} downloaded, {skipped} cached...", flush=True)

    # Save updated mapping
    with open(cards_file, "w", encoding="utf-8") as f:
        json.dump(local_mapping, f, ensure_ascii=False)
    print(f"  Done: {downloaded} downloaded, {skipped} cached.", flush=True)


def main():
    print("=== RiftDecks Bulk Scraper v2 (FlareSolverr) ===", flush=True)

    # Get CF cookies
    cookie_str, ua = get_cf_cookies()

    # Test
    html = fetch_with_cookies(f"{BASE}/riftbound-decks?metagame_id=2", cookie_str, ua)
    if not html or "Just a moment" in html[:500]:
        print("ERROR: Cookies not working!", flush=True)
        return

    print(f"Cookies working. Collecting deck URLs...", flush=True)
    deck_urls, cookie_str, ua = collect_deck_urls(cookie_str, ua)
    print(f"Found {len(deck_urls)} unique deck URLs.\n", flush=True)

    # Refresh cookies before scraping phase
    try:
        cookie_str, ua = get_cf_cookies()
    except Exception:
        pass

    print(f"Scraping deck pages (3 concurrent)...", flush=True)
    decklists = []
    errors = 0
    start = time.time()

    args_list = [(url, cookie_str, ua) for url in deck_urls]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(scrape_one, args): args[0] for args in args_list}
        for i, future in enumerate(as_completed(futures), 1):
            dl = future.result()
            if dl:
                decklists.append(dl)
            else:
                errors += 1

            if i % 200 == 0:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (len(deck_urls) - i) / rate if rate > 0 else 0
                print(f"  {i}/{len(deck_urls)}: {len(decklists)} ok, {errors} fail, "
                      f"{rate:.1f}/s, ETA {eta/60:.0f}m", flush=True)

    elapsed = time.time() - start
    print(f"\nScraped: {len(decklists)} decklists in {elapsed/60:.1f}m ({errors} failed)")

    # Group by legend
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

    # Download card images
    download_card_images(cookie_str, ua)

    # Regenerate web data
    print("\nRegenerating web data...", flush=True)
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
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = sum(l["deck_count"] for l in result["legends"])
    print(f"\nFinal: {len(result['legends'])} legends, {total} decklists")
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
