import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
import sqlite3

from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from scripted_chat_model import DONE_SEARCHING, search_once, ScriptedChatModel, search_call


def scripted(*fragments):
    """A search for "Delver", then one streamed answer made of explicit content fragments."""
    async def respond(call):
        for fragment in fragments:
            yield fragment
            await asyncio.sleep(0)
    return ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, respond])


def send_message(client, conversation_id, question="Delver", **body):
    """One message as one streamed request; returns its decoded newline-delimited events."""
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": question, **body})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]


def test_one_message_streams_its_search_then_answer_deltas_then_done_and_reopens_after_restart(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    answer = {"text": "The transformed face has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, answer]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "Delver")
        kinds = [event["event"] for event in events]
        assert kinds[0] == "start" and kinds[1] == "search" and kinds[-1] == "done"
        assert set(kinds[2:-1]) == {"delta"} and len(kinds[2:-1]) > 1
        search = events[1]
        assert search["query"] == "Delver"
        assert search["card_count"] == 1
        assert search["top_cards"] == [{"card_id": "sample-delver", "name": "Delver of Secrets // Insectile Aberration"}]
        assert search["search"]["query"] == "Delver"
        assert search["search"]["stages"]["keyword"][0]["card_id"] == "sample-delver"
        assert "".join(event["text"] for event in events if event["event"] == "delta") == "The transformed face has flying."
        done = events[-1]
        assert done["generation"]["status"] == "completed"
        assert done["generation"]["citations"][0]["card_id"] == "sample-delver"
        turn_id = events[0]["trace"]["turn_id"]
        assert done["trace"]["turn_id"] == turn_id
        assert done["trace"]["searches"] == [search["search"]]
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["id"] == turn_id
        assert turn["state"] == "completed"
        assert turn["answer"] == "The transformed face has flying."
        assert [saved["query"] for saved in turn["trace"]["searches"]] == ["Delver"]
        assert turn["trace"]["selected_evidence"][0]["card_id"] == "sample-delver"
        assert turn["trace"] == done["trace"]


def test_failed_stream_preserves_partial_text_and_is_not_completed(tmp_path):
    async def failing(call):
        yield '{"text": "Partial explanation'
        raise RuntimeError("private-provider-key")

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, failing]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
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
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, waiting]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        with ThreadPoolExecutor() as pool:
            response_future = pool.submit(client.post, f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
            assert started.wait(5)
            turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
            assert turn["state"] == "in_progress"
            assert turn["trace"]["searches"][0]["query"] == "Delver"
            cancelled = client.post(f"/api/conversations/{conversation_id}/turns/{turn['id']}/cancel")
            assert cancelled.status_code == 200
            response = response_future.result(timeout=5)
        assert closed.wait(5)
        assert "late chunk" not in response.text
        assert json.loads(response.text.splitlines()[-1])["generation"]["status"] == "cancelled"
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "cancelled"
        assert turn["answer"] == "An unfinished "


def test_stop_while_the_agent_chooses_its_search_ends_the_request_before_any_search_or_answer(tmp_path):
    choosing = Event()
    release = Event()

    def model(call):
        if call.kwargs.get("tools"):
            choosing.set()
            release.wait(5)
            return search_call("Delver")
        return {"text": "Never streamed.", "citations": ["sample-delver"]}

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=search_once(model)))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        with ThreadPoolExecutor() as pool:
            response_future = pool.submit(client.post, f"/api/conversations/{conversation_id}/messages", json={"question": "Show Delver"})
            assert choosing.wait(5)
            turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
            assert turn["state"] == "in_progress" and turn["trace"]["searches"] == []
            assert client.post(f"/api/conversations/{conversation_id}/turns/{turn['id']}/cancel").json()["status"] == "cancelled"
            response = response_future.result(timeout=5)
            release.set()
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "done"]
        assert events[-1]["generation"]["status"] == "cancelled"
        saved = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert saved["state"] == "cancelled" and saved["trace"]["searches"] == []


def test_streamed_text_holds_split_escapes_and_sends_the_conversation_session(tmp_path):
    model = scripted('{"text":"The \\u00', '74ransformed ',
                     'face has flying.","citations":["sample-delver"],"insufficient_evidence":false}')
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["text"] for event in events if event["event"] == "delta"] == ["The ", "transformed ", "face has flying."]
    assert events[-1]["generation"]["status"] == "completed"
    assert [call.session for call in model.calls] == [conversation_id] * 3
    assert "Flying" in model.calls[-1].source["selected_evidence"][0]["text"]


@pytest.mark.parametrize("failure", ["unknown_citation", "uncited", "eof", "length"])
def test_incomplete_or_unsupported_stream_never_becomes_completed(tmp_path, failure):
    if failure == "eof":
        model = scripted('{"text": "Partial statement')
    else:
        from langchain_core.messages import AIMessage
        payload = {"text": "Partial statement", "citations": ["invented"] if failure == "unknown_citation" else ["sample-delver"] if failure == "length" else [], "insufficient_evidence": False}
        step = AIMessage(content=json.dumps(payload), response_metadata={"finish_reason": "length"}) if failure == "length" else payload
        model = ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, step])

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
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
    app = create_app(path, chat_model=ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, disconnecting]))
    with TestClient(app) as client:
        conversation_id = client.post("/api/conversations").json()["id"]

    async def disconnected_request():
        disconnected = asyncio.Event()
        first = True

        async def receive():
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": json.dumps({"question": "Delver"}).encode(), "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and b'"event": "delta"' in message.get("body", b""):
                disconnected.set()

        await app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"}, "http_version": "1.1", "method": "POST", "scheme": "http", "path": f"/api/conversations/{conversation_id}/messages", "raw_path": b"/", "query_string": b"", "root_path": "", "headers": [(b"content-type", b"application/json")], "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80)}, receive, send)

    asyncio.run(disconnected_request())
    assert closed.is_set()
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "cancelled"
        assert turn["answer"] == "Partial before disconnect"


def test_without_a_provider_the_typed_text_is_searched_and_done_carries_the_provider_status(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "Delver")
        assert [event["event"] for event in events] == ["start", "search", "done"]
        assert events[1]["query"] == "Delver" and events[1]["card_count"] == 1
        assert events[-1]["generation"]["status"] == "unconfigured"
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "completed"
        assert turn["answer"] is None
        assert turn["trace"]["generation"]["status"] == "unconfigured"
        assert turn["trace"]["searches"][0]["query"] == "Delver"
        assert turn["trace"]["selected_evidence"][0]["card_id"] == "sample-delver"


def test_messages_and_cancel_are_scoped_to_their_conversation_and_reject_invalid_questions(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        turn_id = send_message(client, conversation_id)[0]["trace"]["turn_id"]
        other = client.post("/api/conversations").json()["id"]
        assert client.post(f"/api/conversations/{other}/turns/{turn_id}/cancel").status_code == 404
        assert client.post("/api/conversations/missing/messages", json={"question": "Delver"}).status_code == 404
        assert client.post(f"/api/conversations/{other}/messages", json={"question": "?!"}).status_code == 422
        assert client.post(f"/api/conversations/{other}/messages", json={"question": "Delver", "mode": "psychic"}).status_code == 422
        assert client.get(f"/api/conversations/{other}").json()["turns"] == []
        # The separate retrieve-then-stream request no longer exists.
        assert client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream").status_code in (404, 405)


def test_restart_recovers_an_interrupted_in_progress_turn_as_incomplete(tmp_path):
    waiting = Event()

    async def interrupted(call):
        yield '{"text": "Saved before shutdown'
        waiting.set()
        await asyncio.sleep(2)

    path = tmp_path / "cards.db"
    snapshot = tmp_path / "restart.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, interrupted]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        with ThreadPoolExecutor() as pool:
            result = pool.submit(client.post, f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
            assert waiting.wait(5)
            turn_id = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["id"]
            base = f"/api/conversations/{conversation_id}/turns/{turn_id}"
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
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, answer]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
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
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, {"assets": ["invented-card"]}]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
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
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "search", "done"]
        assert events[-1]["generation"]["status"] == "completed"
        assert events[-1]["generation"]["text"] == ""
        assert events[-1]["generation"]["assets"][0]["card_id"] == "sample-delver"
