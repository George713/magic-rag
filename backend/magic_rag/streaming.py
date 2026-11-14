"""One streamed request per message: its searches, the answer as it is written, then the saved result.

The response is newline-delimited JSON. Events, in order:

- `start`: the saved in-progress turn (`trace`, with `conversation_id` and `turn_id`);
- `search`: one per completed search, in order (`index`, `query`, `card_count`, `top_cards`, and the
  full search record as `search`, i.e. its retrieval details);
- `delta`: answer text fragments;
- `done`: the final `generation` (validated answer, failure, cancellation, or provider status) and the
  saved `trace`.
"""
import json
import asyncio
from contextlib import suppress
from time import perf_counter
from uuid import uuid4

import anyio

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .providers import completed_answer, generate_answer, provider_status
from .retrieval import combined_evidence
from .rewriting import conversation_context, freeze_answer_context, rewrite_query

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


def search_event(index, search):
    evidence = search["selected_evidence"]
    return encode_event("search", index=index, query=search["query"], card_count=len(evidence),
                        top_cards=[{"card_id": card["card_id"], "name": card["name"]} for card in evidence[:TOP_CARDS]],
                        search=search)


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
            "searches": [], "selected_evidence": [], "timings_ms": {}, "rewrite": None,
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
                start = perf_counter()
                query, rewrite = await until_stopped(
                    rewrite_query(provider, request.question, conversation_context(turns), conversation_id), stopped)
                corpus, searches = await until_stopped(anyio.to_thread.run_sync(
                    retrieve, [query], mode, filters, request.settings, abandon_on_cancel=True), stopped)
                evidence = combined_evidence(searches)
                context = freeze_answer_context(query, turns)
                ready = provider_status(provider)["status"] == "ready"
                generation = dict(GENERATING) if ready and evidence else generate_answer(provider, request.question, evidence, conversation_id, context=context)
                trace = {**trace, "corpus": corpus, "searches": searches, "selected_evidence": evidence,
                         "timings_ms": {"rewrite": rewrite["elapsed_ms"], "retrieval": (perf_counter() - start) * 1000},
                         "rewrite": rewrite, "answer_context": context, "generation": generation}
                save(lambda saved: trace)
                for index, search in enumerate(searches):
                    yield search_event(index, search)
                if generation["status"] != "generating":
                    yield encode_event("done", generation=generation, trace=trace)
                    return
                iterator = provider.stream_answer(request.question, evidence, conversation_id, context=context).__aiter__()
                while True:
                    try:
                        event = await until_stopped(anext(iterator), stopped)
                    except StopAsyncIteration:
                        raise ValueError("Stream ended without a validated answer")
                    if "delta" in event:
                        generation["text"] += event["delta"]
                        save(lambda saved: {**saved, "generation": generation})
                        yield encode_event("delta", text=event["delta"])
                    elif "result" in event:
                        generation = completed_answer(event["result"], evidence, streamed_text=generation["text"])
                        save(lambda saved: {**saved, "generation": generation})
                        trace = {**trace, "generation": generation}
                        yield encode_event("done", generation=generation, trace=trace)
                        return
            except StreamStopped:
                trace = store.get_turn(conversation_id, turn_id)["trace"]
                yield encode_event("done", generation=trace["generation"], trace=trace)
            except asyncio.CancelledError:
                finish({**generation, "status": "cancelled", "message": "Connection closed. Partial output is incomplete.", "citations": []})
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
