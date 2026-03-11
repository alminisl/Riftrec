from __future__ import annotations

import json
import logging
import re
from datetime import date
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

from riftbound_agg.models import CardEntry, DeckSection, Decklist, Tournament
from riftbound_agg.scraper.base import BaseScraper
from riftbound_agg.scraper.parser import parse_decklist_text

logger = logging.getLogger(__name__)

BASE_URL = "https://riftbound.leagueoflegends.com"
NEWS_PATH = "/en-us/news/organizedplay/"

ALLOWED_HOSTS = {"riftbound.leagueoflegends.com"}


def _parse_heading(heading_text: str) -> tuple[str, str, str]:
    parts = re.split(r"[–\-|/]", heading_text)
    player = parts[0].strip() if len(parts) >= 1 else ""
    champion = parts[1].strip() if len(parts) >= 2 else "Unknown"
    legend = parts[2].strip() if len(parts) >= 3 else "Unknown"
    return player, champion, legend


class OfficialScraper(BaseScraper):
    def __init__(self, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "RiftboundDeckAggregator/1.0"}
        )
        self.timeout = timeout

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
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    def scrape_tournament(self, url: str) -> Tournament:
        self._validate_url(url)
        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        # Try __NEXT_DATA__ first
        next_data = self._try_next_data(soup)
        if next_data:
            return next_data

        # Fallback: parse HTML directly
        return self._parse_html(soup, url)

    def _try_next_data(self, soup: BeautifulSoup) -> Tournament | None:
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
            props = data.get("props", {}).get("pageProps", {})
            page = props.get("page", {})

            name = page.get("title", "Unknown Tournament")
            url = page.get("url", "")
            date_str = page.get(
                "displayedPublishDate", date.today().isoformat()
            )

            # Extract body from blades – look for articleRichText type
            body = self._extract_body_from_blades(page.get("blades", []))

            # Legacy fallback: article.body / article.content
            if not body:
                article = props.get("article", {})
                if article:
                    name = article.get("title", name)
                    url = article.get("url", url)
                    date_str = article.get("date", date_str)
                    body = article.get("body", "") or article.get("content", "")

            if not body:
                return None

            body_soup = BeautifulSoup(body, "html.parser") if "<" in body else None
            if body_soup:
                decklists = self._extract_decklists_from_soup(body_soup)
            else:
                decklists = []

            if not decklists:
                return None

            return Tournament(
                name=name, url=url, date=date_str, decklists=decklists
            )
        except json.JSONDecodeError as e:
            logger.debug("Failed to parse __NEXT_DATA__ JSON: %s", e)
            return None
        except KeyError as e:
            logger.warning("Unexpected __NEXT_DATA__ structure, missing key: %s", e)
            return None

    @staticmethod
    def _extract_body_from_blades(blades: list[dict]) -> str:
        """Find the articleRichText blade and return its richText.body."""
        for blade in blades:
            if blade.get("type") == "articleRichText":
                rich_text = blade.get("richText", {})
                body = rich_text.get("body", "")
                if body:
                    return body
        return ""

    def _parse_html(self, soup: BeautifulSoup, url: str) -> Tournament:
        title_tag = soup.find("h1")
        name = title_tag.get_text(strip=True) if title_tag else "Unknown Tournament"

        date_tag = soup.find("time")
        date_str = (
            date_tag.get("datetime", date.today().isoformat())
            if date_tag
            else date.today().isoformat()
        )

        decklists = self._extract_decklists_from_soup(soup)
        return Tournament(name=name, url=url, date=date_str, decklists=decklists)

    def _extract_decklists_from_soup(self, soup: BeautifulSoup) -> list[Decklist]:
        decklists: list[Decklist] = []

        # Strategy 1: Look for deck container elements
        deck_blocks = soup.find_all(
            ["div", "section"],
            class_=re.compile(r"deck|decklist", re.I),
        )

        if deck_blocks:
            for block in deck_blocks:
                dl = self._parse_deck_block(block)
                if dl:
                    decklists.append(dl)
            return decklists

        # Strategy 2: Table-based decklists (official Riftbound site format)
        tables = soup.find_all("table")
        for table in tables:
            dl = self._parse_deck_table(table)
            if dl:
                decklists.append(dl)
        if decklists:
            return decklists

        # Strategy 3: Look for <pre> or <code> blocks with card lines
        for pre in soup.find_all(["pre", "code"]):
            text = pre.get_text()
            if re.search(r"^\s*\d+\s+\w", text, re.MULTILINE):
                dl = self._decklist_from_text(text)
                if dl:
                    decklists.append(dl)

        if decklists:
            return decklists

        # Strategy 4: Find headings that look like player names followed by card lists
        headings = soup.find_all(["h2", "h3", "h4"])
        for heading in headings:
            text_after = self._collect_text_after(heading)
            if text_after and re.search(r"^\s*\d+\s+\w", text_after, re.MULTILINE):
                dl = self._decklist_from_text(text_after, heading_text=heading.get_text(strip=True))
                if dl:
                    decklists.append(dl)

        return decklists

    def _parse_deck_block(self, block: Tag) -> Decklist | None:
        player = ""
        champion = "Unknown"
        legend = "Unknown"

        heading = block.find(["h2", "h3", "h4", "h5"])
        if heading:
            heading_text = heading.get_text(strip=True)
            player, champion, legend = _parse_heading(heading_text)
            if champion == "Unknown":
                player = heading_text

        text = block.get_text("\n")
        cards = parse_decklist_text(text)
        if not cards:
            return None

        return Decklist(
            player=player,
            champion=champion,
            legend=legend,
            cards=cards,
        )

    def _decklist_from_text(
        self, text: str, heading_text: str = ""
    ) -> Decklist | None:
        cards = parse_decklist_text(text)
        if not cards:
            return None

        player = ""
        champion = "Unknown"
        legend = "Unknown"

        if heading_text:
            player, champion, legend = _parse_heading(heading_text)
            if champion == "Unknown":
                player = heading_text

        return Decklist(
            player=player,
            champion=champion,
            legend=legend,
            cards=cards,
        )

    # -- Section label to DeckSection mapping for table-based parsing ----------

    _SECTION_MAP: dict[str, DeckSection] = {
        "main deck": DeckSection.MAIN,
        "battlefields": DeckSection.BATTLEFIELDS,
        "rune pool": DeckSection.RUNES,
        "sideboard": DeckSection.SIDEBOARD,
    }

    def _parse_deck_table(self, table: Tag) -> Decklist | None:
        """Parse one <table> element in the official Riftbound format.

        Expected structure:
            row 0 – image (skipped)
            row 1 – <h3> with player name & ranking info
            row 2 – two <td> cells containing labelled card sections
        """
        h3 = table.find("h3")
        if not h3:
            return None

        player, legend, champion = self._parse_player_heading(h3)

        cards: list[CardEntry] = []
        legend_name = "Unknown"
        champion_name = "Unknown"
        # Iterate all <td> cells that contain <strong> section labels
        for td in table.find_all("td"):
            strong_tags = td.find_all("strong")
            if not strong_tags:
                continue
            section_cards, lg, ch = self._parse_labelled_sections(td)
            cards.extend(section_cards)
            if lg:
                legend_name = lg
            if ch:
                champion_name = ch

        if not cards:
            return None

        return Decklist(
            player=player,
            champion=champion_name,
            legend=legend_name,
            cards=cards,
        )

    @staticmethod
    def _parse_player_heading(h3: Tag) -> tuple[str, str, str]:
        """Extract player name from the <h3> heading.

        Format: ``PlayerName<br><strong>Legend Rank:</strong> ...``
        Returns (player, legend, champion) — legend/champion default to
        "Unknown" because the heading only contains ranking info; the actual
        legend/champion cards are parsed from the section labels.
        """
        # Get the first text node before any <br> or <strong>
        player = ""
        for child in h3.children:
            if isinstance(child, str):
                player = child.strip()
                if player:
                    break
            elif isinstance(child, Tag) and child.name in ("br", "strong"):
                break
            elif isinstance(child, Tag):
                player = child.get_text(strip=True)
                if player:
                    break
        return player, "Unknown", "Unknown"

    def _parse_labelled_sections(
        self, td: Tag
    ) -> tuple[list[CardEntry], str, str]:
        """Parse card entries from a <td> that uses <strong> labels.

        Labels are like ``Legend:``, ``Champion:``, ``Main Deck:``, etc.
        Cards follow as ``<br>``-separated ``"3 Card Name"`` lines.

        Returns (cards, legend_name, champion_name).
        """
        cards: list[CardEntry] = []
        legend_name = ""
        champion_name = ""
        paragraphs = td.find_all("p")
        if not paragraphs:
            paragraphs = [td]

        for p in paragraphs:
            label, section, section_cards = self._parse_section_paragraph(p)
            if section_cards:
                cards.extend(section_cards)
                if label == "legend" and section_cards:
                    legend_name = section_cards[0].name
                elif label == "champion" and section_cards:
                    champion_name = section_cards[0].name

        return cards, legend_name, champion_name

    def _parse_section_paragraph(
        self, element: Tag
    ) -> tuple[str, DeckSection | None, list[CardEntry]]:
        """Parse a single <p> block that starts with a <strong> label.

        Returns (label, section, cards).
        """
        strong = element.find("strong")
        if not strong:
            return "", None, []

        label = strong.get_text(strip=True).rstrip(":").strip().lower()

        # Determine which DeckSection this maps to
        section = self._SECTION_MAP.get(label)

        # Special handling for Legend and Champion — they are single-card entries
        # stored in MAIN section conceptually, but we parse them like cards.
        is_legend = label == "legend"
        is_champion = label == "champion"

        if section is None and not is_legend and not is_champion:
            return label, None, []

        if is_legend or is_champion:
            section = DeckSection.MAIN

        # Extract text lines: everything after the <strong> tag
        # We need to convert <br> to newlines for proper parsing
        # Rebuild text from element contents, replacing <br> with \n
        lines: list[str] = []
        past_strong = False
        for child in element.descendants:
            if child is strong or (isinstance(child, Tag) and child is strong):
                past_strong = True
                continue
            if not past_strong:
                continue
            if isinstance(child, Tag) and child.name == "br":
                lines.append("\n")
            elif isinstance(child, str):
                lines.append(child)

        text = "".join(lines)
        cards: list[CardEntry] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\d+)\s+(.+)$", line)
            if m:
                qty = int(m.group(1))
                name = m.group(2).strip()
                cards.append(
                    CardEntry(name=name, quantity=qty, section=section)
                )

        return label, section, cards

    def _collect_text_after(self, element: Tag) -> str:
        lines: list[str] = []
        sibling = element.find_next_sibling()
        while sibling:
            if sibling.name in ("h1", "h2", "h3", "h4"):
                break
            lines.append(sibling.get_text("\n"))
            sibling = sibling.find_next_sibling()
        return "\n".join(lines)

    def discover_tournaments(self) -> list[dict[str, str]]:
        html = self._get(f"{BASE_URL}{NEWS_PATH}")
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, str]] = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if any(
                kw in text.lower()
                for kw in ("top deck", "top 8", "championship", "invitational")
            ) or any(
                kw in href.lower()
                for kw in ("top-deck", "top-8", "championship", "invitational")
            ):
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                results.append({"name": text, "url": full_url})

        return results
