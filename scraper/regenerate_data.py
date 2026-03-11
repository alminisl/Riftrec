"""Regenerate web/public/data.json from current tournament data."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from riftbound_agg.storage.store import load_all_decklists
from riftbound_agg.analysis.aggregator import aggregate, get_unique_legends


def normalize_legend_name(name: str) -> str:
    """Normalize legend names to merge variants."""
    # Canonical legend name mappings (scraped variant -> canonical)
    LEGEND_ALIASES = {
        "reksai, void burrower": "Rek'Sai, Void Burrower",
        "rek'sai, void burrower": "Rek'Sai, Void Burrower",
    }
    key = name.strip().lower()
    return LEGEND_ALIASES.get(key, name.strip())


def main():
    all_dl = load_all_decklists()
    print(f"Loaded {len(all_dl)} decklists")

    # Normalize legend names on all decklists
    for dl in all_dl:
        dl.legend = normalize_legend_name(dl.legend)

    legends = get_unique_legends(all_dl)
    print(f"Found {len(legends)} unique legends")

    # Load card images for name normalization
    cards_file = Path(__file__).parent.parent / "web" / "public" / "cards.json"
    card_images = {}
    if cards_file.exists():
        card_images = json.load(open(cards_file, "r", encoding="utf-8"))

    # Build a lookup: normalized name -> cards.json key
    card_name_map = {}
    for name in card_images:
        card_name_map[name.lower().strip()] = name

    img_dir = Path(__file__).parent.parent / "web" / "public" / "images" / "legends"
    existing_imgs = {f.stem for f in img_dir.glob("*.png")} if img_dir.exists() else set()

    SLUG_OVERRIDES = {
        "Sivir, Mercenary": "sivir-battle-mistress",
        "Rek'Sai, Void Burrower": "reksai-void-burrower",
    }

    result = {"legends": []}

    for legend in legends:
        stats = aggregate(all_dl, legend=legend)
        filtered = [d for d in all_dl if d.legend.strip().lower() == legend.strip().lower()]
        sections = {}
        for s in stats:
            d = s.to_dict()
            name = d["name"]
            # Skip corrupted card names (e.g. "Factory Recall1", "Ruin Runner2 Se")
            if re.search(r"\d+\s*[A-Za-z]{0,2}$", name) and not name[-1].isalpha():
                continue
            if re.search(r"[a-zA-Z]\d+", name):
                # Name has digit stuck to a letter like "Recall1" — likely parse error
                continue
            # Normalize card name to match cards.json
            norm_key = name.lower().strip()
            if norm_key in card_name_map:
                d["name"] = card_name_map[norm_key]
            sections.setdefault(d["section"], []).append(d)

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

        print(f"  {legend}: {len(filtered)} decks, {sum(len(v) for v in sections.values())} cards")

    result["legends"].sort(key=lambda x: -x["deck_count"])

    out = Path(__file__).parent.parent / "web" / "public" / "data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = sum(l["deck_count"] for l in result["legends"])
    print(f"\nFinal: {len(result['legends'])} legends, {total} decklists")
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
