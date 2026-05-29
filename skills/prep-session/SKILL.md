---
name: prep-session
description: Create a pre-session Brief seeded from current campaign state. Use when the GM invokes `/prep-session`, asks to prep the next session, or wants a starting Brief generated from active Adventures, open Threads, pending Beats, recent Consequences, and the prior session's Log.
---

# /prep-session

You are preparing a TTRPG **Session** Brief for a **GM**. The campaign repo is the current working directory (or a directory the GM names). This workflow creates a new **Session** directory and writes its `brief.md` by drafting from current campaign state, presenting a diff-style review, and only writing once the GM approves.

Follow the domain vocabulary defined in the campaign repo's `CLAUDE.md` and the plugin's `CONTEXT.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Campaign overview**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, etc.).

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
                  ├── brief.md      (written by this skill)
                  ├── notes.md      (created empty by this skill)
                  └── log.md        (NOT created here; /wrap-session writes it)
```

If the current working directory is not a campaign repo (no `campaign.md`, no `sessions/`, no `CLAUDE.md` for the campaign), ask the GM where their campaign repo is before proceeding. Don't guess.

## Step 1 — Determine session number and date

1. List `sessions/`. The next **session number** is `1 + max(N)` across existing `sessions/YYYY-MM-DD-session-N/` directory names. If `sessions/` is empty or absent, N = 1.
2. The default **date** is today's date in `YYYY-MM-DD`. If the GM has indicated a different planned date for the next session, use that instead — but confirm with the GM before using a non-default date.
3. The target directory is `sessions/YYYY-MM-DD-session-N/`.

### Re-run guard (confirm-before-overwrite)

Before doing any work, check whether the target session directory already exists and whether it contains a `brief.md`:

- **Target directory does not exist:** proceed normally.
- **Target directory exists, no `brief.md`:** proceed; you'll write `brief.md` and create `notes.md` if it doesn't already exist.
- **Target directory exists and contains `brief.md`:** STOP. Show the GM the existing `brief.md` path and explicitly ask: *"A brief.md already exists for this session. The GM may have hand-edited it. Overwrite?"* Do not proceed without an explicit yes. If the GM says no, exit without writing anything. If yes, continue with Step 2 and, when you write in Step 5, replace the existing `brief.md`. Never touch an existing `notes.md`.

Also watch for the edge case where the GM is prepping a *different* upcoming session than the auto-detected next one (e.g., they want session 7 but session 6's directory exists without a log because it was cancelled). If anything looks ambiguous about which session number this is, confirm with the GM before creating the directory.

## Step 2 — Read current campaign state

Read enough of the repo to seed every Brief section. Be thorough but don't dump everything into context — quote the relevant lines.

### Last time recap source

- **Default:** the most recent prior `sessions/YYYY-MM-DD-session-N-1/log.md`. Read it for the "Last time" recap (per ADR-0011, the Log is what future Briefs read).
- **First-session fallback (N = 1, or no prior `log.md` exists):** use the most recently active **Adventure**'s narrative state — its `adventures/<name>/` directory, especially any `history.md`, `overview.md`, or equivalent narrative file the GM has authored. If multiple Adventures are `status: active`, prefer the one most recently `started` (or, for ingest-era Adventures, the highest `order:`). If no Adventures exist either, set "Last time" to a short note that this is the campaign's opening session and there is no prior state yet — don't fabricate a recap.
- If the prior session has a directory but no `log.md` (the GM hasn't run `/wrap-session` yet), say so explicitly in the Brief and fall back to that session's `notes.md` if it exists, then to the active-Adventure source. Never silently swap sources.

### Other state to pull

- **Active Adventures:** every `adventures/<name>/` whose frontmatter `status: active`. Read each adventure's main file (e.g., `<name>.md` or `overview.md`) for a one-line summary of current state.
- **Open Threads:** every file in `threads/` with frontmatter `status: open`. Filter to those plausibly relevant to current active Adventures, recent location, or the party's current trajectory. If unsure about relevance, include it — false positives are cheaper than missed reminders.
- **Pending Beats:** every file in `beats/` with frontmatter `status: pending`. Use backlinks (Beats referenced by `[[wiki link]]` from an active Adventure file) to scope. Campaign-wide pending Beats with no Adventure scope are also candidates.
- **Recent significant Consequences:** files in `consequences/` ordered by recency (creation/modified date or a `created:` frontmatter field if present), filtered to those likely to come up given current location/Adventure. Don't list every Consequence in the campaign — pick the ones that interact with what's about to happen.
- **NPCs the party may encounter:** Reference notes from `npcs/` that are linked from active Adventures or the prior session's Log, plus locally-relevant recurring NPCs (those tied to the party's current location).
- **Locations:** the party's current location and likely next locations, drawn from the prior Log's closing state and the active Adventure's geography.
- **Items in play that might matter:** PC inventory items (from `items/` or per-PC notes if the campaign tracks them that way) that interact with active Adventures or open Threads.
- **`campaign.md`** at the campaign root — the **Campaign overview** is the agent-maintained snapshot of current state (ADR-0007); use it to cross-check what counts as "active" / "current".

Honor `.claude/rules/sessions.md` and `.claude/rules/adventures.md` if present — they describe campaign-local conventions.

## Step 3 — Draft `brief.md`

Draft the Brief with **all** sections from ADR-0010, **in this exact order and with these exact section headings**:

```markdown
# Session N Brief

## Last time

<3-5 sentence recap from the source determined in Step 2. State the
source explicitly in a parenthetical at the end if it's not the
prior log — e.g., "(from adventures/lost-mines/overview.md; no
prior session log yet)".>

## Active adventures

- **<Adventure name>** — one-line current state.
- ...

## Open threads (likely to surface)

- **<Thread name>** — one-line reminder of what's owed/promised/foreshadowed.
- ...

## Beats to weave in (optional, weave in if possible)

- **<Beat name>** — one-line intent. Optional — land 0–N this session.
- ...

## NPCs the party may encounter

- **<NPC name>** — one-line who-they-are / current stance toward party.
- ...

## Locations

- **<Location name>** — one-line note (where the party is, where they're likely heading).
- ...

## Items in play that might matter

- **<Item name>** — one-line note on why it matters now.
- ...

## Recent significant consequences

- **<Consequence>** — one-line fact about the world that may come up.
- ...

## GM scratchpad

<!-- GM-owned. Foreshadowing reminders, NPC name picks,
"if they go north, then…" branches. Starts empty. -->
```

### Drafting rules

- **Beats section heading must include the "optional, weave in if possible" framing** (ADR-0009). Don't shorten to just "Beats."
- **GM scratchpad starts empty.** Do not pre-populate it with prompts, examples, or boilerplate beyond the HTML comment hint. The comment is fine; any content beyond the comment is not.
- **Every section appears, even when empty.** If there are no open Threads, the section reads `_None._` (or similar terse marker) under its heading. Don't silently omit sections — the GM needs to know the agent looked and found nothing.
- **Use `[[wiki links]]` for Reference notes** (NPCs, locations, factions, items, Threads, Consequences, Beats) so backlinks resolve. Bare names in bullets are fine as the link target.
- **Don't invent content.** If you don't have a fact, don't put it in the Brief. If a section needs the GM to fill something in, say so plainly rather than guessing.
- The Brief is for the GM's eyes, not the party's. It can reference secrets, NPC motivations, planned reveals.

## Step 4 — Diff-style review

Before writing anything to disk, present the full drafted `brief.md` to the GM as a review. Use whatever review affordance Claude Code provides in the current context:

- If a diff-style preview is available (e.g., the file write tool will show a diff), use it.
- Otherwise, show the full draft inline in a single fenced markdown block labelled with the target path, and tell the GM exactly what will be written, where, and which sibling files (`notes.md`) will also be created.

Then ask explicitly: *"Approve as-is, edit inline, or cancel?"* Accept three kinds of response:

1. **Approve** → proceed to Step 5 and write.
2. **Edit** → take the GM's inline edits, apply them to the draft, re-present the updated draft, ask again. Loop until approved or cancelled.
3. **Cancel** → write nothing, leave the filesystem unchanged, exit.

Do **not** write `brief.md` (or create the session directory if it doesn't yet exist) until the GM approves.

## Step 5 — Write

Once approved:

1. Create `sessions/YYYY-MM-DD-session-N/` if it doesn't exist.
2. Write the approved Brief to `sessions/YYYY-MM-DD-session-N/brief.md`.
3. Create `sessions/YYYY-MM-DD-session-N/notes.md` as an **empty file** — no template, no headings, no placeholder content. The GM types into it during play; pre-populating it would defeat its capture-now-structure-later purpose (CONTEXT.md, ADR-0004).
4. Do **not** create `log.md`. `log.md` is written by `/wrap-session` after the session (ADR-0005, ADR-0011).
5. Do **not** commit. The plugin doesn't own ongoing git operations (ADR-0011) — the GM commits when they're ready.

## Step 6 — Closing message

Tell the GM:

- Which files were written and where.
- That `notes.md` is the place to capture during play.
- That `/wrap-session` will produce `log.md` and propose new Threads, Consequences, and Beats from those notes afterward.
- (Optional) a one-line suggested commit message they can use, e.g., `Prep session N (YYYY-MM-DD)`.

Do not auto-commit.

## Quick reference: which ADR governs what

- **ADR-0005** — Session is a directory of three documents; `/prep-session` writes `brief.md` once, doesn't regenerate, confirm-before-overwrite on re-run.
- **ADR-0007** — `campaign.md` is the current-state snapshot; adventure frontmatter (`status`, `order`, `started`) drives "what's active".
- **ADR-0009** — Beats are GM-authored, status `pending|delivered|dropped`; Brief surfaces pending Beats as "weave in if possible".
- **ADR-0010** — Brief section order and propose-then-edit interaction (this skill's primary spec).
- **ADR-0011** — Logs are written by `/wrap-session`; future Briefs read the prior `log.md`.
- **ADR-0012** — Path-scoped rules live in `.claude/rules/`; honor `sessions.md` and `adventures.md` when present.
