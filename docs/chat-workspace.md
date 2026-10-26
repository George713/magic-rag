# Conversational card workspace

Specification: [#15](https://github.com/George713/magic-rag/issues/15). Implementation: [PR #22](https://github.com/George713/magic-rag/pull/22), dependent on the original application in PR #13. Review baseline: `94254c8df10aa2990e212f59f85b418de599630d`.

The workspace uses a dark transcript between chat history and exact filters. Sending retrieves evidence and requests an answer automatically. Each turn owns its retrieval details and evidence targets. Current controls belong to the conversation; historical filter and image snapshots belong to their original turn.

Answers can contain text, selected card assets, or both. The model selects evidence card identities; the service resolves source imagery. It never accepts model-invented image URLs. Source-backed face images enlarge in a centered dialog. Legacy turns and unavailable images retain readable card evidence.

## Search modes, collapsed evidence, and legacy images

Follow-up [#23](https://github.com/George713/magic-rag/issues/23) adds a persisted current search mode alongside each conversation's current filters. The mode saves immediately, including unsent changes, through the same serialized preference-save queue. Switching chats waits for queued writes. New chats default to keyword; existing chats migrate from their latest turn's mode. Opening historical details never changes the current mode.

Retrieved evidence and Retrieval details are separate disclosures, both initially closed. Selected card assets remain visible beneath the answer. Inspector links reveal the matching evidence before fragment navigation. The answer citation and asset-name links originally added here are removed by specification #25 below. No-match guidance remains visible outside the disclosure.

The installed legacy corpus had 38,997 cards but no `card_images` rows. The latest completed answer had four selected card assets with empty image snapshots. This is a missing-metadata migration issue: current imports already retain imagery, but introducing the image table did not populate older corpora or saved turns. Deterministic browser fixtures had supplied image metadata and therefore did not expose the upgrade problem.

Run the explicit repair from the repository root:

```powershell
uv run python -m magic_rag repair-images
# Or reuse a downloaded Scryfall gzip JSONL export:
uv run python -m magic_rag repair-images --source path/to/oracle-cards.jsonl.gz
```

`POST /api/corpus/repair-images` provides the same operation at the backend API. Download and source-image extraction complete before an atomic transaction fills missing images/source links for active cards and saved evidence/assets, matched by canonical card identity. Existing image snapshots stay unchanged. Cards present only in saved history can also be repaired. Cards absent from the supplied source keep their readable evidence. No embedding model is loaded, and canonical text, FTS/vector indexes, corpus identity, answer content, and selected card identities are preserved. Failure rolls back the repair; rerunning it is safe. Repair is explicit and never triggers a startup download.

The local database was backed up to `data/cards-before-image-repair.db` and repaired on 2026-10-26: all 38,997 cards now have image metadata and all four assets in the latest saved answer have imagery. Comparison with the backup verified unchanged canonical card data, FTS and vector contents, corpus identity, and saved traces excluding presentation fields. A restored image URL returned HTTP 200 with JPEG content.

Verification for this follow-up: backend tests cover unsent mode preferences, restart independence, historical snapshots, legacy-mode migration, metadata repair of saved selections and future searches, repeat repair, unsafe URLs, download failure, and transaction rollback. Browser tests cover per-chat mode navigation/reload, independent historical details, collapsed evidence, correct-turn citation expansion/scrolling, visible assets, both faces, enlargement, reopening, and image-load failure.

Follow-up results: **192 backend tests passed, 2 optional real-model tests skipped; 22 browser tests passed** across the standard, workspace, chat, streaming, filters, rewriting, vector, hybrid, and reranking configurations. `npm run check` reports zero errors/warnings and `npm run build` passes. The checks use deterministic answer providers; the live-provider boundary described below is unchanged.

## Card rows and frameless enlargement

Specification [#25](https://github.com/George713/magic-rag/issues/25), tickets [#26](https://github.com/George713/magic-rag/issues/26) and [#27](https://github.com/George713/magic-rag/issues/27). Implementation: [PR #28](https://github.com/George713/magic-rag/pull/28), based on the existing chat follow-up branch in PR #24. Review baseline: `6779cbd62d4dab5c3dfe424ef00c92103db94af4`.

Answers omit the Sources navigation and duplicate linked names above selected images. All selected images, including both faces, appear in one row with 16px gaps, 210px thumbnails, and centered image-name captions. Horizontal scrolling stays inside the row. Focusing a thumbnail scrolls it fully into view for keyboard browsing. Assets without imagery retain a plain card name; image failures keep readable errors. Saved chats adopt the presentation without a data migration. Evidence and retrieval disclosures retain their content and default collapsed state.

The shared enlarged view uses a transparent, frameless modal over the darkened page. The centered name floats below the source image; a semi-transparent X overlays its top-right corner. Clicking any part of the view or pressing Escape closes it and restores focus to its originating thumbnail. The same viewer serves answer assets and Retrieved evidence. Source pixels and printed borders are preserved. Preview and enlarged images share proportional rounded clipping so opaque white padding outside rounded card corners stays hidden at every display size.

### Verification for specification #25

The existing deterministic browser chat seam covers the complete UI/service flow. No live provider request or corpus modification was made. The external image fixture is an illustrated 488 by 680 SVG with transparent corners and an opaque-white-corner mode for JPEG-style padding; it supplies representative proportions and contrast rather than real card artwork.

| Acceptance case | Verification |
| --- | --- |
| Removed Sources and linked headings; preserved response forms and Copy | Chat tests for automatic streaming/copy/follow-ups and assets-only/combined responses |
| One ordered row, both faces, gaps, centered captions | Multi-card desktop/mobile row test with image/caption geometry assertions |
| Readable thumbnails and contained overflow | 1100px and 390px viewport checks; no horizontal page overflow; keyboard reveals the complete later thumbnail; emulated mobile touch swipe scrolls the row |
| Single image without unnecessary scrolling | Ordinary source image/legacy asset browser test |
| Frameless transparent enlargement and retained backdrop | Viewer tests at 1440px and 390px; screenshots inspected for image/caption/control placement and darkening |
| X, image, caption, backdrop, Escape, keyboard close, focus return | Viewer dismissal tests for answers and evidence; immediate image-click test; repeated face opening |
| Preserved evidence/details and history | Closed disclosure checks, per-turn evidence access, saved answer reload and both-face reopening |
| Missing or failed images | Legacy plain-name fallback and unavailable-image scenarios with readable evidence |

Results on Windows, 2026-10-26: **13 chat/viewer browser tests passed; 4 streaming browser tests passed; 192 backend tests passed, 2 optional real-model tests skipped; frontend checks reported zero errors/warnings; production build passed**. Backend tests use a workspace-local temporary directory because the sandbox restricts the default OS pytest temp directory. Run `.venv/Scripts/python.exe -m pytest --basetemp .scratch/implementation/spec-25/pytest` from the repository root, and from `web` run `npx playwright test --config playwright.chat.config.ts`, `npx playwright test --config playwright.streaming.config.ts`, `npm run check`, and `npm run build`.

Visual evidence uses deterministic fixture imagery: [desktop row](images/spec-25/row-desktop.png), [mobile row after swipe](images/spec-25/row-mobile.png), [desktop viewer](images/spec-25/viewer-desktop.png), and [mobile viewer](images/spec-25/viewer-mobile.png). Row screenshots show a browsed position, including intentionally clipped neighboring cards. The older verification sections below describe their original implementation checkpoints; visible citation/asset-name links were superseded by #25.

Independent standards and specification reviews of `6779cbd...c7e9172` each reported zero findings. Both tickets have no incoming or outgoing blocking dependencies; fresh GitHub reads confirmed the empty graph after integration. The issues remain open pending PR merge.

A follow-up corner regression reproduced the reported white corners: a preview clipped the source padding while the unrounded enlargement exposed pure-white pixels (255 brightness). Shared proportional corner clipping fixes the difference without changing image URLs, adding a background, or processing source files. Desktop/mobile browser screenshot tests inspect the rendered corner area, allowing normal antialiasing while rejecting white padding. The updated viewer screenshots use that opaque-corner fixture.

## Pull request handoff verification

On 2026-10-26, PR #24 passed its backend and frontend checks but failed **Issue handoff** with `PR has no closing issue links`. Its description already contained `Closes #23`; GitHub returned an empty `closingIssuesReferences` list because the PR still targeted `implement/spec-15` rather than the default branch. PR #22 had already merged, so PR #24 was retargeted to `main`.

After retargeting, `python scripts/check_issue_handoff.py --pr 24 --json` passed with one checked issue (#23). This checks the issue's review label, implementation status, verification evidence, acceptance criteria, and native dependencies. The audit and application code required no changes. For future stacked PRs, preserve the prerequisite merge order and retarget to the default branch before the final handoff audit; a closing keyword on a non-default target does not establish the native link this audit requires.

PR #28 had the same failure while targeting `fix/chat-preferences-and-images`, despite its `Closes #25`, `Closes #26`, and `Closes #27` lines. Retargeting it to `main` restored all three native links; `python scripts/check_issue_handoff.py --pr 28 --json` then passed with three checked issues. Merge PR #24 before PR #28: until then, PR #28's comparison with `main` also includes the pending PR #24 changes. Neither PR was merged as part of this repair.

PR #28 subsequently merged first on 2026-10-26, bringing PR #24's application changes into `main` as well. Merging `main` back into PR #24 resolved the remaining conflict in this document by preserving the combined verification notes. The reconciled PR #24 differs from `main` only by this reconciliation note; its original application changes and PR #28's presentation changes are already integrated.

## Verification boundaries

FastAPI tests use real temporary SQLite, FTS5, and sqlite-vec with deterministic external embedding, reranking, source, and provider substitutes. Browser tests run SvelteKit and FastAPI; images and model responses are deterministic. These checks do not establish live OpenCode Go support. Workload suitability and credentials remain unresolved; no live model request or paid fallback is used.

API coverage is in `backend/tests/test_conversations.py`, `test_filters.py`, `test_corpus.py`, `test_generation.py`, `test_streaming.py`, and `test_answer_context.py`. Browser verification and acceptance assessment are recorded below after integration.

## Acceptance assessment

| Spec case | Evidence |
| --- | --- |
| 1: dark desktop workspace and narrow side panels | `workspace.spec.ts`, `search.spec.ts`; desktop/mobile screenshots inspected |
| 2: automatic ordered streaming, follow-ups, Stop and Copy | `chat.spec.ts`, `streaming.spec.ts`, `test_streaming.py`, `test_answer_context.py` |
| 3: Legendary eligibility, exact-name restriction, and clearing | `filters.spec.ts`, `test_filters.py` across all four modes |
| 4: exact color set, all card types, colorless and inclusive mana | `filters.spec.ts`, `test_filters.py` |
| 5: independent current filters, unsent edits and restarts | `workspace.spec.ts`, `test_conversations.py` using restarted services |
| 6: immutable historical filters without restoring controls | `workspace.spec.ts`, `filters.spec.ts`, `test_conversations.py` |
| 7: three answer forms and rejected invented selections/URLs | `chat.spec.ts`, `test_generation.py`, `test_streaming.py` |
| 8: separate assets, enlargement/close, both faces | `chat.spec.ts`, `test_corpus.py` |
| 9: reopened selections, source snapshots, legacy and failed images | `chat.spec.ts`, `test_corpus.py`, `test_generation.py`, `test_streaming.py` |
| 10: unavailable/failing provider and unchanged no-match filters | `generation.spec.ts`, `chat.spec.ts`, `filters.spec.ts`, `test_generation.py` |
| 11: per-turn actual query/stages/scores and distinct citation targets | `chat.spec.ts`, `workspace.spec.ts`, retrieval-mode browser suites |
| 12: delete persists, other chats remain readable | `conversations.spec.ts`, `test_conversations.py` |

## Review

Standards and specification reviews independently examined `94254c8...d268b8c` and reported zero remaining findings. Preliminary review findings were corrected: completed selected card names/identities now enter bounded follow-up context, and selected cards always have visible evidence links when imagery is absent. Integration verification also checks the image dialog's reactive binding and rapid New chat/composer interaction.

## Reproduce browser checks

From `web`, run `npx playwright test` and each configuration: `playwright.workspace.config.ts`, `playwright.chat.config.ts`, `playwright.streaming.config.ts`, `playwright.filters.config.ts`, `playwright.rewriting.config.ts`, `playwright.vector.config.ts`, `playwright.hybrid.config.ts`, and `playwright.reranking.config.ts`. Each configuration runs isolated local service processes and ignored test databases. API checks: `uv run pytest`; frontend checks: `npm run check` and `npm run build`.

## Final results

- Backend: **175 passed, 2 skipped**. The skipped tests require explicit real-model execution; deterministic integration checks passed.
- Browser: **21 passed** across standard (4), workspace (2), chat/assets (5), streaming (4), filters (2), rewriting (1), vector (1), hybrid (1), and reranking (1).
- Frontend: `npm run check` has zero errors and warnings; production build passes.
- Reviewed desktop and 390px mobile screenshots; transcript and side panels stay within the viewport.
- Required live-provider limitation remains visible: deterministic application verification does not establish OpenCode Go workload suitability or live model quality.
