"""Bounded conversational context from earlier turns: it resolves references, never supplies card evidence or filters."""

CONTEXT_TURN_LIMIT = 6
ANSWER_CONTEXT_CHARACTER_BUDGET = 16000
ANSWER_CONTEXT_FIELD_LIMIT = 4000


def conversation_context(turns):
    context = []
    for turn in turns[-CONTEXT_TURN_LIMIT:]:
        item = {"question": turn["question"], "query": "; ".join(search["query"] for search in turn["trace"]["searches"])}
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


def freeze_answer_context(queries, turns):
    """The answer's snapshot of this message's search queries and bounded earlier turns."""
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
    return {"search_queries":list(queries), "conversation_context":list(reversed(history)), "context_truncated":truncated}

