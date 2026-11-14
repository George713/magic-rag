"""One streamed request per message: its searches, the answer as it is written, then the saved result.

The response is newline-delimited JSON. Events, in order:

- `start`: the saved in-progress turn (`trace`, with `conversation_id` and `turn_id`);
- `search`: one per completed search, in order (`index`, `query`, `card_count`, `top_cards`, the
  full search record as `search`, i.e. its retrieval details, and the combined `selected_evidence`
  of the searches so far);
- `delta`: answer text fragments;
- `done`: the final `generation` (validated answer, failure, cancellation, or provider status) and the
  saved `trace`.
"""
import json
import asyncio
from contextlib import suppress
from uuid import uuid4

import anyio
from langgraph.errors import NodeCancelledError

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .agent import run_card_search_agent
from .context import freeze_answer_context
from .providers import completed_answer, provider_status
from .retrieval import combined_evidence

SEARCHING = {"status": "searching", "message": "Searching cards.", "text": "", "citations": []}
GENERATING = {"status": "generating", "message": "Generating from selected evidence.", "text": "", "citations": []}
FAILED_MESSAGE = "Answer stream failed or ended unexpectedly. Check the provider or connection and submit another question. Retrieved evidence is preserved."
TOP_CARDS = 3


class StreamStopped(Exception):
    pass


async def until_stopped(awaitable, stopped):
    """Await `awaitable` unless Stop is requested first; the abandoned work is cancelled."""
    pending = asyncio.ensure_future(awaitable)
    cancellation = asyncio.create_task(stopped.wait())
    try:
        ready, _ = await asyncio.wait({pending, cancellation}, return_when=asyncio.FIRST_COMPLETED)
        if cancellation in ready:
            raise StreamStopped()
        return pending.result()
    finally:
        pending.cancel()
        cancellation.cancel()
        with anyio.CancelScope(shield=True):
            with suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                await pending
            with suppress(asyncio.CancelledError):
                await cancellation


def encode_event(event, **data):
    return json.dumps({"event": event, **data}) + "\n"


def search_event(index, search, combined):
    evidence = search["selected_evidence"]
    return encode_event("search", index=index, query=search["query"], card_count=len(evidence),
                        top_cards=[{"card_id": card["card_id"], "name": card["name"]} for card in evidence[:TOP_CARDS]],
                        search=search, selected_evidence=combined)


def failure_message(exc):
    # Retrieval errors carry safe, user-facing details; provider errors never reach the browser.
    return exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else FAILED_MESSAGE


def register_streaming(app, store, provider, *, request_model, constraints, remember, retrieve):
    store.recover_interrupted_turns()
    active = {}

    @app.post("/api/conversations/{conversation_id}/turns/{turn_id}/cancel")
    async def cancel(conversation_id: str, turn_id: str):
        turn = store.get_turn(conversation_id, turn_id)
        generation = turn["trace"]["generation"]
        if turn["state"] == "in_progress":
            generation = {**generation, "status": "cancelled", "message": "Answer stopped. Partial output is incomplete.", "citations": []}
            store.update_generation(conversation_id, turn_id, generation, expected_states={"in_progress"})
            stopped = active.get((conversation_id, turn_id))
            if stopped is not None:
                stopped.set()
        return store.get_turn(conversation_id, turn_id)["trace"]["generation"]

    @app.post("/api/conversations/{conversation_id}/messages")
    async def message(conversation_id: str, request: request_model):
        conversation = store.get(conversation_id)
        filters, mode = constraints(request, conversation)
        remember(conversation_id, request, filters, mode)
        turns = conversation["turns"]
        trace = store.append_trace(conversation_id, {
            "trace_id": str(uuid4()), "question": request.question, "corpus": None,
            "searches": [], "selected_evidence": [], "timings_ms": {},
            "answer_context": None, "generation": SEARCHING})
        turn_id = trace["turn_id"]
        stopped = asyncio.Event()
        active[(conversation_id, turn_id)] = stopped

        def save(change):
            if not store.update_trace(conversation_id, turn_id, change, expected_states={"in_progress"}):
                raise StreamStopped()

        def finish(generation):
            # Terminal states are written once; a concurrent Stop wins the compare-and-set.
            store.update_generation(conversation_id, turn_id, generation, expected_states={"in_progress"})

        async def events():
            nonlocal trace
            generation = trace["generation"]
            iterator = None
            try:
                yield encode_event("start", trace=trace)
                iterator = run_card_search_agent(
                    provider, retrieve, question=request.question, turns=turns, session_id=conversation_id,
                    mode=mode, filters=filters, settings=request.settings).__aiter__()
                searches = []
                while True:
                    try:
                        event = await until_stopped(anext(iterator), stopped)
                    except StopAsyncIteration:
                        break
                    if "search" in event:
                        searches.append(event["search"])
                        trace = {**trace, "corpus": trace["corpus"] or event["corpus"], "searches": list(searches),
                                 "selected_evidence": combined_evidence(searches),
                                 "timings_ms": {"retrieval": sum(search["timings_ms"]["retrieval"] for search in searches)}}
                        save(lambda saved: trace)
                        yield search_event(len(searches) - 1, event["search"], trace["selected_evidence"])
                    elif "answering" in event:
                        generation = dict(GENERATING)
                        trace = {**trace, "answer_context": event["answering"], "generation": generation}
                        save(lambda saved: trace)
                    elif "delta" in event:
                        generation["text"] += event["delta"]
                        save(lambda saved: {**saved, "generation": generation})
                        yield encode_event("delta", text=event["delta"])
                    elif "result" in event or "generation" in event:
                        generation = (completed_answer(event["result"], trace["selected_evidence"], streamed_text=generation["text"])
                                      if "result" in event else event["generation"])
                        trace = {**trace, "generation": generation}
                        save(lambda saved: trace)
                        yield encode_event("done", generation=generation, trace=trace)
                        return
                if provider_status(provider)["status"] == "ready":
                    raise ValueError("The agent ended without an answer")
                # No ready provider: the typed text was searched as-is and no answer is generated.
                generation = provider_status(provider)
                trace = {**trace, "answer_context": freeze_answer_context([search["query"] for search in searches], turns),
                         "generation": generation}
                save(lambda saved: trace)
                yield encode_event("done", generation=generation, trace=trace)
            except StreamStopped:
                trace = store.get_turn(conversation_id, turn_id)["trace"]
                yield encode_event("done", generation=trace["generation"], trace=trace)
            except (asyncio.CancelledError, NodeCancelledError) as exc:
                finish({**generation, "status": "cancelled", "message": "Connection closed. Partial output is incomplete.", "citations": []})
                if isinstance(exc, NodeCancelledError):
                    # LangGraph reports a model call cancelled inside the graph as NodeCancelledError.
                    raise asyncio.CancelledError() from exc
                raise
            except Exception as exc:
                finish({**generation, "status": "failed", "message": failure_message(exc), "citations": []})
                trace = store.get_turn(conversation_id, turn_id)["trace"]
                yield encode_event("done", generation=trace["generation"], trace=trace)
            finally:
                finish({**generation, "status": "cancelled", "message": "Answer connection ended. Partial output is incomplete.", "citations": []})
                active.pop((conversation_id, turn_id), None)
                if iterator is not None:
                    with anyio.CancelScope(shield=True):
                        with suppress(Exception, asyncio.CancelledError):
                            await iterator.aclose()
        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
