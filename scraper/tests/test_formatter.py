from riftbound_agg.output.formatter import (
    _is_sectioned,
    format_csv,
    format_json,
    format_output,
    format_table,
)


SAMPLE_TIERS = {
    "staple": [
        {
            "name": "Card A",
            "section": "Main Deck",
            "inclusion_rate": 0.95,
            "avg_copies": 3.8,
            "deck_count": 19,
            "total_decks": 20,
        }
    ],
    "common": [],
    "uncommon": [],
    "niche": [],
}

SAMPLE_SECTIONED = {
    "Main Deck": SAMPLE_TIERS,
    "Sideboard": {
        "staple": [],
        "common": [
            {
                "name": "Card B",
                "section": "Sideboard",
                "inclusion_rate": 0.60,
                "avg_copies": 2.0,
                "deck_count": 12,
                "total_decks": 20,
            }
        ],
        "uncommon": [],
        "niche": [],
    },
}


def test_is_sectioned_true():
    assert _is_sectioned(SAMPLE_SECTIONED) is True


def test_is_sectioned_false():
    assert _is_sectioned(SAMPLE_TIERS) is False


def test_is_sectioned_empty():
    assert _is_sectioned({}) is False


def test_format_table_flat():
    output = format_table(SAMPLE_TIERS, title="Test")
    assert "Card A" in output
    assert "95.0%" in output
    assert "STAPLE" in output


def test_format_table_sectioned():
    output = format_table(SAMPLE_SECTIONED, title="Test")
    assert "Main Deck" in output
    assert "Sideboard" in output
    assert "Card B" in output


def test_format_json():
    output = format_json(SAMPLE_TIERS)
    assert '"Card A"' in output
    assert '"staple"' in output


def test_format_csv():
    output = format_csv(SAMPLE_TIERS)
    lines = output.strip().split("\n")
    assert len(lines) == 2  # header + 1 data row
    assert "Card A" in lines[1]
    assert "0.95" in lines[1]


def test_format_csv_sectioned():
    output = format_csv(SAMPLE_SECTIONED)
    assert "Main Deck" in output
    assert "Sideboard" in output


def test_format_output_dispatch():
    assert '"staple"' in format_output(SAMPLE_TIERS, fmt="json")
    assert "Card A" in format_output(SAMPLE_TIERS, fmt="csv")
    assert "STAPLE" in format_output(SAMPLE_TIERS, fmt="table")
