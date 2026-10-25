"""Persisted answer streams attached to the exact evidence of a saved turn."""
import json
import asyncio
from contextlib import suppress

import anyio

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .providers import AnswerPayload, generate_answer, provider_status


class StreamStopped(Exception):
    pass


async def next_until_stopped(iterator, stopped):
    pending = asyncio.create_task(anext(iterator))
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
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
            with suppress(asyncio.CancelledError):
                await cancellation


def encode_event(event, **data):
    return json.dumps({"event": event, **data}) + "\n"


def register_streaming(app, store, provider):
    store.recover_interrupted_answers()
    active = {}

    @app.post("/api/conversations/{conversation_id}/turns/{turn_id}/cancel")
    async def cancel(conversation_id: str, turn_id: str):
        turn = store.get_turn(conversation_id, turn_id)
        generation = turn["trace"]["generation"]
        if turn["state"] == "generating":
            generation = {**generation, "status": "cancelled", "message": "Answer stopped. Partial output is incomplete.", "citations": []}
            store.update_generation(conversation_id, turn_id, generation, expected_states={"generating"})
            stopped = active.get((conversation_id, turn_id))
            if stopped is not None:
                stopped.set()
        return store.get_turn(conversation_id, turn_id)["trace"]["generation"]

    @app.post("/api/conversations/{conversation_id}/turns/{turn_id}/stream")
    async def stream(conversation_id: str, turn_id: str):
        turn = store.get_turn(conversation_id, turn_id)
        generation = {"status": "generating", "message": "Generating from selected evidence.", "text": "", "citations": []}
        if not store.update_generation(conversation_id, turn_id, generation, expected_states={"retrieval_complete"}):
            raise HTTPException(409, "This turn already has an answer state. Submit another question.")
        stopped = asyncio.Event()
        active[(conversation_id, turn_id)] = stopped

        async def events():
            nonlocal generation
            evidence = turn["trace"]["selected_evidence"]
            iterator = None
            try:
                yield encode_event("start", generation=generation)
                if provider_status(provider)["status"] != "ready" or not evidence:
                    generation = generate_answer(provider, turn["question"], evidence, conversation_id)
                    store.update_generation(conversation_id, turn_id, generation, expected_states={"generating"})
                    yield encode_event("done", generation=generation)
                    return
                iterator = provider.stream_answer(turn["question"], evidence, conversation_id).__aiter__()
                while True:
                    try:
                        event = await next_until_stopped(iterator, stopped)
                    except StopAsyncIteration:
                        raise ValueError("Stream ended without a validated answer")
                    if "delta" in event:
                        generation["text"] += event["delta"]
                        if not store.update_generation(conversation_id, turn_id, generation, expected_states={"generating"}):
                            raise StreamStopped()
                        yield encode_event("delta", text=event["delta"])
                    elif "result" in event:
                        result = AnswerPayload.model_validate(event["result"])
                        cards = {card["card_id"]: card for card in evidence}
                        if result.text != generation["text"] or (not result.insufficient_evidence and not result.citations):
                            raise ValueError("Incomplete or uncited answer")
                        generation = {"status": "completed", "message": "Answer grounded in selected card evidence.",
                                      "text": result.text, "insufficient_evidence": result.insufficient_evidence,
                                      "citations": [{"card_id": card_id, "name": cards[card_id]["name"]} for card_id in dict.fromkeys(result.citations)]}
                        if not store.update_generation(conversation_id, turn_id, generation, expected_states={"generating"}):
                            raise StreamStopped()
                        yield encode_event("done", generation=generation)
                        return
            except StreamStopped:
                generation = store.get_turn(conversation_id, turn_id)["trace"]["generation"]
                yield encode_event("done", generation=generation)
            except asyncio.CancelledError:
                generation = {**generation, "status": "cancelled", "message": "Connection closed. Partial output is incomplete.", "citations": []}
                store.update_generation(conversation_id, turn_id, generation, expected_states={"generating"})
                raise
            except Exception:
                generation = {**generation, "status": "failed", "message": "Answer stream failed or ended unexpectedly. Check the provider or connection and submit another question. Retrieved evidence is preserved.", "citations": []}
                store.update_generation(conversation_id, turn_id, generation, expected_states={"generating"})
                yield encode_event("done", generation=generation)
            finally:
                store.update_generation(conversation_id, turn_id,
                    {**generation, "status": "cancelled", "message": "Answer connection ended. Partial output is incomplete.", "citations": []}, expected_states={"generating"})
                active.pop((conversation_id, turn_id), None)
                if iterator is not None:
                    with anyio.CancelScope(shield=True):
                        with suppress(Exception, asyncio.CancelledError):
                            await iterator.aclose()
        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
