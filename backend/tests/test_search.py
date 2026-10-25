from fastapi.testclient import TestClient
from magic_rag.app import create_app


def test_empty_corpus_still_explains_search_and_provider_state(tmp_path):
    with TestClient(create_app(tmp_path / "cards.db")) as client:
        response = client.post("/api/search", json={"question": "Lightning Bolt"})
    assert response.status_code == 200
    trace = response.json()
    assert trace["query"] == "Lightning Bolt"
    assert trace["mode"] == "keyword"
    assert trace["corpus"] is None
    assert trace["selected_evidence"] == []
    assert trace["generation"]["status"] == "unconfigured"
    assert trace["rewrite"]["status"] == "unavailable"


def test_sample_search_retains_all_faces_and_collapses_printings(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        trace = client.post("/api/search", json={"question": "Delver"}).json()
        assert len(trace["stages"]["keyword"]) == 1
        card = trace["selected_evidence"][0]
        assert card["name"] == "Delver of Secrets // Insectile Aberration"
        assert "Flying" in card["text"]
        assert "look at the top card" in card["text"]
        assert card["mana_value"] == 1
        assert card["colors"] == ["U"]
        assert trace["corpus"]["id"] == "controlled-sample-v1"
        assert client.post("/api/search", json={"question": "unfindableword"}).json()["selected_evidence"] == []


def test_keyword_ranking_literal_syntax_and_request_validation(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        trace = client.post("/api/search", json={"question": '"Lightning Bolt" (Sol)'}).json()
        cards = trace["stages"]["keyword"]
        assert cards[0]["name"] == "Lightning Bolt"
        assert [c["rank"] for c in cards] == [1, 2]
        assert cards[0]["score"] < cards[1]["score"]
        assert client.post("/api/search", json={"question": "???"}).status_code == 422
        assert client.post("/api/search", json={"question": "Bolt", "mode": "unknown"}).status_code == 422
        assert client.post("/api/search", json={"question": ""}).status_code == 422
