import json

import pytest
from fastapi.testclient import TestClient

from magic_rag.app import create_app
from artifact_cards import ATOG, INITIAL, FOLLOWUP, FOLLOWUP_SEARCH, seed_artifact_cards
from scripted_chat_model import search_once, ScriptedChatModel, offers_tools, search_call, searching
from test_streaming import send_message


def test_followup_answers_receive_frozen_topic_context_separate_from_card_evidence(tmp_path):
    answer_requests = []

    async def unfinished(call):
        yield '{"text":"Failed unverified partial'

    def answer(call):
        source = call.source
        answer_requests.append(source)
        if source["question"] == INITIAL:
            return unfinished(call)
        if source["question"] == FOLLOWUP:
            return {"text":"A cheaper artifact-sacrifice option.","citations":[ATOG],"insufficient_evidence":False}
        return {"text":"Completed Atog explanation.","citations":[ATOG],"insufficient_evidence":False}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    model = ScriptedChatModel(script=searching(answer, query=lambda call: FOLLOWUP_SEARCH if call.source["question"] == FOLLOWUP else call.source["question"]))
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation = client.post("/api/conversations").json()["id"]
        assert send_message(client, conversation, INITIAL)[-1]["generation"]["status"] == "failed"
        assert send_message(client, conversation, "Atog")[-1]["generation"]["status"] == "completed"
        events = send_message(client, conversation, FOLLOWUP)
        assert events[1]["query"] == FOLLOWUP_SEARCH
        followup = events[-1]["trace"]
        assert followup["generation"]["status"] == "completed"
        request = answer_requests[-1]
        # The failed first turn is not context; only completed turns are.
        expected = [{"question":"Atog","query":"Atog","answer":"Completed Atog explanation."}]
        assert request["search_queries"] == [FOLLOWUP_SEARCH]
        assert request["conversation_context"] == expected
        assert all("selected_evidence" not in item for item in request["conversation_context"])
        assert request["selected_evidence"][0]["card_id"] == ATOG
        assert "Failed unverified partial" not in json.dumps(request)
        assert followup["answer_context"]["conversation_context"] == expected


def test_answer_context_bounds_older_text_and_turn_count_without_clipping_card_evidence(tmp_path):
    def answer(call):
        verbose = call.source["question"] == "Atog"
        return {"text":"A completed explanation. " + ("x" * 12000 if verbose else ""),"citations":[ATOG],"insufficient_evidence":False}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=searching(answer, query=lambda call: "Atog")))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        send_message(client, conversation, "Atog")
        trace = send_message(client, conversation, "Atog again")[-1]["trace"]
        context = trace["answer_context"]
        assert context["context_truncated"] is True
        assert len(context["conversation_context"][0]["answer"]) <= 4000
        assert "Sacrifice an artifact" in trace["selected_evidence"][0]["text"]
        for index in range(8):
            send_message(client, conversation, f"Atog turn {index}")
        final = send_message(client, conversation, "Atog final")[-1]["trace"]
        history = final["answer_context"]["conversation_context"]
        assert len(history) == 6
        assert history[0]["question"] == "Atog turn 2"
        assert sum(len(value) for item in history for value in item.values()) <= 16000

@pytest.mark.parametrize("text", ["", "Atog sacrifices artifacts."])
def test_completed_asset_references_reach_the_followup_search_and_frozen_answer_context(tmp_path, text):
    requests = []
    def model(call):
        requests.append(call)
        if offers_tools(call):
            return search_call("Atog")
        return {"assets":[ATOG], "text":text, "citations":[ATOG] if text else []}
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=search_once(model)))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        assert send_message(client, conversation, "Atog")[-1]["generation"]["status"] == "completed"
        followup = send_message(client, conversation, "Which of those cost less mana?")[-1]["trace"]
        expected = {"question":"Atog", "query":"Atog", "shown_cards":f"Atog [{ATOG}]"}
        if text:
            expected["answer"] = text
        search_choice, answer = requests[-2:]
        assert offers_tools(search_choice) and search_choice.source["conversation_context"] == [expected]
        assert answer.source["conversation_context"] == [expected]
        assert followup["answer_context"]["conversation_context"] == [expected]
        saved = client.get(f"/api/conversations/{conversation}").json()["turns"][-1]["trace"]
        assert saved["answer_context"]["conversation_context"] == [expected]

@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_or_cancelled_generation_does_not_supply_shown_card_context(tmp_path, cancelled):
    import asyncio
    async def unvalidated(call):
        yield '{"text":"Unvalidated output'
        if cancelled and call.source["question"] == "Atog":
            raise asyncio.CancelledError()
        yield '", "assets":["%s"], "citations":["invented-card"]}' % ATOG
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=searching(unvalidated, query=lambda call: "Atog")))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{conversation}/messages", json={"question":"Atog"})
        turns = client.get(f"/api/conversations/{conversation}").json()["turns"]
        # A cancelled run is a stopped run: its turn is removed, so it supplies no context at all.
        assert [turn["state"] for turn in turns] == ([] if cancelled else ["failed"])
        followup = send_message(client, conversation, "Those cards?")[-1]["trace"]
        assert followup["answer_context"]["conversation_context"] == []


def test_selected_asset_names_share_existing_context_character_and_history_limits(tmp_path):
    from magic_rag.app import connect
    captured = []
    def model(call):
        if offers_tools(call):
            captured.append(call.source["conversation_context"])
            return search_call("Atog")
        return {"assets":[ATOG]}
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with connect(path) as database:
        database.execute("UPDATE cards SET name = ? WHERE card_id = ?", ("Atog " + "x" * 9000, ATOG))
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=search_once(model)))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        for index in range(8):
            assert send_message(client, conversation, f"Atog {index}")[-1]["generation"]["status"] == "completed"
        followup = send_message(client, conversation, "Those cards?")[-1]["trace"]
        history = followup["answer_context"]["conversation_context"]
        assert len(captured[-1]) == 6
        assert all(len(item["shown_cards"]) <= 4000 for item in captured[-1])
        assert followup["answer_context"]["context_truncated"] is True
        assert sum(len(value) for item in history for value in item.values()) <= 16000
        assert "selected_evidence" not in history[-1]
