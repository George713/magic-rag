"""Real browser application with deterministic external provider and image metadata."""
import asyncio
import json
import os
from pathlib import Path
import uvicorn
from magic_rag.app import create_app, connect
from magic_rag.ingest import ingest_sample

class BrowserProvider:
    async def rewrite(self, question, history, session_id):
        return {"query": "Delver" if question == "Show those again" else question}

    async def stream_answer(self, question, evidence, session_id, *, context=None):
        assets = [evidence[0]["card_id"]] if "assets" in question else []
        text = "" if "assets only" in question else "The transformed face has flying."
        if text:
            yield {"delta": "The transformed "}
            await asyncio.sleep(15 if "stop" in question else .2)
            if "fail" in question:
                raise RuntimeError("deterministic provider failure")
            yield {"delta": "face has flying."}
        yield {"result": {"text":text,"assets":assets,"citations":[evidence[0]["card_id"]] if text else [],"insufficient_evidence":False}}

if __name__ == "__main__":
    path=Path(os.environ["MAGIC_RAG_DB"])
    ingest_sample(path)
    with connect(path) as db:
        db.execute("INSERT OR REPLACE INTO card_images VALUES (?, ?, ?)",("sample-delver",json.dumps([
            {"name":"Delver of Secrets","url":"https://cards.test/delver-front.jpg"},
            {"name":"Insectile Aberration","url":"https://cards.test/delver-back.jpg"}
        ]),"https://cards.test/delver"))
        db.execute("INSERT OR REPLACE INTO card_images VALUES (?, ?, ?)",("sample-lightning-bolt",json.dumps([
            {"name":"Lightning Bolt","url":"https://cards.test/bolt.jpg"}
        ]),"https://cards.test/bolt"))
    uvicorn.run(create_app(path,provider=BrowserProvider()),host="127.0.0.1",port=8131)
