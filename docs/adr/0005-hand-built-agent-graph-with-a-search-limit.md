# Hand-build the card-search agent graph with a search limit, no checkpointer, and no sub-agents

The model writes its own card searches through a hand-built LangGraph `StateGraph`. It has two nodes: `agent`, which is the chat model with one `search_cards(query)` tool, and `search`, which runs the application's retrieval. Conditional edges route each search back to the agent, and after at most three searches per message the tool is no longer offered. The application keeps the parts the model must not control: it applies the player's explicit filters and search mode to every search, caps the combined evidence, and writes the answer in a separate request without tools. The SQLite conversation store remains the only record of conversation state, so the graph has no checkpointer. It runs fresh for each message with bounded context from the last six completed turns. There are no sub-agents, because one bounded loop over one tool gains nothing from them.

## Considered Options

- **Prebuilt ReAct agent (`create_react_agent`).** Less code, but its loop runs until the model stops calling tools. Enforcing the search limit would mean recursion-limit errors or wrapper hooks, and the separate tool-free answer request, the no-provider path, and the custom per-search stream events would all have to be worked around the prebuilt structure. With two nodes the hand-built graph is about as short and states the limit directly.
- **Keep the fixed pipeline with a rewrite call.** This was the previous design: one search per message, and a model-written query only for follow-ups. It can't retry weak wording or look up each card being compared. It is not kept as a selectable mode.
- **LangGraph checkpointer (SQLite saver).** It would persist graph state between messages and allow resuming. Nothing needs resuming: there are no human-in-the-loop interrupts, and Stop deletes the turn. A second copy of conversation state could drift from the conversation store, which already holds every saved turn and its searches.
- **Sub-agents (for example, one searcher per compared card).** They add coordination and extra model calls. A single agent can already search once per card within the limit.
- **Letting the model set filters or the search mode through tool arguments.** Rejected. The player's explicit constraints must hold for every search, so the tool takes only a query string.

## Consequences

- A message with N searches makes N + 2 model calls below the limit: N tool calls, one reply without a tool call that ends searching, and the answer. At the limit it makes 4: three tool calls and the answer. With no evidence, no answer call is made.
- Tool calls and the JSON response format are never combined in one request, because no provider has been verified to combine them.
- Raising the search limit or adding tools is a graph change, not a configuration change. Adding resumable runs would mean revisiting the no-checkpointer decision.
