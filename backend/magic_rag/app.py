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
from .vectors import BgeEmbedder, Embedder, EmbeddingError, load_vec, search_vectors
from .retrieval import fuse
from .conversations import register_conversations
from .filters import ExactFilters, register_filter_functions


def default_db_path() -> Path:
    return Path(os.environ.get("MAGIC_RAG_DB", Path.home() / ".magic-rag" / "cards.db"))


@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    register_filter_functions(db)
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


class RetrievalSettings(BaseModel):
    keyword_candidates: int = Field(default=20, ge=1, le=1000)
    vector_candidates: int = Field(default=20, ge=1, le=1000)
    rrf_constant: int = Field(default=60, ge=0, le=10000)
    evidence_limit: int = Field(default=8, ge=1, le=1000)


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    mode: str = "keyword"
    settings: RetrievalSettings = Field(default_factory=RetrievalSettings)
    generate_answer: bool = False
    conversation_id: str | None = None
    filters: ExactFilters = Field(default_factory=ExactFilters)


def create_app(db_path: Path | None = None, *, embedder: Embedder | None = None, provider=None) -> FastAPI:
    provider = provider if provider is not None else provider_from_env()
    path = Path(db_path or default_db_path())
    with connect(path):
        pass
    app = FastAPI(title="Magic RAG", version="0.1.0")
    conversations = register_conversations(app, lambda: connect(path))
    embedding_model = embedder or BgeEmbedder()

    @app.get("/api/provider")
    def configured_provider():
        return provider_status(provider)

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
        if request.mode not in ("keyword", "vector", "hybrid"):
            raise HTTPException(422, "Choose keyword, vector, or hybrid mode.")
        tokens = re.findall(r"[^\W_]+", request.question, flags=re.UNICODE)
        if not tokens:
            raise HTTPException(422, "Enter at least one word to search.")
        expression = " OR ".join('"' + token + '"' for token in tokens)
        eligibility, filter_parameters = request.filters.sql()
        stages = {}
        timings = {}
        with connect(path) as db:
            corpus = db.execute("SELECT id, metadata FROM corpus LIMIT 1").fetchone()
            branches = ("keyword", "vector") if request.mode == "hybrid" else (request.mode,)
            for branch in branches:
                stage_start = perf_counter()
                try:
                    rows = search_vectors(db, request.question, embedding_model, request.settings.vector_candidates, request.filters) if branch == "vector" else db.execute(f"""SELECT cards.*, bm25(card_fts) AS score
                        FROM card_fts JOIN cards ON cards.card_id = card_fts.card_id
                        WHERE card_fts MATCH ? AND {eligibility} ORDER BY score, cards.card_id LIMIT ?""", (expression, *filter_parameters, request.settings.keyword_candidates)).fetchall()
                except EmbeddingError as exc:
                    raise HTTPException(422, str(exc)) from exc
                stages[branch] = []
                for rank, row in enumerate(rows, 1):
                    card = dict(row)
                    card["colors"] = json.loads(card["colors"])
                    card["rank"] = rank
                    stages[branch].append(card)
                timings[branch] = (perf_counter() - stage_start) * 1000
        if request.mode == "hybrid":
            fusion_start = perf_counter()
            stages["fused"] = fuse(stages, request.settings.rrf_constant)
            timings["fusion"] = (perf_counter() - fusion_start) * 1000
        candidates = stages["fused" if request.mode == "hybrid" else request.mode]
        trace_id = str(uuid4())
        trace = {"trace_id": trace_id, "question": request.question, "query": request.question,
                "mode": request.mode, "filters": request.filters.model_dump(exclude_defaults=True), "corpus": dict(corpus) if corpus else None,
                "models": {"embedding": embedding_model.config} if request.mode != "keyword" else {},
                "settings": {**request.settings.model_dump(), "vector_metric": "cosine distance (lower is better)", "fusion_metric": "reciprocal rank fusion (higher is better)"},
                "stages": stages, "selected_evidence": candidates[:request.settings.evidence_limit],
                "timings_ms": {**timings, "retrieval": (perf_counter() - start) * 1000},
                "rewrite": {"status": "unavailable", "message": "Conversational rewriting is unavailable. Submitted text is searched as-is."},
                "generation": generate_answer(provider, request.question, candidates[:request.settings.evidence_limit], request.conversation_id or trace_id) if request.generate_answer else provider_status(provider)}
        if request.conversation_id is not None:
            conversations.append_trace(request.conversation_id, trace)
        return trace

    return app
