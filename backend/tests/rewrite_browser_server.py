"""Deterministic rewrite provider; no external model traffic for browser tests."""
import os
from pathlib import Path
import uvicorn
from magic_rag.app import create_app, connect
from test_rewriting import seed_artifact_cards, TopicEmbedder, TopicReranker, STANDALONE, FOLLOWUP


class BrowserProvider:
    async def rewrite(self, question, history, session_id):
        if question == "simulate rewrite failure":
            raise RuntimeError("Controlled rewrite outage")
        return {"query": STANDALONE if question == FOLLOWUP else question}


if __name__ == "__main__":
    path = Path(os.environ["MAGIC_RAG_DB"])
    with connect(path) as db:
        db.execute("DELETE FROM cards")
        db.execute("DELETE FROM card_fts")
        db.execute("DELETE FROM corpus")
    seed_artifact_cards(path)
    uvicorn.run(create_app(path, embedder=TopicEmbedder(), reranker=TopicReranker(), provider=BrowserProvider()), host="127.0.0.1", port=8111)
