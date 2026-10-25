from fastapi.testclient import TestClient
from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from magic_rag.vectors import EmbeddingError


class ControlledEmbedder:
    config = {"model": "controlled", "revision": "1", "dimensions": 3,
              "normalization": True, "query_instruction": "", "input_policy": "reject-overlength"}

    def document(self, text):
        return [1., 0., 0.] if "Sol Ring" in text else ([0., 1., 0.] if "Delver" in text else [0., 0., 1.])

    def query(self, text):
        return [1., 0., 0.]


def test_vector_search_returns_real_sqlite_vec_distances_and_model_provenance(tmp_path):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    with TestClient(create_app(path, embedder=model)) as client:
        response = client.post("/api/search", json={"question": "accelerate mana", "mode": "vector"})
        assert response.status_code == 200
        trace = response.json()
        assert trace["stages"]["vector"][0]["name"] == "Sol Ring"
        assert trace["stages"]["vector"][0]["score"] == 0
        assert trace["models"]["embedding"] == model.config
        assert trace["settings"]["vector_metric"] == "cosine distance (lower is better)"
        assert len(trace["selected_evidence"]) == 3
        assert trace["timings_ms"]["vector"] >= 0


def test_missing_or_incompatible_embeddings_leave_keyword_search_available(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, embedder=ControlledEmbedder())) as client:
        assert "no embeddings" in client.post("/api/search", json={"question":"mana", "mode":"vector"}).json()["detail"]
    ingest_sample(path, embedder=ControlledEmbedder())
    class ChangedModel(ControlledEmbedder):
        config = {**ControlledEmbedder.config, "revision": "2"}
    with TestClient(create_app(path, embedder=ChangedModel())) as client:
        response = client.post("/api/search", json={"question":"mana", "mode":"vector"})
        assert response.status_code == 422
        assert "incompatible" in response.json()["detail"]
        assert client.post("/api/search", json={"question":"Sol Ring"}).json()["selected_evidence"][0]["name"] == "Sol Ring"


def test_overlength_query_error_is_actionable_and_preserves_corpus(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path, embedder=ControlledEmbedder())
    class LimitedModel(ControlledEmbedder):
        def query(self, text):
            raise EmbeddingError("Embedding input is 513 tokens; limit is 512. Input was not truncated.")
    with TestClient(create_app(path, embedder=LimitedModel())) as client:
        response = client.post("/api/search", json={"question":"long query", "mode":"vector"})
        assert response.status_code == 422
        assert "not truncated" in response.json()["detail"]
        assert client.get("/api/health").json()["card_count"] == 3
