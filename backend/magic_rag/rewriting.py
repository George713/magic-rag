"""Conversational context produces a search query, never new card evidence or filters."""
import re
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from .providers import provider_status

CONTEXT_TURN_LIMIT = 6
ANSWER_CONTEXT_CHARACTER_BUDGET = 16000
ANSWER_CONTEXT_FIELD_LIMIT = 4000


class RewritePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    query: str = Field(min_length=1, max_length=10000)


def conversation_context(turns):
    context = []
    for turn in turns[-CONTEXT_TURN_LIMIT:]:
        item = {"question": turn["question"], "query": turn["trace"]["query"]}
        if turn["state"] == "completed" and turn.get("answer"):
            item["answer"] = turn["answer"]
        if turn["state"] == "completed":
            assets = turn["trace"].get("generation", {}).get("assets", [])
            if assets:
                # Names/identities resolve conversational references; prior card
                # text and source imagery do not become evidence for a new turn.
                references = "\n".join(f'{asset["name"]} [{asset["card_id"]}]' for asset in assets)
                item["shown_cards"] = references if len(references) <= ANSWER_CONTEXT_FIELD_LIMIT else references[:ANSWER_CONTEXT_FIELD_LIMIT-1] + "…"
        context.append(item)
    return context


def freeze_answer_context(query, turns):
    history = []
    remaining = ANSWER_CONTEXT_CHARACTER_BUDGET
    truncated = len(turns) > CONTEXT_TURN_LIMIT
    for item in reversed(conversation_context(turns)):
        truncated = truncated or item.get("shown_cards", "").endswith("…")
        clipped = {}
        for key, value in item.items():
            clipped[key] = value if len(value) <= ANSWER_CONTEXT_FIELD_LIMIT else value[:ANSWER_CONTEXT_FIELD_LIMIT-1] + "…"
            truncated = truncated or len(value) > ANSWER_CONTEXT_FIELD_LIMIT
        size = sum(len(value) for value in clipped.values())
        if size > remaining:
            truncated = True
            break
        history.append(clipped)
        remaining -= size
    return {"retrieval_query":query, "conversation_context":list(reversed(history)), "context_truncated":truncated}


async def rewrite_query(provider, question, history, session_id):
    start = perf_counter()
    query = question
    status = "unavailable"
    message = "Conversational rewriting is unavailable. Submitted text is searched as-is; submit a self-contained question."
    if provider_status(provider)["status"] == "ready" and hasattr(provider, "rewrite"):
        if not history:
            status = "not_needed"
            message = "No earlier turns in this conversation. Submitted text is searched as-is."
        else:
            try:
                result = RewritePayload.model_validate(await provider.rewrite(question, history, session_id))
                standalone = result.query.strip()
                if not re.search(r"[^\W_]+", standalone, flags=re.UNICODE):
                    raise ValueError("A retrieval query must contain words.")
                query = standalone
                status = "rewritten"
                message = "Standalone search query rewritten from this conversation. Explicit filters are unchanged."
            except Exception:
                pass
    return query, {"status": status, "message": message, "elapsed_ms": (perf_counter() - start) * 1000}
