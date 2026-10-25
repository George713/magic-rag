import json

import httpx
import pytest
from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.providers import ChatCompletionsProvider, ProviderConfig
from test_rewriting import ATOG, INITIAL, FOLLOWUP, STANDALONE, seed_artifact_cards


@pytest.mark.parametrize("streamed", [False, True])
def test_followup_answers_receive_frozen_topic_context_separate_from_card_evidence(tmp_path, streamed):
    answer_requests = []

    class AnswerStream(httpx.AsyncByteStream):
        def __init__(self, question):
            self.question = question

        async def __aiter__(self):
            payload = '{"text":"Failed unverified partial' if self.question == INITIAL else json.dumps({"text":"A cheaper artifact-sacrifice option.","citations":[ATOG],"insufficient_evidence":False})
            yield ("data: " + json.dumps({"choices":[{"delta":{"content":payload},"finish_reason":None}]}) + "\n\n").encode()
            if self.question != INITIAL:
                yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'

    def remote(request):
        body = json.loads(request.content)
        source = json.loads(body["messages"][1]["content"])
        if "history" in source:
            return httpx.Response(200, json={"choices":[{"message":{"content":json.dumps({"query":STANDALONE})}}]})
        answer_requests.append(source)
        if body.get("stream"):
            return httpx.Response(200, stream=AnswerStream(source["question"]))
        return httpx.Response(200, json={"choices":[{"message":{"content":json.dumps({"text":"Completed Atog explanation.","citations":[ATOG],"insufficient_evidence":False})}}]})

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    provider = ChatCompletionsProvider(ProviderConfig("https://provider.example/chat/completions","model","server-key",True),transport=httpx.MockTransport(remote))
    with TestClient(create_app(path, provider=provider)) as client:
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
    class VerboseProvider:
        def answer(self, question, evidence, session_id, *, context):
            return {"text":"A completed explanation. " + "x" * 12000,"citations":[ATOG],"insufficient_evidence":False}

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    with TestClient(create_app(path, provider=VerboseProvider())) as client:
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
