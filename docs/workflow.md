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
2. Complete [blocker reconciliation](#github-blocker-reconciliation) for all closing issues. Give each open closing issue an `## Implementation status` section linking the implementing PR. State whether the change is implemented, awaiting merge, or limited by an external prerequisite. Include a `## Verification evidence` section with links to test results, source, or documentation. The existing inline `Implementation and verification evidence: ...` format is also accepted.
3. Change the current triage role to `ready-for-human` when implementation is handed over for review or a documented human decision. Preserve unrelated labels and remove stale triage roles. Keep issues open until the change lands.
4. Run the read-only audit from the repository root, including while the PR is still a draft:

   ```powershell
   uv run --python 3.11 python scripts/check_issue_handoff.py --pr 13
   ```

   Replace `13` with the actual PR number. The command follows GitHub's native closing references, reads issue bodies/labels and every page of native blockers, and reports missing PR/status/evidence, stale or conflicting triage roles, unexplained unchecked criteria, and unreconciled blockers. Native relationships and active `Blocked by: #<number>` or issue-URL entries in the body require reconciliation. Code-fenced examples are ignored. Exit codes are 0 for a structurally complete handoff, 1 for findings, and 2 when data cannot be obtained or parsed. `--json` emits a machine-readable report; `--snapshot <file>` checks saved `{pr, issues}` JSON without network access. Each open issue in an offline snapshot must include `blockedBy`, a complete array of native blocker objects with `url` (plus `number` and `state` in live exports), or `[]` after a successful empty read. Missing or invalid dependency data fails rather than being interpreted as no blockers. No issue, label, checkbox, or PR is changed by the audit.
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

For multi-ticket execution, invoke the repository-local `$implement-spec` (UI label **Implement Spec (repo version)**). Its [coordination reference](agents/implementation.md) defines ownership and merge handoffs; global skills remain unchanged.

## GitHub blocker reconciliation

An implementation dependency becomes satisfied when the prerequisite's code is integrated and the affected checks pass. Issue closure records landing the PR. Keep those transitions separate.

The integration owner performs this sequence after each verified integration and again before handoff:

1. Read the prerequisite's native outgoing dependencies with `gh api --paginate repos/OWNER/REPO/issues/PREREQUISITE/dependencies/blocking`. Inspect downstream issue bodies for fallback `Blocked by:` references as well.
2. Assess each relationship against the integrated commit and verification evidence. A checked acceptance list, shared PR, triage label, or open/closed state alone does not prove that a prerequisite was implemented. Preserve genuine unresolved requirements, including external prerequisites.
3. Remove each satisfied native relationship using `gh api --method DELETE repos/OWNER/REPO/issues/DEPENDENT/dependencies/blocked_by/PREREQUISITE_ID`. `PREREQUISITE_ID` is the numeric API issue ID from `gh api repos/OWNER/REPO/issues/PREREQUISITE`, not its issue number. Update fallback body references to remove satisfied prerequisites. Preserve historical implementation links, parent/sub-issue links, unrelated labels, and open issue state.
4. Read each affected issue's `dependencies/blocked_by` endpoint and body again. Confirm the satisfied relationships are absent. Document every remaining relationship in that issue's `## Remaining blockers` section, one canonical issue URL and specific reason per line:

   ```markdown
   ## Remaining blockers
   - https://github.com/OWNER/REPO/issues/7: Required provider approval is still outstanding.
   ```

   The audit matches each active relationship to its own reason; an unrelated limitation or checkbox explanation cannot waive another relationship. An unresolved required criterion remains unchecked with its inline `Blocked:` explanation as well. An explained blocker permits an accurate partial handoff, not a claim of complete implementation. Reasons are assessed by the implementer/reviewer; the audit checks their presence, not their truth.
5. Record the integrated commit, affected relationships, verification, and fresh-read result in the existing temporary run record. Report update/read failures as incomplete reconciliation. The integration step finishes only when GitHub reflects the verified implementation state.

## Automated checks

`.github/workflows/checks.yml` runs the backend suite (including audit CLI regression tests), frontend type checks, and production build on PRs and pushes to `main`.

`.github/workflows/issue-handoff.yml` audits open PRs and publishes an **Issue handoff** commit status on each PR head. It runs after PR updates and issue edits/state/label changes, supports manual dispatch, and schedules a recheck every 15 minutes. GitHub exposes native dependency changes through an [`issue_dependencies` webhook](https://docs.github.com/en/webhooks/webhook-events-and-payloads#issue_dependencies), which is not in its [supported Actions triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows). The schedule covers native-only relationship changes; GitHub may delay scheduled runs. An external webhook integration can request an immediate recheck through `repository_dispatch` with event type `issue_dependencies`; that external integration is not provisioned by this repository.

To request a recheck after reconciliation:

```powershell
gh workflow run issue-handoff.yml
```

The handoff workflow runs trusted default-branch tooling with issue/PR read permissions and commit-status write permission. It never runs PR-head code with that token and never changes issues or removes blockers automatically. Missing data and API failures publish an error status; handoff findings publish failure. Ordinary PR checks run with read-only permissions.

Issue-event/scheduled/manual handoff automation becomes available after the workflow and updated audit land on the default branch. Requiring the published statuses for merge is a separate branch-protection setting; the workflow does not change repository protection rules.

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
