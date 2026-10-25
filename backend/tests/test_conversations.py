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
