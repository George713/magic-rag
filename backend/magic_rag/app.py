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
from magic_rag.providers import generate_answer, provider_status, provider_from_env


def default_db_path() -> Path:
    return Path(os.environ.get("MAGIC_RAG_DB", Path.home() / ".magic-rag" / "cards.db"))


@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
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
    generate_answer: bool = False


def create_app(db_path: Path | None = None, *, provider=None) -> FastAPI:
    provider = provider if provider is not None else provider_from_env()
    path = Path(db_path or default_db_path())
    with connect(path):
        pass
    app = FastAPI(title="Magic RAG", version="0.1.0")

    @app.get("/api/provider")
    def configured_provider():
        return provider_status(provider)

    @app.get("/api/health")
    def health():
        with connect(path) as db:
            return {"status": "ok", "sqlite_version": sqlite3.sqlite_version,
                    "fts5": True, "card_count": db.execute("SELECT count(*) FROM cards").fetchone()[0]}

    @app.post("/api/search")
    def search(request: SearchRequest):
        start = perf_counter()
        if request.mode != "keyword":
            raise HTTPException(422, "Only keyword mode is currently available.")
        tokens = re.findall(r"[^\W_]+", request.question, flags=re.UNICODE)
        if not tokens:
            raise HTTPException(422, "Enter at least one word to search.")
        expression = " OR ".join('"' + token + '"' for token in tokens)
        with connect(path) as db:
            corpus = db.execute("SELECT id, metadata FROM corpus LIMIT 1").fetchone()
            rows = db.execute("""SELECT cards.*, bm25(card_fts) AS score
                FROM card_fts JOIN cards ON cards.card_id = card_fts.card_id
                WHERE card_fts MATCH ? ORDER BY score, cards.card_id LIMIT 20""", (expression,)).fetchall()
        candidates = []
        for rank, row in enumerate(rows, 1):
            card = dict(row)
            card["colors"] = json.loads(card["colors"])
            card["rank"] = rank
            candidates.append(card)
        return {"trace_id": str(uuid4()), "question": request.question, "query": request.question,
                "mode": "keyword", "filters": {}, "corpus": dict(corpus) if corpus else None,
                "models": {}, "settings": {"keyword_candidates": 20, "evidence_limit": 8},
                "stages": {"keyword": candidates}, "selected_evidence": candidates[:8],
                "timings_ms": {"retrieval": (perf_counter() - start) * 1000},
                "rewrite": {"status": "unavailable", "message": "Conversational rewriting is unavailable. Submitted text is searched as-is."},
                "generation": generate_answer(provider, request.question, candidates[:8], str(uuid4())) if request.generate_answer else provider_status(provider)}

    return app
