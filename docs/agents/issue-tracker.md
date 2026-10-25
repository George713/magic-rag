# Issue tracker: GitHub

Specifications and implementation issues live in [George713/magic-rag](https://github.com/George713/magic-rag/issues). Use the `gh` CLI for tracker operations; infer the repository from the Git remote.

- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open --json number,title,labels`.
- Create: write the exact body to a temporary UTF-8 file, then run `gh issue create --title "..." --body-file <path>`.
- Apply or remove a triage label with `gh issue edit <number> --add-label <label>` or `--remove-label <label>` using the configured mapping.
- Use parent/sub-issue relationships for a spec and its implementation slices. Record blockers through native issue dependencies where available; otherwise include `Part of #<parent>` and `Blocked by: #<number>` in the issue body.
- Keep implementation issues demonstrable and scoped to a focused session. See [the workflow](../workflow.md).
- Before handing implementation to human review, follow the [handoff completion criterion and read-only audit](../workflow.md#implementation-handoff).

**PRs as a request surface: no.** Pull requests implement tracked work; external PRs are not automatically treated as requests in the triage queue.
