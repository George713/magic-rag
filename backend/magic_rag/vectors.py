"""SQLite vector persistence and the replaceable local embedding boundary."""
import json
import math
import os
from pathlib import Path
from typing import Protocol

import sqlite_vec
from .windows import token_windows
from .filters import ExactFilters


class Embedder(Protocol):
    @property
    def config(self) -> dict: ...
    def document(self, text: str) -> list[float]: ...
    def query(self, text: str) -> list[float]: ...


class EmbeddingError(ValueError):
    pass


def load_vec(db):
    try:
        db.enable_load_extension(True)
        sqlite_vec.load(db)
    except Exception as exc:
        raise RuntimeError("sqlite-vec could not load. Use 64-bit Python 3.11+ with extension loading and run uv sync.") from exc
    finally:
        db.enable_load_extension(False)
    db.execute("CREATE TABLE IF NOT EXISTS embedding_config (config TEXT NOT NULL)")


def checked_vector(vector, dimensions):
    if len(vector) != dimensions or not all(math.isfinite(float(value)) for value in vector) or not any(vector):
        raise EmbeddingError("Embedding must be a finite nonzero vector with the configured dimensions.")
    return sqlite_vec.serialize_float32(vector)


def prepare_vectors(documents: list[tuple[str, str]], embedder: Embedder):
    config = embedder.config
    dimensions = int(config["dimensions"])
    texts = [text for _, text in documents]
    encoded = embedder.documents(texts) if hasattr(embedder, "documents") else [embedder.document(text) for text in texts]
    if len(encoded) != len(documents):
        raise EmbeddingError("Embedding count does not match the complete document count.")
    vectors = [(card_id, checked_vector(vector, dimensions)) for (card_id, _), vector in zip(documents, encoded)]
    return config, vectors


def write_vectors(db, config, vectors):
    dimensions = int(config["dimensions"])
    db.execute("DROP TABLE IF EXISTS card_vectors")
    db.execute(f"CREATE VIRTUAL TABLE card_vectors USING vec0(card_id TEXT PRIMARY KEY, embedding float[{dimensions}] distance_metric=cosine)")
    db.executemany("INSERT INTO card_vectors(card_id, embedding) VALUES (?, ?)", vectors)
    db.execute("DELETE FROM embedding_config")
    db.execute("INSERT INTO embedding_config VALUES (?)", (json.dumps(config, sort_keys=True),))


def store_vectors(db, documents: list[tuple[str, str]], embedder: Embedder):
    write_vectors(db, *prepare_vectors(documents, embedder))


def search_vectors(db, query: str, embedder: Embedder, limit: int = 20, filters: ExactFilters | None = None):
    saved = db.execute("SELECT config FROM embedding_config LIMIT 1").fetchone()
    if not saved:
        raise EmbeddingError("This corpus has no embeddings. Run the sample-vectors ingestion command first.")
    if json.loads(saved[0]) != embedder.config:
        raise EmbeddingError("Embedding configuration is incompatible with this corpus. Re-ingest cards with the configured model and settings.")
    vector = checked_vector(embedder.query(query), int(embedder.config["dimensions"]))
    eligibility, parameters = (filters or ExactFilters()).sql()
    return db.execute(f"""SELECT cards.*, matches.distance AS score FROM
        (SELECT card_id, distance FROM card_vectors WHERE embedding MATCH ? AND k = ?
         AND card_id IN (SELECT cards.card_id FROM cards WHERE {eligibility})) matches
        JOIN cards ON cards.card_id = matches.card_id ORDER BY score, cards.card_id""", (vector, limit, *parameters)).fetchall()


class BgeEmbedder:
    """Lazy CPU baseline. No model is acquired for keyword-only operation."""
    def __init__(self, device: str | None = None, revision: str | None = None):
        self.device = device or os.environ.get("MAGIC_RAG_DEVICE", "cpu")
        self.revision = revision or os.environ.get("MAGIC_RAG_EMBEDDING_REVISION", "main")
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                from huggingface_hub import hf_hub_download
            except ImportError as exc:
                raise EmbeddingError("Local models are not installed. Run uv sync --extra models --python 3.11.") from exc
            try:
                config_path = hf_hub_download("BAAI/bge-small-en-v1.5", "config.json", revision=self.revision)
                self._resolved_revision = Path(config_path).parent.name
                if len(self._resolved_revision) != 40:
                    raise EmbeddingError("The model cache did not expose an immutable snapshot revision.")
                self._model = SentenceTransformer("BAAI/bge-small-en-v1.5", revision=self._resolved_revision, device=self.device)
            except Exception as exc:
                raise EmbeddingError("Unable to acquire/load BGE. Check model download access and MAGIC_RAG_DEVICE; keyword search remains available.") from exc
        return self._model

    @property
    def config(self):
        model = self.model
        return {"model": "BAAI/bge-small-en-v1.5", "revision": self._resolved_revision, "dimensions": 384,
                "normalization": True, "query_instruction": "Represent this sentence for searching relevant passages: ",
                "input_policy": "complete-document-windows-v1;reject-overlength-query", "max_tokens": int(model.max_seq_length),
                "aggregation":"token-weighted normalized mean", "document_window_tokens":int(model.max_seq_length)-model.tokenizer.num_special_tokens_to_add(pair=False)}

    def _encode(self, text: str):
        model = self.model
        count = len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False))
        if count > model.max_seq_length:
            raise EmbeddingError(f"Embedding input is {count} tokens; limit is {model.max_seq_length}. Input was not truncated.")
        return model.encode(text, normalize_embeddings=True, convert_to_numpy=True).tolist()

    def document(self, text: str):
        return self.documents([text])[0]

    def documents(self, texts: list[str]):
        import numpy as np
        model = self.model
        chunks, spans, weights = [], [], []
        for text in texts:
            windows = token_windows(text, model.tokenizer, self.config["document_window_tokens"], EmbeddingError)
            start = len(chunks)
            chunks.extend(windows)
            spans.append((start,len(chunks)))
            weights.extend(max(1,len(model.tokenizer.encode(window, add_special_tokens=False, truncation=False))) for window in windows)
        if not chunks:
            return []
        vectors = model.encode(chunks, batch_size=int(os.environ.get("MAGIC_RAG_EMBEDDING_BATCH_SIZE", "32")),
                               normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=True)
        results = []
        for start, end in spans:
            mean = np.average(vectors[start:end], axis=0, weights=weights[start:end])
            norm = np.linalg.norm(mean)
            if not np.isfinite(norm) or norm == 0:
                raise EmbeddingError("Document window aggregation produced an invalid vector.")
            results.append((mean / norm).tolist())
        return results

    def query(self, text: str):
        return self._encode(self.config["query_instruction"] + text)
