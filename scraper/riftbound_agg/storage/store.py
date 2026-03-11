from __future__ import annotations

import json
import os
import re
from pathlib import Path

from riftbound_agg.models import Decklist, Tournament


def _get_data_dir() -> Path:
    env_dir = os.environ.get("RIFTBOUND_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd() / "data"


DATA_DIR = _get_data_dir()
TOURNAMENTS_DIR = DATA_DIR / "tournaments"
AGGREGATED_DIR = DATA_DIR / "aggregated"


def _ensure_dirs() -> None:
    TOURNAMENTS_DIR.mkdir(parents=True, exist_ok=True)
    AGGREGATED_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(text: str, max_length: int = 200) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:max_length]


def save_tournament(tournament: Tournament) -> Path:
    _ensure_dirs()
    base = _slugify(tournament.name)
    filename = f"{base}.json"
    path = TOURNAMENTS_DIR / filename
    counter = 1
    while path.exists():
        existing = json.loads(path.read_text())
        if existing.get("url") == tournament.url:
            break  # Same tournament, overwrite is intentional
        filename = f"{base}-{counter}.json"
        path = TOURNAMENTS_DIR / filename
        counter += 1
    path.write_text(json.dumps(tournament.to_dict(), indent=2))
    return path


def load_tournament(path: Path) -> Tournament:
    data = json.loads(path.read_text())
    return Tournament.from_dict(data)


def list_tournaments() -> list[Tournament]:
    _ensure_dirs()
    tournaments = []
    for p in sorted(TOURNAMENTS_DIR.glob("*.json")):
        tournaments.append(load_tournament(p))
    return tournaments


def load_all_decklists() -> list[Decklist]:
    decklists: list[Decklist] = []
    for t in list_tournaments():
        decklists.extend(t.decklists)
    return decklists


def save_aggregated(name: str, data: dict) -> Path:
    _ensure_dirs()
    path = AGGREGATED_DIR / f"{_slugify(name)}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def load_aggregated(name: str) -> dict | None:
    _ensure_dirs()
    path = AGGREGATED_DIR / f"{_slugify(name)}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None
