# Agent instructions

## Agent skills

Project skills live in [.agents/skills](.agents/skills), vendored from [Matt Pocock's skills](https://github.com/mattpocock/skills) (see [UPSTREAM.md](.agents/skills/UPSTREAM.md)). `.claude/skills` is a symlink to the same folder for Claude Code.

### Issue tracker

Track specifications and implementation issues in GitHub Issues. Before creating, reading, or updating work items, read [the tracker conventions](docs/agents/issue-tracker.md).

### Triage labels

Use the five configured triage roles when classifying issues. Read [the role mapping](docs/agents/triage-labels.md) before changing triage labels.

### Domain docs

This repository has one domain context. Before exploring domain behavior or proposing changes, read [the domain documentation rules](docs/agents/domain.md).
