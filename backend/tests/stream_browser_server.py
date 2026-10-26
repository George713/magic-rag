"""Deterministic external provider for real browser streaming and Stop checks."""
import asyncio
import os
from pathlib import Path

import uvicorn

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample


class BrowserProvider:
    async def stream_answer(self, question, evidence, session_id, *, context=None):
        yield {"delta": "The transformed "}
        if "stop" in question:
            await asyncio.sleep(15)
        else:
            await asyncio.sleep(0.8)
        if "fail" in question:
            raise RuntimeError("controlled provider failure")
        yield {"delta": "face has flying."}
        yield {"result": {"text": "The transformed face has flying.", "citations": [evidence[0]["card_id"]], "insufficient_evidence": False}}


if __name__ == "__main__":
    path = Path(os.environ["MAGIC_RAG_DB"])
    ingest_sample(path)
    uvicorn.run(create_app(path, provider=BrowserProvider()), host="127.0.0.1", port=8100)
