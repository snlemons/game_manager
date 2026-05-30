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

## Step 0 — Locate the campaign repo

The skill operates on **a campaign repo**, which may or may not be the current working directory. Don't assume cwd.

1. Check cwd for the campaign-repo markers: `CLAUDE.md` at the root, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, and `campaign.md`. If all four are present, cwd is the campaign repo — use it.
2. If any are missing, **ask the GM** for the absolute path of the campaign repo (e.g., *"I don't see a scaffolded campaign in the current directory. Where is the campaign repo? (Give an absolute path or a `~/`-anchored path.)"*). Resolve their answer to an absolute path. Re-check the four markers there. If still missing, surface what was missing and stop — the campaign isn't scaffolded.
3. Use that absolute path as the **campaign root** for the rest of this workflow. Every path in subsequent steps (e.g., `sessions/...`, `adventures/...`, `beats/...`, `.ttrpg-staging/...`) resolves *relative to the campaign root*, not relative to cwd. Pass absolute paths to file tools so they work regardless of cwd.

Don't repeat the pre-flight if the campaign root is already determined in this run.

### Settings preflight (run once before Step 1)

Before any other work, follow the procedure in `references/preflight.md` against the campaign root resolved above. If the baked paths in `.claude/settings.json` no longer match the current campaign root, the preflight surfaces a regenerate-or-proceed prompt to the GM and handles either outcome. If the GM declines regeneration, continue with the current settings — do not warn again this run. If the GM accepts, the file is rewritten and the skill continues with no further preflight output.

Run the preflight exactly once per `/prep-session` invocation; cache the result for the rest of the run.

## Step 1 — Determine session number and date

### Step 1a: Determine session number

List `sessions/` (under the campaign root). Sort directories by session number. Then:

- **If `sessions/` is empty or absent**: N = 1.
- **If the highest-numbered existing session has a `log.md`** (it was played and wrapped): N = max + 1. This is a new upcoming session.
- **If the highest-numbered existing session has NO `log.md`** (it was prepped but never wrapped — typically because the GM is re-running prep before playing): N = max. **Target the existing session and revise its Brief**, don't create a new one. The Step 4 staging review will surface the existing `brief.md`'s content, and the re-run guard further down handles confirm-before-overwrite. Tell the GM in chat: *"Found `sessions/YYYY-MM-DD-session-N/` with a Brief but no Log — re-prepping the existing session instead of creating a new one. Cancel if you wanted a different session."*

Edge cases:
- The highest-numbered session has a `notes.md` with content but no `log.md` — the GM started playing but hasn't wrapped. Treat as "re-prep the existing session" but warn explicitly: *"This session has in-play notes but no Log. Re-running prep will revise the Brief, not the notes. Continue?"* Wait for explicit confirmation.
- Skipped session numbers (e.g., session 3 exists but session 2 doesn't). Don't try to fill gaps — N = max + 1 if max is logged, max if not.

### Step 1b: Ask the GM for the date

Ask explicitly, even if you have a default in mind: *"What date should this session be filed under? (Today is YYYY-MM-DD. Reply with `today`, a specific date in `YYYY-MM-DD` form, or e.g. `next saturday`.)"* Accept these response shapes:

- `today` (or empty / no override mentioned) → use today's date in `YYYY-MM-DD`.
- An explicit `YYYY-MM-DD` → use it verbatim.
- A relative phrase (`tomorrow`, `next saturday`, `friday`) → resolve to a date and confirm it back: *"That resolves to YYYY-MM-DD — proceed?"* Wait for confirmation before continuing.
- Anything that doesn't parse → tell the GM what you understood and ask them to clarify.

When re-prepping an existing session (Step 1a determined N = max with no Log), the date is **already encoded in the existing directory name** — don't ask, just use it. Tell the GM: *"Using the existing session's date (YYYY-MM-DD) from its directory name."*

### Step 1c: State the planned target path

Before moving to Step 2, state the resolved target in chat:

- New session: *"Prepping new session N for YYYY-MM-DD → will create `sessions/YYYY-MM-DD-session-N/` on approval."*
- Re-prep of existing: *"Re-prepping existing session N → `sessions/YYYY-MM-DD-session-N/`. The current Brief will be replaced after your edit-and-approve in Step 4."*

Then continue without pausing. The Step 4 review is the GM's chance to back out.

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

- **Active Adventures:** every `adventures/<name>/` whose frontmatter `status: active`. Read each adventure's main file (e.g., `<name>.md` or `overview.md`) for a one-line summary of current state. The set may be empty (open-world / sandbox campaigns between arcs) — that's a normal state, not an error to flag (issue #13).
- **Introduced Adventures (menu candidates):** every `adventures/<name>/` whose frontmatter `status: introduced`. Read each adventure's main file for a one-line hook/state. This is the menu of next-session options the party could pick up. In single-arc campaigns this list is usually short or empty; in sandbox campaigns it can be large. If the campaign has 10+ introduced Adventures, surface them all — the GM owns curation, and the Brief showing them is the point of the menu. Order: ascending by `order:` if set, then alphabetical by slug.
- **Open Threads:** every file in `threads/` with frontmatter `status: open`. Filter to those plausibly relevant to current active Adventures, recent location, or the party's current trajectory. If unsure about relevance, include it — false positives are cheaper than missed reminders.
- **Session-driver Threads (menu candidates):** the subset of open Threads substantial enough to drive a session focus, not just flavor reminders. Used in the "Menu of next-session options" section (see Step 3). When uncertain, include rather than drop — the GM scans cheaply.
- **Pending Beats:** every file in `beats/` with frontmatter `status: pending`. Read frontmatter `linked_pcs` / `linked_npcs` / `linked_adventures` / `linked_locations` and use backlinks (Beats referenced by `[[wiki link]]` from an active Adventure file) to scope. **Don't surface all pending Beats in the Brief** — they are filtered into tiers (see "Tiered Beat surfacing" below). Long-running campaigns commonly have many pending Beats after `/ingest`; an unfiltered list defeats the Brief's purpose (ADR-0009).
- **Recent significant Consequences:** files in `consequences/` ordered by recency (creation/modified date or a `created:` frontmatter field if present), filtered to those likely to come up given current location/Adventure. Don't list every Consequence in the campaign — pick the ones that interact with what's about to happen.
- **NPCs the party may encounter:** Reference notes from `npcs/` that are linked from active Adventures or the prior session's Log, plus locally-relevant recurring NPCs (those tied to the party's current location).
- **Locations:** the party's current location and likely next locations, drawn from the prior Log's closing state and the active Adventure's geography.
- **Items in play that might matter:** PC inventory items (from `items/` or per-PC notes if the campaign tracks them that way) that interact with active Adventures or open Threads.
- **`campaign.md`** at the campaign root — the **Campaign overview** is the agent-maintained snapshot of current state (ADR-0007); use it to cross-check what counts as "active" / "current".

Honor `.claude/rules/sessions.md` and `.claude/rules/adventures.md` if present — they describe campaign-local conventions.

### Tiered Beat surfacing

Per ADR-0009, the Brief filters pending Beats by relevance instead of listing them all. Apply the tiers below **after** you've loaded active Adventures, the party's current location, and the cast of PCs and NPCs the party may encounter (you need those signals to score relevance). The output is two lists and two counts that Step 3 renders into the "Beats to weave in" section.

**Inputs computed earlier in Step 2:**

- `IN_FOCUS_ADVENTURES` — the union of (a) every Adventure with `status: active` and (b) every Adventure with `status: introduced` that the Brief is surfacing in its "Menu of next-session options" section (see Step 3). This is the **in-focus Adventure set** per the broadened ADR-0009 rule: active arcs the party may continue, plus introduced arcs the GM is putting on the menu for this session — both classes are "this might come up next." `introduced` Adventures not in the menu are not in-focus on the Adventure signal; `completed` and `abandoned` Adventures are never in-focus. This broadening was added for open-world / sandbox campaigns where the active set may be empty but several introduced arcs are available (issue #13).
- `IN_FOCUS_PCS` — PCs the prior session's Log foregrounded (named in the recap), PCs the in-focus Adventures explicitly reference, and PCs named in any **open** Thread or **pending** Beat the agent is also surfacing. When focus is ambiguous, default to **all PCs** rather than dropping Beats — false positives are cheaper than missed reminders (the same principle the Threads bullet uses).
- `NEAR_LOCATIONS` — the party's current location, locations one step away in the Reference-note graph (locations linked from the current location's Reference note, or that link to it), and locations the in-focus Adventures' geography names as the party's likely next stops. If the current location is unknown (e.g., the prior Log didn't pin it down), treat `NEAR_LOCATIONS` as empty — don't guess — and Beats with `linked_locations` fall through to the out-of-focus tier on the location signal alone.
- `ENCOUNTERABLE_NPCS` — the same set you compute for the "NPCs the party may encounter" Brief section.

**Per-Beat classification.** For each Beat with `status: pending`:

1. **In-focus — show in full.** The Beat hits at least one of these signals:
   - `linked_adventures` overlaps `IN_FOCUS_ADVENTURES`, **or**
   - `linked_pcs` overlaps `IN_FOCUS_PCS`, **or**
   - `linked_locations` overlaps `NEAR_LOCATIONS`, **or**
   - `linked_npcs` overlaps `ENCOUNTERABLE_NPCS` (secondary signal — Beats tied to an NPC the party is likely to encounter are clearly in focus, even though ADR-0009 doesn't enumerate this tier separately).

   Also treat as in-focus any Beat that has **no `linked_*` fields populated but is backlinked from an in-focus Adventure file** (a `[[wiki link]]` from that Adventure's main file). That backlink is the older scoping convention from before the `linked_*` frontmatter existed; honor it so legacy Beats still surface.

2. **Out-of-focus, linked but not in focus — counted only.** The Beat has at least one `linked_*` field populated, but none of the populated fields overlap any in-focus signal. These get counted with a one-line breakdown by what they're linked to (see Step 3).

3. **Unlinked — counted with a "review and tag" nudge.** The Beat has no `linked_*` fields populated and isn't backlinked from any active Adventure. The Brief should acknowledge the count and nudge the GM to triage tags later, so future prep can use the relevance signal.

**Don't apply the tiers to delivered or dropped Beats** — they aren't candidates for the Brief at all (ADR-0009 lifecycle).

**Tie-breaks and edge cases:**

- A Beat with multiple populated `linked_*` fields counts as in-focus if **any one** signal hits. Don't require all to hit.
- A Beat whose `linked_adventures` names a `status: introduced` Adventure is **in focus** if that Adventure is in the Brief's "Menu of next-session options" — the menu marks the GM's intent that the arc could come up. If the introduced Adventure is *not* in the menu (e.g., the GM has many introduced arcs and this one isn't on the table this session), the Beat is out-of-focus on the Adventure signal alone. Other signals (PC / location / NPC) can still bring it in-focus.
- A Beat that's in focus on multiple signals still appears once in the in-focus list. Don't duplicate.
- When the in-focus list is empty but unlinked or out-of-focus counts are non-zero, still render the section with the counts and the triage nudge — the GM needs to know Beats exist and weren't surfaced (the "agent looked and found nothing surfaceable" signal).

Carry these results into Step 3:

- `BEATS_IN_FOCUS` — list of Beats to render in full (ordered by `created:` ascending so freshly-ingested prep keeps source-doc order).
- `BEATS_OUT_OF_FOCUS_BY_SCOPE` — a small map from scope (`linked_adventures` name, `linked_pcs` name, etc.) to count, used for the breakdown line.
- `BEATS_OUT_OF_FOCUS_TOTAL` — total count across out-of-focus linked Beats.
- `BEATS_UNLINKED_TOTAL` — count of unlinked pending Beats.

### Refresh `campaign.md` from the just-read state

`campaign.md` is the agent-maintained Campaign overview (ADR-0007). Between sessions, the GM may have edited state (closed Threads, marked Adventures, added Reference notes), and the overview can go stale. You've just read all the relevant state to compose the Brief — regenerate `campaign.md` now from the same data, *before* drafting the Brief, so:

- The Brief's "Active adventures" / "Open threads" / "Recent consequences" sections reflect actually-current state, not what a stale `campaign.md` said.
- The overview file is honest by the time the GM opens it for any reason.

**Run the composer at `references/campaign-overview-composer.md`** — that file is the canonical spec for section ordering, sub-bucket rendering, derivation rules, and the determinism contract. `/prep-session` runs the **base composer** with no skill-specific variants: no `## Adventures` history section, no Status / Last event header lines, Consequences truncated to the top 5–10. See the reference's "Skill-specific variants" section for the full list of where `/wrap-session` / `/prep-session` differ from `/ingest`.

Write the regenerated `campaign.md` to `<campaign-root>/campaign.md`.

**This write is independent of Brief approval.** Even if the GM cancels at Step 4, the regeneration stays — the refresh reflects state the GM already changed, it's not a new edit waiting on approval. The agent-maintained file going from stale to current is honesty, not a decision.

Briefly tell the GM in chat that this happened: *"Refreshed `campaign.md` to reflect current state before composing the Brief."* If the regeneration produced no actual diff against the prior `campaign.md` (state was already current), skip the message — it's noise.

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

<!-- If no Adventures have status: active, render `_None._` under this heading. Open-world / sandbox campaigns between arcs may legitimately have zero active Adventures — the "Menu of next-session options" section below is then the forward-looking surface. -->

## Menu of next-session options

<!-- Forward-looking menu the party could pick up next session (issue #13). The set of `status: introduced` Adventures the GM is putting on the table this session feeds the `IN_FOCUS_ADVENTURES` set the Beats section uses. -->

**Introduced Adventures the party could pick up:**

- **[[<Adventure name>]]** — one-line hook/state. *(order N)* if `order:` is set; omit otherwise.
- ...

<!-- If no `status: introduced` Adventures, render `_None._` under this sub-heading. -->

**Open Threads that could become a session focus:**

- **[[<Thread name>]]** — one-line reminder.
- ...

<!-- A curated subset of the full Open threads list — the ones substantial enough to drive a session, not flavor reminders. Render `_None._` if none qualify. -->

<!-- If at least one Adventure was listed under "Active adventures" above, append this line: -->
_Or continue any of the active adventures above._

## Open threads (likely to surface)

- **<Thread name>** — one-line reminder of what's owed/promised/foreshadowed.
- ...

## Beats to weave in (optional, weave in if possible)

<!-- In-focus Beats (BEATS_IN_FOCUS) — show in full. Ordered by `created:` ascending. -->
- **<Beat name>** [[beats/<slug>]] — one-line intent. *(scope: <one of: active Adventure name | PC name | location name | NPC name>)*
- ...

<!-- Out-of-focus linked Beats — counted only. Skip this line if BEATS_OUT_OF_FOCUS_TOTAL == 0. -->
_Plus <BEATS_OUT_OF_FOCUS_TOTAL> more pending Beats linked to other Adventures / PCs / locations not in focus this session (<short breakdown by scope, e.g., "2 in Curse of Strahd, 1 for Darius, 3 elsewhere">). Browse `beats/` if you want to weave one in deliberately._

<!-- Unlinked Beats — counted with triage nudge. Skip this line if BEATS_UNLINKED_TOTAL == 0. -->
_Plus <BEATS_UNLINKED_TOTAL> pending Beats with no `linked_*` tags — review and tag them so future prep can surface them when relevant._

<!-- If BEATS_IN_FOCUS is empty AND both counts above are zero, render `_None._` under this heading. -->
<!-- If BEATS_IN_FOCUS is empty but a count line is non-zero, render the count line(s) and skip the bullets. -->
<!-- Framing stays "optional, weave in if possible" — land 0–N this session. -->


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

- **Order matters: draft "Menu of next-session options" before classifying Beats.** The introduced Adventures listed in the menu feed `IN_FOCUS_ADVENTURES` for the tiered Beat surfacing — the menu is the GM-facing surface and the in-focus signal simultaneously. If you change the menu (add or drop an introduced Adventure), reclassify Beats whose `linked_adventures` references the changed slugs.
- **Active adventures, Menu of next-session options, and Open threads are three distinct sections.** Don't collapse them. The menu is the forward-looking summary the GM scans first; "Active adventures" is the steady-state ongoing list; "Open threads" is the full reminder set. Sandbox campaigns may show `_None._` under "Active adventures" while the menu is rich — that's the open-world case rendering correctly, not a bug.
- **Beats section heading must include the "optional, weave in if possible" framing** (ADR-0009). Don't shorten to just "Beats."
- **Render Beats per the tiered surfacing classification.** The "Beats to weave in" section shows in-focus Beats in full as bullets (with a short `*(scope: …)*` hint identifying which signal hit), then a count line for out-of-focus linked Beats (with a one-line breakdown by scope), then a count line for unlinked Beats (with the "review and tag" nudge). Skip empty count lines; render `_None._` if all three are empty. Never dump every pending Beat into the Brief — that's exactly the wall of text ADR-0009 fixed.
- **GM scratchpad starts empty.** Do not pre-populate it with prompts, examples, or boilerplate beyond the HTML comment hint. The comment is fine; any content beyond the comment is not.
- **Every section appears, even when empty.** If there are no open Threads, the section reads `_None._` (or similar terse marker) under its heading. Don't silently omit sections — the GM needs to know the agent looked and found nothing.
- **Use `[[wiki links]]` for Reference notes** (NPCs, locations, factions, items, Threads, Consequences, Beats) so backlinks resolve. Bare names in bullets are fine as the link target.
- **Don't invent content.** If you don't have a fact, don't put it in the Brief. If a section needs the GM to fill something in, say so plainly rather than guessing.
- The Brief is for the GM's eyes, not the party's. It can reference secrets, NPC motivations, planned reveals.

### Worked example: tiered Beats section

Say a campaign has 22 pending Beats. 4 have `linked_adventures` populated (two of which point at active Adventures); all 22 have `linked_locations` (after the GM's tagging pass). The party is at `[[Phandalin]]`, the active Adventures are `[[Lost Mines of Phandelver]]` and `[[Cult of the Reborn Flame]]`, and `IN_FOCUS_PCS = {Darius, Sera}` from the prior Log.

Classifying the 22 Beats might produce: 5 in-focus (3 hit `linked_locations`, 2 hit `linked_adventures`), 14 out-of-focus linked (other locations / other Adventures), 3 still unlinked because the GM's tag pass missed them. The Beats section then renders roughly:

```markdown
## Beats to weave in (optional, weave in if possible)

- **Old Owl Well rumor at the inn** [[beats/old-owl-well-rumor]] — bard drops the name; sets up the side trail. *(scope: location — Phandalin)*
- **Sera's locket reveal** [[beats/sera-locket-reveal]] — when she next short-rests in a temple. *(scope: PC — Sera)*
- **Goblin ambush from the south road** [[beats/goblin-ambush-south-road]] — combat opener if they leave town. *(scope: Adventure — Lost Mines of Phandelver)*
- **Cult sigil chalked on a door** [[beats/cult-sigil-on-door]] — silent escalation reminder. *(scope: Adventure — Cult of the Reborn Flame)*
- **Darius's old commander recognizes him** [[beats/darius-old-commander]] — passing in the street. *(scope: PC — Darius)*

_Plus 14 more pending Beats linked to other Adventures / PCs / locations not in focus this session (6 in Curse of Strahd, 5 around Neverwinter, 3 elsewhere). Browse `beats/` if you want to weave one in deliberately._

_Plus 3 pending Beats with no `linked_*` tags — review and tag them so future prep can surface them when relevant._
```

This is the desired output shape. The framing stays "optional, weave in if possible" — the GM lands 0–N this session.

## Step 4 — Diff-style review via staging file

**This step follows the shared staging-file review pattern at `references/staging-pattern.md`** — write the proposed final content to the gitignored `.ttrpg-staging/` directory at the campaign root, present a chat summary with continue/cancel ask, re-read on continue to capture GM edits, clean up on cancel.

Prep-session-specific staging shape: a single staged file. Before creating the session directory or writing anything to its final location, write the drafted Brief to `.ttrpg-staging/brief-draft.md` using the Write tool. Claude Code's standard file-write diff shows the full draft to the GM in their IDE. Create `.ttrpg-staging/` if it doesn't exist.

Then ask explicitly: *"The drafted Brief is at `.ttrpg-staging/brief-draft.md`. On approve I'll create `sessions/YYYY-MM-DD-session-N/` and move the brief there (plus an empty `notes.md`). Edit the draft in place if you want changes, then tell me to continue. Or say cancel to exit cleanly. If the session date is wrong, say so now — you can change it before the directory is created."* Accept two response shapes:

1. **Continue** → re-read `.ttrpg-staging/brief-draft.md` to capture any GM edits, then proceed to Step 5 to commit it to its final location.
2. **Cancel** → delete `.ttrpg-staging/brief-draft.md` (and remove `.ttrpg-staging/` if it's now empty), leave the rest of the filesystem unchanged, exit.

Do **not** create `sessions/YYYY-MM-DD-session-N/` or write `brief.md` to its final location during the review — the session directory's existence is the GM's signal that they approved a Brief for that session.

## Step 5 — Write and commit

Once the GM says continue:

1. Create `sessions/YYYY-MM-DD-session-N/` if it doesn't exist.
2. Move `.ttrpg-staging/brief-draft.md` to `sessions/YYYY-MM-DD-session-N/brief.md` (i.e., write the final content there, then delete the staging file). If `.ttrpg-staging/` is now empty, remove the directory.
3. Create `sessions/YYYY-MM-DD-session-N/notes.md` as an **empty file** — no template, no headings, no placeholder content. The GM types into it during play; pre-populating it would defeat its capture-now-structure-later purpose (CONTEXT.md, ADR-0004).
4. Do **not** create `log.md`. `log.md` is written by `/wrap-session` after the session (ADR-0005, ADR-0011).
5. **Make a commit** in the campaign repo capturing this prep's changes. ADR-0011 originally said the plugin doesn't own ongoing git operations, but `/prep-session`'s output is a discrete checkpoint (one Brief + one notes.md + a possibly-refreshed `campaign.md`) — the same category as `/ingest`'s bookend commits. Auto-committing here matches `/ingest`'s behavior and means the GM doesn't have to remember to commit between prep and play.

   Stage the specific files this run wrote:

   - `sessions/YYYY-MM-DD-session-N/brief.md`
   - `sessions/YYYY-MM-DD-session-N/notes.md` (even though empty — having it tracked is what matters)
   - `campaign.md` — only if Step 2's refresh actually produced a diff (use `git diff --quiet campaign.md` or equivalent; skip the add if unchanged)

   Commit message format:
   - New session: `Prep session N (YYYY-MM-DD)`
   - Re-prep of existing session: `Re-prep session N (YYYY-MM-DD)`

   If the commit fails (e.g., git has no user configured), surface the error verbatim and stop — don't try to repair. The brief and notes files stay written; the GM can commit manually.

   Edge case: if the campaign repo has uncommitted changes from other sources mixed in (GM was hand-editing other files between sessions), stage **only** the three paths above. Don't sweep in unrelated changes. If you can't isolate (e.g., `campaign.md` was edited by the GM AND the regen would also edit it), surface the conflict to the GM and ask before staging.

## Step 6 — Closing message

Tell the GM:

- Which files were written and where.
- That `notes.md` is the place to capture during play.
- That `/wrap-session` will produce `log.md` and propose new Threads, Consequences, and Beats from those notes afterward.
- The commit that was just made: hash and message. If the commit was skipped (failure / edge case from Step 5), say so explicitly and tell the GM what's staged or unstaged for them to handle manually.

## Quick reference: which ADR governs what

- **ADR-0005** — Session is a directory of three documents; `/prep-session` writes `brief.md` once, doesn't regenerate, confirm-before-overwrite on re-run.
- **ADR-0007** — `campaign.md` is the current-state snapshot; adventure frontmatter (`status`, `order`, `started`) drives "what's active".
- **ADR-0009** — Beats are GM-authored, status `pending|delivered|dropped`; Brief surfaces pending Beats as "weave in if possible," tiered by relevance (in-focus shown in full; out-of-focus and unlinked counted).
- **ADR-0010** — Brief section order and propose-then-edit interaction (this skill's primary spec).
- **ADR-0011** — Logs are written by `/wrap-session`; future Briefs read the prior `log.md`.
- **ADR-0012** — Path-scoped rules live in `.claude/rules/`; honor `sessions.md` and `adventures.md` when present.
