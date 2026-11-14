"""Deterministic chat model for real browser streaming and Stop checks."""
import asyncio
import json
import os
from pathlib import Path

import uvicorn

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from scripted_chat_model import ScriptedChatModel, offers_tools, search_call, search_once


async def answer(call):
    question = call.source["question"]
    card_id = call.source["selected_evidence"][0]["card_id"]
    if "slow" in question:
        await asyncio.sleep(2)
    yield '{"text": "The transformed '
    await asyncio.sleep(15 if "stop" in question else 0.8)
    if "fail" in question:
        raise RuntimeError("controlled provider failure")
    yield 'face has flying.", "citations": ' + json.dumps([card_id]) + ', "insufficient_evidence": false}'


def chat_model(call):
    if offers_tools(call):
        return search_call(call.source["question"])
    return answer(call)


if __name__ == "__main__":
    path = Path(os.environ["MAGIC_RAG_DB"])
    ingest_sample(path)
    uvicorn.run(create_app(path, chat_model=ScriptedChatModel(script=search_once(chat_model))), host="127.0.0.1", port=8100)
