from fastapi.testclient import TestClient

from magic_rag.app import create_app


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
        trace = client.post("/api/search", json={
            "question": "Delver", "conversation_id": conversation_id}).json()
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
        assert turn["state"] == "retrieval_complete"
        assert turn["answer"] is None
        assert turn["trace"]["generation"]["status"] == "unconfigured"
        assert "Flying" in turn["trace"]["selected_evidence"][0]["text"]
        assert restarted.post("/api/search", json={"question": "Delver"}).json()["selected_evidence"] == []


def test_delete_conversation_removes_history_after_restart_and_isolates_other_chats(tmp_path):
    path = tmp_path / "cards.db"
    with TestClient(create_app(path)) as client:
        first = client.post("/api/conversations").json()["id"]
        second = client.post("/api/conversations").json()["id"]
        client.post("/api/search", json={"question": "First question", "conversation_id": first})
        client.post("/api/search", json={"question": "Second question", "conversation_id": second})
        assert client.delete(f"/api/conversations/{first}").status_code == 204
    with TestClient(create_app(path)) as restarted:
        assert [c["id"] for c in restarted.get("/api/conversations").json()] == [second]
        assert restarted.get(f"/api/conversations/{first}").status_code == 404
        assert restarted.post("/api/search", json={"question": "Old chat", "conversation_id": first}).status_code == 404
        assert restarted.get(f"/api/conversations/{second}").json()["turns"][0]["question"] == "Second question"
        assert restarted.delete(f"/api/conversations/{first}").status_code == 404


def test_cited_answer_is_saved_with_original_evidence_and_stable_conversation_session(tmp_path):
    from magic_rag.ingest import ingest_sample
    path = tmp_path / "cards.db"
    ingest_sample(path)
    sessions = []

    class Provider:
        def answer(self, question, evidence, session_id, *, context=None):
            sessions.append(session_id)
            return {"text": "The back face has flying.", "citations": ["sample-delver"], "insufficient_evidence": False}

    with TestClient(create_app(path, provider=Provider())) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        trace = client.post("/api/search", json={"question": "Delver", "conversation_id": conversation_id, "generate_answer": True}).json()
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
        trace = client.post("/api/search", json={"question": "Delver", "conversation_id": conversation, "filters": {"colors": ["U"]}}).json()
        client.patch(f"/api/conversations/{conversation}", json={"filters": {"colors": []}})
        saved = client.get(f"/api/conversations/{conversation}").json()
        assert saved["current_filters"] == {"colors": []}
        assert saved["turns"][0]["trace"] == trace
        assert saved["turns"][0]["trace"]["filters"] == {"colors": ["U"]}


def test_pre_extension_chat_inherits_latest_filters_without_rewriting_history(tmp_path):
    import json
    import sqlite3
    path = tmp_path / "legacy.db"
    trace = {"filters": {"colors": ["R"]}, "question": "Legacy card", "generation": {"status": "unconfigured"}}
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE conversation_turns (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, question TEXT NOT NULL, state TEXT NOT NULL, trace TEXT NOT NULL, answer TEXT, error TEXT, created_at TEXT NOT NULL);
            INSERT INTO conversations VALUES ('legacy', 'Old chat', '2026-01-01', '2026-01-01');
        """)
        db.execute("INSERT INTO conversation_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ('turn', 'legacy', 'Legacy card', 'retrieval_complete', json.dumps(trace), None, None, '2026-01-01'))
    with TestClient(create_app(path)) as client:
        saved = client.get('/api/conversations/legacy').json()
        assert saved["current_filters"] == {"colors": ["R"]}
        assert saved["turns"][0]["trace"] == trace
