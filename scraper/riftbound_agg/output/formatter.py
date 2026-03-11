from __future__ import annotations

import csv
import io
import json


def format_table(recommendations: dict, title: str = "") -> str:
    lines: list[str] = []
    if title:
        lines.append(f"\n{'=' * 60}")
        lines.append(f"  {title}")
        lines.append(f"{'=' * 60}")

    # Could be per-section or flat tiers
    if _is_sectioned(recommendations):
        for section_name, tiers in recommendations.items():
            lines.append(f"\n--- {section_name} ---")
            lines.extend(_format_tiers(tiers))
    else:
        lines.extend(_format_tiers(recommendations))

    has_data = any(line.strip().startswith("[") for line in lines)
    if not has_data:
        lines.append("\nNo data found.")

    return "\n".join(lines)


def _is_sectioned(data: dict) -> bool:
    if not data:
        return False
    first_value = next(iter(data.values()))
    return isinstance(first_value, dict)


def _format_tiers(tiers: dict[str, list[dict]]) -> list[str]:
    lines: list[str] = []
    for tier_name, cards in tiers.items():
        if not cards:
            continue
        label = tier_name.upper()
        lines.append(f"\n  [{label}]")
        lines.append(f"  {'Card':<35} {'Rate':>7} {'Avg Qty':>8} {'Decks':>6}")
        lines.append(f"  {'-' * 35} {'-' * 7} {'-' * 8} {'-' * 6}")
        for c in cards:
            rate_pct = f"{c['inclusion_rate'] * 100:.1f}%"
            lines.append(
                f"  {c['name']:<35} {rate_pct:>7} {c['avg_copies']:>8.1f} {c['deck_count']:>6}"
            )
    return lines


def format_json(recommendations: dict) -> str:
    return json.dumps(recommendations, indent=2)


def format_csv(recommendations: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["section", "tier", "card", "inclusion_rate", "avg_copies", "deck_count", "total_decks"]
    )

    if _is_sectioned(recommendations):
        for section_name, tiers in recommendations.items():
            _write_tier_rows(writer, tiers, section_name)
    else:
        _write_tier_rows(writer, recommendations)

    return output.getvalue()


def _write_tier_rows(
    writer, tiers: dict[str, list[dict]], section: str = ""
) -> None:
    for tier_name, cards in tiers.items():
        for c in cards:
            writer.writerow(
                [
                    section or c.get("section", ""),
                    tier_name,
                    c["name"],
                    c["inclusion_rate"],
                    c["avg_copies"],
                    c["deck_count"],
                    c["total_decks"],
                ]
            )


def format_output(recommendations: dict, fmt: str = "table", title: str = "") -> str:
    if fmt == "json":
        return format_json(recommendations)
    elif fmt == "csv":
        return format_csv(recommendations)
    return format_table(recommendations, title=title)
