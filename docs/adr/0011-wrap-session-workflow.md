# `/wrap-session` workflow

`/wrap-session` is the structural moment of the system — where unstructured in-play notes become canonical content (Log, Threads, Consequences, Beats, Reference-note updates, Adventure status changes, refreshed `campaign.md`).

> **Live specs:** the dedup normalization rule pinned by `tests/test_wrap_session_idempotency.py` is `references/dedup-matching.md`. The shared `.ttrpg-staging/` review pattern is `references/staging-pattern.md`. The Reference-note extraction heuristic shared with `/ingest` is `references/reference-note-extraction.md`. The frontmatter schemas the wrap writes (Thread, Consequence, Beat, Adventure) live in `references/frontmatter-schemas.md`. The `campaign.md` composer lives in `references/campaign-overview-composer.md`. This ADR is the historical decision record.

> **Preflight runs first:** before the Sequence below begins, `/wrap-session` runs the settings-path preflight per `references/preflight.md` (issue #21). The preflight is a no-op when `.claude/settings.json` paths match the current campaign root; on mismatch it offers a regenerate-or-proceed prompt. The wrap workflow steps below are unchanged; the preflight just precedes Step 1.

## Sequence

1. **Read** `sessions/YYYY-MM-DD-session-N/notes.md`.
2. **Multi-pass extraction** (each pass uses prior context):
   - Adventure-relevance and status changes. **The session may touch zero, one, or multiple Adventures** — the agent does not assume a single current focus. A pure-exploration session that didn't engage any arc produces no Adventure status changes (and the agent does not invent one to justify the wrap). A session that engaged multiple arcs is evaluated per Adventure: each may transition status independently, or just accrete progress without transitioning. The status enum (`introduced | active | completed | abandoned`) is unchanged; the detection logic just stops assuming there's exactly one Adventure in play. This handles single-arc, multi-arc, and open-world / sandbox sessions equally (issue #13).
   - New Reference notes (NPCs, locations, factions, items).
   - Updates to existing Reference notes.
   - New Threads and Thread closures.
   - New Consequences.
   - Beat deliveries (pending → delivered) and any dropped Beats.
   - New Beat candidates (e.g., scratchpad items).
   - **Log draft** — narrative rewrite of `notes.md`.
3. **Ambiguity clarification** — agent surfaces missing/ambiguous info before review (e.g., "new NPC mentioned but no name — provide one?", "Sera's status changed — hostile or just wary?", "this could be a Thread or just narrative — which?"). GM resolves; clarifications feed into the proposed wrap.
4. **Single proposed-wrap review** — diff-style screen with all proposed changes grouped: Log (full preview, editable inline), Reference-note creates/updates (collapsed, expandable), Thread/Consequence/Beat operations, Adventure status changes, regenerated `campaign.md`.
5. **GM approves, edits, or rejects per item or wholesale.**
6. **Agent writes** approved changes and regenerates `campaign.md`.
7. **Closing message** — agent does **not** auto-commit, but encourages it: summarizes what changed ("3 new Reference notes, 2 Threads opened, 1 closed, Log written"), offers a suggested commit message, and prompts the GM to commit. The GM owns git.

## Why ambiguity clarification before review

Putting ambiguity-resolution between extraction and review keeps the review clean (no `[ambiguous]` markers in the proposed-wrap) and means the diff the GM sees is one the agent is committing to. Mixing ambiguity prompts into the review would force the GM to mentally separate "what the agent is confident about" from "what it wants me to decide."

## Why no auto-commit

The plugin owns scaffolding (`/ingest` runs `git init` and commits once at migration), but does not own ongoing git operations by default. After v0.1 launch, the GM commits with their own messages, amends as needed, and uses git however they like. Auto-commit would introduce surprise (commits the GM didn't expect) and create reconciliation burden if they wanted to edit before committing.

The closing message provides the affordance ("here's what changed, here's a suggested commit message") without taking the action.

**Amendment (post-v0.1 dogfooding):** All three skills now auto-commit their discrete checkpoints. `/prep-session` commits a single coherent change (one Brief + one notes.md + possibly-refreshed `campaign.md`). `/wrap-session` commits the post-session structural moment (log + new/updated lifecycle objects + Reference-note updates + Adventure status changes + regenerated `campaign.md`). The original "plugin doesn't own ongoing git operations" rule was internally consistent but produced confusing asymmetry between ingest (auto-commit) and prep/wrap (no commit). Commits are still scoped: each skill stages only the paths it wrote, never sweeping in unrelated GM edits, and surfaces git failures verbatim rather than retrying. `git push` remains GM-owned — the plugin never publishes.

## Re-running `/wrap-session`

If `log.md` already exists, confirm-before-overwrite. Threads/Consequences/Beats already created get matched-and-updated rather than duplicated (agent dedups against existing files by name + recent provenance).
