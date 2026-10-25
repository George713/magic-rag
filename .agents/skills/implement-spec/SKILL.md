---
name: implement-spec
description: "Implement a Magic RAG specification and its GitHub tickets with coordinated worktrees and a verified issue handoff."
---

# Implement Spec (repo version)

Repository-local adaptation of Matt Pocock's `implement-spec` workflow. Keep one integration branch for the specification, use its ticket dependency graph, and finish with review-ready code and accurate GitHub issue status. Invoke this version as `$implement-spec` and select **Implement Spec (repo version)** in the UI. The repository pointer selects this local copy; the global skill remains unchanged.

1. Read the repository's [tracker conventions](../../../docs/agents/issue-tracker.md), the requested spec, and its implementation issues. Record the integration branch's starting commit as the review baseline. Resolve missing scope or dependencies before dispatching dependent work.
2. Plan ownership using [implementation coordination](../../../docs/agents/implementation.md). Establish the shared response/registration contracts before parallel edits to the same integration files. Store only temporary coordination state under `.scratch/implementation/`; GitHub remains the work tracker.
3. Implement the ready frontier. Give independent workers separate worktrees based on the integration branch, explicit file ownership, and pointers to the spec, ticket, contracts, and research. Apply `tdd` at the specification's agreed test boundaries; seek boundary agreement only when it is missing. Reuse available workers instead of allocating a new agent identity for every ticket. A small single-ticket frontier can be implemented directly.
4. Wait for completion messages and serialize merges through the integration owner. Merge clean completed branches directly; use a merger worker when conflict resolution needs implementation context. Run affected integration checks, record the integrated commit, and dispatch newly unblocked work. A dependency is satisfied by verified code on the integration branch, even while its GitHub issue remains open pending PR merge.
5. After the first implementation merge, open a draft PR if the repository workflow and current publication authorization call for one. Link the spec and tickets with closing references. Preserve visible external prerequisites rather than implying unverified integrations work.
6. Review the integration branch against the recorded baseline with `code-review`, covering both standards and the originating spec. Give all findings to one fix worker, then verify the fixes and relevant checks.
7. Complete the [implementation handoff](../../../docs/workflow.md#implementation-handoff). Assess each acceptance criterion, update issue evidence and review labels, and run `python scripts/check_issue_handoff.py --pr <number>` from the repository root. Fix audit failures before marking the PR ready, then rerun it after the ready transition. The audit is read-only and cannot decide whether a criterion is true.
8. Remove completed worker worktrees after their commits and artifacts are preserved. Report the integration branch, review-ready PR, checks, and remaining limitations. If publication or a prerequisite is blocked, report the concrete incomplete handoff instead of claiming completion.
