"""Deterministic LangChain chat model: the single model substitution point for tests.

No network traffic. Each model call consumes one scripted step (a list script) or asks a
responder (a callable script). A step is resolved against the `ModelCall`:

- `str`: assistant content; `dict`: JSON-encoded assistant content;
- `AIMessage`: returned as-is, including `tool_calls` (streamed as tool-call chunks);
- an exception instance: raised by the model;
- a callable taking the `ModelCall`: called, and its result resolved as a step;
- an async generator (from an `async def ...: yield` callable): streamed content fragments,
  which may sleep or raise between fragments. Streaming only.

Plain content streams in whitespace-delimited fragments and finishes with `finish_reason="stop"`.
"""
from dataclasses import dataclass, field
import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool


@dataclass
class ModelCall:
    messages: list[BaseMessage]
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def system(self):
        return next((m.content for m in self.messages if m.type == "system"), "")

    @property
    def source(self):
        """The JSON payload of the latest human message, or None when it is not JSON."""
        human = next((m for m in reversed(self.messages) if m.type == "human"), None)
        try:
            return json.loads(human.content) if human is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def session(self):
        return (self.kwargs.get("extra_headers") or {}).get("x-opencode-session")


class ScriptedChatModel(BaseChatModel):
    script: Any = None
    calls: list = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self.bind(tools=[convert_to_openai_tool(tool) for tool in tools], **kwargs)

    def _next_step(self, messages, kwargs):
        call = ModelCall(list(messages), {k: v for k, v in kwargs.items() if k != "run_manager"})
        self.calls.append(call)
        if callable(self.script):
            step = self.script
        else:
            if not self.script:
                raise AssertionError("Scripted chat model has no remaining steps")
            step = self.script.pop(0)
        while callable(step) and not isinstance(step, (BaseMessage, BaseException)):
            step = step(call)
        if isinstance(step, BaseException):
            raise step
        return step

    @staticmethod
    def _message(step):
        if isinstance(step, AIMessage):
            return step
        if isinstance(step, dict):
            step = json.dumps(step)
        if isinstance(step, str):
            return AIMessage(content=step, response_metadata={"finish_reason": "stop"})
        raise TypeError(f"Unsupported scripted step for a complete response: {step!r}")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self._message(self._next_step(messages, kwargs)))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        step = self._next_step(messages, kwargs)
        if hasattr(step, "__aiter__"):
            async for fragment in step:
                yield ChatGenerationChunk(message=AIMessageChunk(content=fragment))
            yield ChatGenerationChunk(message=AIMessageChunk(content="", response_metadata={"finish_reason": "stop"}))
            return
        message = self._message(step)
        content = message.content if isinstance(message.content, str) else ""
        for fragment in (part for part in re.split(r"(\s+)", content) if part):
            yield ChatGenerationChunk(message=AIMessageChunk(content=fragment))
        chunks = [tool_call_chunk(name=call["name"], args=json.dumps(call["args"]), id=call.get("id"), index=index)
                  for index, call in enumerate(message.tool_calls)]
        yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=chunks,
                                                         response_metadata=message.response_metadata or {"finish_reason": "stop"}))


def search_call(*queries):
    """A scripted assistant turn that calls `search_cards` once per query."""
    return AIMessage(content="", tool_calls=[{"name": "search_cards", "args": {"query": query}, "id": f"call-{index}"}
                                            for index, query in enumerate(queries)],
                     response_metadata={"finish_reason": "tool_calls"})


def offers_tools(call):
    """Whether this model call is the agent choosing a search (tools offered) rather than the answer call."""
    return bool(call.kwargs.get("tools"))


DONE_SEARCHING = "Done searching."
"""A scripted agent turn without tool calls: the model stops searching, and the answer call follows."""


def has_searched(call):
    """Whether this message's searches already ran (the model call carries tool results)."""
    return any(message.type == "tool" for message in call.messages)


def search_once(responder):
    """Wrap a responder so each message searches once: later tool-offering calls stop searching."""
    def respond(call):
        if offers_tools(call) and has_searched(call):
            return DONE_SEARCHING
        return responder(call)
    return respond


def searching(answer, query=None):
    """A responder for any number of messages: search once (`query(call)`, default the typed question), then answer.

    `answer` is a scripted step (or a responder) for the answer call.
    """
    def respond(call):
        if offers_tools(call):
            return search_call(query(call) if query else call.source["question"])
        return answer
    return search_once(respond)
