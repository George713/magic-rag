from fastapi.testclient import TestClient
from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from test_vectors import ControlledEmbedder
from magic_rag.reranking import RerankingError


class ControlledReranker:
    config = {"model":"controlled-reranker","revision":"1","input_policy":"reject-overlength"}
    def score(self, query, documents):
        assert query in ("Sol Ring", "Sol Ring artifact")
        return [9.0 if "Flying" in text else 1.0 for text in documents]


def test_reranker_changes_evidence_order_and_preserves_fused_positions_and_signals(tmp_path):
    path = tmp_path / "cards.db"
    embedder = ControlledEmbedder()
    ingest_sample(path, embedder=embedder)
    with TestClient(create_app(path, embedder=embedder, reranker=ControlledReranker())) as client:
        trace = client.post("/api/search", json={"question":"Sol Ring artifact", "mode":"hybrid_rerank",
            "settings":{"rerank_candidates":2,"evidence_limit":1}}).json()
        assert trace["stages"]["fused"][0]["card_id"] == "sample-sol-ring"
        reranked = trace["stages"]["reranked"]
        assert [c["card_id"] for c in reranked] == ["sample-delver", "sample-sol-ring"]
        assert reranked[0]["score"] == 9.0
        assert reranked[0]["fused_rank"] == 2
        assert reranked[0]["rank_change"] == 1
        assert reranked[1]["rank_change"] == -1
        assert reranked[0]["fusion_score"] == trace["stages"]["fused"][1]["score"]
        assert reranked[0]["signals"] == trace["stages"]["fused"][1]["signals"]
        assert trace["selected_evidence"] == [reranked[0]]
        assert trace["models"]["embedding"] == embedder.config
        assert trace["models"]["reranker"] == ControlledReranker.config
        assert trace["timings_ms"]["reranking"] >= 0


def test_reranker_failure_and_nonfinite_scores_are_explicit_and_other_modes_remain_usable(tmp_path):
    path = tmp_path / "cards.db"
    embedder = ControlledEmbedder()
    ingest_sample(path, embedder=embedder)
    class TooLong(ControlledReranker):
        def score(self, query, documents):
            raise RerankingError("Reranker query/card pair exceeds 512 tokens. Evidence was not truncated.")
    with TestClient(create_app(path, embedder=embedder, reranker=TooLong())) as client:
        response = client.post("/api/search", json={"question":"Sol Ring", "mode":"hybrid_rerank"})
        assert response.status_code == 422
        assert "not truncated" in response.json()["detail"]
        assert client.post("/api/search", json={"question":"Sol Ring", "mode":"hybrid"}).status_code == 200
    class InvalidScores(ControlledReranker):
        def score(self, query, documents):
            return [float("nan")] * len(documents)
    with TestClient(create_app(path, embedder=embedder, reranker=InvalidScores())) as client:
        assert client.post("/api/search", json={"question":"Sol Ring", "mode":"hybrid_rerank"}).status_code == 422


def test_other_modes_bypass_reranking_and_replacing_reranker_reuses_vectors(tmp_path):
    path = tmp_path / "cards.db"
    embedder = ControlledEmbedder()
    ingest_sample(path, embedder=embedder)
    class UnavailableReranker:
        @property
        def config(self):
            raise AssertionError("Non-reranking mode touched reranker")
        def score(self, query, documents):
            raise AssertionError("Non-reranking mode touched reranker")
    with TestClient(create_app(path, embedder=embedder, reranker=UnavailableReranker())) as client:
        for mode in ("keyword", "vector", "hybrid"):
            trace = client.post("/api/search", json={"question":"Sol Ring", "mode":mode}).json()
            assert "reranked" not in trace["stages"]
            assert "reranker" not in trace["models"]
    class ChangedReranker(ControlledReranker):
        config = {**ControlledReranker.config, "revision":"2"}
    with TestClient(create_app(path, embedder=embedder, reranker=ChangedReranker())) as client:
        trace = client.post("/api/search", json={"question":"Sol Ring", "mode":"hybrid_rerank"}).json()
        assert trace["models"]["reranker"]["revision"] == "2"
        assert trace["models"]["embedding"] == embedder.config
