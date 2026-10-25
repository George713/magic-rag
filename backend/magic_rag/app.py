import os
import json
import re
import sqlite3
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .vectors import BgeEmbedder, Embedder, EmbeddingError, load_vec, search_vectors
from .conversations import register_conversations


def default_db_path() -> Path:
    return Path(os.environ.get("MAGIC_RAG_DB", Path.home() / ".magic-rag" / "cards.db"))


@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    load_vec(db)
    try:
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS card_fts USING fts5(card_id UNINDEXED, text)")
    except sqlite3.OperationalError as exc:
        db.close()
        raise RuntimeError("SQLite FTS5 is required. Install official 64-bit Python 3.11+ with FTS5 support, then recreate the virtual environment.") from exc
    db.executescript("""
        CREATE TABLE IF NOT EXISTS cards (card_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            text TEXT NOT NULL, mana_cost TEXT NOT NULL, mana_value REAL NOT NULL,
            colors TEXT NOT NULL, type_line TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS corpus (id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    mode: str = "keyword"
    conversation_id: str | None = None


def create_app(db_path: Path | None = None, *, embedder: Embedder | None = None) -> FastAPI:
    path = Path(db_path or default_db_path())
    with connect(path):
        pass
    app = FastAPI(title="Magic RAG", version="0.1.0")
    conversations = register_conversations(app, lambda: connect(path))
    embedding_model = embedder or BgeEmbedder()

    @app.get("/api/health")
    def health():
        with connect(path) as db:
            return {"status": "ok", "sqlite_version": sqlite3.sqlite_version,
                    "sqlite_vec_version": db.execute("SELECT vec_version()").fetchone()[0],
                    "fts5": True, "card_count": db.execute("SELECT count(*) FROM cards").fetchone()[0]}

    @app.post("/api/search")
    def search(request: SearchRequest):
        if request.conversation_id is not None:
            conversations.get(request.conversation_id)
        start = perf_counter()
        if request.mode not in ("keyword", "vector"):
            raise HTTPException(422, "Choose keyword or vector mode.")
        tokens = re.findall(r"[^\W_]+", request.question, flags=re.UNICODE)
        if not tokens:
            raise HTTPException(422, "Enter at least one word to search.")
        expression = " OR ".join('"' + token + '"' for token in tokens)
        with connect(path) as db:
            corpus = db.execute("SELECT id, metadata FROM corpus LIMIT 1").fetchone()
            stage_start = perf_counter()
            try:
                rows = search_vectors(db, request.question, embedding_model) if request.mode == "vector" else db.execute("""SELECT cards.*, bm25(card_fts) AS score
                    FROM card_fts JOIN cards ON cards.card_id = card_fts.card_id
                    WHERE card_fts MATCH ? ORDER BY score, cards.card_id LIMIT 20""", (expression,)).fetchall()
            except EmbeddingError as exc:
                raise HTTPException(422, str(exc)) from exc
            stage_ms = (perf_counter() - stage_start) * 1000
        candidates = []
        for rank, row in enumerate(rows, 1):
            card = dict(row)
            card["colors"] = json.loads(card["colors"])
            card["rank"] = rank
            candidates.append(card)
        trace = {"trace_id": str(uuid4()), "question": request.question, "query": request.question,
                "mode": request.mode, "filters": {}, "corpus": dict(corpus) if corpus else None,
                "models": {"embedding": embedding_model.config} if request.mode == "vector" else {},
                "settings": {"keyword_candidates": 20, "vector_candidates": 20, "evidence_limit": 8, "vector_metric": "cosine distance (lower is better)"},
                "stages": {request.mode: candidates}, "selected_evidence": candidates[:8],
                "timings_ms": {request.mode: stage_ms, "retrieval": (perf_counter() - start) * 1000},
                "rewrite": {"status": "unavailable", "message": "Conversational rewriting is unavailable. Submitted text is searched as-is."},
                "generation": {"status": "unconfigured", "message": "Remote generation is not configured."}}
        if request.conversation_id is not None:
            conversations.append_trace(request.conversation_id, trace)
        return trace

    return app
