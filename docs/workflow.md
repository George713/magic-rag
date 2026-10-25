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
