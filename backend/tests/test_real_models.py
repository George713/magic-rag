"""Opt in with MAGIC_RAG_REAL_MODELS=1; downloads weights on first execution."""
import os
import pytest
from fastapi.testclient import TestClient
from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from magic_rag.vectors import BgeEmbedder, EmbeddingError
from magic_rag.reranking import MiniLmReranker, RerankingError


@pytest.mark.skipif(os.environ.get("MAGIC_RAG_REAL_MODELS") != "1", reason="Opt-in real-model smoke")
def test_real_bge_encoding_and_sqlite_vector_search(tmp_path):
    model = BgeEmbedder()
    path = tmp_path / "cards.db"
    ingest_sample(path, embedder=model)
    with TestClient(create_app(path, embedder=model)) as client:
        response = client.post("/api/search", json={"question":"a spell that deals three damage", "mode":"vector"})
        assert response.status_code == 200
        assert len(response.json()["selected_evidence"]) == 3
        assert response.json()["models"]["embedding"]["dimensions"] == 384
        assert len(response.json()["models"]["embedding"]["revision"]) == 40
    assert len(model.document("ability " * 600 + " final ability")) == 384
    with pytest.raises(EmbeddingError, match="not truncated"):
        model.query("ability " * 600)


@pytest.mark.skipif(os.environ.get("MAGIC_RAG_REAL_MODELS") != "1", reason="Opt-in real-model smoke")
def test_real_cross_encoder_reranks_and_rejects_oversized_pairs(tmp_path):
    embedder = BgeEmbedder()
    reranker = MiniLmReranker()
    path = tmp_path / "cards.db"
    ingest_sample(path, embedder=embedder)
    with TestClient(create_app(path, embedder=embedder, reranker=reranker)) as client:
        response = client.post("/api/search", json={"question":"a spell dealing three damage", "mode":"hybrid_rerank"})
        assert response.status_code == 200
        trace = response.json()
        assert len(trace["stages"]["reranked"]) == 3
        assert len(trace["models"]["reranker"]["revision"]) == 40
        assert trace["models"]["embedding"]["model"] != trace["models"]["reranker"]["model"]
    assert len(reranker.score("query", ["ability " * 600 + " final ability"])) == 1
    with pytest.raises(RerankingError, match="not truncated"):
        reranker.score("query " * 600, ["short evidence"])
