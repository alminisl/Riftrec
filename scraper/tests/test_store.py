import json

from riftbound_agg.models import CardEntry, DeckSection, Decklist, Tournament
from riftbound_agg.storage import store


def _make_tournament(name="Test Open", url="https://example.com/t1"):
    return Tournament(
        name=name,
        url=url,
        date="2025-01-15",
        decklists=[
            Decklist(
                player="Alice",
                champion="Draven",
                legend="Garen",
                cards=[
                    CardEntry(name="Card A", quantity=4, section=DeckSection.MAIN),
                    CardEntry(name="Card B", quantity=2, section=DeckSection.SIDEBOARD),
                ],
            )
        ],
    )


def test_save_and_load_tournament(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TOURNAMENTS_DIR", tmp_path / "tournaments")
    monkeypatch.setattr(store, "AGGREGATED_DIR", tmp_path / "aggregated")

    t = _make_tournament()
    path = store.save_tournament(t)
    assert path.exists()

    loaded = store.load_tournament(path)
    assert loaded.name == t.name
    assert loaded.url == t.url
    assert len(loaded.decklists) == 1
    assert loaded.decklists[0].champion == "Draven"
    assert len(loaded.decklists[0].cards) == 2


def test_list_tournaments(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TOURNAMENTS_DIR", tmp_path / "tournaments")
    monkeypatch.setattr(store, "AGGREGATED_DIR", tmp_path / "aggregated")

    store.save_tournament(_make_tournament("T1", "https://example.com/1"))
    store.save_tournament(_make_tournament("T2", "https://example.com/2"))
    tournaments = store.list_tournaments()
    assert len(tournaments) == 2


def test_load_all_decklists(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TOURNAMENTS_DIR", tmp_path / "tournaments")
    monkeypatch.setattr(store, "AGGREGATED_DIR", tmp_path / "aggregated")

    store.save_tournament(_make_tournament())
    decklists = store.load_all_decklists()
    assert len(decklists) == 1
    assert decklists[0].player == "Alice"


def test_slugify_collision_avoidance(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TOURNAMENTS_DIR", tmp_path / "tournaments")
    monkeypatch.setattr(store, "AGGREGATED_DIR", tmp_path / "aggregated")

    t1 = _make_tournament("Same Name", "https://example.com/1")
    t2 = _make_tournament("Same Name", "https://example.com/2")

    p1 = store.save_tournament(t1)
    p2 = store.save_tournament(t2)

    assert p1 != p2
    assert p1.exists()
    assert p2.exists()


def test_save_aggregated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TOURNAMENTS_DIR", tmp_path / "tournaments")
    monkeypatch.setattr(store, "AGGREGATED_DIR", tmp_path / "aggregated")

    data = {"key": "value"}
    path = store.save_aggregated("test", data)
    assert path.exists()

    loaded = store.load_aggregated("test")
    assert loaded == data


def test_load_aggregated_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TOURNAMENTS_DIR", tmp_path / "tournaments")
    monkeypatch.setattr(store, "AGGREGATED_DIR", tmp_path / "aggregated")

    assert store.load_aggregated("nonexistent") is None
