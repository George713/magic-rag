"""The agent writes its own card searches: behavior through the streamed-message endpoint."""
import json

from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from scripted_chat_model import DONE_SEARCHING, search_once, ScriptedChatModel, offers_tools, search_call
from test_streaming import send_message

DELVER = "sample-delver"


def test_first_turn_question_is_searched_with_the_model_written_query_and_answered_with_citations(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    answer = {"text": "It transforms into a flier.", "citations": [DELVER], "insufficient_evidence": False}
    model = ScriptedChatModel(script=[search_call(" Delver of Secrets "), DONE_SEARCHING, answer])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "which blue one-drop flips into a flier?")
        kinds = [event["event"] for event in events]
        assert kinds[:2] == ["start", "search"] and kinds[-1] == "done"
        assert set(kinds[2:-1]) == {"delta"}
        assert events[1]["query"] == "Delver of Secrets"
        assert events[1]["top_cards"][0]["card_id"] == DELVER
        assert "".join(event["text"] for event in events if event["event"] == "delta") == "It transforms into a flier."
        done = events[-1]
        assert done["generation"]["status"] == "completed"
        assert [citation["card_id"] for citation in done["generation"]["citations"]] == [DELVER]
        assert [search["query"] for search in done["trace"]["searches"]] == ["Delver of Secrets"]
        first = model.calls[0]
        assert [tool["function"]["name"] for tool in first.kwargs["tools"]] == ["search_cards"]
        assert first.session == conversation_id
        assert "which blue one-drop flips into a flier?" in first.messages[-1].content


def test_explicit_filters_and_search_mode_apply_to_the_agents_search_and_the_model_cannot_see_them(tmp_path):
    from test_vectors import ControlledEmbedder

    path = tmp_path / "cards.db"
    ingest_sample(path, embedder=ControlledEmbedder())
    answers = []

    def model(call):
        if offers_tools(call):
            assert set(call.kwargs["tools"][0]["function"]["parameters"]["properties"]) == {"query"}
            assert "colors" not in json.dumps(call.source) and "hybrid" not in json.dumps(call.source)
            return search_call("Lightning Bolt red instant")
        answers.append(call)
        return {"text": "Only a blue card matched.", "citations": ["sample-lightning-bolt"], "insufficient_evidence": False}

    with TestClient(create_app(path, embedder=ControlledEmbedder(), chat_model=ScriptedChatModel(script=search_once(model)))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        first = send_message(client, conversation_id, "the red burn spell", mode="hybrid", filters={"colors": ["U"]})
        second = send_message(client, conversation_id, "the red burn spell again")
        for events in (first, second):
            search = next(event for event in events if event["event"] == "search")
            assert search["query"] == "Lightning Bolt red instant"
            assert search["search"]["mode"] == "hybrid" and search["search"]["filters"] == {"colors": ["U"]}
            stage_cards = {card["card_id"] for cards in search["search"]["stages"].values() for card in cards}
            assert stage_cards == {DELVER}
            done = events[-1]
            assert done["generation"]["status"] == "failed"
            assert {card["card_id"] for card in done["trace"]["selected_evidence"]} == {DELVER}
            assert "sample-lightning-bolt" not in json.dumps(done["generation"])
        tool_results = [message.content for call in answers for message in call.messages]
        assert all("Lightning Bolt deals" not in content for content in tool_results)
        assert [card["card_id"] for card in answers[0].source["selected_evidence"]] == [DELVER]


def test_long_card_text_arrives_complete_in_the_search_and_the_answer_evidence(tmp_path):
    from magic_rag.app import connect

    path = tmp_path / "cards.db"
    ingest_sample(path)
    long_text = "Flying\n" + "\n".join(f"Ability {index}: draw a card." for index in range(2000)) + "\nFinal ability: you win the game."
    with connect(path) as db:
        db.execute("UPDATE cards SET text = ? WHERE card_id = ?", (long_text, DELVER))
    model = ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, lambda call: {
        "text": "It has many abilities.", "citations": [DELVER], "insufficient_evidence": False}])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "what does the long card do?")
        assert events[1]["search"]["selected_evidence"][0]["text"] == long_text
        assert events[-1]["generation"]["status"] == "completed"
        assert model.calls[-1].source["selected_evidence"][0]["text"] == long_text
        assert events[-1]["trace"]["selected_evidence"][0]["text"] == long_text


def test_without_a_provider_the_typed_text_is_searched_as_is_and_no_answer_is_generated(tmp_path, monkeypatch):
    for name in ("URL", "MODEL", "API_KEY"):
        monkeypatch.delenv(f"MAGIC_RAG_PROVIDER_{name}", raising=False)
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "  Lightning Bolt  ")
        assert [event["event"] for event in events] == ["start", "search", "done"]
        assert events[1]["query"] == "  Lightning Bolt  "
        assert events[1]["top_cards"][0]["card_id"] == "sample-lightning-bolt"
        assert events[-1]["generation"]["status"] == "unconfigured"
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "completed" and not turn.get("answer")
        assert [search["query"] for search in turn["trace"]["searches"]] == ["  Lightning Bolt  "]
        assert turn["trace"]["selected_evidence"][0]["card_id"] == "sample-lightning-bolt"


def test_followups_receive_bounded_context_from_earlier_completed_turns_and_the_model_resolves_the_reference(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    contexts = []

    async def failing(call):
        yield '{"text": "Unverified partial'
        raise RuntimeError("controlled provider failure")

    def model(call):
        if offers_tools(call):
            contexts.append(call.source["conversation_context"])
            question = call.source["question"]
            return search_call("Lightning Bolt" if question == "what did that one cost?" else question)
        if call.source["question"] == "Sol Ring fails":
            return failing(call)
        card = call.source["selected_evidence"][0]
        return {"text": f"About {card['name']}.", "citations": [card["card_id"]], "insufficient_evidence": False}

    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=search_once(model)))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        assert send_message(client, conversation_id, "Delver")[-1]["generation"]["status"] == "completed"
        assert contexts[-1] == []
        for index in range(5):
            send_message(client, conversation_id, f"Delver {index}")
        assert send_message(client, conversation_id, "Sol Ring fails")[-1]["generation"]["status"] == "failed"
        send_message(client, conversation_id, "Lightning Bolt")
        events = send_message(client, conversation_id, "what did that one cost?")
        history = contexts[-1]
        assert len(history) == 6
        # Only completed turns are context: the failed turn and its partial text are left out.
        assert [item["question"] for item in history] == ["Delver 0", "Delver 1", "Delver 2", "Delver 3", "Delver 4", "Lightning Bolt"]
        assert history[-1] == {"question": "Lightning Bolt", "query": "Lightning Bolt", "answer": "About Lightning Bolt."}
        assert "Sol Ring fails" not in json.dumps(history) and "Unverified partial" not in json.dumps(history)
        assert all("selected_evidence" not in item for item in history)
        assert events[1]["query"] == "Lightning Bolt"
        done = events[-1]
        assert done["generation"]["citations"][0]["card_id"] == "sample-lightning-bolt"
        assert done["trace"]["answer_context"]["search_queries"] == ["Lightning Bolt"]
        assert done["trace"]["answer_context"]["conversation_context"][-1]["answer"] == "About Lightning Bolt."


def test_out_of_scope_requests_are_declined_under_instructions_that_name_the_scope(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    decline = {"text": "Deck building is out of scope; I can explain Lightning Bolt instead.", "citations": [], "insufficient_evidence": True}
    model = ScriptedChatModel(script=[search_call("Lightning Bolt"), DONE_SEARCHING, decline])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        done = send_message(client, conversation_id, "Build me the best burn deck around Lightning Bolt")[-1]
        assert done["generation"]["status"] == "completed"
        assert done["generation"]["insufficient_evidence"] is True and done["generation"]["citations"] == []
        for call in model.calls:
            instructions = call.system.lower()
            assert "deck building" in instructions and "rules rulings" in instructions
