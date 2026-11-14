"""Follow-ups: the agent writes the follow-up's search from bounded conversation context; filters stay the player's."""
import json

from fastapi.testclient import TestClient
import pytest

from magic_rag.app import create_app
from artifact_cards import ATOG, FOLLOWUP, INITIAL, FOLLOWUP_SEARCH, TopicEmbedder, TopicReranker, seed_artifact_cards
from scripted_chat_model import DONE_SEARCHING, search_once, ScriptedChatModel, offers_tools, search_call
from test_streaming import send_message


def topic_model(call):
    if offers_tools(call):
        question = call.source["question"]
        if question == FOLLOWUP:
            assert call.source["conversation_context"] == [{"question": INITIAL, "query": INITIAL,
                                                           "answer": "Atog sacrifices artifacts."}]
        return search_call(FOLLOWUP_SEARCH if question == FOLLOWUP else question)
    return {"text": "Atog sacrifices artifacts.", "citations": [ATOG], "insufficient_evidence": False}


@pytest.mark.parametrize("mode", ["keyword", "vector", "hybrid", "hybrid_rerank"])
def test_followup_search_uses_the_model_written_topic_in_every_stage_and_keeps_filters(tmp_path, mode):
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    filters = {"card_types": ["Creature"], "mana_value_max": 2}
    model = ScriptedChatModel(script=search_once(topic_model))
    with TestClient(create_app(path, embedder=TopicEmbedder(), reranker=TopicReranker(), chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        initial = send_message(client, conversation_id, INITIAL, mode=mode, filters=filters)[-1]["trace"]
        calls_before = len(model.calls)
        events = send_message(client, conversation_id, FOLLOWUP)
        trace = events[-1]["trace"]
        assert trace["question"] == FOLLOWUP
        assert [search["query"] for search in trace["searches"]] == [FOLLOWUP_SEARCH]
        assert trace["searches"][0]["mode"] == mode and trace["searches"][0]["filters"] == filters
        assert trace["selected_evidence"][0]["card_id"] == ATOG
        assert trace["generation"]["status"] == "completed"
        assert "rewrite" not in trace
        # The agent searches, stops searching, then the answer: no separate rewrite request.
        followup_calls = model.calls[calls_before:]
        assert [offers_tools(call) for call in followup_calls] == [True, True, False]
        assert {call.session for call in followup_calls} == {conversation_id}
        saved = client.get(f"/api/conversations/{conversation_id}").json()["turns"]
        assert saved[0]["trace"] == initial and saved[1]["trace"] == trace


def test_a_provider_failure_while_choosing_the_search_fails_the_turn_without_exposing_details(tmp_path):
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    model = ScriptedChatModel(script=[RuntimeError("private-provider-key-and-endpoint"), search_call("Atog"), DONE_SEARCHING,
                                      {"text": "Atog sacrifices artifacts.", "citations": [ATOG]}])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": FOLLOWUP})
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "done"]
        assert events[-1]["generation"]["status"] == "failed"
        assert "private-provider" not in response.text
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "failed" and turn["error"] and turn["trace"]["searches"] == []
        assert send_message(client, conversation_id, "Atog")[-1]["generation"]["status"] == "completed"


def test_absent_provider_retains_filters_and_explicit_empty_object_clears_them(tmp_path):
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        initial = send_message(client, conversation_id, INITIAL, filters={"mana_value_max": 0})[-1]["trace"]
        inherited = send_message(client, conversation_id, "Atog")[-1]["trace"]
        assert inherited["searches"][0]["query"] == "Atog"
        assert inherited["searches"][0]["filters"] == {"mana_value_max": 0}
        assert inherited["selected_evidence"] == []
        cleared = send_message(client, conversation_id, "Atog", filters={})[-1]["trace"]
        assert cleared["searches"][0]["filters"] == {}
        assert cleared["selected_evidence"][0]["card_id"] == ATOG
        assert client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["trace"] == initial


def test_context_and_filters_are_isolated_between_conversations(tmp_path):
    contexts = []

    def model(call):
        if offers_tools(call):
            contexts.append(call.source["conversation_context"])
            return search_call(call.source["question"])
        return {"text": "Nothing relevant.", "citations": [], "insufficient_evidence": True}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=search_once(model)))) as client:
        first = client.post("/api/conversations").json()["id"]
        second = client.post("/api/conversations").json()["id"]
        send_message(client, first, INITIAL, filters={"colors": ["R"]})
        send_message(client, second, "Another private topic", filters={"colors": ["U"]})
        assert contexts[-1] == []
        followup = send_message(client, second, FOLLOWUP)[-1]["trace"]
        assert [item["question"] for item in contexts[-1]] == ["Another private topic"]
        assert INITIAL not in json.dumps(contexts[-1])
        assert followup["searches"][0]["filters"] == {"colors": ["U"]}


def test_unconfirmed_workload_searches_the_typed_text_and_never_sends_a_model_request(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_URL", "https://provider.example/chat/completions")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_MODEL", "model")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_API_KEY", "private-key")
    monkeypatch.delenv("MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED", raising=False)
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        send_message(client, conversation_id, INITIAL)
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": FOLLOWUP})
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "search", "done"]
        assert events[1]["query"] == FOLLOWUP
        assert events[-1]["generation"]["status"] == "suitability_required"
        assert "private-key" not in response.text
