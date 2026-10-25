"""Deterministic local model boundary for exact-filter presentation checks."""
import os
from pathlib import Path
import uvicorn
from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from test_vectors import ControlledEmbedder
from test_filters import FilterReranker

if __name__ == "__main__":
    path = Path(os.environ["MAGIC_RAG_DB"])
    model = ControlledEmbedder()
    ingest_sample(path, embedder=model)
    uvicorn.run(create_app(path, embedder=model, reranker=FilterReranker()), host="127.0.0.1", port=8106)
