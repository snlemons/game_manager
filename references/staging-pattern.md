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

### 2. Write proposed content

Use the Write tool — this surfaces the file in the GM's IDE with a standard diff view. Write the **full proposed final content** of each file, not a diff or a patch:

- **For new files (CREATE):** the staged content is exactly what will land at the final location.
- **For updates to existing files (UPDATE):** read the existing file, apply the proposed edits in memory, write the merged result to staging. The GM sees the final state, not a partial diff.
- **For regenerated files (`campaign.md`):** the staged content is the full regenerated file.

Write order doesn't matter (files are independent), but a sensible order helps the GM scan.

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
