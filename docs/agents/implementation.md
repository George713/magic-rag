# Implementation coordination

The repository-local `$implement-spec` adapts the integration-branch workflow for this project's shared application files and GitHub tracker. Use these rules when coordinating its workers.

## Ownership before parallelism

Read the ticket graph and planned changes before dispatch. Files such as `backend/magic_rag/app.py`, `web/src/routes/+page.svelte`, and lockfiles often participate in several tickets. Give every shared file one active owner. When ready tickets require the same file, sequence those edits or land the shared interface/registration hook first, then let workers implement separate modules, components, and tests against it. Make the ownership explicit; separate worktrees alone do not prevent overlapping changes.

Keep a temporary run record in `.scratch/implementation/<spec>/run.md` with the integration branch and baseline, ticket/dependency pointers, worker identities, worktree/branch paths, owned files, contract/research pointers, and integrated commits. Update it when ownership or integration state changes. This is coordination state, not a second backlog.

## Worker handoffs

Dispatch only tickets whose prerequisite implementations are verified on the integration branch. Each worker receives pointers and its ownership boundary, rather than copied issue bodies and repository-wide instructions. New file ownership needs an explicit handoff before another worker edits that file.

Create each worker branch from the current integration tip and verify its base before implementation. Preserve existing user changes; use a fresh worktree instead of resetting unrelated work. Before reporting done, synchronize with the latest integration tip once, resolve integration effects, and run the affected checks. A completion message contains the ticket, branch/commit, validation outcomes, and blockers; detailed notes stay at their context pointers.

Use background workers for genuinely independent ready work. Reuse idle workers for subsequent tickets, conflict resolution, and review when agent slots are limited. When only one ready ticket needs work, the integration owner can implement it without creating idle specialist roles.

## One merge queue

Only the integration owner mutates the integration worktree. Consume completion notifications, merge one branch at a time, verify affected application behavior, then release newly ready tickets. Clean merges are routine controller work; delegate conflicts to a worker with pointers to both contracts and commits. Other workers stay in their own worktrees until their handoff is integrated.

Wait on agent completion notifications or tool continuation results. Use an idle interval for independent useful work, rather than fixed sleep-and-Git-status polling. Keep progress messages about phase changes, findings, or blockers.

## Shared caches, isolated environments

Use one stable absolute `UV_CACHE_DIR` such as the main checkout's ignored `.uv-cache`, outside disposable worker worktrees. Keep each worktree's virtual environment separate so its editable package resolves to that worker's code. Reuse the existing model cache; record its location in the run notes instead of downloading weights per ticket. Keep full-corpus imports and benchmarks in background processes and preserve their database/report paths outside worktrees before cleanup.

## Review and handoff

Review against the baseline recorded at the start. Reuse available workers for the standards/spec review, and use one fix worker for all findings. The [implementation handoff](../workflow.md#implementation-handoff) defines the GitHub completion criterion and audit; an integrated commit alone does not finish the handoff. Closing issues remains a consequence of landing the PR, not a way to unblock the local dependency graph.
