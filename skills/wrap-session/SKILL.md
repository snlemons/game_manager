---
name: wrap-session
description: Read a session's in-play notes, draft the Log, propose new Threads, Consequences, Reference notes, Beat updates, and Adventure status changes, resolve ambiguity with the GM, write approved changes, and regenerate campaign.md. Use when the GM invokes `/wrap-session`, asks to wrap a session, says the session is over and they want to extract structure from their notes, or wants to turn in-play notes into a canonical Log.
---

# /wrap-session

You are completing a TTRPG **Session** for a **GM**. The campaign repo is the current working directory (or a directory the GM names). This workflow is the **Post-session extraction** moment — where messy **In-play notes** become canonical content: a written **Log**, new and updated **Reference notes**, opened and closed **Threads**, new **Consequences**, **Beat** deliveries and proposals, **Adventure** status transitions, and a regenerated **Campaign overview** (`campaign.md`).

Follow the domain vocabulary defined in the campaign repo's `CLAUDE.md` and the plugin's `CONTEXT.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Campaign overview**, **Post-session extraction**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, "recap"/"summary" for Log, "fact"/"event" for Consequence, etc.).

## Locate the campaign repo

The campaign repo has this shape (per ADR-0002, ADR-0005, ADR-0007, ADR-0012):

```
<campaign>/
├── CLAUDE.md
├── campaign.md
├── .claude/rules/
├── adventures/<name>/        # each with frontmatter status: introduced|active|completed|abandoned
├── npcs/        locations/   factions/   items/
├── threads/                  # status: open | closed | decayed
├── consequences/
├── beats/                    # status: pending | delivered | dropped
└── sessions/YYYY-MM-DD-session-N/
                  ├── brief.md      (read for context if present)
                  ├── notes.md      (input — never modified)
                  └── log.md        (output — written by this skill)
```

If the current working directory is not a campaign repo (no `campaign.md`, no `sessions/`, no `CLAUDE.md` for the campaign), ask the GM where their campaign repo is before proceeding. Don't guess.

Honor `.claude/rules/sessions.md` and `.claude/rules/adventures.md` if present — they describe campaign-local conventions.

## Step 0 — Locate the campaign repo

The skill operates on **a campaign repo**, which may or may not be the current working directory. Don't assume cwd.

1. Check cwd for the campaign-repo markers: `CLAUDE.md` at the root, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, and `campaign.md`. If all four are present, cwd is the campaign repo — use it.
2. If any are missing, **ask the GM** for the absolute path of the campaign repo (e.g., *"I don't see a scaffolded campaign in the current directory. Where is the campaign repo? (Give an absolute path or a `~/`-anchored path.)"*). Resolve their answer to an absolute path. Re-check the four markers there. If still missing, surface what was missing and stop — the campaign isn't scaffolded.
3. Use that absolute path as the **campaign root** for the rest of this workflow. Every path in subsequent steps (e.g., `sessions/...`, `npcs/...`, `threads/...`, `.ttrpg-staging/...`) resolves *relative to the campaign root*, not relative to cwd. Pass absolute paths to file tools so they work regardless of cwd.

Don't repeat the pre-flight if the campaign root is already determined in this run.

## Step 1 — Select the target session

The default target is the **latest session that has a non-empty `notes.md` and no `log.md`**. Resolve as follows:

1. List `sessions/` (under the campaign root). Sort directories lexicographically by name (`YYYY-MM-DD-session-N` sorts correctly by date then number).
2. Scan from newest to oldest. The target is the first session where `notes.md` exists and is non-empty and `log.md` does **not** exist.
3. If no such session exists, check whether the latest session has `log.md` already. If so, this is a **re-run candidate** — see "Re-run guard" below.
4. If `sessions/` is empty or no session has `notes.md`, tell the GM there is nothing to wrap and stop.

If the GM names a specific session explicitly (e.g., "wrap session 4" or a directory path), use that instead of the default. Confirm the resolved directory back to the GM before reading.

**State the planned target upfront** in chat before extraction, so the GM has an obvious moment to redirect to a different session. Format: *"Wrapping `sessions/YYYY-MM-DD-session-N/` — reading `notes.md` and extracting Log, Threads, Consequences, Beat updates, Reference notes, and Adventure status changes. Lifecycle-object dates will use the session date (YYYY-MM-DD), not today's date. Say a different session (e.g., `wrap session 4`) if I picked the wrong one."* Then continue with the rest of the workflow. Don't pause for confirmation — the GM redirects only if needed.

### Re-run guard (confirm-before-overwrite)

Before doing any work, check whether the target session already has a `log.md`:

- **No `log.md`:** proceed normally.
- **`log.md` exists:** STOP. Show the GM the existing `log.md` path and ask explicitly: *"A `log.md` already exists for this session. The GM may have hand-edited it, or this is a re-run after corrections. Overwrite the Log and re-propose extractions?"* Do not proceed without an explicit yes. If the GM declines, exit without writing anything. If yes, continue — and when you reach the write step, dedup proposed Threads / Consequences / Beats / Reference notes against what already exists in the repo so the re-run does not create duplicates (see "Dedup" under Step 2).

If `notes.md` does not exist or is empty for the chosen session, tell the GM and stop. There is nothing to extract.

## Step 2 — Multi-pass extraction

Read `notes.md` in full. Also read these for context (do not modify):

- `brief.md` for the same session if present — tells you what the GM was planning, including pending Beats they hoped to land and the scratchpad. **Scratchpad items are a primary source of new Beat candidates** (ADR-0009).
- The prior session's `log.md` if present — gives you continuity for what was already established.
- `campaign.md` — current state snapshot, useful for cross-checking what's already active or open.
- Active `adventures/<name>/adventure.md` files — to evaluate status transitions and adventure relevance.
- Existing `threads/`, `consequences/`, `beats/`, and Reference-note files you might be updating or matching against (lazy-read; list directories first, then read files when an extraction candidate plausibly matches by name).

Run the extraction in **this exact order**. Each pass uses prior-pass context (ADR-0011).

### Pass 1 — Adventure relevance and status transitions

The session may have touched **zero, one, or multiple Adventures**. Don't assume a single current focus — open-world / sandbox campaigns commonly run sessions that engage several arcs at once or none at all (issue #13, ADR-0011). Evaluate each Adventure independently against the notes.

For every `adventures/<name>/` directory, decide whether `notes.md` indicates a status change:

- `introduced → active` — the party began running this adventure this session. Sets `started:` to the session's date (the `YYYY-MM-DD` from the session directory name).
- `active → completed` — the party resolved this adventure. Sets `completed:` to the session date.
- `active → abandoned` — the party walked away or the GM is dropping it. Sets `completed:` to the session date (per ADR-0007, abandoned still records a completion date with abandoned semantics).
- New adventure not yet in `adventures/` but clearly started this session — propose creating `adventures/<slug>/adventure.md` with `status: active`, `started: <session date>`, and other dates left null.

The three shapes to handle:

- **Session touched no arc** (pure exploration, downtime, a session of pure character interaction). Don't propose any Adventure status changes. Don't pick a "best fit" Adventure to attribute the session to — the wrap can be valid with zero Adventure transitions. The Log, Threads, Consequences, and Reference notes still get extracted normally.
- **Session touched one arc.** The familiar case: one Adventure's frontmatter may transition, or it may just accrete in-play progress with no status change. Don't force a transition where the notes don't load-bear one.
- **Session touched multiple arcs.** Each Adventure is evaluated independently. Multiple Adventures may transition status in the same wrap, or some transition while others just record progress. This is normal for sandbox play — don't collapse the proposals into a single dominant arc.

Don't infer transitions from vague references — require a load-bearing event in the notes (party accepts the job; final boss falls; party explicitly walks away). Surface borderline cases via ambiguity clarification (Step 3) rather than guessing.

### Pass 2 — New Reference notes

For each NPC, location, faction, or item mentioned in `notes.md` that does not already have a file in `npcs/`, `locations/`, `factions/`, or `items/`:

- Propose creating a one-line Reference note (ADR-0003: default content is a one-liner; the GM never fills out a form).
- Filename: lowercase slug of the name (e.g., `npcs/sera.md`, `locations/the-broken-mines.md`).
- Body: one sentence stating who/what they are and how they appeared this session. Add `[[wiki links]]` for any related Reference notes that exist or are also being proposed.
- If the notes reference a thing whose **name is missing or unclear** (e.g., "the blacksmith said…" with no name), do NOT invent a name — defer to ambiguity clarification (Step 3).

Match conservatively. "The captain" in this session is the same as `npcs/captain-marra.md` only if the notes make that link explicit or the prior Log establishes it. When in doubt, flag for clarification.

### Pass 3 — Updates to existing Reference notes

For each existing Reference note whose entry appears in `notes.md` with new information (changed disposition, new title, new location, new fact), propose an update:

- Show the GM the existing one-liner / current content and the proposed addition or replacement.
- Prefer **append** (additional sentence at end) for accreted facts; prefer **edit** for changes that contradict the existing line (e.g., "Sera moved from the village to the city").
- Don't lose existing GM-authored content. If you would overwrite GM prose, flag it for review with both versions visible.

### Pass 4 — New Threads and Thread closures

A **Thread** is a hook the GM should be reminded about — a promise, an unresolved question, a foreshadowed danger; future-facing (CONTEXT.md, ADR-0004).

- **New Threads:** for each promise the party made, unresolved question raised, or piece of foreshadowing dropped in notes that does not already match an open Thread, propose creating `threads/<slug>.md` with frontmatter `status: open`, `created: <session date>`, `closed: ~`. Body: one or two sentences describing what's open and why it matters.
- **Thread closures:** for each existing open Thread that the session's events resolved (the promise was kept, the question was answered, the foreshadowed danger landed and is done), propose updating that file's frontmatter to `status: closed`, `closed: <session date>`. Include a one-line note in the body explaining how it closed.

If something in the notes *could* be a Thread or *could* be just narrative color (a one-off rumor, a flavor mention), defer to ambiguity clarification — do not silently include or exclude.

### Pass 5 — New Consequences

A **Consequence** is a persistent fact about the world resulting from the party's actions; past-facing; it doesn't close (CONTEXT.md, ADR-0004).

- For each load-bearing change the party caused this session (the captain owes them a favor, the bridge is destroyed, the cult knows their faces), propose creating `consequences/<slug>.md` with frontmatter `created: <session date>`. Body: one sentence stating the persistent fact, using `[[wiki links]]` for any Reference notes it touches.
- Do not double-write the same fact as both a Thread and a Consequence. If the party owes the favor (future obligation), it's a Thread. If the captain owes them a favor (persistent world fact), it's a Consequence. If both framings apply, propose both and explain the split to the GM.

### Pass 6 — Beat deliveries and dropped Beats

For each Beat currently in `beats/` with `status: pending`:

- **Delivered** — the session landed the Beat (the planned moment played out). Propose updating frontmatter to `status: delivered`, `delivered: <session date>`. Optionally update `linked_pcs:` / `linked_npcs:` if the session clarified who was involved.
- **Dropped** — the session made the Beat obsolete (the NPC is dead, the location is gone, the GM signaled they're abandoning it). Propose updating to `status: dropped`. Leave `delivered:` null.
- **Untouched** — pending Beats not addressed this session stay pending. Do not propose changes.

Use the prior `brief.md` (if present) as a hint to which Beats the GM intended to land. The notes' content is the source of truth for whether they actually landed.

### Pass 7 — New Beat candidates

Propose new Beats from:

- The prior `brief.md`'s **GM scratchpad** — items the GM jotted as "if X then Y", "land this next time", name picks they want to use. These are the canonical promotion path (ADR-0009).
- Notes phrases like "I want to set up X next session", "remind me to land Y", "save Z for later".

Propose each as `beats/<slug>.md` with frontmatter `status: pending`, `created: <session date>`, `delivered: ~`, and optional `linked_pcs:` / `linked_npcs:` lists if the scratchpad scoped them. Body: one or two sentences stating the intent. If the Beat is scoped to a specific Adventure, include a `[[wiki link]]` to that Adventure in the body so backlinks resolve (ADR-0009).

### Pass 8 — Log draft

Draft `log.md` as a clean narrative rewrite of `notes.md`. The Log is the canonical, human-readable record of what happened — what future Briefs will read.

**Drop mechanical noise:**

- Roll outcomes, DCs, HP totals, initiative order, spell slots, ability checks unless the *outcome* is load-bearing.
- Snack-break asides, real-world tangents, table chatter.
- Lookup pauses ("checking the rules on grappling"), retcons resolved at the table.

**Preserve load-bearing events:**

- Promises made by the party (these become Threads).
- Consequences caused by the party (these become Consequences).
- Beats that landed (these match Beat deliveries).
- NPCs met or whose stance shifted.
- Locations entered, left, or changed.
- Information learned that future Briefs will reference.

**Voice:** third-person past tense, narrative prose. Section headings if the session had clear scene breaks; otherwise flowing paragraphs. Use `[[wiki links]]` for Reference notes so backlinks resolve. The Log is for the GM (and the agent's future-Brief reads), not for the players — secrets and NPC motivations the players don't know are fine to include.

The Log should be readable as a standalone narrative by someone catching up on the campaign. Length scales with what happened — a quiet session is a short Log; a pivotal session is a longer one. No fixed minimum.

### Dedup (applies across passes; matters most on re-runs)

Before proposing any new Thread / Consequence / Beat / Reference note, match against existing files:

- **Name match:** case-insensitive, light normalization (strip leading "the", collapse whitespace, hyphenate). Match candidate name against existing filenames and the first-heading title inside each file.
- **Recent provenance:** for Threads/Consequences/Beats, prefer files whose `created:` (or the session referenced in their body) is recent — within the last few sessions. A new Thread proposal that name-matches an existing **open** Thread created last session is almost certainly the same Thread; treat as a no-op or as an update rather than a new file.
- **On ambiguous match:** do not silently dedup. Flag it for ambiguity clarification ("`threads/deliver-the-letter.md` already exists from session 4; this looks like the same Thread — update or new?").

The goal is that re-running `/wrap-session` against the same `notes.md` (after the GM corrected something downstream) produces zero spurious duplicates.

## Step 3 — Ambiguity clarification (BEFORE the proposed-wrap review)

Surface every unresolved question to the GM **before** showing the proposed wrap. The review screen must contain only proposals the agent is confident about (ADR-0011 — "no `[ambiguous]` markers in the proposed-wrap").

Typical ambiguity buckets:

- **Missing names** — "An unnamed blacksmith appears in the notes. Provide a name, or skip creating a Reference note?"
- **Unclear classification** — "The party promised to 'look into' the missing caravan. Thread (active obligation), or narrative color (passing comment)?"
- **Status interpretation** — "Sera 'wasn't pleased' with the party. Update her disposition to hostile, wary, or leave unchanged?"
- **Thread-vs-Consequence framing** — "'The cult knows their faces.' Read this as a Thread (the party owes themselves caution next time) or a Consequence (persistent world fact)? Or both?"
- **Dedup matches** — "`threads/deliver-the-letter.md` already exists. Is this the same Thread, an update, or a new one?"
- **Adventure transitions** — "The party left the Sunless Citadel mid-arc to chase another lead. Mark Sunless Citadel as `abandoned`, or keep `active` because they might return?"
- **Beat deliveries on the edge** — "The 'Sera reveals the locket' Beat was set up but the reveal didn't quite land. Delivered, still pending, or dropped?"

Present the questions as a short numbered list. The GM answers in whatever form is easiest (numbered replies, free prose). Apply each resolution back into the extraction set:

- New names update Reference-note proposals (filename and body).
- Classification answers move items between Thread / Consequence / Beat / "neither — drop it".
- Dedup answers convert "new file" proposals into "update existing" proposals.
- Adventure-transition answers change or drop the proposed frontmatter update.

If the GM's resolution surfaces **new** ambiguities (e.g., "actually call her Sera — and she's the same Sera from the Lost Mines, not a new one"), loop: ask the follow-up questions, then refold. Don't proceed to review until the question list is empty.

If there are no ambiguities, say so and move to Step 4 directly. Don't manufacture questions to look thorough.

## Step 4 — Single proposed-wrap review via staging directory

Write the full proposed change set to `.ttrpg-staging/wrap/` in the campaign repo, mirroring the campaign's directory structure. The `.ttrpg-staging/` directory is gitignored by the scaffolder; create it (and `wrap/` inside it) if it doesn't exist. Each proposed file lands at its eventual relative path *inside* `wrap/`:

| Proposed change | Staging path |
|---|---|
| Drafted Log | `.ttrpg-staging/wrap/sessions/YYYY-MM-DD-session-N/log.md` |
| CREATE Reference note | `.ttrpg-staging/wrap/npcs/<slug>.md` (or `locations/`, `factions/`, `items/`) |
| UPDATE Reference note | `.ttrpg-staging/wrap/<kind>/<slug>.md` — write the **full proposed new content**, not a diff |
| CREATE Thread | `.ttrpg-staging/wrap/threads/<slug>.md` |
| UPDATE Thread (closure) | `.ttrpg-staging/wrap/threads/<slug>.md` — full proposed new content |
| CREATE Consequence | `.ttrpg-staging/wrap/consequences/<slug>.md` |
| CREATE / DROP / DELIVER Beat | `.ttrpg-staging/wrap/beats/<slug>.md` — full proposed new content |
| UPDATE Adventure (status transition) | `.ttrpg-staging/wrap/adventures/<slug>/adventure.md` — full proposed new content |
| New Adventure | `.ttrpg-staging/wrap/adventures/<slug>/adventure.md` — full new file |
| `campaign.md` regen | `.ttrpg-staging/wrap/campaign.md` — full proposed new content |

For UPDATEs, the staged file contains the full file as it would land — existing content plus the proposed additions/changes — so the GM sees and edits the full final state, not just a diff. The agent does this by reading the existing file, applying proposed edits in memory, and writing the merged result to staging.

Then present a summary in chat listing the staged paths and what each represents:

```
Wrap proposal staged at .ttrpg-staging/wrap/. Edit any file in place in your IDE, then tell me to continue. Or delete a staged file to reject that proposal individually.

Files:
  sessions/2026-05-29-session-5/log.md           — drafted Log
  npcs/sera.md                                   — CREATE (new NPC)
  locations/the-broken-mines.md                  — CREATE (new location)
  npcs/captain-marra.md                          — UPDATE (full new content staged)
  npcs/orin.md                                   — UPDATE (disposition change; full new content staged)
  threads/cult-of-the-broken-flame.md            — CREATE (new Thread)
  consequences/marra-owes-favor.md               — CREATE (new Consequence)
  beats/orin-armor.md                            — DROP (status: pending → dropped)
  adventures/lost-mines/adventure.md             — UPDATE (status: active → completed)
  campaign.md                                    — regenerate
```

Then ask exactly: *"Edit any file in `.ttrpg-staging/wrap/`, delete any file to reject that proposal, then tell me to continue. Or say cancel to exit cleanly."* Accept two response shapes:

1. **Continue** → re-read every file remaining in `.ttrpg-staging/wrap/` to capture GM edits. Treat any staged file the GM deleted as rejection (don't write that one). Proceed to Step 5 to move surviving staged files to their final locations.
2. **Cancel** → delete `.ttrpg-staging/`, leave the rest of the filesystem unchanged, exit cleanly.

Do **not** write to any file outside `.ttrpg-staging/wrap/` during Step 4. The final-location writes happen only in Step 5 after the GM says continue.

## Step 5 — Move approved changes from staging to final locations

Once the GM says continue, move every file that's still in `.ttrpg-staging/wrap/` to its final location (paths inside `wrap/` mirror the campaign repo, so the move is a path translation — strip the `.ttrpg-staging/wrap/` prefix). Read each staged file, write its content to the corresponding final path (creating parent directories as needed), then delete the staged file. After all moves, delete `.ttrpg-staging/` entirely.

Order doesn't matter for correctness (files are independent) but a sensible order helps the GM read git diffs later. The per-file rules below describe **what gets written to the final location** — the content was already prepared and edited in staging during Step 4, so by the time you reach this step you're just translating paths.

1. **Write `log.md`** to `sessions/YYYY-MM-DD-session-N/log.md`. Overwrite if confirmed in the re-run guard.
2. **Create or update Reference notes** under `npcs/`, `locations/`, `factions/`, `items/`. Create parent directories if missing.
3. **Create or update Threads** under `threads/`. Frontmatter shape:

   ```yaml
   ---
   status: open                 # open | closed | decayed
   created: 2026-05-29          # YYYY-MM-DD of the session that opened it
   closed: ~                    # null until status transitions to closed/decayed
   ---
   ```

   On closure, set `status: closed` (or `decayed` if that's the disposition) and `closed: <session date>`.

4. **Create Consequences** under `consequences/`. Frontmatter shape:

   ```yaml
   ---
   created: 2026-05-29
   ---
   ```

5. **Create or update Beats** under `beats/`. Frontmatter shape:

   ```yaml
   ---
   status: pending              # pending | delivered | dropped
   created: 2026-05-29
   delivered: ~                 # null until status transitions to delivered
   linked_pcs: []               # optional
   linked_npcs: []              # optional
   ---
   ```

   On delivery, set `status: delivered`, `delivered: <session date>`. On drop, set `status: dropped` and leave `delivered:` null.

6. **Update Adventure frontmatter** in `adventures/<name>/adventure.md` (or the adventure's main file). Only touch the fields that changed:

   - `introduced → active`: set `status: active`, set `started: <session date>` if currently null. Leave `order:` alone — it's ingest-era data.
   - `active → completed`: set `status: completed`, set `completed: <session date>`.
   - `active → abandoned`: set `status: abandoned`, set `completed: <session date>` (per ADR-0007).
   - New adventure: write the full file with the GM-approved name, slug, and minimal frontmatter (`status: active`, `started: <session date>`, other dates null).

7. **Regenerate `campaign.md`** at the campaign root. Rewrite the whole file from current state. Sections, in this order (mirroring the template and ADR-0007):

   - Header: campaign name, system (carry from existing `campaign.md` frontmatter or H1 — do not invent if missing; tell the GM).
   - **Where the party might go next session** — the forward-looking menu the GM is orienting against. A bulleted set, with sub-buckets for active arcs / introduced arcs / session-driver Threads / party location:
     - If any Adventures have `status: active`, list each as a bullet with a one-line current state, then add a short note: *"could continue any of these."* If none are active, omit this sub-bucket entirely (don't render an empty "Active arcs" line).
     - **Introduced Adventures the party could pick up:** every Adventure with `status: introduced`, one bullet each, with the Adventure's H1 title (wiki-linked) and a one-line hook/state pulled from the Adventure's own file. This is the open-world menu of next-session options. Order: ascending by `order:` if set (ingest-era sequence), then alphabetical by slug for null-order Adventures. If none, render `_None._` under this sub-bucket so the GM sees the agent looked.
     - **Recent open Threads that could become a session focus:** a curated subset of `status: open` Threads — the ones substantial enough to drive a session (a Thread that's just a flavor reminder doesn't belong here; one that's an arc-in-waiting does). Order: most-recent first by `created:` (slug asc as tiebreak). If there are no session-driver Threads, render `_None._`.
     - **Party location:** one line, derived from the just-written Log's closing state, with `[[wiki link]]` to the location's Reference note. If unclear, say so plainly ("Party location not stated in this session's Log.") — do not guess. This is a piece of context, not the framing — keep it as a single line at the end of the menu.
   - **Open threads** — every Thread with `status: open`, one line each, most-recent first. (This is the full list; the menu above is a curated subset.)
   - **Recent significant consequences** — Consequences ordered by `created:` descending, top 5–10 (whatever fits on a glance-readable screen). Don't dump the entire history.
   - **Pending beats** — every Beat with `status: pending`, one line each.

   The "Where the party might go next session" section replaces the older "Active adventures" + "Party location" framing. The new shape handles zero, one, or many `status: active` Adventures equally — open-world / sandbox campaigns with many `introduced` Adventures available and none currently active render naturally instead of leaving the GM with empty sections (issue #13, ADR-0007).

   Preserve the agent-maintained header comment from the template ("This file is agent-maintained…"). If the existing `campaign.md` has GM hand-edits that conflict with regenerated content, the regeneration overwrites (ADR-0007: "Manual GM edits to `campaign.md` are reconciled (or overwritten with warning) at next regeneration"). Surface this warning to the GM in the closing message if hand-edits were detected and overwritten.

   This composer's section shape and tone must match `/ingest` Phase 4 Step 2 (`skills/ingest/SKILL.md`) so the two produce a consistent campaign overview from the same campaign state. Skills don't share code; consistency is by alignment of these specs. If the two drift, treat that as a documentation bug to fix in both places.

**Do not modify `notes.md`.** It is the source of truth and stays unchanged (ADR-0005, ADR-0011).

8. **Commit the wrap.** `/wrap-session` auto-commits its discrete checkpoint, matching `/ingest` and `/prep-session` (ADR-0011 amended — see that ADR's "Amendment" section). Stage **only** the files this run wrote or modified:

   - `sessions/YYYY-MM-DD-session-N/log.md`
   - New and updated files under `npcs/`, `locations/`, `factions/`, `items/`, `threads/`, `consequences/`, `beats/` — exactly the ones approved at Step 4.
   - Updated `adventures/<slug>/adventure.md` files where status transitioned.
   - `campaign.md`

   Commit message format (build incrementally based on counts):

   ```
   Wrap session N (YYYY-MM-DD)
   ```

   Or richer when there's a clearly load-bearing change to call out — e.g., `Wrap session 5: Broken Mines active, Captain Marra owes a favor`. Pick at most 1–2 load-bearing items for the subject line; leave the rest for the body if you include one.

   If the commit fails (git has no user configured, hooks reject, etc.), surface the error verbatim and stop. Files stay written; the GM can commit manually.

   Edge case: if the campaign repo has uncommitted changes from other sources mixed in (the GM was hand-editing other files between sessions), stage **only** the paths this wrap touched. Don't sweep in unrelated GM edits. If you can't isolate (e.g., a file the GM hand-edited and this wrap also modified), surface the conflict to the GM and ask before staging.

## Step 6 — Closing message

Tell the GM, concisely:

- A **count summary** of what changed. Example:

  > Wrap complete for session 5 (2026-05-29):
  > - Log written: `sessions/2026-05-29-session-5/log.md`
  > - 3 new Reference notes (2 NPCs, 1 location)
  > - 1 Reference note updated
  > - 2 Threads opened, 1 closed
  > - 1 Consequence added
  > - 1 Beat delivered, 2 new Beat candidates
  > - Adventure status: *The Broken Mines* → `active`
  > - `campaign.md` regenerated

  Multi-arc sessions list each Adventure transition on its own line. A session that touched no arc (pure exploration) omits the "Adventure status" line entirely — don't manufacture a transition to fill the bullet (issue #13).

- If the regenerated `campaign.md` overwrote hand-edits, say so explicitly.
- **The commit that was just made**: hash and message. Example: *"Committed as `a1b2c3d` — `Wrap session 5 (2026-05-29)`."*
- If the commit was skipped (failure from Step 5#8 or the GM had unrelated uncommitted changes the agent couldn't isolate), say so explicitly and tell the GM what's staged or unstaged for them to handle manually.

## Quick reference: which ADR governs what

- **ADR-0003** — Reference notes are one file per item; default content is a one-liner.
- **ADR-0004** — Threads and Consequences are per-file with status frontmatter, created via Post-session extraction. This is the lifecycle reference for both kinds.
- **ADR-0005** — Session is a directory of three documents. `notes.md` is input, `log.md` is output, `notes.md` is never modified.
- **ADR-0007** — Adventure frontmatter (`status`, `started`, `completed`) and the agent-maintained `campaign.md` — you regenerate it at the end.
- **ADR-0009** — Beats are GM-authored or proposed by `/wrap-session`; status `pending | delivered | dropped`; brief-scratchpad items are a primary creation path.
- **ADR-0011** — This skill's primary spec: sequence, ambiguity-before-review, single-batch grouped review, auto-commit the discrete checkpoint (per the amendment in that ADR — wrap is the third place the plugin commits, alongside ingest and prep).
- **ADR-0012** — Honor `.claude/rules/sessions.md` and `.claude/rules/adventures.md` when present.

## What to avoid

- Don't modify `notes.md` under any circumstance.
- Don't run `git push`. The plugin auto-commits but never pushes — that's a publication decision the GM owns.
- Don't sweep in unrelated GM edits when staging the wrap commit. Stage only files this run wrote.
- Don't write the Log or any extracted file before the GM approves.
- Don't put `[ambiguous]` markers in the proposed-wrap review — clarify before review (ADR-0011).
- Don't invent NPC names, dates, or facts the notes don't support. If the notes don't say, the wrap doesn't say.
- Don't double-write the same fact as both a Thread and a Consequence without explaining the split.
- Don't use the words "DM", "module" (for non-published adventures), "hook" (for Thread), "seed" (for Beat), "recap" / "summary" (for Log), "fact" / "event" (for Consequence). Use the glossary.
- Don't surface every pending Beat in the closing summary — only ones whose status changed.
- Don't dump the entire campaign's Consequence history into `campaign.md`. Keep "Recent significant consequences" glance-readable.
