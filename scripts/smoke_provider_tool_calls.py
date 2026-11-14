"""Manual live check: does the configured provider return tool calls through LangChain?

Sends one tool-calling request (and one streamed repeat) to the provider configured by the
MAGIC_RAG_PROVIDER_* variables, using LangChain's OpenAI-compatible chat model with a single
card-search tool. Reports the returned tool call or a clear failure. Never prints credentials.

This is not part of the automated checks: it calls a paid remote model.

    uv run python scripts/smoke_provider_tool_calls.py [--env-file PATH] [--no-stream]
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
import uuid


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "MAGIC_RAG_PROVIDER_"
USER_AGENT = "magic-rag/0.1"
QUESTION = "I'm looking for a red instant that deals 3 damage to a creature. Search the card database for it."
SYSTEM = ("You help players find Magic: The Gathering cards. Use the search_cards tool to search the "
          "card database before answering.")


def read_env_file(path):
    """Read KEY=VALUE lines; process environment variables take precedence."""
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[key] = value
    for key in ("URL", "MODEL", "API_KEY", "SUITABILITY_CONFIRMED"):
        if os.environ.get(PREFIX + key):
            values[PREFIX + key] = os.environ[PREFIX + key]
    return values


class Refusal(Exception):
    pass


def config_from(values):
    url = values.get(PREFIX + "URL", "").strip()
    model = values.get(PREFIX + "MODEL", "").strip()
    key = values.get(PREFIX + "API_KEY", "").strip()
    if not all((url, model, key)):
        raise Refusal("Set MAGIC_RAG_PROVIDER_URL, MAGIC_RAG_PROVIDER_MODEL, and MAGIC_RAG_PROVIDER_API_KEY.")
    if values.get(PREFIX + "SUITABILITY_CONFIRMED", "").strip().lower() != "true":
        raise Refusal("Refusing to send requests: MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED is not 'true'. "
                      "Confirm workload suitability with the provider first.")
    parsed = urlparse(url)
    loopback = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.username or parsed.password or parsed.query or not parsed.hostname or not (parsed.scheme == "https" or loopback):
        raise Refusal("MAGIC_RAG_PROVIDER_URL must be an HTTPS chat-completions endpoint without embedded credentials.")
    # The application stores the full chat-completions endpoint; LangChain wants the API base.
    base_url = url.rstrip("/").removesuffix("/chat/completions")
    return base_url, model, key


def build_model(base_url, model, key):
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    @tool
    def search_cards(query: str) -> str:
        """Search the Magic card database. `query` is a search string describing the cards wanted."""
        return "[]"

    # OpenCode Go's client guidance asks for an application user agent and a stable per-conversation
    # session ID; requests without x-opencode-session are rejected with HTTP 400.
    headers = {"User-Agent": USER_AGENT, "x-opencode-session": str(uuid.uuid4())}
    chat = ChatOpenAI(model=model, base_url=base_url, api_key=key, max_retries=0, timeout=120, temperature=0,
                      default_headers=headers)
    return chat.bind_tools([search_cards])


def check_tool_calls(tool_calls, invalid_tool_calls):
    """Return (ok, summary) for the tool calls of one response."""
    if invalid_tool_calls:
        return False, f"malformed tool calls: {json.dumps(invalid_tool_calls, default=str)[:500]}"
    if not tool_calls:
        return False, "no tool call returned"
    problems = []
    for call in tool_calls:
        if call.get("name") != "search_cards":
            problems.append(f"unexpected tool name {call.get('name')!r}")
        query = (call.get("args") or {}).get("query")
        if not isinstance(query, str) or not query.strip():
            problems.append(f"missing query string in args {call.get('args')!r}")
        if not call.get("id"):
            problems.append("tool call has no id")
    summary = "; ".join(f"{c.get('name')}({json.dumps(c.get('args'))}) id={'yes' if c.get('id') else 'no'}" for c in tool_calls)
    return not problems, summary + ("" if not problems else " -- " + "; ".join(problems))


def run(bound, stream):
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(SYSTEM), HumanMessage(QUESTION)]
    if not stream:
        message = bound.invoke(messages)
    else:
        message, chunks = None, 0
        for chunk in bound.stream(messages):
            chunks += 1
            message = chunk if message is None else message + chunk
        if message is None:
            return False, "stream produced no chunks", ""
        print(f"  stream chunks received: {chunks}")
    ok, summary = check_tool_calls(message.tool_calls, getattr(message, "invalid_tool_calls", []))
    meta = message.response_metadata or {}
    detail = f"finish_reason={meta.get('finish_reason')!r} model={meta.get('model_name')!r}"
    text = message.content if isinstance(message.content, str) else json.dumps(message.content)
    if text.strip():
        detail += f" text={text.strip()[:200]!r}"
    return ok, summary, detail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--no-stream", action="store_true", help="skip the streamed tool-call check")
    args = parser.parse_args(argv)
    try:
        base_url, model, key = config_from(read_env_file(args.env_file))
    except Refusal as error:
        print(error, file=sys.stderr)
        return 2

    print(f"Provider host: {urlparse(base_url).hostname}  model: {model}")
    bound = build_model(base_url, model, key)
    results = []
    for stream in ([False] if args.no_stream else [False, True]):
        label = "streamed" if stream else "non-streamed"
        print(f"{label} request:")
        try:
            ok, summary, detail = run(bound, stream)
        except Exception as error:  # report any provider/client failure clearly, without credentials
            message = f"{type(error).__name__}: {error}".replace(key, "[redacted]")
            ok, summary, detail = False, "request failed", message[:500]
        print(f"  {'PASS' if ok else 'FAIL'}: {summary}")
        if detail:
            print(f"  {detail}")
        results.append(ok)
    print("RESULT:", "tool calls returned well-formed" if all(results) else "tool calls did NOT work reliably")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
