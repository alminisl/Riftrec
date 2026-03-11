import pytest

from riftbound_agg.cli import build_parser, main
from riftbound_agg.storage import store
from riftbound_agg.models import CardEntry, DeckSection, Decklist, Tournament


def _seed_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TOURNAMENTS_DIR", tmp_path / "tournaments")
    monkeypatch.setattr(store, "AGGREGATED_DIR", tmp_path / "aggregated")

    t = Tournament(
        name="Test Open",
        url="https://example.com",
        date="2025-06-01",
        decklists=[
            Decklist(
                player="Alice",
                champion="Draven",
                legend="Garen",
                cards=[
                    CardEntry("Card A", 4, DeckSection.MAIN),
                    CardEntry("Card B", 2, DeckSection.MAIN),
                    CardEntry("Rune X", 1, DeckSection.RUNES),
                ],
            ),
            Decklist(
                player="Bob",
                champion="Draven",
                legend="Garen",
                cards=[
                    CardEntry("Card A", 3, DeckSection.MAIN),
                    CardEntry("Card C", 1, DeckSection.MAIN),
                ],
            ),
        ],
    )
    store.save_tournament(t)


def test_parser_scrape():
    parser = build_parser()
    args = parser.parse_args(["scrape", "https://example.com"])
    assert args.command == "scrape"
    assert args.url == "https://example.com"


def test_parser_list():
    parser = build_parser()
    args = parser.parse_args(["list", "champions"])
    assert args.command == "list"
    assert args.what == "champions"


def test_parser_recommend():
    parser = build_parser()
    args = parser.parse_args(["recommend", "Draven", "--format", "json", "--top", "5"])
    assert args.command == "recommend"
    assert args.name == "Draven"
    assert args.fmt == "json"
    assert args.top == 5


def test_cmd_stats(tmp_path, monkeypatch, capsys):
    _seed_data(tmp_path, monkeypatch)
    main(["stats"])
    out = capsys.readouterr().out
    assert "Tournaments:" in out
    assert "Decklists:" in out


def test_cmd_list_champions(tmp_path, monkeypatch, capsys):
    _seed_data(tmp_path, monkeypatch)
    main(["list", "champions"])
    out = capsys.readouterr().out
    assert "Draven" in out


def test_cmd_list_tournaments(tmp_path, monkeypatch, capsys):
    _seed_data(tmp_path, monkeypatch)
    main(["list", "tournaments"])
    out = capsys.readouterr().out
    assert "Test Open" in out


def test_cmd_recommend_table(tmp_path, monkeypatch, capsys):
    _seed_data(tmp_path, monkeypatch)
    main(["recommend", "Draven"])
    out = capsys.readouterr().out
    assert "Card A" in out


def test_cmd_recommend_json(tmp_path, monkeypatch, capsys):
    _seed_data(tmp_path, monkeypatch)
    main(["recommend", "Draven", "--format", "json"])
    out = capsys.readouterr().out
    assert '"staple"' in out or '"common"' in out or '"niche"' in out


def test_cmd_recommend_export(tmp_path, monkeypatch, capsys):
    _seed_data(tmp_path, monkeypatch)
    export_file = tmp_path / "output.csv"
    main(["recommend", "Draven", "--format", "csv", "--export", str(export_file)])
    assert export_file.exists()
    content = export_file.read_text()
    assert "Card A" in content


def test_cmd_recommend_bad_export_suffix(tmp_path, monkeypatch):
    _seed_data(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        main(["recommend", "Draven", "--export", "output.exe"])
