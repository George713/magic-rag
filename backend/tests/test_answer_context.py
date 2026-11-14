import json

import pytest
from fastapi.testclient import TestClient

from magic_rag.app import create_app
from scripted_chat_model import ScriptedChatModel
from test_rewriting import ATOG, INITIAL, FOLLOWUP, STANDALONE, seed_artifact_cards


@pytest.mark.parametrize("streamed", [False, True])
def test_followup_answers_receive_frozen_topic_context_separate_from_card_evidence(tmp_path, streamed):
    answer_requests = []

    async def unfinished(call):
        yield '{"text":"Failed unverified partial'

    def model(call):
        source = call.source
        if "history" in source:
            return {"query":STANDALONE}
        answer_requests.append(source)
        if source["question"] == INITIAL:
            return unfinished(call)
        if source["question"] == FOLLOWUP:
            return {"text":"A cheaper artifact-sacrifice option.","citations":[ATOG],"insufficient_evidence":False}
        return {"text":"Completed Atog explanation.","citations":[ATOG],"insufficient_evidence":False}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=model))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        first = client.post("/api/search", json={"question":INITIAL,"conversation_id":conversation}).json()
        failed = client.post(f'/api/conversations/{conversation}/turns/{first["turn_id"]}/stream')
        assert json.loads(failed.text.splitlines()[-1])["generation"]["status"] == "failed"
        client.post("/api/search", json={"question":"Atog","conversation_id":conversation,"generate_answer":True})
        followup = client.post("/api/search", json={"question":FOLLOWUP,"conversation_id":conversation,"generate_answer":not streamed}).json()
        if streamed:
            # Later and unrelated turns must not enter an already retrieved turn's answer context.
            client.post("/api/search", json={"question":"Future topic","conversation_id":conversation})
            other = client.post("/api/conversations").json()["id"]
            client.post("/api/search", json={"question":"Other private conversation","conversation_id":other})
            completed = client.post(f'/api/conversations/{conversation}/turns/{followup["turn_id"]}/stream')
            assert json.loads(completed.text.splitlines()[-1])["generation"]["status"] == "completed"
        else:
            assert followup["generation"]["status"] == "completed"
        request = next(source for source in reversed(answer_requests) if source["question"] == FOLLOWUP)
        expected = [{"question":INITIAL,"query":INITIAL},{"question":"Atog","query":STANDALONE,"answer":"Completed Atog explanation."}]
        assert request["retrieval_query"] == STANDALONE
        assert request["conversation_context"] == expected
        assert all("selected_evidence" not in item for item in request["conversation_context"])
        assert request["selected_evidence"][0]["card_id"] == ATOG
        assert "Failed unverified partial" not in json.dumps(request)
        assert followup["answer_context"]["conversation_context"] == expected


def test_answer_context_bounds_older_text_and_turn_count_without_clipping_card_evidence(tmp_path):
    def verbose(call):
        if "history" in call.source:
            return {"query":call.source["question"]}
        return {"text":"A completed explanation. " + "x" * 12000,"citations":[ATOG],"insufficient_evidence":False}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=verbose))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question":"Atog","conversation_id":conversation,"generate_answer":True})
        trace = client.post("/api/search", json={"question":"Atog again","conversation_id":conversation}).json()
        context = trace["answer_context"]
        assert context["context_truncated"] is True
        assert len(context["conversation_context"][0]["answer"]) <= 4000
        assert "Sacrifice an artifact" in trace["selected_evidence"][0]["text"]
        for index in range(8):
            client.post("/api/search", json={"question":f"Atog turn {index}","conversation_id":conversation})
        final = client.post("/api/search", json={"question":"Atog final","conversation_id":conversation}).json()
        history = final["answer_context"]["conversation_context"]
        assert len(history) == 6
        assert history[0]["question"] == "Atog turn 2"
        assert sum(len(value) for item in history for value in item.values()) <= 16000

@pytest.mark.parametrize("text", ["", "Atog sacrifices artifacts."])
def test_completed_asset_references_reach_followup_rewrite_and_frozen_answer_context(tmp_path, text):
    requests = []
    def model(call):
        source = call.source
        requests.append(source)
        if "history" in source:
            return {"query":"Atog"}
        return {"assets":[ATOG], "text":text, "citations":[ATOG] if text else []}
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=model))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        first = client.post("/api/search", json={"question":"Atog", "conversation_id":conversation, "generate_answer":True}).json()
        assert first["generation"]["status"] == "completed"
        followup = client.post("/api/search", json={"question":"Which of those cost less mana?", "conversation_id":conversation, "generate_answer":True}).json()
        expected = {"question":"Atog", "query":"Atog", "shown_cards":f"Atog [{ATOG}]"}
        if text:
            expected["answer"] = text
        assert next(item for item in requests if "history" in item)["history"] == [expected]
        assert requests[-1]["conversation_context"] == [expected]
        assert followup["answer_context"]["conversation_context"] == [expected]
        saved = client.get(f"/api/conversations/{conversation}").json()["turns"][-1]["trace"]
        assert saved["answer_context"]["conversation_context"] == [expected]

@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_or_cancelled_generation_does_not_supply_shown_card_context(tmp_path, cancelled):
    import asyncio
    async def unvalidated(call):
        yield '{"text":"Unvalidated output'
        if cancelled:
            raise asyncio.CancelledError()
        yield '", "assets":["%s"], "citations":["invented-card"]}' % ATOG
    def model(call):
        return {"query":"Atog"} if "history" in call.source else unvalidated(call)
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=model))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        first = client.post("/api/search", json={"question":"Atog", "conversation_id":conversation}).json()
        client.post(f'/api/conversations/{conversation}/turns/{first["turn_id"]}/stream')
        saved = client.get(f"/api/conversations/{conversation}").json()["turns"][0]
        assert saved["state"] == ("cancelled" if cancelled else "failed")
        followup = client.post("/api/search", json={"question":"Those cards?", "conversation_id":conversation}).json()
        assert followup["answer_context"]["conversation_context"] == [{"question":"Atog", "query":"Atog"}]


def test_selected_asset_names_share_existing_context_character_and_history_limits(tmp_path):
    from magic_rag.app import connect
    captured = []
    def model(call):
        if "history" in call.source:
            captured.append(call.source["history"])
            return {"query":"Atog"}
        return {"assets":[ATOG]}
    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with connect(path) as database:
        database.execute("UPDATE cards SET name = ? WHERE card_id = ?", ("Atog " + "x" * 9000, ATOG))
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=model))) as client:
        conversation = client.post("/api/conversations").json()["id"]
        for index in range(8):
            first = client.post("/api/search", json={"question":f"Atog {index}", "conversation_id":conversation, "generate_answer":True}).json()
            assert first["generation"]["status"] == "completed"
        followup = client.post("/api/search", json={"question":"Those cards?", "conversation_id":conversation}).json()
        history = followup["answer_context"]["conversation_context"]
        assert len(captured[-1]) == 6
        assert all(len(item["shown_cards"]) <= 4000 for item in captured[-1])
        assert followup["answer_context"]["context_truncated"] is True
        assert sum(len(value) for item in history for value in item.values()) <= 16000
        assert "selected_evidence" not in history[-1]
