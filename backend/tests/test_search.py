from fastapi.testclient import TestClient
from magic_rag.app import create_app
import pytest


def test_empty_corpus_still_explains_search_and_provider_state(tmp_path):
    with TestClient(create_app(tmp_path / "cards.db")) as client:
        response = client.post("/api/search", json={"question": "Lightning Bolt"})
        assert client.get("/api/provider").json()["status"] == "unconfigured"
    assert response.status_code == 200
    trace = response.json()
    assert trace["searches"][0]["query"] == "Lightning Bolt"
    assert trace["searches"][0]["mode"] == "keyword"
    assert trace["corpus"] is None
    assert trace["selected_evidence"] == []
    assert "rewrite" not in trace


@pytest.mark.parametrize("extra", [{"generate_answer": True}, {"conversation_id": "chat"}])
def test_search_is_plain_retrieval_that_never_answers_or_saves_a_turn(tmp_path, extra):
    from magic_rag.ingest import ingest_sample
    from scripted_chat_model import ScriptedChatModel
    path = tmp_path / "cards.db"
    ingest_sample(path)
    model = ScriptedChatModel(script=[])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        extra = {key: conversation_id if key == "conversation_id" else value for key, value in extra.items()}
        assert client.post("/api/search", json={"question": "Delver", **extra}).status_code == 422
        trace = client.post("/api/search", json={"question": "Delver"}).json()
        assert trace["selected_evidence"][0]["card_id"] == "sample-delver"
        assert not {"generation", "answer_context", "conversation_id", "turn_id"} & trace.keys()
        assert client.get(f"/api/conversations/{conversation_id}").json()["turns"] == []
    assert model.calls == []


def test_sample_search_retains_all_faces_and_collapses_printings(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        trace = client.post("/api/search", json={"question": "Delver"}).json()
        assert len(trace["searches"][0]["stages"]["keyword"]) == 1
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
        cards = trace["searches"][0]["stages"]["keyword"]
        assert cards[0]["name"] == "Lightning Bolt"
        assert [c["rank"] for c in cards] == [1, 2]
        assert cards[0]["score"] < cards[1]["score"]
        assert client.post("/api/search", json={"question": "???"}).status_code == 422
        assert client.post("/api/search", json={"question": "Bolt", "mode": "unknown"}).status_code == 422
        assert client.post("/api/search", json={"question": ""}).status_code == 422


@pytest.mark.parametrize("mode", ["keyword", "vector", "hybrid", "hybrid_rerank"])
@pytest.mark.parametrize("limit", [1, 20])
def test_exact_name_precedes_split_card_despite_raw_scores(tmp_path, mode, limit):
    from magic_rag.app import connect
    from magic_rag.ingest import ingest_sample
    from test_vectors import ControlledEmbedder

    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    with connect(path) as db:
        # A shorter document wins BM25; a different card wins vector distance.
        db.execute("UPDATE card_fts SET text = ? WHERE card_id = 'sample-lightning-bolt'",
                   ("Lightning Bolt " + "filler " * 200,))
        db.execute("UPDATE cards SET name = 'Lightning // Bolt' WHERE card_id = 'sample-sol-ring'")
        db.execute("UPDATE card_fts SET text = 'Lightning // Bolt' WHERE card_id = 'sample-sol-ring'")

    class PreferSplitCard:
        config = {"model": "controlled"}

        def score(self, query, documents):
            return [9.0 if "Lightning // Bolt" in text else 1.0 for text in documents]

    with TestClient(create_app(path, embedder=model, reranker=PreferSplitCard())) as client:
        response = client.post("/api/search", json={
            "question": "  lIgHtNiNg bOlT  ", "mode": mode,
            "settings": {"keyword_candidates": limit, "vector_candidates": limit,
                         "rerank_candidates": 1 if limit == 1 else 40, "evidence_limit": 1},
        })
        assert response.status_code == 200
        trace = response.json()
        for cards in trace["searches"][0]["stages"].values():
            assert cards[0]["name"] == "Lightning Bolt"
            assert cards[0]["rank"] == 1
            assert len({card["card_id"] for card in cards}) == len(cards)
        assert trace["selected_evidence"][0]["name"] == "Lightning Bolt"
        # Exact-name priority must never override explicit eligibility filters.
        filtered = client.post("/api/search", json={
            "question": "lightning bolt", "mode": mode, "filters": {"colors": []},
        }).json()
        assert all(card["name"] != "Lightning Bolt" for card in filtered["selected_evidence"])
