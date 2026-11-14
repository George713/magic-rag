"""Real browser application with a deterministic chat model and image metadata."""
import asyncio
import json
import os
from pathlib import Path
import uvicorn
from magic_rag.app import create_app, connect
from magic_rag.ingest import ingest_sample
from scripted_chat_model import ScriptedChatModel, offers_tools, search_call, search_once

def chat_model(call):
    source = call.source
    question = source["question"]
    if offers_tools(call):
        return search_call("Delver" if question == "Show those again" else question)
    evidence = source["selected_evidence"]
    assets = [evidence[0]["card_id"]] if "assets" in question else []
    if "multiple assets" in question:
        assets = sorted(card["card_id"] for card in evidence)
    text = "" if "assets only" in question else "The transformed face has flying."
    tail = {"assets": assets, "citations": [evidence[0]["card_id"]] if text else [], "insufficient_evidence": False}
    if not text:
        return {"text": text, **tail}

    async def stream():
        yield '{"text": "The transformed '
        await asyncio.sleep(15 if "stop" in question else .2)
        if "fail" in question:
            raise RuntimeError("deterministic provider failure")
        yield 'face has flying.", ' + json.dumps(tail)[1:]
    return stream()

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
    uvicorn.run(create_app(path,chat_model=ScriptedChatModel(script=search_once(chat_model))),host="127.0.0.1",port=8131)
