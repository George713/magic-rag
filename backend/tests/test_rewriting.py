import json

from fastapi.testclient import TestClient
import pytest

from magic_rag.app import create_app, connect
from magic_rag.vectors import store_vectors


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


class TopicProvider:
    async def rewrite(self, question, history, session_id):
        assert history[-1]["question"] == INITIAL
        assert history[-1]["query"] == INITIAL
        assert "selected_evidence" not in history[-1]
        return {"query": STANDALONE}

    def answer(self, question, evidence, session_id, *, context=None):
        assert question == FOLLOWUP
        return {"text": "Atog sacrifices artifacts.", "citations": [ATOG], "insufficient_evidence": False}


@pytest.mark.parametrize("mode", ["keyword", "vector", "hybrid", "hybrid_rerank"])
def test_followup_uses_standalone_topic_in_every_stage_and_retains_filters(tmp_path, mode):
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    filters = {"card_types": ["Creature"], "mana_value_max": 2}
    with TestClient(create_app(path, embedder=TopicEmbedder(), reranker=TopicReranker(), provider=TopicProvider())) as client:
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


def test_production_rewrite_adapter_sends_conversation_context_in_a_separate_call(tmp_path):
    import httpx
    from magic_rag.providers import ChatCompletionsProvider, ProviderConfig

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    sessions = []

    def remote(request):
        sessions.append(request.headers["x-opencode-session"])
        assert request.headers["Authorization"] == "Bearer private-key"
        body = json.loads(request.content)
        source = json.loads(body["messages"][1]["content"])
        assert source["question"] == FOLLOWUP
        assert source["history"] == [{"question": INITIAL, "query": INITIAL}]
        assert "selected_evidence" not in source
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"query": STANDALONE})}}]})

    provider = ChatCompletionsProvider(ProviderConfig("https://provider.example/chat/completions", "configured-model", "private-key", True), transport=httpx.MockTransport(remote))
    with TestClient(create_app(path, provider=provider)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question": INITIAL, "conversation_id": conversation_id})
        response = client.post("/api/search", json={"question": FOLLOWUP, "conversation_id": conversation_id})
        assert response.json()["query"] == STANDALONE
        assert response.json()["rewrite"]["status"] == "rewritten"
        assert sessions == [conversation_id]
        assert "private-key" not in response.text


@pytest.mark.parametrize("payload", [None, {"query": ""}, {"query": "???"}, {"query": 12},
                                    {"query": STANDALONE, "filters": {}}, "provider failure"])
def test_rewrite_failure_searches_exact_submitted_text_under_retained_filters(tmp_path, payload):
    class FailedRewrite:
        async def rewrite(self, question, history, session_id):
            if payload == "provider failure":
                raise RuntimeError("private-provider-key-and-endpoint")
            return payload

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, provider=FailedRewrite())) as client:
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
    class IsolatedProvider:
        async def rewrite(self, question, history, session_id):
            return {"query": history[-1]["query"] + " " + question}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, provider=IsolatedProvider())) as client:
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


def test_unconfirmed_workload_never_sends_a_rewrite_request(tmp_path):
    import httpx
    from magic_rag.providers import ChatCompletionsProvider, ProviderConfig
    requests = []

    def remote(request):
        requests.append(request)
        return httpx.Response(500)

    provider = ChatCompletionsProvider(ProviderConfig("https://provider.example/chat/completions", "model", "private-key", False), transport=httpx.MockTransport(remote))
    with TestClient(create_app(tmp_path / "cards.db", provider=provider)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question": INITIAL, "conversation_id": conversation_id})
        followup = client.post("/api/search", json={"question": FOLLOWUP, "conversation_id": conversation_id}).json()
        assert followup["rewrite"]["status"] == "unavailable"
        assert followup["query"] == FOLLOWUP
        assert requests == []


def test_rewrite_context_includes_completed_answers_but_omits_failed_partial_output(tmp_path):
    class ContextProvider:
        async def rewrite(self, question, history, session_id):
            assert "answer" not in history[0]
            if question == FOLLOWUP:
                assert history[1]["answer"] == "Atog sacrifices artifacts."
                assert all("selected_evidence" not in item for item in history)
            return {"query": STANDALONE if question == FOLLOWUP else question}

        async def stream_answer(self, question, evidence, session_id, *, context=None):
            if question == INITIAL:
                yield {"delta": "Unfinished unverified thought"}
                raise RuntimeError("Controlled failed stream")
            assert question == "Atog"
            yield {"delta": "Atog sacrifices artifacts."}
            yield {"result": {"text": "Atog sacrifices artifacts.", "citations": [ATOG], "insufficient_evidence": False}}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, provider=ContextProvider())) as client:
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
