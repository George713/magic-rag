import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import httpx
import pytest
import sqlite3

from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from magic_rag.providers import ChatCompletionsProvider, ProviderConfig


class StreamingProvider:
    async def stream_answer(self, question, evidence, session_id, *, context=None):
        yield {"delta": "The transformed "}
        await asyncio.sleep(0)
        yield {"delta": "face has flying."}
        yield {"result": {"text": "The transformed face has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}}


def saved_search(client):
    conversation = client.post("/api/conversations").json()
    trace = client.post("/api/search", json={"question": "Delver", "conversation_id": conversation["id"]}).json()
    return conversation["id"], trace["turn_id"]


def test_streamed_answer_keeps_evidence_and_completed_state_after_restart(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=StreamingProvider())) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "delta", "delta", "done"]
        assert events[1]["text"] == "The transformed "
        assert events[2]["text"] == "face has flying."
        assert events[-1]["generation"]["citations"][0]["card_id"] == "sample-delver"
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "completed"
        assert turn["answer"] == "The transformed face has flying."
        assert turn["trace"]["selected_evidence"][0]["card_id"] == "sample-delver"


def test_failed_stream_preserves_partial_text_and_is_not_completed(tmp_path):
    class FailingProvider:
        async def stream_answer(self, *args, context=None):
            yield {"delta": "Partial explanation"}
            raise RuntimeError("private-provider-key")

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=FailingProvider())) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[-1]["generation"]["status"] == "failed"
        assert "private-provider-key" not in response.text
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "failed"
        assert turn["answer"] == "Partial explanation"
        assert turn["error"]


def test_stop_cancels_waiting_provider_and_preserves_partial_state(tmp_path):
    started = Event()
    closed = Event()

    class WaitingProvider:
        async def stream_answer(self, *args, context=None):
            try:
                yield {"delta": "An unfinished "}
                started.set()
                await asyncio.sleep(2)
                yield {"delta": "late chunk"}
            finally:
                closed.set()

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=WaitingProvider())) as client:
        conversation_id, turn_id = saved_search(client)
        base = f"/api/conversations/{conversation_id}/turns/{turn_id}"
        with ThreadPoolExecutor() as pool:
            response_future = pool.submit(client.post, base + "/stream")
            assert started.wait(5)
            cancelled = client.post(base + "/cancel")
            assert cancelled.status_code == 200
            response = response_future.result(timeout=5)
        assert closed.wait(5)
        assert "late chunk" not in response.text
        assert json.loads(response.text.splitlines()[-1])["generation"]["status"] == "cancelled"
        assert client.post(base + "/stream").status_code == 409
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "cancelled"
        assert turn["answer"] == "An unfinished "


def test_actual_http_adapter_streams_text_before_validating_final_citations(tmp_path):
    class RemoteStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for content in ['{"text":"The \\u00', '74ransformed ', 'face has flying.","citations":["sample-delver"],"insufficient_evidence":false}']:
                yield ("data: " + json.dumps({"choices": [{"delta": {"content": content}, "finish_reason": None}]}) + "\n\n").encode()
                await asyncio.sleep(0)
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'

    async def remote(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert "Flying" in payload["messages"][1]["content"]
        return httpx.Response(200, stream=RemoteStream())

    path = tmp_path / "cards.db"
    ingest_sample(path)
    provider = ChatCompletionsProvider(ProviderConfig("https://provider.example/chat/completions", "model", "secret-key", True), transport=httpx.MockTransport(remote))
    with TestClient(create_app(path, provider=provider)) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["text"] for event in events if event["event"] == "delta"] == ["The ", "transformed ", "face has flying."]
    assert events[-1]["generation"]["status"] == "completed"


@pytest.mark.parametrize("failure", ["unknown_citation", "uncited", "eof"])
def test_incomplete_or_unsupported_stream_never_becomes_completed(tmp_path, failure):
    class InvalidProvider:
        async def stream_answer(self, *args, context=None):
            yield {"delta": "Partial statement"}
            if failure != "eof":
                yield {"result": {"text": "Partial statement", "citations": ["invented"] if failure == "unknown_citation" else [], "insufficient_evidence": False}}

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=InvalidProvider())) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        assert json.loads(response.text.splitlines()[-1])["generation"]["status"] == "failed"
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "failed"
        assert turn["trace"]["generation"]["citations"] == []


def test_disconnected_browser_cancels_upstream_and_saves_partial_answer(tmp_path):
    closed = Event()

    class DisconnectProvider:
        async def stream_answer(self, *args, context=None):
            try:
                yield {"delta": "Partial before disconnect"}
                await asyncio.sleep(5)
            finally:
                closed.set()

    path = tmp_path / "cards.db"
    ingest_sample(path)
    app = create_app(path, provider=DisconnectProvider())
    with TestClient(app) as client:
        conversation_id, turn_id = saved_search(client)

    async def disconnected_request():
        disconnected = asyncio.Event()
        first = True

        async def receive():
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": b"", "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and b'"event": "delta"' in message.get("body", b""):
                disconnected.set()

        await app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"}, "http_version": "1.1", "method": "POST", "scheme": "http", "path": f"/api/conversations/{conversation_id}/turns/{turn_id}/stream", "raw_path": b"/", "query_string": b"", "root_path": "", "headers": [], "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80)}, receive, send)

    asyncio.run(disconnected_request())
    assert closed.is_set()
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "cancelled"
        assert turn["answer"] == "Partial before disconnect"


def test_unconfigured_stream_is_clear_and_cannot_access_another_conversations_turn(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation_id, turn_id = saved_search(client)
        other = client.post("/api/conversations").json()["id"]
        assert client.post(f"/api/conversations/{other}/turns/{turn_id}/stream").status_code == 404
        assert client.post(f"/api/conversations/{other}/turns/{turn_id}/cancel").status_code == 404
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        final = json.loads(response.text.splitlines()[-1])
        assert final["generation"]["status"] == "unconfigured"
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "retrieval_complete"
        assert turn["trace"]["selected_evidence"]


def test_restart_recovers_interrupted_generating_turn_as_incomplete(tmp_path):
    waiting = Event()

    class InterruptedProvider:
        async def stream_answer(self, *args, context=None):
            yield {"delta": "Saved before shutdown"}
            waiting.set()
            await asyncio.sleep(2)

    path = tmp_path / "cards.db"
    snapshot = tmp_path / "restart.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=InterruptedProvider())) as client:
        conversation_id, turn_id = saved_search(client)
        base = f"/api/conversations/{conversation_id}/turns/{turn_id}"
        with ThreadPoolExecutor() as pool:
            result = pool.submit(client.post, base + "/stream")
            assert waiting.wait(5)
            # Include committed WAL pages in the simulated shutdown image.
            with sqlite3.connect(path) as original, sqlite3.connect(snapshot) as restart_image:
                original.backup(restart_image)
            client.post(base + "/cancel")
            result.result(timeout=5)
    with TestClient(create_app(snapshot)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "cancelled"
        assert turn["answer"] == "Saved before shutdown"
        assert "interrupted" in turn["trace"]["generation"]["message"].lower()
