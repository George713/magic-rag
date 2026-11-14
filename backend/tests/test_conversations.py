from fastapi.testclient import TestClient

from magic_rag.app import create_app
from test_streaming import message_trace


def test_new_conversation_can_be_reopened_after_application_restart(tmp_path):
    path = tmp_path / "cards.db"
    with TestClient(create_app(path)) as client:
        response = client.post("/api/conversations", json={})
        assert response.status_code == 201
        conversation = response.json()
        assert conversation["title"] == "New conversation"
        assert conversation["turns"] == []
    with TestClient(create_app(path)) as restarted:
        assert restarted.get("/api/conversations").json()[0]["id"] == conversation["id"]
        assert restarted.get(f'/api/conversations/{conversation["id"]}').json() == conversation


def test_saved_turn_reopens_original_evidence_after_corpus_changes(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        trace = message_trace(client, **{
            "question": "Delver", "conversation_id": conversation_id})
        assert trace["conversation_id"] == conversation_id
        assert trace["selected_evidence"][0]["card_id"] == "sample-delver"
    # Arrange a changed source corpus without altering saved conversations.
    # Assertions below observe only the public application seam.
    import sqlite3
    with sqlite3.connect(path) as source:
        source.execute("DELETE FROM card_fts")
        source.execute("DELETE FROM cards")
        source.execute("DELETE FROM corpus")
    with TestClient(create_app(path)) as restarted:
        saved = restarted.get(f"/api/conversations/{conversation_id}").json()
        assert saved["title"] == "Delver"
        turn = saved["turns"][0]
        assert turn["trace"] == trace
        assert turn["state"] == "completed"
        assert turn["answer"] is None
        assert turn["trace"]["generation"]["status"] == "unconfigured"
        assert "Flying" in turn["trace"]["selected_evidence"][0]["text"]
        assert restarted.post("/api/search", json={"question": "Delver"}).json()["selected_evidence"] == []


def test_delete_conversation_removes_history_after_restart_and_isolates_other_chats(tmp_path):
    path = tmp_path / "cards.db"
    with TestClient(create_app(path)) as client:
        first = client.post("/api/conversations").json()["id"]
        second = client.post("/api/conversations").json()["id"]
        message_trace(client, question="First question", conversation_id=first)
        message_trace(client, question="Second question", conversation_id=second)
        assert client.delete(f"/api/conversations/{first}").status_code == 204
    with TestClient(create_app(path)) as restarted:
        assert [c["id"] for c in restarted.get("/api/conversations").json()] == [second]
        assert restarted.get(f"/api/conversations/{first}").status_code == 404
        assert restarted.post(f"/api/conversations/{first}/messages", json={"question": "Old chat"}).status_code == 404
        assert restarted.get(f"/api/conversations/{second}").json()["turns"][0]["question"] == "Second question"
        assert restarted.delete(f"/api/conversations/{first}").status_code == 404


def test_cited_answer_is_saved_with_original_evidence_and_stable_conversation_session(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "cards.db"
    ingest_sample(path)
    sessions = []

    from scripted_chat_model import ScriptedChatModel, searching

    def answer(call):
        sessions.append(call.session)
        return {"text": "The back face has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}

    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=searching(answer)))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        trace = message_trace(client, **{"question": "Delver", "conversation_id": conversation_id})
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert sessions == [conversation_id]
        assert turn["state"] == "completed"
        assert turn["answer"] == "The back face has flying."
        assert turn["trace"] == trace
        assert turn["trace"]["generation"]["citations"][0]["card_id"] == "sample-delver"


def test_current_filters_persist_without_sending_and_are_independent_after_restart(tmp_path):
    path = tmp_path / "cards.db"
    with TestClient(create_app(path)) as client:
        first = client.post("/api/conversations").json()
        second = client.post("/api/conversations").json()
        assert first["current_filters"] == second["current_filters"] == {}
        updated = client.patch(f'/api/conversations/{first["id"]}', json={"filters": {"colors": ["U"], "card_types": ["Creature"]}})
        assert updated.status_code == 200
        assert updated.json()["current_filters"] == {"colors": ["U"], "card_types": ["Creature"]}
        assert client.patch(f'/api/conversations/{second["id"]}', json={"filters": {"colors": []}}).status_code == 200
    with TestClient(create_app(path)) as restarted:
        assert restarted.get(f'/api/conversations/{first["id"]}').json()["current_filters"] == {"colors": ["U"], "card_types": ["Creature"]}
        assert restarted.get(f'/api/conversations/{second["id"]}').json()["current_filters"] == {"colors": []}
        assert restarted.patch(f'/api/conversations/{first["id"]}', json={"filters": {}}).json()["current_filters"] == {}
        assert restarted.patch(f'/api/conversations/{first["id"]}', json={"filters": {"colors": ["purple"]}}).status_code == 422
        assert restarted.get(f'/api/conversations/{first["id"]}').json()["current_filters"] == {}
        assert restarted.patch('/api/conversations/missing', json={"filters": {}}).status_code == 404


def test_current_filter_edits_do_not_change_historical_turn_snapshots(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation = client.post("/api/conversations").json()["id"]
        trace = message_trace(client, **{"question": "Delver", "conversation_id": conversation, "filters": {"colors": ["U"]}})
        client.patch(f"/api/conversations/{conversation}", json={"filters": {"colors": []}})
        saved = client.get(f"/api/conversations/{conversation}").json()
        assert saved["current_filters"] == {"colors": []}
        assert saved["turns"][0]["trace"] == trace
        assert saved["turns"][0]["trace"]["searches"][0]["filters"] == {"colors": ["U"]}


def test_conversations_saved_before_search_lists_are_wiped_once_and_cards_are_kept(tmp_path):
    import json
    import sqlite3
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "single-query.db"
    ingest_sample(path)
    old_trace = {"question": "Delver", "query": "Delver", "mode": "keyword", "filters": {}, "stages": {},
                 "selected_evidence": [], "generation": {"status": "unconfigured"}}
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                current_filters TEXT, current_mode TEXT NOT NULL DEFAULT 'keyword');
            CREATE TABLE conversation_turns (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, question TEXT NOT NULL, state TEXT NOT NULL,
                trace TEXT NOT NULL, answer TEXT, error TEXT, created_at TEXT NOT NULL);
            INSERT INTO conversations VALUES ('old', 'Old chat', '2026-01-01', '2026-01-01', '{"colors": ["U"]}', 'hybrid');
        """)
        db.execute("INSERT INTO conversation_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   ("turn", "old", "Delver", "retrieval_complete", json.dumps(old_trace), None, None, "2026-01-01"))
    with TestClient(create_app(path)) as client:
        assert client.get("/api/conversations").json() == []
        assert client.get("/api/conversations/old").status_code == 404
        assert client.get("/api/health").json()["card_count"] > 0
        assert client.get("/api/corpus").json()["id"] == "controlled-sample-v1"
        new_chat = client.post("/api/conversations").json()["id"]
        trace = message_trace(client, **{"question": "Delver", "conversation_id": new_chat})
        assert trace["searches"][0]["selected_evidence"][0]["card_id"] == "sample-delver"
    with TestClient(create_app(path)) as restarted:
        assert [chat["id"] for chat in restarted.get("/api/conversations").json()] == [new_chat]
        assert restarted.get(f"/api/conversations/{new_chat}").json()["turns"][0]["trace"] == trace


def test_search_uses_current_filters_without_restoring_old_turn_snapshot(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "current.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        first = message_trace(client, **{"question": "Delver", "conversation_id": conversation_id, "filters": {"colors": ["U"]}})
        assert client.get(f"/api/conversations/{conversation_id}").json()["current_filters"] == {"colors": ["U"]}
        client.patch(f"/api/conversations/{conversation_id}", json={"filters": {"legendary": True}}).raise_for_status()
        second = message_trace(client, **{"question": "Delver", "conversation_id": conversation_id})
        assert second["searches"][0]["filters"] == {"legendary": True}
        assert second["selected_evidence"] == []
        saved = client.get(f"/api/conversations/{conversation_id}").json()
        assert saved["turns"][0]["trace"]["searches"][0]["filters"] == first["searches"][0]["filters"] == {"colors": ["U"]}


def test_search_mode_persists_unsent_edits_independently_and_preserves_history(tmp_path):
    from magic_rag.ingest import ingest_sample
    from test_vectors import ControlledEmbedder
    from test_reranking import ControlledReranker
    path = tmp_path / "modes.db"
    ingest_sample(path, embedder=ControlledEmbedder())
    with TestClient(create_app(path, embedder=ControlledEmbedder())) as client:
        first = client.post('/api/conversations').json()
        second = client.post('/api/conversations').json()
        assert first['current_mode'] == second['current_mode'] == 'keyword'
        original = message_trace(client, **{'question': 'Delver', 'conversation_id': first['id']})
        for mode in ('keyword', 'vector', 'hybrid', 'hybrid_rerank'):
            response = client.patch(f"/api/conversations/{first['id']}", json={'mode': mode})
            assert response.status_code == 200
            assert response.json()['current_mode'] == mode
        client.patch(f"/api/conversations/{first['id']}", json={'filters': {'legendary': True}}).raise_for_status()
        assert client.patch(f"/api/conversations/{first['id']}", json={'mode': 'unknown'}).status_code == 422
        assert client.patch(f"/api/conversations/{first['id']}", json={}).status_code == 422
        assert client.patch(f"/api/conversations/{first['id']}", json={'mode': None}).status_code == 422
        assert client.patch('/api/conversations/missing', json={'mode': 'vector'}).status_code == 404
    with TestClient(create_app(path, embedder=ControlledEmbedder(), reranker=ControlledReranker())) as restarted:
        saved = restarted.get(f"/api/conversations/{first['id']}").json()
        assert saved['current_mode'] == 'hybrid_rerank'
        assert saved['current_filters'] == {'legendary': True}
        assert saved['turns'][0]['trace'] == original
        assert restarted.get(f"/api/conversations/{second['id']}").json()['current_mode'] == 'keyword'
        # Omitted mode inherits the preference; explicit mode updates it.
        inherited = message_trace(restarted, **{'question': 'Delver', 'conversation_id': first['id']})
        assert inherited['searches'][0]['mode'] == 'hybrid_rerank'
        message_trace(restarted, question='Delver', conversation_id=first['id'], mode='keyword')
        assert restarted.get(f"/api/conversations/{first['id']}").json()['current_mode'] == 'keyword'


def test_saved_turn_reopens_its_ordered_searches_after_restart(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "searches.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        trace = message_trace(client, **{
            "question": "Delver", "conversation_id": conversation_id, "filters": {"colors": ["U"]}})
    with TestClient(create_app(path)) as restarted:
        turn = restarted.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
    assert turn["trace"] == trace
    [search] = turn["trace"]["searches"]
    assert search["query"] == "Delver"
    assert search["mode"] == "keyword"
    assert search["filters"] == {"colors": ["U"]}
    assert search["stages"]["keyword"][0]["card_id"] == "sample-delver"
    assert search["timings_ms"]["keyword"] >= 0
    assert search["timings_ms"]["retrieval"] >= 0
    assert search["selected_evidence"][0]["card_id"] == "sample-delver"
    assert turn["trace"]["selected_evidence"] == search["selected_evidence"]
    assert not {"query", "mode", "filters", "stages", "models", "settings"} & turn["trace"].keys()
