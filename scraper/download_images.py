"""Download legend card images from riftdecks.com."""

import os
import re
import subprocess
import time

SLUGS = [
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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE_URL = "https://riftdecks.com"
OUTPUT_DIR = r"F:\Projects\riftrec\web\public\images\legends"


def fetch_page(url: str) -> str:
    """Fetch a page using curl and return the HTML."""
    result = subprocess.run(
        ["curl", "-s", "-L", "-A", USER_AGENT, url],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def download_file(url: str, dest: str) -> bool:
    """Download a file using curl. Returns True on success."""
    result = subprocess.run(
        ["curl", "-s", "-L", "-A", USER_AGENT, "-o", dest, url],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 0


def find_card_image(html: str) -> str | None:
    """Find the card image URL in the HTML."""
    # Match <img ... src="/img/cards/riftbound/..." ...> but not containing 'symbol'
    pattern = r'<img[^>]+src="(/img/cards/riftbound/[^"]+)"'
    matches = re.findall(pattern, html)
    for match in matches:
        if "symbol" not in match.lower():
            return match
    return None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = {"success": [], "failed": []}

    for i, slug in enumerate(SLUGS):
        print(f"[{i+1}/{len(SLUGS)}] Processing {slug}...")

        detail_url = f"{BASE_URL}/cards/details-{slug}"
        html = fetch_page(detail_url)

        if not html:
            print(f"  ERROR: Failed to fetch page for {slug}")
            results["failed"].append((slug, "failed to fetch page"))
            time.sleep(0.5)
            continue

        img_path = find_card_image(html)
        if not img_path:
            print(f"  ERROR: No card image found for {slug}")
            results["failed"].append((slug, "no card image found"))
            time.sleep(0.5)
            continue

        img_url = f"{BASE_URL}{img_path}"
        dest = os.path.join(OUTPUT_DIR, f"{slug}.png")

        print(f"  Image URL: {img_url}")
        success = download_file(img_url, dest)

        if success:
            size_kb = os.path.getsize(dest) / 1024
            print(f"  Downloaded: {dest} ({size_kb:.1f} KB)")
            results["success"].append(slug)
        else:
            print(f"  ERROR: Failed to download image for {slug}")
            results["failed"].append((slug, "download failed"))

        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Successfully downloaded: {len(results['success'])}/{len(SLUGS)}")
    if results["success"]:
        for s in results["success"]:
            print(f"  OK: {s}")
    if results["failed"]:
        print(f"\nFailed: {len(results['failed'])}")
        for s, reason in results["failed"]:
            print(f"  FAIL: {s} - {reason}")


if __name__ == "__main__":
    main()
