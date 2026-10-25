from fastapi.testclient import TestClient
import pytest

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from test_vectors import ControlledEmbedder


@pytest.mark.parametrize("mode", ["keyword", "vector", "hybrid"])
def test_exact_filters_limit_candidates_before_each_branch_ranks(tmp_path, mode):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    with TestClient(create_app(path, embedder=model)) as client:
        response = client.post("/api/search", json={
            "question": "Sol Ring Delver", "mode": mode,
            "filters": {"colors": ["U"], "card_types": ["Creature"], "mana_value_min": 1, "mana_value_max": 1},
            "settings": {"keyword_candidates": 1, "vector_candidates": 1}})
        assert response.status_code == 200
        trace = response.json()
        assert trace["filters"]["colors"] == ["U"]
        for candidates in trace["stages"].values():
            assert [card["card_id"] for card in candidates] == ["sample-delver"]
        assert trace["selected_evidence"][0]["name"] == "Delver of Secrets // Insectile Aberration"


def seed_filter_fixture(path):
    """Arrange real source data; all behavior assertions use the FastAPI seam."""
    import json
    from magic_rag.app import connect
    from magic_rag.vectors import store_vectors
    fixtures = [
        ("red", "Red creature", 1, ["R"], "Creature — Wizard"),
        ("dual", "Two-color construct", 2.5, ["R", "U"], "Artifact Creature — Construct"),
        ("colorless", "Colorless construct", 0, [], "Artifact Creature — Construct"),
        ("subtype", "Subtype decoy", 0.5, ["U"], "Enchantment — Creature"),
        ("faces", "Multi-face fixture", 3, ["W"], "Instant // Creature — Human"),
        ("artifact", "Equipment fixture", 2, ["U"], "Artifact — Equipment"),
    ]
    with connect(path) as db:
        for card_id, name, mana_value, colors, type_line in fixtures:
            db.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (card_id, name, "fixture ability", "", mana_value, json.dumps(colors), type_line))
            db.execute("INSERT INTO card_fts VALUES (?, ?)", (card_id, f"{name} fixture ability"))
        db.execute("INSERT INTO corpus VALUES ('filter-fixture', '{}')")
        store_vectors(db, [(row[0], row[1]) for row in fixtures], ControlledEmbedder())


@pytest.mark.parametrize("mode", ["keyword", "vector", "hybrid"])
@pytest.mark.parametrize("filters, expected", [
    ({"colors": []}, {"colorless"}),
    ({"colors": ["R"]}, {"red"}),
    ({"colors": ["U", "R"]}, {"dual"}),
    ({"card_types": ["Artifact", "Creature"]}, {"dual", "colorless"}),
    ({"card_types": ["Creature"]}, {"red", "dual", "colorless", "faces"}),
    ({"card_types": ["Instant", "Creature"]}, {"faces"}),
    ({"mana_value_min": 0, "mana_value_max": 0}, {"colorless"}),
    ({"mana_value_min": 0.5, "mana_value_max": 2.5}, {"red", "dual", "subtype", "artifact"}),
])
def test_exact_color_type_and_inclusive_fractional_mana_boundaries(tmp_path, mode, filters, expected):
    path = tmp_path / "cards.db"
    seed_filter_fixture(path)
    with TestClient(create_app(path, embedder=ControlledEmbedder())) as client:
        response = client.post("/api/search", json={"question": "fixture", "mode": mode, "filters": filters})
        assert response.status_code == 200
        for stage in response.json()["stages"].values():
            assert {card["card_id"] for card in stage} == expected


def test_clearing_filters_returns_candidates_and_keeps_saved_trace_constraints(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path, embedder=ControlledEmbedder())
    with TestClient(create_app(path, embedder=ControlledEmbedder())) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        trace = client.post("/api/search", json={"question": "Sol Ring", "mode": "hybrid", "conversation_id": conversation_id,
                            "filters": {"colors": ["G"]}}).json()
        assert all(not candidates for candidates in trace["stages"].values())
        cleared = client.post("/api/search", json={"question": "Sol Ring", "mode": "hybrid", "filters": {}}).json()
        assert cleared["selected_evidence"][0]["card_id"] == "sample-sol-ring"
        assert cleared["filters"] == {}
        saved = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["trace"]
        assert saved["filters"] == {"colors": ["G"]}


@pytest.mark.parametrize("filters", [
    {"mana_value_min": 3, "mana_value_max": 2}, {"mana_value_min": -0.1},
    {"colors": ["purple"]}, {"card_types": ["Wizard"]}, {"mana_value_max": "Infinity"},
    {"unsupported_control": True},
])
def test_invalid_filters_are_rejected_explicitly(tmp_path, filters):
    with TestClient(create_app(tmp_path / "cards.db")) as client:
        assert client.post("/api/search", json={"question": "fixture", "filters": filters}).status_code == 422
