"""SQLite vector persistence and the replaceable local embedding boundary."""
import json
import math
import os
from pathlib import Path
from typing import Protocol

import sqlite_vec


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


def store_vectors(db, documents: list[tuple[str, str]], embedder: Embedder):
    config = embedder.config
    dimensions = int(config["dimensions"])
    vectors = [(card_id, checked_vector(embedder.document(text), dimensions)) for card_id, text in documents]
    db.execute("DROP TABLE IF EXISTS card_vectors")
    db.execute(f"CREATE VIRTUAL TABLE card_vectors USING vec0(card_id TEXT PRIMARY KEY, embedding float[{dimensions}] distance_metric=cosine)")
    db.executemany("INSERT INTO card_vectors(card_id, embedding) VALUES (?, ?)", vectors)
    db.execute("DELETE FROM embedding_config")
    db.execute("INSERT INTO embedding_config VALUES (?)", (json.dumps(config, sort_keys=True),))


def search_vectors(db, query: str, embedder: Embedder, limit: int = 20):
    saved = db.execute("SELECT config FROM embedding_config LIMIT 1").fetchone()
    if not saved:
        raise EmbeddingError("This corpus has no embeddings. Run the sample-vectors ingestion command first.")
    if json.loads(saved[0]) != embedder.config:
        raise EmbeddingError("Embedding configuration is incompatible with this corpus. Re-ingest cards with the configured model and settings.")
    vector = checked_vector(embedder.query(query), int(embedder.config["dimensions"]))
    return db.execute("""SELECT cards.*, matches.distance AS score FROM
        (SELECT card_id, distance FROM card_vectors WHERE embedding MATCH ? AND k = ?) matches
        JOIN cards ON cards.card_id = matches.card_id ORDER BY score, cards.card_id""", (vector, limit)).fetchall()


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
                "input_policy": "reject-overlength", "max_tokens": int(model.max_seq_length)}

    def _encode(self, text: str):
        model = self.model
        count = len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False))
        if count > model.max_seq_length:
            raise EmbeddingError(f"Embedding input is {count} tokens; limit is {model.max_seq_length}. Input was not truncated.")
        return model.encode(text, normalize_embeddings=True, convert_to_numpy=True).tolist()

    def document(self, text: str):
        return self._encode(text)

    def query(self, text: str):
        return self._encode(self.config["query_instruction"] + text)
