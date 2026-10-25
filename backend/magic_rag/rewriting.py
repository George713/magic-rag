"""Conversational context produces a search query, never new card evidence or filters."""
import re
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from .providers import provider_status


class RewritePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    query: str = Field(min_length=1, max_length=10000)


def conversation_context(turns):
    context = []
    for turn in turns[-6:]:
        item = {"question": turn["question"], "query": turn["trace"]["query"]}
        if turn["state"] == "completed" and turn.get("answer"):
            item["answer"] = turn["answer"]
        context.append(item)
    return context


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
