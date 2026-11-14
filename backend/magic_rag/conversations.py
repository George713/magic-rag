"""Saved conversations retain their original evidence, independent of the active corpus."""
from datetime import datetime, timezone
import json
from uuid import uuid4
from typing import Literal

from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict, model_validator

from .filters import ExactFilters


SearchMode = Literal['keyword', 'vector', 'hybrid', 'hybrid_rerank']


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filters: ExactFilters | None = None
    mode: SearchMode | None = None

    @model_validator(mode='after')
    def require_preference(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('Provide filters or a search mode; preferences cannot be null.')
        return self


def timestamp():
    return datetime.now(timezone.utc).isoformat()


IN_PROGRESS_STATUSES = {"searching", "generating"}
TERMINAL_STATUSES = {"completed", "failed"}


def turn_state(generation):
    """A turn is in progress until it completes or fails. A stopped run is deleted, never saved.

    A run without a ready provider completes after its search; its generation keeps the provider status.
    """
    status = generation["status"]
    if status in IN_PROGRESS_STATUSES:
        return "in_progress"
    return status if status in TERMINAL_STATUSES else "completed"


# Version 2 saves an ordered list of searches per turn. Earlier single-query
# turns are not migrated: conversations are wiped once when this version first
# opens a database. Card data, embeddings, and corpus tables are never touched.
STORAGE_VERSION = 2


class ConversationStore:
    def __init__(self, connection):
        self.connection = connection
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("CREATE TABLE IF NOT EXISTS conversation_storage (version INTEGER NOT NULL)")
            stored = db.execute("SELECT max(version) FROM conversation_storage").fetchone()[0]
            if stored is None or stored < STORAGE_VERSION:
                db.execute("DROP TABLE IF EXISTS conversation_turns")
                db.execute("DROP TABLE IF EXISTS conversations")
                db.execute("DELETE FROM conversation_storage")
                db.execute("INSERT INTO conversation_storage VALUES (?)", (STORAGE_VERSION,))
            db.execute("""CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    current_filters TEXT NOT NULL DEFAULT '{}',
                    current_mode TEXT NOT NULL DEFAULT 'keyword')""")
            db.execute("""CREATE TABLE IF NOT EXISTS conversation_turns (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                    question TEXT NOT NULL, state TEXT NOT NULL,
                    trace TEXT NOT NULL, answer TEXT, error TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id))""")
            db.execute("""CREATE INDEX IF NOT EXISTS turns_by_conversation
                    ON conversation_turns(conversation_id, created_at)""")

    def create(self):
        now = timestamp()
        conversation_id = str(uuid4())
        with self.connection() as db:
            db.execute("INSERT INTO conversations (id, title, created_at, updated_at, current_filters) VALUES (?, ?, ?, ?, ?)",
                       (conversation_id, "New conversation", now, now, "{}"))
        return self.get(conversation_id)

    def list(self):
        with self.connection() as db:
            return [{**dict(row), "current_filters": json.loads(row["current_filters"] or "{}")} for row in db.execute(
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
            return {**dict(row), "current_filters": json.loads(row["current_filters"] or "{}"), "turns": turns}

    def update_filters(self, conversation_id, filters):
        return self.update_preferences(conversation_id, filters=filters)

    def update_preferences(self, conversation_id, *, filters=None, mode=None):
        assignments = ['updated_at = ?']
        values = [timestamp()]
        if filters is not None:
            assignments.append('current_filters = ?')
            values.append(json.dumps(filters.model_dump(exclude_defaults=True)))
        if mode is not None:
            assignments.append('current_mode = ?')
            values.append(mode)
        with self.connection() as db:
            updated = db.execute(f"UPDATE conversations SET {', '.join(assignments)} WHERE id = ?", (*values, conversation_id))
            if updated.rowcount == 0:
                raise HTTPException(404, "Conversation not found. Start a new conversation.")
        return self.get(conversation_id)

    def append_trace(self, conversation_id, trace):
        """Save a new turn for this trace; its state follows the trace's generation."""
        now = timestamp()
        turn_id = str(uuid4())
        with self.connection() as db:
            conversation = db.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise HTTPException(404, "Conversation not found. Start a new conversation.")
            trace.update(conversation_id=conversation_id, turn_id=turn_id)
            generation = trace["generation"]
            state = turn_state(generation)
            db.execute("INSERT INTO conversation_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (turn_id, conversation_id, trace["question"], state,
                        json.dumps(trace), generation.get("text"),
                        generation.get("message") if state == "failed" else None, now))
            db.execute("UPDATE conversations SET title = CASE WHEN title = 'New conversation' THEN ? ELSE title END, updated_at = ? WHERE id = ?",
                       (trace["question"][:80], now, conversation_id))
        return trace

    def delete(self, conversation_id):
        with self.connection() as db:
            db.execute("DELETE FROM conversation_turns WHERE conversation_id = ?", (conversation_id,))
            deleted = db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            if deleted.rowcount == 0:
                raise HTTPException(404, "Conversation not found.")

    def get_turn(self, conversation_id, turn_id):
        for turn in self.get(conversation_id)["turns"]:
            if turn["id"] == turn_id:
                return turn
        raise HTTPException(404, "Conversation turn not found.")

    def delete_turn(self, conversation_id, turn_id, *, expected_states=None):
        """Remove a turn and everything saved with it; returns whether it was removed.

        With `expected_states`, only a turn in one of those states is removed (compare-and-delete).
        A conversation left without turns gets its default title back, so no trace of the turn remains.
        """
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM conversation_turns WHERE id = ? AND conversation_id = ?", (turn_id, conversation_id)).fetchone()
            if row is None or (expected_states is not None and row["state"] not in expected_states):
                return False
            db.execute("DELETE FROM conversation_turns WHERE id = ?", (turn_id,))
            db.execute("""UPDATE conversations SET updated_at = ?, title = CASE WHEN EXISTS (
                    SELECT 1 FROM conversation_turns WHERE conversation_id = ?) THEN title ELSE 'New conversation' END
                    WHERE id = ?""", (timestamp(), conversation_id, conversation_id))
            return True

    def remove_interrupted_turns(self):
        """Runs cut off by a shutdown are stopped runs: nothing from them is kept."""
        with self.connection() as db:
            interrupted = db.execute("SELECT conversation_id, id FROM conversation_turns WHERE state = 'in_progress'").fetchall()
        for row in interrupted:
            self.delete_turn(row["conversation_id"], row["id"], expected_states={"in_progress"})

    def update_generation(self, conversation_id, turn_id, generation, *, expected_states):
        return self.update_trace(conversation_id, turn_id, lambda trace: {**trace, "generation": generation}, expected_states=expected_states)

    def update_trace(self, conversation_id, turn_id, change, *, expected_states):
        """Compare-and-set prevents late searches, deltas, or completion from overwriting terminal or deleted turns.

        `change` maps the saved trace to its replacement; the turn state follows the new generation.
        """
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state, trace FROM conversation_turns WHERE id = ? AND conversation_id = ?", (turn_id, conversation_id)).fetchone()
            if row is None or row["state"] not in expected_states:
                # A Stop may delete the turn while its run is still writing.
                return False
            trace = change(json.loads(row["trace"]))
            generation = trace["generation"]
            state = turn_state(generation)
            db.execute("UPDATE conversation_turns SET state = ?, trace = ?, answer = ?, error = ? WHERE id = ? AND conversation_id = ?",
                       (state, json.dumps(trace), generation.get("text"),
                        generation.get("message") if state == "failed" else None,
                        turn_id, conversation_id))
            db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (timestamp(), conversation_id))
            return True


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

    @app.patch("/api/conversations/{conversation_id}")
    def update_preferences(conversation_id: str, request: ConversationUpdate):
        return store.update_preferences(conversation_id, filters=request.filters, mode=request.mode)

    return store
