import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
import sqlite3

from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from scripted_chat_model import DONE_SEARCHING, has_searched, offers_tools, search_once, ScriptedChatModel, search_call


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


def stop(client, conversation_id):
    """Press Stop on the running turn, found the way the browser knows it (saved before `start`)."""
    turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][-1]
    assert turn["state"] == "in_progress"
    response = client.post(f"/api/conversations/{conversation_id}/turns/{turn['id']}/cancel")
    assert response.status_code == 204, response.text
    return turn


def test_provider_failure_mid_answer_saves_a_failed_turn_and_the_conversation_stays_usable(tmp_path):
    async def failing(call):
        yield '{"text": "Partial explanation'
        raise RuntimeError("private-provider-key")

    answer = {"text": "It has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}
    path = tmp_path / "cards.db"
    ingest_sample(path)
    model = ScriptedChatModel(script=[search_call("Delver"), DONE_SEARCHING, failing,
                                      search_call("Delver"), DONE_SEARCHING, answer])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "Delver")
        failure = events[-1]["generation"]
        assert failure["status"] == "failed"
        assert "try again" in failure["message"].lower()
        assert "private-provider-key" not in json.dumps(events)
        assert send_message(client, conversation_id, "Delver again")[-1]["generation"]["status"] == "completed"
    with TestClient(create_app(path)) as restarted:
        failed, completed = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"]
        assert failed["state"] == "failed"
        assert failed["answer"] == "Partial explanation"
        assert failed["error"] == failure["message"]
        assert completed["state"] == "completed"


def test_provider_failure_between_searches_saves_a_failed_turn_with_its_searches(tmp_path):
    calls = []

    def model(call):
        calls.append(call)
        if len(calls) == 2:
            raise RuntimeError("private-provider-key")
        return search_call("Delver")

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=model))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "Delver")
        assert [event["event"] for event in events] == ["start", "search", "done"]
        assert events[-1]["generation"]["status"] == "failed"
        assert "private-provider-key" not in json.dumps(events)
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "failed"
        assert [search["query"] for search in turn["trace"]["searches"]] == ["Delver"]


def test_stop_during_answer_streaming_removes_the_turn_with_its_partial_text(tmp_path):
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
            stop(client, conversation_id)
            response = response_future.result(timeout=5)
        assert closed.wait(5)
        assert "late chunk" not in response.text
        done = json.loads(response.text.splitlines()[-1])
        assert done["event"] == "done" and done["generation"]["status"] == "cancelled" and done["trace"] is None
    with TestClient(create_app(path)) as restarted:
        conversation = restarted.get(f"/api/conversations/{conversation_id}").json()
        assert conversation["turns"] == []
        assert conversation["title"] == "New conversation"


def test_stop_during_searching_removes_the_turn_and_its_completed_searches(tmp_path):
    choosing_again = Event()
    release = Event()

    def model(call):
        if not offers_tools(call):
            return {"text": "It has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}
        if not has_searched(call):
            return search_call("Delver")
        if call.source["question"] == "Show Delver":
            choosing_again.set()
            release.wait(5)
            return search_call("Never searched")
        return DONE_SEARCHING

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=model))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        assert send_message(client, conversation_id, "Earlier question")[-1]["generation"]["status"] == "completed"
        with ThreadPoolExecutor() as pool:
            response_future = pool.submit(client.post, f"/api/conversations/{conversation_id}/messages", json={"question": "Show Delver"})
            assert choosing_again.wait(5)
            assert [search["query"] for search in stop(client, conversation_id)["trace"]["searches"]] == ["Delver"]
            response = response_future.result(timeout=5)
            release.set()
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "search", "done"]
        assert events[-1]["generation"]["status"] == "cancelled"
    with TestClient(create_app(path)) as restarted:
        conversation = restarted.get(f"/api/conversations/{conversation_id}").json()
        assert [turn["question"] for turn in conversation["turns"]] == ["Earlier question"]
        assert conversation["title"] == "Earlier question"
        assert "Show Delver" not in json.dumps(conversation)


def test_stop_while_the_agent_chooses_its_first_search_removes_the_turn(tmp_path):
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
            assert stop(client, conversation_id)["trace"]["searches"] == []
            response = response_future.result(timeout=5)
            release.set()
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["event"] for event in events] == ["start", "done"]
        assert events[-1]["generation"]["status"] == "cancelled"
        assert client.get(f"/api/conversations/{conversation_id}").json()["turns"] == []


def test_follow_up_after_a_stopped_turn_does_not_receive_it_as_context(tmp_path):
    started = Event()
    contexts = []

    async def waiting(call):
        yield '{"text": "Stopped answer'
        started.set()
        await asyncio.sleep(5)

    def model(call):
        if offers_tools(call):
            contexts.append(call.source["conversation_context"])
            return search_call("Delver")
        if call.source["question"] == "Stopped question":
            return waiting(call)
        return {"text": "It has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=search_once(model)))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        assert send_message(client, conversation_id, "First question")[-1]["generation"]["status"] == "completed"
        with ThreadPoolExecutor() as pool:
            response_future = pool.submit(client.post, f"/api/conversations/{conversation_id}/messages", json={"question": "Stopped question"})
            assert started.wait(5)
            stop(client, conversation_id)
            response_future.result(timeout=5)
        followup = send_message(client, conversation_id, "Any cheaper ones?")[-1]
        assert followup["generation"]["status"] == "completed"
        assert [entry["question"] for entry in contexts[-1]] == ["First question"]
        assert "Stopped" not in json.dumps(followup["trace"]["answer_context"])
        turns = client.get(f"/api/conversations/{conversation_id}").json()["turns"]
        assert [turn["question"] for turn in turns] == ["First question", "Any cheaper ones?"]


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


def test_dropped_connection_cancels_upstream_and_removes_the_turn(tmp_path):
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
        conversation = restarted.get(f"/api/conversations/{conversation_id}").json()
        assert conversation["turns"] == []
        assert conversation["title"] == "New conversation"


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
        # Stop through another conversation never reaches this turn; an unknown conversation is 404.
        assert client.post(f"/api/conversations/{other}/turns/{turn_id}/cancel").status_code == 204
        assert client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["id"] == turn_id
        assert client.post(f"/api/conversations/missing/turns/{turn_id}/cancel").status_code == 404
        assert client.post("/api/conversations/missing/messages", json={"question": "Delver"}).status_code == 404
        assert client.post(f"/api/conversations/{other}/messages", json={"question": "?!"}).status_code == 422
        assert client.post(f"/api/conversations/{other}/messages", json={"question": "Delver", "mode": "psychic"}).status_code == 422
        assert client.get(f"/api/conversations/{other}").json()["turns"] == []
        # The separate retrieve-then-stream request no longer exists.
        assert client.post(f"/api/conversations/{conversation_id}/turns/{turn_id}/stream").status_code in (404, 405)


def test_restart_removes_a_turn_interrupted_by_shutdown(tmp_path):
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
        conversation = restarted.get(f"/api/conversations/{conversation_id}").json()
        assert conversation["turns"] == []
        assert conversation["title"] == "New conversation"

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
