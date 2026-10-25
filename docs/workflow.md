# GitHub issue workflow

GitHub Issues is the source of truth for requests, specifications, and implementation work in this repository. The workflow is inspired by [Matt Pocock's engineering skills](https://github.com/mattpocock/skills).

## From design to implementation

1. Clarify the goal and record accepted domain terminology and architectural trade-offs.
2. Capture a feature specification as a parent GitHub issue, referring to the relevant design documentation and ADRs.
3. Propose small implementation issues. Each should deliver a demonstrable path through the relevant storage, backend, and interface layers, with observable acceptance criteria.
4. Review issue scope and dependencies before publishing the implementation breakdown. Use GitHub sub-issues and native blocking relationships where available; otherwise include parent and blocking issue links in the body.
5. Implement one ready issue in a focused branch. Validate behavior at the highest practical application boundary, using deterministic substitutes for remote providers where appropriate.
6. Open a pull request linking the issue, describe the behavior and validation, and close the issue when the change lands.

Research uncertainties, such as provider suitability or dataset export compatibility, should be explicit prerequisites for the work they block. Keep unresolved questions visible rather than treating them as accepted implementation facts.

## Implementation handoff

Before reporting implementation complete or marking a PR ready for review:

1. Review each acceptance criterion against implementation and verification evidence. Check only satisfied criteria; a recorded limitation is not proof of live-provider support. Keep unfinished criteria unchecked and explain each one inline with `Blocked: <reason>` or `Deferred: <agreed decision or follow-up>`. Deferral requires agreement in the spec or with the user. A blocked required criterion means the spec is only partially implemented, even if the audit passes.
2. Give each open closing issue an `## Implementation status` section linking the implementing PR. State whether the change is implemented, awaiting merge, or limited by an external prerequisite. Include a `## Verification evidence` section with links to test results, source, or documentation. The existing inline `Implementation and verification evidence: ...` format is also accepted.
3. Change the current triage role to `ready-for-human` when implementation is handed over for review or a documented human decision. Preserve unrelated labels and remove stale triage roles. Keep issues open until the change lands.
4. Run the read-only audit from the repository root, including while the PR is still a draft:

   ```powershell
   uv run --python 3.11 python scripts/check_issue_handoff.py --pr 13
   ```

   Replace `13` with the actual PR number. The command follows GitHub's native closing references, reads issue bodies/labels, and reports missing PR/status/evidence, stale or conflicting triage roles, and unexplained unchecked criteria. Exit codes are 0 for a structurally complete handoff, 1 for findings, and 2 when data cannot be obtained or parsed. `--json` emits a machine-readable report; `--snapshot <file>` checks saved `{pr, issues}` JSON without network access. No issue, label, checkbox, or PR is changed by the audit.
5. Resolve the findings, mark the PR ready, and rerun the audit to verify the actual review-ready state. Report any publication blocker or incomplete requirement explicitly.

An issue can use this handoff structure:

```markdown
## Implementation status
Ready for human review in [PR #13](https://github.com/George713/magic-rag/pull/13); not merged yet.

## Verification evidence
- [Implementation and verification notes](https://github.com/George713/magic-rag/blob/<commit>/docs/running.md)

## Acceptance criteria
- [x] Verified behavior, supported by the evidence above.
- [ ] Run the approved live-provider smoke. **Blocked:** awaiting workload approval and credentials.
```

The audit checks handoff structure, not the truth of implementation claims or whether a limitation is acceptable. The implementer and reviewer still assess those individually.

For multi-ticket execution, invoke the repository-local `$magic-rag-implement-spec` (UI label **Magic RAG: Implement Spec**). Its [coordination reference](agents/implementation.md) defines ownership and merge handoffs; global skills remain unchanged.

## Issue content

Each implementation issue should explain:

- The user-visible behavior it delivers and why it matters.
- The parent specification and any blocking issues.
- Observable acceptance criteria, including important failure cases.
- The relevant design decisions and any unresolved prerequisites.

GitHub remains the tracker; repository documents provide stable context rather than a competing task list. [Specification #1](https://github.com/George713/magic-rag/issues/1) links the published implementation issues and their native blocking relationships.

## Current planning references

- [Accepted architecture](design.md)
- [Domain vocabulary](../GLOSSARY.md)
- [Architecture decisions](adr/)
