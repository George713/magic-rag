from fastapi.testclient import TestClient
import pytest

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from test_vectors import ControlledEmbedder
from test_reranking import ControlledReranker


def controlled_suite():
    return {"version":"controlled-v1", "review":"Controlled positive judgment for an independently known rank.",
            "source":{"snapshot":"controlled-sample-v1"},
            "questions":[{"id":"q1", "category":"controlled", "question":"Sol Ring artifact", "filters":{},
                          "qrels":[{"card_id":"sample-delver", "name":"Delver of Secrets // Insectile Aberration", "relevance":1, "rationale":"Controlled positive at rank two before reranking."}],
                          "unsupported":False, "review":"Controlled ranking fixture."}]}


def test_benchmark_reports_all_modes_known_positive_metrics_and_original_traces(tmp_path):
    path = tmp_path / "cards.db"
    embedder = ControlledEmbedder()
    ingest_sample(path, embedder=embedder)
    with TestClient(create_app(path, embedder=embedder, reranker=ControlledReranker())) as client:
        response = client.post("/api/benchmark", json={"suite":controlled_suite(), "warmup":False})
    assert response.status_code == 200
    report = response.json()
    assert report["cutoff"] == 5
    assert report["quality_question_count"] == 1
    assert report["corpus"]["id"] == "controlled-sample-v1"
    runs = report["questions"][0]["runs"]
    assert set(runs) == {"keyword", "vector", "hybrid", "hybrid_rerank"}
    assert runs["keyword"]["metrics"]["mrr"] == 0
    assert runs["vector"]["metrics"] == pytest.approx({"mrr":0.5,"ndcg":0.6309297535714575,"known_positive_precision":0.2})
    assert runs["hybrid_rerank"]["metrics"] == {"mrr":1.0,"ndcg":1.0,"known_positive_precision":0.2}
    assert runs["vector"]["trace"]["selected_evidence"][1]["card_id"] == "sample-delver"
    assert report["models"]["embedding"] == embedder.config
    assert report["aggregates"]["vector"]["mean_metrics"]["mrr"] == 0.5
    assert report["environment"]["python"]


def test_exact_constraints_and_unsupported_probes_keep_quality_denominators_honest(tmp_path):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    suite = controlled_suite()
    suite["questions"][0]["filters"] = {"colors":["U"],"card_types":["Creature"],"mana_value_max":1}
    suite["questions"].append({**suite["questions"][0],"id":"unsupported","filters":{},"qrels":[],"unsupported":True})
    with TestClient(create_app(path, embedder=model, reranker=ControlledReranker())) as client:
        report = client.post("/api/benchmark", json={"suite":suite,"warmup":False}).json()
    assert report["quality_question_count"] == 1
    supported, unsupported = report["questions"]
    for run in supported["runs"].values():
        assert run["trace"]["filters"] == {"colors":["U"],"card_types":["Creature"],"mana_value_max":1.0}
        assert all(card["card_id"] == "sample-delver" for card in run["trace"]["selected_evidence"])
    assert unsupported["runs"]["vector"]["metrics"] is None
    assert unsupported["runs"]["vector"]["trace"]["selected_evidence"]
    assert report["aggregates"]["vector"]["mean_metrics"]["mrr"] == 1
    assert report["aggregates"]["keyword"]["mean_metrics"] == {"mrr":0.0,"ndcg":0.0,"known_positive_precision":0.0}


def test_report_records_warmups_settings_metric_definitions_and_execution_environment(tmp_path):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    settings = {"keyword_candidates":3,"vector_candidates":3,"rrf_constant":10,"rerank_candidates":3,"evidence_limit":5}
    with TestClient(create_app(path, embedder=model, reranker=ControlledReranker())) as client:
        report = client.post("/api/benchmark", json={"suite":controlled_suite(),"warmup":True,"settings":settings}).json()
    assert len(report["warmups"]) == 4
    assert report["settings"] == settings
    assert "unjudged" in report["judgment_policy"].lower()
    assert report["metric_definitions"]["known_positive_precision"].startswith("Known positives")
    assert report["suite_sha256"]
    assert report["source"] == {"snapshot":"controlled-sample-v1"}
    assert report["environment"]["platform"]
    assert report["environment"]["cpu_count"] >= 1
    for run in report["questions"][0]["runs"].values():
        assert run["application_call_ms"] >= 0
        assert run["trace"]["timings_ms"]["retrieval"] >= 0
        assert run["trace"]["settings"]["rrf_constant"] == 10


@pytest.mark.parametrize("mutation", ["cutoff_exceeds_evidence","duplicate_question","unsupported_positive","missing_positive","invalid_settings"])
def test_invalid_benchmark_definitions_fail_before_reporting_scores(tmp_path, mutation):
    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    suite = controlled_suite()
    payload = {"suite":suite,"warmup":False}
    if mutation == "cutoff_exceeds_evidence": payload["cutoff"] = 6
    if mutation == "duplicate_question": suite["questions"].append(suite["questions"][0])
    if mutation == "unsupported_positive": suite["questions"][0]["unsupported"] = True
    if mutation == "missing_positive": suite["questions"][0]["qrels"] = []
    if mutation == "invalid_settings": payload["settings"] = {"keyword_candidates":0}
    with TestClient(create_app(path, embedder=model, reranker=ControlledReranker())) as client:
        assert client.post("/api/benchmark", json=payload).status_code == 422


def test_empty_corpus_is_an_actionable_benchmark_prerequisite(tmp_path):
    with TestClient(create_app(tmp_path / "empty.db", embedder=ControlledEmbedder(), reranker=ControlledReranker())) as client:
        response = client.post("/api/benchmark", json={"suite":controlled_suite(),"warmup":False})
    assert response.status_code == 409
    assert "corpus" in response.json()["detail"].lower()


def test_default_reviewed_suite_runs_twenty_questions_with_auditable_markdown(tmp_path):
    class NeutralReranker:
        config = {"model":"controlled-neutral","revision":"1"}
        def score(self, query, documents):
            return [1.0] * len(documents)

    path = tmp_path / "cards.db"
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    with TestClient(create_app(path, embedder=model, reranker=NeutralReranker())) as client:
        response = client.post("/api/benchmark?format=markdown", json={"warmup":False})
    assert response.status_code == 200
    assert "Known-positive retrieval benchmark" in response.text
    assert "18 supported questions" in response.text
    assert "q16" in response.text
    assert "hybrid_rerank" in response.text
    assert "not exhaustive" in response.text
    assert "controlled-sample-v1" in response.text
