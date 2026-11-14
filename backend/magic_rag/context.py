"""Bounded conversational context from earlier completed turns: it resolves references, never supplies card evidence or filters."""

CONTEXT_TURN_LIMIT = 6
ANSWER_CONTEXT_CHARACTER_BUDGET = 16000
ANSWER_CONTEXT_FIELD_LIMIT = 4000


def clip(value):
    return value if len(value) <= ANSWER_CONTEXT_FIELD_LIMIT else value[:ANSWER_CONTEXT_FIELD_LIMIT-1] + "…"


def completed_turns(turns):
    """Failed, stopped, and in-progress turns never become context."""
    return [turn for turn in turns if turn["state"] == "completed"]


def conversation_context(turns):
    context = []
    for turn in completed_turns(turns)[-CONTEXT_TURN_LIMIT:]:
        item = {"question": turn["question"], "query": "; ".join(search["query"] for search in turn["trace"]["searches"])}
        if turn.get("answer"):
            item["answer"] = turn["answer"]
        assets = turn["trace"].get("generation", {}).get("assets", [])
        if assets:
            # Names/identities resolve conversational references; prior card
            # text and source imagery do not become evidence for a new turn.
            item["shown_cards"] = clip("\n".join(f'{asset["name"]} [{asset["card_id"]}]' for asset in assets))
        context.append(item)
    return context


def freeze_answer_context(searches, turns):
    """The answer's snapshot of this message's search queries and bounded earlier turns."""
    history = []
    remaining = ANSWER_CONTEXT_CHARACTER_BUDGET
    truncated = len(completed_turns(turns)) > CONTEXT_TURN_LIMIT
    for item in reversed(conversation_context(turns)):
        truncated = truncated or item.get("shown_cards", "").endswith("…")
        clipped = {key: clip(value) for key, value in item.items()}
        truncated = truncated or any(len(value) > ANSWER_CONTEXT_FIELD_LIMIT for value in item.values())
        size = sum(len(value) for value in clipped.values())
        if size > remaining:
            truncated = True
            break
        history.append(clipped)
        remaining -= size
    return {"search_queries": [search["query"] for search in searches], "conversation_context": list(reversed(history)), "context_truncated": truncated}
