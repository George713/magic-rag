import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
import sqlite3

from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from scripted_chat_model import ScriptedChatModel


def scripted(*fragments):
    """One streamed model response made of explicit content fragments."""
    async def respond(call):
        for fragment in fragments:
            yield fragment
            await asyncio.sleep(0)
    return ScriptedChatModel(script=[respond])


def saved_search(client):
    conversation = client.post("/api/conversations").json()
    trace = client.post("/api/search", json={"question": "Delver", "conversation_id": conversation["id"]}).json()
    return conversation["id"], trace["turn_id"]


def test_streamed_answer_keeps_evidence_and_completed_state_after_restart(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    answer = {"text": "The transformed face has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[answer]))) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[0]["event"] == "start" and events[-1]["event"] == "done"
        deltas = [event["text"] for event in events[1:-1] if event["event"] == "delta"]
        assert len(deltas) > 1
        assert "".join(deltas) == "The transformed face has flying."
        assert events[-1]["generation"]["citations"][0]["card_id"] == "sample-delver"
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "completed"
        assert turn["answer"] == "The transformed face has flying."
        assert turn["trace"]["selected_evidence"][0]["card_id"] == "sample-delver"


def test_failed_stream_preserves_partial_text_and_is_not_completed(tmp_path):
    async def failing(call):
        yield '{"text": "Partial explanation'
        raise RuntimeError("private-provider-key")

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[failing]))) as client:
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


def test_stop_cancels_waiting_model_and_preserves_partial_state(tmp_path):
    started = Event()
    closed = Event()

    async def waiting(call):
        try:
            yield '{"text": "An unfinished '
            started.set()
            await asyncio.sleep(2)
            yield 'late chunk"}'
        finally:
            closed.set()

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[waiting]))) as client:
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


def test_streamed_text_holds_split_escapes_and_sends_the_conversation_session(tmp_path):
    model = scripted('{"text":"The \\u00', '74ransformed ',
                     'face has flying.","citations":["sample-delver"],"insufficient_evidence":false}')
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["text"] for event in events if event["event"] == "delta"] == ["The ", "transformed ", "face has flying."]
    assert events[-1]["generation"]["status"] == "completed"
    assert model.calls[0].session == conversation_id
    assert "Flying" in model.calls[0].source["selected_evidence"][0]["text"]


@pytest.mark.parametrize("failure", ["unknown_citation", "uncited", "eof", "length"])
def test_incomplete_or_unsupported_stream_never_becomes_completed(tmp_path, failure):
    if failure == "eof":
        model = scripted('{"text": "Partial statement')
    else:
        from langchain_core.messages import AIMessage
        payload = {"text": "Partial statement", "citations": ["invented"] if failure == "unknown_citation" else ["sample-delver"] if failure == "length" else [], "insufficient_evidence": False}
        step = AIMessage(content=json.dumps(payload), response_metadata={"finish_reason": "length"}) if failure == "length" else payload
        model = ScriptedChatModel(script=[step])

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        assert json.loads(response.text.splitlines()[-1])["generation"]["status"] == "failed"
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "failed"
        assert turn["trace"]["generation"]["citations"] == []


def test_disconnected_browser_cancels_upstream_and_saves_partial_answer(tmp_path):
    closed = Event()

    async def disconnecting(call):
        try:
            yield '{"text": "Partial before disconnect'
            await asyncio.sleep(5)
        finally:
            closed.set()

    path = tmp_path / "cards.db"
    ingest_sample(path)
    app = create_app(path, chat_model=ScriptedChatModel(script=[disconnecting]))
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

    async def interrupted(call):
        yield '{"text": "Saved before shutdown'
        waiting.set()
        await asyncio.sleep(2)

    path = tmp_path / "cards.db"
    snapshot = tmp_path / "restart.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[interrupted]))) as client:
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

@pytest.mark.parametrize("with_text", [False, True])
def test_stream_validates_assets_only_at_completion_and_reopens_them(tmp_path, with_text):
    answer = {"text": "A flying transformed face." if with_text else "", "assets": ["sample-delver"], "citations": ["sample-delver"] if with_text else []}
    path = tmp_path / "assets.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[answer]))) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        events = [json.loads(line) for line in response.text.splitlines()]
        assert all(not event.get("generation", {}).get("assets") for event in events[:-1])
        answer = events[-1]["generation"]
        assert answer["status"] == "completed"
        assert answer["assets"][0]["card_id"] == "sample-delver"
        assert answer["text"] == ("A flying transformed face." if with_text else "")
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["trace"]["generation"] == answer


def test_invalid_stream_asset_selection_is_never_saved_as_success(tmp_path):
    path = tmp_path / "assets.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[{"assets": ["invented-card"]}]))) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        answer = json.loads(response.text.splitlines()[-1])["generation"]
        assert answer["status"] == "failed"
        assert not answer.get("assets")
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "failed"
        assert turn["trace"]["selected_evidence"][0]["card_id"] == "sample-delver"


def test_streamed_assets_only_json_without_text_completes(tmp_path):
    path = tmp_path / "assets.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=scripted(json.dumps({"assets": ["sample-delver"]})))) as client:
        conversation_id, turn_id = saved_search(client)
        response = client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream")
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "done"]
        assert events[-1]["generation"]["status"] == "completed"
        assert events[-1]["generation"]["text"] == ""
        assert events[-1]["generation"]["assets"][0]["card_id"] == "sample-delver"
