from fastapi.testclient import TestClient
from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from test_vectors import ControlledEmbedder


def test_hybrid_fuses_overlapping_cards_once_and_preserves_raw_branch_signals(tmp_path):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    with TestClient(create_app(path, embedder=model)) as client:
        response = client.post("/api/search", json={"question":"Sol Ring", "mode":"hybrid"})
        assert response.status_code == 200
        trace = response.json()
        assert set(trace["stages"]) == {"keyword", "vector", "fused"}
        fused = trace["stages"]["fused"]
        assert len(fused) == 3
        assert fused[0]["card_id"] == "sample-sol-ring"
        assert abs(fused[0]["score"] - 0.03278688524590164) < 1e-12
        assert fused[0]["signals"]["vector"] == {"rank":1,"score":0.0}
        assert fused[0]["signals"]["keyword"]["rank"] == 1
        assert fused[0]["signals"]["keyword"]["score"] < 0
        assert fused[1]["signals"].keys() == {"vector"}
        assert len({c["card_id"] for c in trace["selected_evidence"]}) == 3
        assert trace["timings_ms"]["fusion"] >= 0


def test_configured_counts_and_fusion_ties_keep_branch_only_cards_honest(tmp_path):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    with TestClient(create_app(path, embedder=model)) as client:
        trace = client.post("/api/search", json={"question":"Lightning Bolt card", "mode":"hybrid",
            "settings":{"keyword_candidates":1,"vector_candidates":1,"rrf_constant":0,"evidence_limit":1}}).json()
        assert [card["card_id"] for card in trace["stages"]["fused"]] == ["sample-lightning-bolt", "sample-sol-ring"]
        assert trace["stages"]["fused"][0]["score"] == 1.0
        assert trace["stages"]["fused"][1]["score"] == 1.0
        assert trace["stages"]["fused"][0]["signals"].keys() == {"keyword"}
        assert trace["stages"]["fused"][1]["signals"].keys() == {"vector"}
        assert len(trace["selected_evidence"]) == 1
        assert trace["settings"]["rrf_constant"] == 0


def test_empty_keyword_branch_keeps_vector_evidence_without_invented_signals(tmp_path):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    with TestClient(create_app(path, embedder=model)) as client:
        trace = client.post("/api/search", json={"question":"unmatchedword", "mode":"hybrid"}).json()
        assert trace["stages"]["keyword"] == []
        assert trace["selected_evidence"][0]["card_id"] == "sample-sol-ring"
        assert abs(trace["selected_evidence"][0]["score"] - 0.01639344262295082) < 1e-12
        assert all(card["signals"].keys() == {"vector"} for card in trace["stages"]["fused"])
        assert client.post("/api/search", json={"question":"Sol", "settings":{"vector_candidates":0}}).status_code == 422


def test_saved_hybrid_turn_and_provider_share_the_same_limited_evidence(tmp_path):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    class EvidenceProvider:
        def answer(self, question, evidence, session_id, *, context=None):
            assert len(evidence) == 1
            assert evidence[0]["card_id"] == "sample-sol-ring"
            return {"text":"This card produces mana.", "citations":["sample-sol-ring"], "insufficient_evidence":False}
    with TestClient(create_app(path, embedder=model, provider=EvidenceProvider())) as client:
        conversation = client.post("/api/conversations").json()
        trace = client.post("/api/search", json={"question":"Sol Ring", "mode":"hybrid", "generate_answer":True,
            "conversation_id":conversation["id"], "settings":{"evidence_limit":1}}).json()
        assert trace["generation"]["status"] == "completed"
        saved = client.get(f'/api/conversations/{conversation["id"]}').json()["turns"][0]["trace"]
        assert saved == trace
