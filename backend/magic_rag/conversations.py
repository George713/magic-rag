"""Saved conversations retain their original evidence, independent of the active corpus."""
from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi import HTTPException, Response


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    def __init__(self, connection):
        self.connection = connection
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                    question TEXT NOT NULL, state TEXT NOT NULL,
                    trace TEXT NOT NULL, answer TEXT, error TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id));
                CREATE INDEX IF NOT EXISTS turns_by_conversation
                    ON conversation_turns(conversation_id, created_at);
            """)

    def create(self):
        now = timestamp()
        conversation_id = str(uuid4())
        with self.connection() as db:
            db.execute("INSERT INTO conversations VALUES (?, ?, ?, ?)",
                       (conversation_id, "New conversation", now, now))
        return self.get(conversation_id)

    def list(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC, id")]

    def get(self, conversation_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Conversation not found. Start a new conversation.")
            turns = []
            for turn in db.execute("SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY created_at, id", (conversation_id,)):
                saved = dict(turn)
                saved["trace"] = json.loads(saved["trace"])
                turns.append(saved)
            return {**dict(row), "turns": turns}

    def append_trace(self, conversation_id, trace):
        now = timestamp()
        turn_id = str(uuid4())
        with self.connection() as db:
            conversation = db.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise HTTPException(404, "Conversation not found. Start a new conversation.")
            trace.update(conversation_id=conversation_id, turn_id=turn_id)
            generation = trace["generation"]
            state = generation["status"] if generation["status"] in {"completed", "failed", "cancelled"} else "retrieval_complete"
            db.execute("INSERT INTO conversation_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (turn_id, conversation_id, trace["question"], state,
                        json.dumps(trace), generation.get("text"), generation.get("error"), now))
            db.execute("UPDATE conversations SET title = CASE WHEN title = 'New conversation' THEN ? ELSE title END, updated_at = ? WHERE id = ?",
                       (trace["question"][:80], now, conversation_id))
        return trace

    def delete(self, conversation_id):
        with self.connection() as db:
            db.execute("DELETE FROM conversation_turns WHERE conversation_id = ?", (conversation_id,))
            deleted = db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            if deleted.rowcount == 0:
                raise HTTPException(404, "Conversation not found.")


def register_conversations(app, connection):
    store = ConversationStore(connection)
    app.state.conversations = store

    @app.post("/api/conversations", status_code=201)
    def create_conversation():
        return store.create()

    @app.get("/api/conversations")
    def list_conversations():
        return store.list()

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: str):
        return store.get(conversation_id)

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str):
        store.delete(conversation_id)
        return Response(status_code=204)

    return store
