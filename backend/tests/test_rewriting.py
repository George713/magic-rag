import json

from fastapi.testclient import TestClient
import pytest

from magic_rag.app import create_app, connect
from magic_rag.vectors import store_vectors
from scripted_chat_model import ScriptedChatModel


INITIAL = "Find artifact-sacrifice creatures"
FOLLOWUP = "Any cheaper ones?"
STANDALONE = "Atog artifact sacrifice cheaper creatures"
ATOG = "3095f2cf-05c3-4381-929f-c526b6fc30a7"
ENGINEER = "c1d6cce8-085f-42cb-8b0c-b6fbbf88b16a"


class TopicEmbedder:
    config = {"model": "rewrite-test-embedding", "revision": "1", "dimensions": 2}

    def document(self, text):
        return [1.0, 0.0] if text.startswith("Atog") else [0.0, 1.0]

    def query(self, text):
        return [1.0, 0.0] if text.startswith("Atog") else [0.0, 1.0]


class TopicReranker:
    config = {"model": "rewrite-test-reranker", "revision": "1"}

    def score(self, query, documents):
        return [9.0 if text.startswith("Atog") == query.startswith("Atog") else 1.0 for text in documents]


def seed_artifact_cards(path):
    cards = [
        (ATOG, "Atog", "Sacrifice an artifact: This creature gets +2/+2 until end of turn.", "{1}{R}", 2, '["R"]', "Creature — Atog"),
        (ENGINEER, "Goblin Engineer", "When this creature enters, you may search your library for an artifact card, put it into your graveyard, then shuffle.\n{R}, {T}, Sacrifice an artifact: Return target artifact card with mana value 3 or less from your graveyard to the battlefield.", "{1}{R}", 2, '["R"]', "Creature — Goblin Artificer"),
    ]
    with connect(path) as db:
        for card in cards:
            db.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?)", card)
            db.execute("INSERT INTO card_fts VALUES (?, ?)", (card[0], f"{card[1]} {card[2]} {card[6]}"))
        db.execute("INSERT INTO corpus VALUES ('rewrite-fixture', '{}')")
        store_vectors(db, [(card[0], f"{card[1]} {card[2]}") for card in cards], TopicEmbedder())


def is_rewrite(call):
    return "history" in call.source


def topic_model(call):
    if is_rewrite(call):
        history = call.source["history"]
        assert history[-1]["question"] == INITIAL
        assert history[-1]["query"] == INITIAL
        assert "selected_evidence" not in history[-1]
        return {"query": STANDALONE}
    assert call.source["question"] == FOLLOWUP
    return {"text": "Atog sacrifices artifacts.", "citations": [ATOG], "insufficient_evidence": False}


@pytest.mark.parametrize("mode", ["keyword", "vector", "hybrid", "hybrid_rerank"])
def test_followup_uses_standalone_topic_in_every_stage_and_retains_filters(tmp_path, mode):
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    filters = {"card_types": ["Creature"], "mana_value_max": 2}
    with TestClient(create_app(path, embedder=TopicEmbedder(), reranker=TopicReranker(), chat_model=ScriptedChatModel(script=topic_model))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        initial = client.post("/api/search", json={"question": INITIAL, "mode": mode, "conversation_id": conversation_id, "filters": filters}).json()
        response = client.post("/api/search", json={"question": FOLLOWUP, "mode": mode, "conversation_id": conversation_id, "generate_answer": True})
        assert response.status_code == 200
        trace = response.json()
        assert trace["question"] == FOLLOWUP
        assert trace["query"] == STANDALONE
        assert trace["rewrite"]["status"] == "rewritten"
        assert trace["timings_ms"]["rewrite"] >= 0
        assert trace["filters"] == filters
        assert trace["selected_evidence"][0]["card_id"] == ATOG
        assert trace["generation"]["status"] == "completed"
        saved = client.get(f"/api/conversations/{conversation_id}").json()["turns"]
        assert saved[0]["trace"] == initial
        assert saved[1]["trace"] == trace


def test_rewrite_sends_conversation_context_in_a_separate_call_with_the_conversation_session(tmp_path):
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)

    def rewrite(call):
        assert call.source["question"] == FOLLOWUP
        assert call.source["history"] == [{"question": INITIAL, "query": INITIAL}]
        assert "selected_evidence" not in call.source
        return {"query": STANDALONE}

    model = ScriptedChatModel(script=[rewrite])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question": INITIAL, "conversation_id": conversation_id})
        response = client.post("/api/search", json={"question": FOLLOWUP, "conversation_id": conversation_id})
        assert response.json()["query"] == STANDALONE
        assert response.json()["rewrite"]["status"] == "rewritten"
        assert [call.session for call in model.calls] == [conversation_id]
        assert model.calls[0].kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("payload", [None, {"query": ""}, {"query": "???"}, {"query": 12},
                                    {"query": STANDALONE, "filters": {}}, "provider failure"])
def test_rewrite_failure_searches_exact_submitted_text_under_retained_filters(tmp_path, payload):
    step = RuntimeError("private-provider-key-and-endpoint") if payload == "provider failure" else json.dumps(payload)
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[step]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question": INITIAL, "conversation_id": conversation_id, "filters": {"colors": ["R"]}})
        original = "  Any cheaper ones?  "
        response = client.post("/api/search", json={"question": original, "conversation_id": conversation_id})
        trace = response.json()
        assert trace["query"] == original
        assert trace["rewrite"]["status"] == "unavailable"
        assert "as-is" in trace["rewrite"]["message"]
        assert trace["filters"] == {"colors": ["R"]}
        assert trace["selected_evidence"] == []
        assert "private-provider" not in response.text
        subsequent = client.post("/api/search", json={"question": "Atog", "conversation_id": conversation_id}).json()
        assert subsequent["selected_evidence"][0]["card_id"] == ATOG


def test_absent_provider_retains_filters_and_explicit_empty_object_clears_them(tmp_path):
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        initial = client.post("/api/search", json={"question": INITIAL, "conversation_id": conversation_id,
                                                  "filters": {"mana_value_max": 0}}).json()
        inherited = client.post("/api/search", json={"question": "Atog", "conversation_id": conversation_id}).json()
        assert inherited["query"] == "Atog"
        assert inherited["rewrite"]["status"] == "unavailable"
        assert inherited["filters"] == {"mana_value_max": 0}
        assert inherited["selected_evidence"] == []
        cleared = client.post("/api/search", json={"question": "Atog", "conversation_id": conversation_id, "filters": {}}).json()
        assert cleared["filters"] == {}
        assert cleared["selected_evidence"][0]["card_id"] == ATOG
        assert client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["trace"] == initial


def test_history_is_isolated_between_conversations(tmp_path):
    def isolated(call):
        return {"query": call.source["history"][-1]["query"] + " " + call.source["question"]}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=isolated))) as client:
        first = client.post("/api/conversations").json()["id"]
        second = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question": INITIAL, "conversation_id": first, "filters": {"colors": ["R"]}})
        other = client.post("/api/search", json={"question": "Another private topic", "conversation_id": second,
                                                "filters": {"colors": ["U"]}}).json()
        assert other["query"] == "Another private topic"
        assert other["rewrite"]["status"] == "not_needed"
        followup = client.post("/api/search", json={"question": FOLLOWUP, "conversation_id": second}).json()
        assert followup["query"] == "Another private topic Any cheaper ones?"
        assert followup["filters"] == {"colors": ["U"]}
        assert INITIAL not in followup["query"]


def test_unconfirmed_workload_never_sends_a_rewrite_request(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_URL", "https://provider.example/chat/completions")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_MODEL", "model")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_API_KEY", "private-key")
    monkeypatch.delenv("MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED", raising=False)
    with TestClient(create_app(tmp_path / "cards.db")) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question": INITIAL, "conversation_id": conversation_id})
        followup = client.post("/api/search", json={"question": FOLLOWUP, "conversation_id": conversation_id})
        assert followup.json()["rewrite"]["status"] == "unavailable"
        assert followup.json()["query"] == FOLLOWUP
        assert "private-key" not in followup.text


def test_rewrite_context_includes_completed_answers_but_omits_failed_partial_output(tmp_path):
    async def failed_stream(call):
        yield '{"text": "Unfinished unverified thought'
        raise RuntimeError("Controlled failed stream")

    def context_model(call):
        question = call.source["question"]
        if is_rewrite(call):
            history = call.source["history"]
            assert "answer" not in history[0]
            if question == FOLLOWUP:
                assert history[1]["answer"] == "Atog sacrifices artifacts."
                assert all("selected_evidence" not in item for item in history)
            return {"query": STANDALONE if question == FOLLOWUP else question}
        if question == INITIAL:
            return failed_stream(call)
        assert question == "Atog"
        return {"text": "Atog sacrifices artifacts.", "citations": [ATOG], "insufficient_evidence": False}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=context_model))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        first = client.post("/api/search", json={"question": INITIAL, "conversation_id": conversation_id}).json()
        failed = client.post(f'/api/conversations/{conversation_id}/turns/{first["turn_id"]}/stream')
        assert json.loads(failed.text.splitlines()[-1])["generation"]["status"] == "failed"
        second = client.post("/api/search", json={"question": "Atog", "conversation_id": conversation_id}).json()
        completed = client.post(f'/api/conversations/{conversation_id}/turns/{second["turn_id"]}/stream')
        assert json.loads(completed.text.splitlines()[-1])["generation"]["status"] == "completed"
        third = client.post("/api/search", json={"question": FOLLOWUP, "conversation_id": conversation_id}).json()
        assert third["rewrite"]["status"] == "rewritten"
        assert third["query"] == STANDALONE
