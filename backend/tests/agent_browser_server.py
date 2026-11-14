"""Deterministic agent chat model writing its own card searches; no external model traffic for browser tests."""
import asyncio
import os
from pathlib import Path

import uvicorn

from magic_rag.app import create_app, connect
from artifact_cards import ATOG, ENGINEER, FOLLOWUP, STANDALONE, TopicEmbedder, TopicReranker, seed_artifact_cards
from scripted_chat_model import DONE_SEARCHING, ScriptedChatModel, offers_tools, search_call

LOOSE = "something red that eats artifacts"
WRITTEN = "Atog sacrifice an artifact creature"
COMPARE = "compare Atog and Goblin Engineer"


def agent(call):
    question = call.source["question"]
    searched = [message for message in call.messages if message.type == "tool"]
    if offers_tools(call):
        if question == "simulate provider failure":
            raise RuntimeError("Controlled provider outage")
        if question == COMPARE:
            # One search per compared card, as separate model turns.
            return search_call(["Atog", "Goblin Engineer"][len(searched)]) if len(searched) < 2 else DONE_SEARCHING
        return DONE_SEARCHING if searched else search_call({LOOSE: WRITTEN, FOLLOWUP: STANDALONE}.get(question, question))
    if question == COMPARE:
        async def comparison():
            await asyncio.sleep(3)  # Long enough to see both live search lines.
            yield '{"text": "Atog grows; Goblin Engineer returns artifacts.", '
            yield '"citations": ["%s", "%s"], "insufficient_evidence": false}' % (ATOG, ENGINEER)
        return comparison()

    async def answer():
        # Slow enough that the live search line is visible before the answer completes.
        await asyncio.sleep(1.5)
        yield '{"text": "Atog sacrifices artifacts to grow.", '
        yield '"citations": ["%s"], "insufficient_evidence": false}' % ATOG
    return answer()


if __name__ == "__main__":
    path = Path(os.environ["MAGIC_RAG_DB"])
    with connect(path) as db:
        db.execute("DELETE FROM cards")
        db.execute("DELETE FROM card_fts")
        db.execute("DELETE FROM corpus")
    seed_artifact_cards(path)
    uvicorn.run(create_app(path, embedder=TopicEmbedder(), reranker=TopicReranker(), chat_model=ScriptedChatModel(script=agent)), host="127.0.0.1", port=8111)
