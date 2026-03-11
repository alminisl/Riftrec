from __future__ import annotations

import logging
import re
import subprocess
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from riftbound_agg.models import CardEntry, Decklist, DeckSection

logger = logging.getLogger(__name__)

BASE_URL = "https://riftdecks.com"

ALLOWED_HOSTS = {"riftdecks.com", "www.riftdecks.com"}

# Map section names found in div.deck-content-area to DeckSection values.
SECTION_MAP: dict[str, DeckSection] = {
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

# Regex to detect a section header like "unit (12)" or "legend (1)"
SECTION_HEADER_RE = re.compile(r"^([a-z]+(?:\s[a-z]+)?)\s*\(\d+\)$", re.IGNORECASE)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_DELAY = 0.5  # seconds between requests


class RiftDecksScraper:
    """Scraper for riftdecks.com deck pages.

    Uses curl for HTTP requests to bypass Cloudflare protection.
    """

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self._last_request_time: float = 0.0

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
        if parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError(
                f"URL host '{parsed.hostname}' is not allowed. "
                f"Expected one of: {ALLOWED_HOSTS}"
            )

    def _get(self, url: str) -> str:
        self._validate_url(url)
        # Polite delay between requests
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)

        result = subprocess.run(
            [
                "curl", "-s", "-L",
                "-H", f"User-Agent: {USER_AGENT}",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "--max-time", str(self.timeout),
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout + 10,
        )
        self._last_request_time = time.monotonic()

        if result.returncode != 0:
            raise RuntimeError(f"curl failed for {url}: {result.stderr}")
        if not result.stdout or "Just a moment..." in result.stdout[:500]:
            raise RuntimeError(f"Cloudflare challenge not bypassed for {url}")
        return result.stdout

    def scrape_legend_decks(
        self, legend_slug: str, max_pages: int = 1
    ) -> list[Decklist]:
        """Scrape decks for a given legend from riftdecks.com.

        Args:
            legend_slug: The legend slug, e.g. "volibear-relentless-storm".
            max_pages: Maximum number of paginated pages to fetch.

        Returns:
            List of Decklist objects parsed from individual deck pages.
        """
        decklists: list[Decklist] = []
        deck_urls: list[str] = []

        for page in range(1, max_pages + 1):
            url = f"{BASE_URL}/legends/constructed/{legend_slug}"
            if page > 1:
                url = f"{url}?page={page}"

            logger.info("Fetching legend page: %s", url)
            try:
                html = self._get(url)
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                logger.warning("Failed to fetch legend page %d: %s", page, e)
                break

            soup = BeautifulSoup(html, "html.parser")
            links = self._extract_deck_links(soup)
            if not links:
                logger.info("No deck links found on page %d, stopping.", page)
                break
            deck_urls.extend(links)

        logger.info("Found %d deck links for '%s'", len(deck_urls), legend_slug)

        for deck_url in deck_urls:
            try:
                dl = self.scrape_deck(deck_url)
                if dl:
                    decklists.append(dl)
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                logger.warning("Failed to scrape deck %s: %s", deck_url, e)
            except Exception as e:
                logger.warning("Error parsing deck %s: %s", deck_url, e)

        return decklists

    def _extract_deck_links(self, soup: BeautifulSoup) -> list[str]:
        """Find all deck page links on a legend listing page."""
        urls: list[str] = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/riftbound-metagame/deck-" in href:
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    def scrape_deck(self, url: str) -> Decklist | None:
        """Scrape a single deck page and return a Decklist.

        Args:
            url: Full URL to a riftdecks.com deck page.

        Returns:
            A Decklist object, or None if the page could not be parsed.
        """
        logger.info("Scraping deck: %s", url)
        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        # Parse cards from deck-content-area
        deck_area = soup.find("div", class_="deck-content-area")
        if not deck_area:
            logger.warning("No div.deck-content-area found at %s", url)
            return None

        cards, legend_name, champion_name = self._parse_deck_content(deck_area)

        if not cards:
            logger.warning("No cards parsed from %s", url)
            return None

        # Parse metadata from div.card.mt-4
        player, placement = self._parse_metadata(soup)

        return Decklist(
            player=player,
            champion=champion_name,
            legend=legend_name,
            cards=cards,
            placement=placement,
        )

    def _parse_deck_content(
        self, deck_area: Tag
    ) -> tuple[list[CardEntry], str, str]:
        """Parse the deck-content-area div into card entries.

        Returns:
            Tuple of (cards, legend_name, champion_name).
        """
        cards: list[CardEntry] = []
        legend_name = "Unknown"
        champion_name = "Unknown"

        text = deck_area.get_text("\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        current_section = DeckSection.MAIN
        current_section_key = ""
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check for section header like "unit (12)"
            header_match = SECTION_HEADER_RE.match(line)
            if header_match:
                section_name = header_match.group(1).lower()
                current_section_key = section_name
                current_section = SECTION_MAP.get(section_name, DeckSection.MAIN)
                i += 1
                continue

            # Try to parse a card entry: quantity line followed by card name line
            # Pattern: a line that is just a number (quantity)
            if line.isdigit() and i + 1 < len(lines):
                qty = int(line)
                card_name = lines[i + 1]

                # Skip price lines (start with $)
                skip = 2
                if i + 2 < len(lines) and lines[i + 2].startswith("$"):
                    skip = 3

                # Track legend and champion names
                if current_section_key == "legend":
                    legend_name = card_name
                elif current_section_key == "champion":
                    champion_name = card_name

                cards.append(
                    CardEntry(
                        name=card_name,
                        quantity=qty,
                        section=current_section,
                    )
                )
                i += skip
                continue

            # Also handle "quantity CardName" on a single line
            single_match = re.match(r"^(\d+)\s+(.+)$", line)
            if single_match:
                qty = int(single_match.group(1))
                card_name = single_match.group(2).strip()
                # Remove trailing price if present
                card_name = re.sub(r"\s*\$[\d.]+\s*$", "", card_name)

                if current_section_key == "legend":
                    legend_name = card_name
                elif current_section_key == "champion":
                    champion_name = card_name

                cards.append(
                    CardEntry(
                        name=card_name,
                        quantity=qty,
                        section=current_section,
                    )
                )
                i += 1
                continue

            i += 1

        return cards, legend_name, champion_name

    def _parse_metadata(self, soup: BeautifulSoup) -> tuple[str, str | None]:
        """Extract player name and placement from deck metadata.

        Returns:
            Tuple of (player_name, placement).
        """
        player = "Unknown"
        placement: str | None = None

        meta_div = soup.find("div", class_=re.compile(r"\bcard\b.*\bmt-4\b|\bmt-4\b.*\bcard\b"))
        if not meta_div:
            # Try finding any div that has both "card" and "mt-4" in its classes
            for div in soup.find_all("div"):
                classes = div.get("class", [])
                if "card" in classes and "mt-4" in classes:
                    meta_div = div
                    break

        if meta_div:
            text = meta_div.get_text("\n")
            lines = [line.strip() for line in text.splitlines() if line.strip()]

            # Try to extract player name — typically the first meaningful text
            for line in lines:
                # Skip common labels
                if line.lower() in (
                    "deck details",
                    "tournament",
                    "format",
                    "date",
                    "placement",
                ):
                    continue
                # Look for "Player:" or "Pilot:" patterns
                player_match = re.match(
                    r"(?:player|pilot|by)\s*[:\-]\s*(.+)", line, re.IGNORECASE
                )
                if player_match:
                    player = player_match.group(1).strip()
                    break

            # If no labeled player found, try the first non-label line
            if player == "Unknown":
                for line in lines:
                    if not re.match(
                        r"^(deck details|tournament|format|date|placement|player|pilot|by)\b",
                        line,
                        re.IGNORECASE,
                    ):
                        player = line
                        break

            # Look for placement
            for line in lines:
                place_match = re.match(
                    r"(?:placement|place|finish)\s*[:\-]\s*(.+)",
                    line,
                    re.IGNORECASE,
                )
                if place_match:
                    placement = place_match.group(1).strip()
                    break
                # Also match standalone ordinals like "1st", "Top 8"
                if re.match(r"^(?:\d+(?:st|nd|rd|th)|top\s+\d+)$", line, re.IGNORECASE):
                    placement = line
                    break

        return player, placement
