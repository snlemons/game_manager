# `/wrap-session` workflow

`/wrap-session` is the structural moment of the system — where unstructured in-play notes become canonical content (Log, Threads, Consequences, Beats, Reference-note updates, Adventure status changes, refreshed `campaign.md`).

## Sequence

1. **Read** `sessions/YYYY-MM-DD-session-N/notes.md`.
2. **Multi-pass extraction** (each pass uses prior context):
   - Adventure-relevance and status changes.
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

**Amendment (post-v0.1 dogfooding):** `/prep-session` also auto-commits its discrete checkpoint (one Brief + one notes.md + possibly-refreshed `campaign.md`), since it's the same category of "single coherent change" as `/ingest`'s bookend commits and the asymmetry between ingest (auto-commit) and prep (no commit) was confusing in practice. `/wrap-session`'s auto-commit policy is being evaluated separately — see comments on this ADR or follow-on commits.

## Re-running `/wrap-session`

If `log.md` already exists, confirm-before-overwrite. Threads/Consequences/Beats already created get matched-and-updated rather than duplicated (agent dedups against existing files by name + recent provenance).
