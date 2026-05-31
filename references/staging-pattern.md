# Staging-file review pattern

All three skills (`/ingest`, `/prep-session`, `/wrap-session`) use the same review pattern for proposed changes: the agent writes drafts to `.ttrpg-staging/` in the campaign repo, the GM edits or deletes files in their IDE, the agent reads back on continue, and the staging area is cleaned up on completion or cancellation. This reference is the shared shape; each SKILL.md keeps the per-skill specifics (where exactly inside `.ttrpg-staging/`, what kinds of entries are staged, what response shapes the chat exchange accepts).

## Why staging exists

The Write tool's standard diff display surfaces full proposed file contents in the IDE. Writing into a gitignored staging directory means:

- The GM **edits the proposed content in place**, with full IDE affordances (search, syntax highlighting, multi-cursor) instead of dictating edits in chat.
- **Deleting a staged file is the rejection signal** for that proposal — no separate "list which ones to drop" prompt.
- The final-location write is deferred until the GM explicitly approves; nothing the agent drafted leaks into the real campaign tree if the GM cancels.
- Staging contents never enter git history — `.ttrpg-staging/` is gitignored by the `/ingest` scaffolder via `templates/.gitignore.template`.

## Where staging lives

The staging root is `.ttrpg-staging/` at the **campaign repo root**, regardless of which skill is writing into it. Each skill owns its own sub-path inside:

| Skill | Sub-path | Contents |
|---|---|---|
| `/ingest` Phase 2 | `.ttrpg-staging/survey-descriptions.md`, `.ttrpg-staging/survey-order.md` | Single editable lists for the survey phase. |
| `/ingest` Phase 3 | `.ttrpg-staging/doc-<N>/` mirroring the campaign repo layout | One sub-directory per source doc in the multi-doc run; per-doc proposed changes. |
| `/ingest` Phase 4 | `.ttrpg-staging/adventure-order.md` | The bulk order-prompt list. |
| `/prep-session` | `.ttrpg-staging/brief-draft.md` | The drafted Brief, single file. |
| `/wrap-session` | `.ttrpg-staging/wrap/` mirroring the campaign repo layout | All proposed wrap changes — Log, lifecycle objects, Reference notes, Adventure updates, `campaign.md` regen. |

Skills that mirror the campaign layout inside their staging directory do so so that the "move from staging to final" step (after the GM approves) is just a path translation — strip the staging prefix and write to the same relative path.

## The lifecycle

### 1. Create the staging area

Before writing the first staged file, ensure `.ttrpg-staging/` exists (`mkdir -p` semantics). The scaffolder doesn't pre-create it; each skill creates it lazily.

If the skill writes per-doc or per-batch sub-directories, create those at the same time.

### 2. Stage proposed content

The mechanism differs by entry kind so that **Claude Code's native Edit-diff display surfaces the actual delta** wherever there is one. The GM sees changes the way Claude Code shows changes for any file edit — no separate chat-summary workaround needed.

**CREATE entries** — proposed new files. Use the Write tool to write the full proposed content to the staging path. The IDE / chat shows a new-file write; no diff applies because there is no original to compare against.

**UPDATE entries** — proposed modifications to existing files. Stage in two steps:

1. **Copy the live file into staging** via Bash: `cp <live_path> <staging_path>` (create any missing parent directories first with `mkdir -p`).
2. **Apply the proposed changes via the Edit tool** against the staged copy. Because the cp made the staged content byte-identical to the live file at that moment, the Edit's diff display shows the live → proposed delta — the same delta the GM expects to see for any file Claude Code touches.

For whole-file rewrites where a clean `old_string` / `new_string` boundary is hard to express (a fully-rewritten Reference note body, for example), use Edit with `old_string` = the entire staged content and `new_string` = the proposed content; the chat-rendered diff still shows the live → proposed change.

**Regenerated files** (`campaign.md` rewritten by `/wrap-session` Step 5 or `/prep-session` Step 2.5): treat as UPDATE if a previous `campaign.md` exists at the live path (cp + Edit shows the previous-vs-regenerated diff). Treat as CREATE if the file doesn't exist yet (fresh ingest, first session).

**No-op UPDATEs.** Before staging an UPDATE, compare the proposed content against the live file. If they are byte-identical, **skip staging entirely** and surface the entry in the chat summary as `<path> — UPDATE (no-op against existing file; consider dropping)`. This avoids cluttering staging with no-change files and the Edit tool's empty-diff failure mode. It is also the right signal to the GM that the agent thought a change applied but didn't.

Stage order doesn't matter (files are independent), but a sensible order helps the GM scan.

### 3. Present a chat summary and ask for the continue/cancel decision

After staging, present a short summary in chat listing what was staged, where it lives, and what the GM's response options are. The summary's exact format is per-skill (some include scope hints, lesson summaries, per-doc context), but the contract is uniform:

- **List the staged paths**, ideally with a one-word annotation per path (CREATE / UPDATE / etc.) so the GM can scan quickly.
- **Tell the GM the edit contract:** *"Edit any file in `.ttrpg-staging/<sub-path>/`, delete any file to reject that proposal, then tell me to continue. Or say cancel to exit cleanly."*
- **Accept these response shapes:**
  - **Continue / approve** → re-read every file remaining in the staging area to capture GM edits; treat deleted files as rejections; proceed to the move-to-final-location step.
  - **Cancel** → delete the skill's staging sub-path (and `.ttrpg-staging/` itself if it's now empty), leave the rest of the filesystem unchanged, exit cleanly.
  - Some skills also accept **edit-the-message** or **reject-everything** shapes specific to their flow; those stay in the per-skill SKILL.md.

Do **not** write to any file outside `.ttrpg-staging/` between the stage-write and the GM's continue response. The final-location writes happen only after approval.

### 4. Re-read on continue (capture GM edits)

When the GM says continue, **re-read every file in the staging area** before promoting. The GM may have edited content, frontmatter, or paths in place; the agent must use the edited content, not the originally-drafted content from memory.

Deleted files in the staging area are rejections — those proposals are dropped; nothing is written for them at the final location.

### 4a. Iterative agent revisions during a review loop

Some skills (`/prep-session` Step 3.5 per [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md)) extend the v0.1 terminal yes/no/cancel review into a multi-turn refinement loop. The skill stays inside the staging-area review for several turns: the agent asks rule-based follow-up questions, the GM responds, the agent revises the staged file(s) in place via Edit, and the loop continues until the GM explicitly approves or cancels.

The contract from sections 2–4 still holds — the staging area is the sole surface the agent writes to between stage-write and approval, and the GM's final approve is what gates the move to the final location. The loop just inserts multiple turns of agent-revises-staging-via-Edit between the initial stage-write (section 2) and the final approve (sections 4–5). Each turn within the loop has the same shape:

1. **Re-read every file in the staging area** before the agent does anything else. The GM may have edited the staged file directly in their IDE between turns; the agent must observe those edits and treat them as the current ground truth. Re-reading is the same operation the terminal-review continue path uses (section 4); the loop just runs it on every turn rather than only at exit.
2. **Compute revisions from the GM's reply.** The agent decides what (if any) changes to the staged file the GM's reply implies — adding a section, appending a bullet, rephrasing a header, dropping a paragraph. Skill-specific question categories (e.g., `references/prep-session-questions.md` for `/prep-session`) define what kinds of revisions each kind of GM reply produces.
3. **Apply revisions via the Edit tool against the staged file.** Per [#16](https://github.com/snlemons/game_manager/issues/16), Edit's diff display is the right native affordance for showing the GM a delta against content they've already reviewed once. Don't rewrite the whole staged file via Write — that's a re-stage, not a revision, and the chat shows it as a fresh full-file diff rather than the targeted change the GM is reacting to. If the revision is a whole-section rewrite, Edit can still express it (old_string = the whole section's current bytes, new_string = the rewritten section); the targeted diff is still preferable to a full re-stage.
4. **Do not clobber GM edits.** Before applying an Edit, the just-completed re-read in step 1 reflects the current staged bytes including any GM hand-edits. If the agent's intended revision would overwrite GM-authored content the agent did not draft, surface the conflict to the GM in chat rather than silently overwriting (*"You edited the Locations section after the last turn; my proposed Secret-Push revision would touch a bullet you changed. Apply anyway, or skip?"*). The same posture the terminal-review re-read uses — the GM's edits are the source of truth.
5. **Return to the loop preamble or move to approval.** After the revision (or after no-op if the GM's reply implied no change), the agent either presents the next queued question or asks for approval. The next turn re-reads from scratch — the agent never holds a cached view of the staged file across turns.

A loop turn that produces no revision (the GM declined a question, or asked the agent to skip the rest) advances the loop without an Edit call. The staged file stays byte-identical for that turn; the next turn still re-reads (cheap; guarantees the agent never drifts from the file state).

**Loop termination.** Two terminal signals exit the loop, both treated exactly as the terminal review's responses in section 4:

- **Approve / continue / "looks good"** — final re-read of staging, move to final locations (section 5), clean up (section 6).
- **Cancel** — delete the skill's staging sub-path immediately, leave the rest of the filesystem unchanged (section 6's cancel path). Pending revisions that were queued but not yet committed are discarded along with the staging file.

**Cancel mid-loop is safe.** Because every loop turn writes only to `.ttrpg-staging/`, the on-cancel cleanup is the same `rm -r` as the terminal-review cancel path. The campaign tree is byte-identical before staging and after cleanup regardless of how many loop turns ran.

**Manual edits between loop turns are picked up automatically.** The re-read at the top of each turn (step 1) is what makes this work. A GM who prefers to edit the staged file directly rather than asking via chat can do so freely — the agent observes the edits on the next loop turn and treats them as authoritative. The agent does not need a separate "I edited the file directly, here are the changes" signal from the GM; the re-read is unconditional.

### 5. Move from staging to final locations

For each surviving staged file, translate the staging path to the final path (strip the skill's staging prefix) and write the file there. Create any missing parent directories. Then delete the staged file.

For skills that mirror the campaign layout (`/ingest` Phase 3, `/wrap-session`), this is purely path translation — content was finalized in staging.

For skills that stage to a single file (`/prep-session`'s `brief-draft.md`), the move is a single write + delete.

### 6. Clean up

When the staging sub-path is empty after the move, remove it. When `.ttrpg-staging/` itself is empty (no other workflows' staging present), remove that too.

On cancel, the same cleanup happens immediately — delete the staging sub-path (and `.ttrpg-staging/` if empty) before exiting.

## Invariants the pattern guarantees

These are the properties downstream code (including the test suite at `tests/test_wrap_session_idempotency.py::TestConfirmBeforeOverwriteLog`) relies on:

- **No file outside `.ttrpg-staging/` is created or modified between stage-write and the GM's continue response.** Cancel is safe: the campaign tree is byte-identical before staging and after cleanup.
- **`.ttrpg-staging/` is gitignored at the campaign root** (scaffolded by `/ingest` Phase 1 via `templates/.gitignore.template`). A cancelled session leaves no trace in `git status`.
- **The GM's edits are the source of truth** for what lands at the final location, not the agent's original draft. Re-reading on continue is mandatory.
- **Deleted staged files are rejections.** Don't ask "did you mean to delete that?" — the deletion is the answer.
- **Staging is not git-committed.** Even if the skill auto-commits after promoting (per ADR-0011 amended), it stages only the final-location paths, never anything under `.ttrpg-staging/`.

## What this pattern is not

- **Not a long-lived workspace.** Staging is per-invocation; there's no expectation that `.ttrpg-staging/` survives across separate `/ingest` or `/wrap-session` runs. Each skill cleans up its own sub-path at the end of its run.
- **Not for in-progress GM work.** The GM's authoring lives in the real tree (or wherever the GM wants to draft). Staging is the agent's review surface, not the GM's scratch space.
- **Not a substitute for the chat exchange.** The chat summary is the load-bearing prompt — staging on its own doesn't tell the GM what's expected of them. Don't write files and stop; always pair the stage-write with the continue/cancel ask.

## Per-skill nuances live in the SKILL.md

Each SKILL.md documents:

- The exact staging sub-path it uses.
- What kinds of files it stages and how it groups them.
- The exact response shapes the chat exchange accepts (some have richer than just continue/cancel).
- What summary metadata it surfaces alongside the file list (carried-forward lessons in `/ingest` Phase 3, scope hints in `/wrap-session`, etc.).

This reference is the shape; the SKILL.md is the per-skill behavior on top of the shape.
