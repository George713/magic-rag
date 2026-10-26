---
name: grilling
description: "Repository-local design interview and handoff procedure for grill-me, grill-with-docs, and requests to be grilled."
---

# Grilling (repo version)

Interview the user relentlessly until you reach shared understanding. Map the problem as a **design tree**: each decision branches into the decisions that depend on it. This is the design stage of [the repository workflow](../../../docs/workflow.md#from-design-to-implementation).

## Interview rounds

Work the tree in rounds. The **frontier** contains every unresolved decision whose prerequisites are settled. Ask the whole frontier in one round, number each question, and give a recommended answer. Word each question so that "yes" accepts the recommendation. Then wait for the user's answers.

Use this format for each question:

```text
Q1 — <decision title>: <question and relevant choices>
Recommended: <specific answer and brief reason>
```

Recompute the frontier after every round. A question that depends on another unanswered question belongs in a later round. Challenge vague answers and contradictions with concrete scenarios. Include scope, constraints, important failure cases, and the behavior that would demonstrate success; mark intentional deferrals explicitly.

Finding facts is the agent's job. Inspect the repository, documentation, and existing behavior before asking the user for information available there. Use read-only exploration and isolated checks. When an environment fact needs independent exploration, dispatch a read-only subagent, and continue with decisions that do not depend on its result. Reserve implementation edits, operational data changes, and tracker/PR publication for their selected workflow stages. The with-docs entry point additionally records agreed domain documentation during the interview.

## Confirm shared understanding

When the frontier is empty, present a concise account of the goal, accepted behavior, scope, constraints, and explicitly deferred decisions. Ask **"Is this our shared understanding?"** as a separate round, and wait. Corrections reopen the affected branches.

Answers such as "yes" or "yes to all" settle the questions they answer. Agreement on the design completes the interview; it does not select an implementation or publication stage.

## Choose the next stage

After shared understanding is confirmed, ask which skill to use next:

- Recommend `$to-spec` for the usual path: `$to-spec` → `$to-tickets` → the repository-local `$implement-spec`.
- Offer `$implement` for a small, sufficiently scoped piece of work, or the repository-local `$implement-spec` when a specification and tickets already exist.
- The user may also finish the session at the accepted design.

Wait for an explicit next-stage choice before starting that skill. Ordinary language such as "implement this now" counts; a repeated design confirmation does not. If the user confirms the summary and explicitly selects the next skill in the same reply, follow that selection without asking again. An explicitly requested sequence can authorize multiple stages; the usual sequence alone does not.

Implementation invokes `code-review` itself. The user invokes `$retro` when they want a retrospective. Follow the selected skill's own completion criteria and any internal design or testing questions.
