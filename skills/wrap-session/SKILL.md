---
name: wrap-session
description: Read a session's in-play notes, draft the Log, propose new Threads, Consequences, Secrets, Reference notes, Beat updates (including kind classification), and Adventure status changes, resolve ambiguity with the GM, write approved changes (maintaining bidirectional Secret↔container links and auto-transitioning Secret status when Clue Beats deliver), and regenerate campaign.md. Use when the GM invokes `/wrap-session`, asks to wrap a session, says the session is over and they want to extract structure from their notes, or wants to turn in-play notes into a canonical Log.
---

# /wrap-session

You are completing a TTRPG **Session** for a **GM**. The campaign repo is the current working directory (or a directory the GM names). This workflow is the **Post-session extraction** moment — where messy **In-play notes** become canonical content: a written **Log**, new and updated **Reference notes**, opened and closed **Threads**, new **Consequences**, **Secrets** (with bidirectional `## Secrets` sections in every container they belong to), **Beat** deliveries and proposals (including `kind:` classification and `linked_secrets:` for Clue Beats), **Adventure** status transitions, **Secret** status transitions driven by Clue Beat deliveries, and a regenerated **Campaign overview** (`campaign.md`).

Follow the domain vocabulary defined in the campaign repo's `CLAUDE.md` and the plugin's `CONTEXT.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Secret**, **Non-ephemeral container**, **Campaign overview**, **Post-session extraction**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, "recap"/"summary" for Log, "fact"/"event" for Consequence, "hidden info"/"twist" for Secret, etc.).

## Locate the campaign repo

The campaign repo has this shape (per ADR-0002, ADR-0005, ADR-0007, ADR-0012):

```
<campaign>/
├── CLAUDE.md
├── campaign.md
├── .claude/rules/
├── adventures/<name>/        # each with frontmatter status: introduced|active|completed|abandoned
├── npcs/        locations/   factions/   items/   pcs/
├── threads/                  # status: open | closed | decayed
├── consequences/
├── beats/                    # status: pending | delivered | dropped; optional kind: + linked_secrets:
├── secrets/                  # status: hidden | partially-revealed | revealed; belongs_to: ≥1 non-ephemeral container
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

### Settings preflight (run once before Step 1)

Before any other work, follow the procedure in `../../references/preflight.md` against the campaign root resolved above. If the baked paths in `.claude/settings.json` no longer match the current campaign root, the preflight surfaces a regenerate-or-proceed prompt to the GM and handles either outcome. If the GM declines regeneration, continue with the current settings — do not warn again this run. If the GM accepts, the file is rewritten and the skill continues with no further preflight output.

Run the preflight exactly once per `/wrap-session` invocation; cache the result for the rest of the run.

### Bidi-link lint (run once alongside the preflight)

After the settings preflight resolves, walk the `secrets/`-to-container symmetry using the linter described in `../../references/bidi-link-maintenance.md` (the `lint` operation: scan every container under `npcs/`, `pcs/`, `locations/`, `factions/`, `items/`, and `adventures/<slug>/adventure.md` for `[[secrets/<slug>]]` wiki-links; cross-reference against `secrets/*.md` filenames; emit `orphan` and `missing-back-reference` findings).

Cache the lint output for this run. If there are findings, surface a short summary to the GM up front (do not list every finding inline — name the counts and offer to walk through them at ambiguity clarification): *"Found N bidi-link drift cases in `secrets/` (M orphan wiki-links, K missing back-references). I'll surface specifics during ambiguity clarification."* If a finding overlaps with a container the wrap is touching this run, fold the reconciliation into the staging review for that container.

If `secrets/` does not exist (no Secrets in this campaign yet), the lint is a no-op.

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
- Existing `threads/`, `consequences/`, `beats/`, `secrets/`, and Reference-note files you might be updating or matching against (lazy-read; list directories first, then read files when an extraction candidate plausibly matches by name). For `secrets/` enumeration, follow `../../references/secret-store.md` — the `list_all` and `find_by_container` operations support reverse-lookup queries when notes name an NPC / location / Adventure whose Secrets might be relevant.

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

**Before drafting any Reference-note candidates, consult `../../references/reference-note-extraction.md`** — it defines what counts as a Reference note vs. a passing mention, the folder-by-kind layout, the slug rule for filenames, the one-liner default body, the missing-name handling, and the minimal-frontmatter convention. Apply that heuristic to every NPC, location, faction, or item mentioned in `notes.md` that doesn't already have a file in `npcs/`, `locations/`, `factions/`, or `items/`.

Session-specific orchestration on top of the shared heuristic:

- The candidate's body draws from `notes.md` — one sentence stating who/what they are **and how they appeared this session**. The "this session" framing is the wrap-time distinction.
- Match conservatively. "The captain" in this session is the same as `npcs/captain-marra.md` only if the notes make that link explicit or the prior Log establishes it. When in doubt, flag for clarification (Step 3).
- If the notes reference a thing whose **name is missing or unclear** (e.g., "the blacksmith said…" with no name), defer to Step 3 ambiguity clarification rather than inventing a name.

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

#### Secret-status side effects on delivery

When a Beat being proposed as `delivered` carries `linked_secrets:` populated (every entry is a Secret slug, see `../../references/frontmatter-schemas.md` Beat section), the delivery has knock-on effects on those Secrets — Clue Beats are the primary path, but any Beat with `linked_secrets:` incidentally contributes to revelation per ADR-0014. For each linked Secret slug:

1. **Look up the Secret file.** Resolve to `secrets/<slug>.md` (enumeration spec: `../../references/secret-store.md`, `list_all`). If the file does not exist, surface as ambiguity: *"Beat `<beat-slug>` has `linked_secrets: [<slug>]` but `secrets/<slug>.md` does not exist. Rename the link, create the Secret, or drop the entry?"* Do not silently invent the Secret file.
2. **Append this Beat's slug to `revealed_by:`** on the Secret if it is not already present. The `revealed_by:` list is the historical record of which Beats have contributed to revealing this Secret; idempotent on re-run.
3. **Auto-transition `hidden → partially-revealed`.** If the Secret's current `status:` is `hidden`, propose updating it to `partially-revealed`. This is automatic on the first Clue delivery (or first incidental linked Beat delivery) per ADR-0014. Do not skip this transition — `partially-revealed` is what `/prep-session`'s Secret Push question filters on, so a missed flip means the Secret silently doesn't surface in future Briefs.
4. **Prompt for `partially-revealed → revealed` only when `kind: clue`.** When the delivering Beat is `kind: clue` (the canonical Clue-Beat shape) and the Secret's current `status:` is `partially-revealed` (either already, or as a result of step 3), surface a prompt at ambiguity clarification: *"This Clue revealed [[secrets/<slug>]] ([Secret title]). Is the Secret now fully revealed (`revealed`), or still partial?"* **Default to partial if no answer; never auto-promote to `revealed`.** The GM's judgment is required because partial-to-revealed is the "the party has the picture" line, not a structural condition the agent can compute.
5. **Do not auto-promote for incidental linked Beats.** A Beat with `linked_secrets:` populated but `kind:` other than `clue` is an incidental link; it can flip `hidden → partially-revealed` (step 3) but does not surface the `partially-revealed → revealed` prompt — that prompt is reserved for `kind: clue` to match GM authorial intent (ADR-0014 distinguishes Clue from incidental: a Clue is *primarily* about revelation).
6. **Stage the Secret update.** Every Secret whose `status:` or `revealed_by:` changed is staged as an UPDATE entry under `.ttrpg-staging/wrap/secrets/<slug>.md` per the staging pattern (`../../references/staging-pattern.md`: cp the live file, Edit to apply the change so the IDE diff shows the delta). The Beat-delivery staging and the Secret-update staging both surface in the same Step 4 review.

When the GM is reviewing, if they reject the Beat delivery (delete the staged Beat file), also drop the corresponding Secret updates — the side effects only land when the Beat delivery lands.

### Pass 7 — New Beat candidates

Propose new Beats from:

- The prior `brief.md`'s **GM scratchpad** — items the GM jotted as "if X then Y", "land this next time", name picks they want to use. These are the canonical promotion path (ADR-0009).
- Notes phrases like "I want to set up X next session", "remind me to land Y", "save Z for later".

Propose each as `beats/<slug>.md` with frontmatter `status: pending`, `created: <session date>`, `delivered: ~`, and optional `linked_pcs:` / `linked_npcs:` lists if the scratchpad scoped them. Body: one or two sentences stating the intent. If the Beat is scoped to a specific Adventure, include a `[[wiki link]]` to that Adventure in the body so backlinks resolve (ADR-0009).

#### Classify `kind:` at proposal time

**Apply `../../references/beat-kind-classification.md`** to draft a `kind:` value (one of `news | handout | character-moment | set-piece | clue | escalation`, or `~` unclassified) for every proposed Beat from the Beat's description. The classification is a draft — the GM confirms or overrides at the staging review. A wrong classification the GM corrects at review is cheaper than no classification at all.

When the classification is `kind: clue`, **also draft `linked_secrets:`**:

- If the description names a Secret that already exists (`../../references/secret-store.md`'s `find_dedup_candidates` returns a hit), populate `linked_secrets:` with that Secret's slug.
- If the description names a Secret that does not yet exist (the scratchpad says "Clue: drop that Maren is the spy" and `secrets/maren-is-the-spy.md` is absent), **also propose the Secret** in Pass 7.5 below — the Beat and the Secret are co-proposed for the same staging review.
- If `kind: clue` is the right call but no specific Secret is named, surface as ambiguity at Step 3: *"This Beat is classified as a Clue but doesn't name the Secret it reveals. Which Secret? Or reclassify as `news` / `set-piece`?"*

If the description doesn't clearly match any starter `kind:` value, leave the field unset (`kind: ~`) rather than guessing.

### Pass 7.5 — New Secret candidates

**Apply `../../references/secret-extraction.md`** to identify hints in the notes (and in any Pass 7 Beat proposals classified `kind: clue`) that suggest a hidden fact worth promoting to a Secret. The full extraction heuristic — what shapes of prose suggest a Secret, what shouldn't (already a Consequence, already a Thread the party is pursuing, etc.), how to draft `belongs_to:`, how to dedup — lives in that reference; this Pass is the wrap-session orchestration on top.

Wrap-session-specific orchestration:

- **Source content** is the session's `notes.md` *plus* any Pass 7 Beat candidates whose `kind:` was classified as `clue`. A "Clue: drop that the duke has a half-dragon son" scratchpad item produces both a Beat (Pass 7) and a co-proposed Secret (this Pass) wired together via `linked_secrets:` on the Beat and an implicit `revealed_by:` add on the Secret when that Beat eventually delivers (Pass 6's side-effect step, on the next wrap).
- **Validate `belongs_to:`** for each candidate via `../../references/secret-store.md`'s `validate_belongs_to`. Reject empty, all-ephemeral, or unknown-folder-root candidates and surface to ambiguity clarification rather than staging an invalid Secret.
- **Dedup against existing `secrets/`** via `../../references/secret-store.md`'s `find_dedup_candidates`. Apply the dedup classification per `../../references/secret-extraction.md` and `../../references/dedup-matching.md`:
  - CREATE → stage a new `secrets/<slug>.md`.
  - Confident UPDATE (same Secret, possibly with a new container in `belongs_to:`) → stage an UPDATE on the existing Secret per the staging pattern (cp + Edit).
  - ASK (near-match or ambiguous) → surface at Step 3 ambiguity clarification with the *"merge, separate, or rename?"* prompt.
- **Confirm `belongs_to:` with the GM at the staging review.** The drafted `belongs_to:` list is the agent's best read; the GM trims, adds, or replaces entries by editing the staged file. Per the staging pattern, the GM's edits are the source of truth re-read at promotion time.
- **If `belongs_to:` references a container that does not exist yet** (e.g., the candidate Secret claims `npcs/maren.md` but Maren doesn't have a Reference note), the container needs to land in the same wrap. Propose the Reference note in Pass 2 (CREATE) and the Secret in this Pass; the staging review presents both together, and the GM approves the dependency chain or rejects the unwoven half.

Propose each new Secret as `secrets/<slug>.md` with frontmatter:

- `status: hidden` (Secrets start hidden at extraction time — `partially-revealed` only happens when a linked Beat delivers).
- `belongs_to:` — the GM-confirmed list (drafted at extraction, finalized at approval).
- `revealed_by: []` (empty at creation; populated by Pass 6's delivery side effects on subsequent wraps).

Body: H1 + one or two sentences stating the fact for the GM, drawn from the notes. Use `[[wiki links]]` to the containers in `belongs_to:` so backlinks resolve.

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

**Before proposing any new Thread / Consequence / Beat / Secret / Reference note, apply the matching rule from `../../references/dedup-matching.md`** — it defines the normalization (case-insensitive, strip leading "the", collapse whitespace, hyphenate), what to match against (existing filenames and the first-heading title inside each file), and the three buckets (CREATE / UPDATE / ASK). The test suite at `tests/test_wrap_session_idempotency.py::TestDedupOnRerun` pins this rule against this skill's behavior. For Secrets specifically, the enumeration query is `../../references/secret-store.md`'s `find_dedup_candidates` — scoped to the `secrets/` folder per ADR-0014.

Wrap-session-specific orchestration on top of the shared rule:

- **Recent provenance bias.** For Threads / Consequences / Beats, prefer files whose `created:` (or the session referenced in their body) is recent — within the last few sessions. A new Thread proposal that name-matches an existing **open** Thread created last session is almost certainly the same Thread; treat as a confident UPDATE (or a no-op) rather than a new file. This is what makes a `/wrap-session` re-run idempotent against the same `notes.md`.
- **Secret-specific UPDATE shape: new container in `belongs_to:`.** A confident Secret dedup match may carry a new container the existing Secret doesn't yet list. Treat as a confident UPDATE that *adds* the new container to `belongs_to:` (and triggers a bidi-link write into that container at promotion time per `../../references/bidi-link-maintenance.md`); do not create a duplicate Secret file. The existing Secret's other containers stay in `belongs_to:` unchanged.
- **ASK routes to Step 3 ambiguity clarification** (before the staging review). Don't carry ambiguity into Step 4.

The goal is that re-running `/wrap-session` against the same `notes.md` (after the GM corrected something downstream) produces zero spurious duplicates.

## Step 3 — Ambiguity clarification (BEFORE the proposed-wrap review)

Surface every unresolved question to the GM **before** showing the proposed wrap. The review screen must contain only proposals the agent is confident about (ADR-0011 — "no `[ambiguous]` markers in the proposed-wrap").

Typical ambiguity buckets:

- **Missing names** — "An unnamed blacksmith appears in the notes. Provide a name, or skip creating a Reference note?"
- **Unclear classification** — "The party promised to 'look into' the missing caravan. Thread (active obligation), or narrative color (passing comment)?"
- **Status interpretation** — "Sera 'wasn't pleased' with the party. Update her disposition to hostile, wary, or leave unchanged?"
- **Thread-vs-Consequence framing** — "'The cult knows their faces.' Read this as a Thread (the party owes themselves caution next time) or a Consequence (persistent world fact)? Or both?"
- **Dedup matches** — "`threads/deliver-the-letter.md` already exists. Is this the same Thread, an update, or a new one?"
- **PC vs NPC (safety net)** — per [ADR-0018](../../docs/adr/0018-pc-roster-as-survey-deliverable.md): a named character in `notes.md` whose name doesn't match any existing `pcs/<slug>.md` filename or `aliases:` entry **and** doesn't match any existing `npcs/<slug>.md` either (so the Pass 2 dedup pass would otherwise propose a CREATE under `npcs/`), and whose prose framing reads PC-shaped (named as actor; party-pronoun proximity; new player joined this campaign): "`Marisa` appears in this session's notes as an actor alongside the party — PC or NPC?" On *"PC"*, drop the proposed `npcs/marisa.md` CREATE and stage a `pcs/marisa.md` stub instead, same shape as `/ingest` Phase 2's stubs (`kind: pc` frontmatter, optional `aliases:` from any nickname the GM provides, optional one-line body if the notes give a clear role one-liner — otherwise H1-only). Any Beat `linked_pcs:` or Secret `belongs_to:` references the agent drafted using the rejected NPC slug are rewritten to point at the new PC slug before staging. `/wrap-session` is single-session, so this confirmation does not become a carried-forward lesson — it applies only to this wrap; future sessions re-confirm if needed (though the just-created `pcs/marisa.md` will route subsequent `Marisa` mentions to PC via the standard PC-vs-NPC discriminator in `../../references/reference-note-extraction.md`). On *"NPC"*, the proposed `npcs/marisa.md` CREATE stands. Less load-bearing than the `/ingest` Phase 3 safety net because `/wrap-session` runs against an established campaign where the roster usually exists — but worth including for the case where a brand-new PC first appears in a session log.
- **Reference-note alias relationship** — per [ADR-0017](../../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md): "The notes mention 'The Shadow' with the same role and location as `npcs/maren.md` (same-section dual-name pattern). Merge into `npcs/maren.md` with 'The Shadow' added to its `aliases:` list, or create a separate `npcs/the-shadow.md`?" Apply per the GM's answer: *merge* → UPDATE the existing canonical to append the alias to `aliases:` (preserve every other frontmatter field); subsequent prose mentions of the alias use piped wiki links (`[[npcs/maren|The Shadow]]`). *Separate* → CREATE the new file at the disambiguated slug with no `aliases:` linkage. *Pick canonical from two new candidates in the same notes* → CREATE one file at the chosen slug with the other name in `aliases:`. The prose patterns the agent watches for at extraction time are documented in `../../references/reference-note-extraction.md` under "Alias detection at extraction time." Alias confirmations are session-local — `/wrap-session` is single-session, so no carried-forward lessons; each session's confirmations apply only to that wrap run.
- **Adventure transitions** — "The party left the Sunless Citadel mid-arc to chase another lead. Mark Sunless Citadel as `abandoned`, or keep `active` because they might return?"
- **Beat deliveries on the edge** — "The 'Sera reveals the locket' Beat was set up but the reveal didn't quite land. Delivered, still pending, or dropped?"
- **Beat kind** — "I classified the 'messenger arrives with warfront news' Beat as `news`. Confirm, or reclassify (e.g., `clue` if this is dropping a Secret-shaped fact)?"
- **Clue-Beat without `linked_secrets:`** — "This Beat is classified as a Clue but doesn't name the Secret it reveals. Which Secret? Or reclassify as `news` / `set-piece`?"
- **Secret `belongs_to:`** — "I drafted the new Secret 'Maren is the spy' with `belongs_to: [npcs/maren.md, adventures/the-prism/]`. Confirm both containers, drop one, or add another?"
- **Secret dedup near-match** — "You may already have this Secret at `secrets/<existing-slug>` — merge (add the new container to its `belongs_to:`), separate (treat as a distinct Secret at a disambiguated slug), or rename?"
- **Secret `partially-revealed → revealed`** — "The Clue `<beat-slug>` revealed `[[secrets/<slug>]]` ([Secret title]). Is the Secret now fully revealed (`revealed`), or still partial? (Default: partial.)"
- **Bidi-link drift** — "I found an orphan wiki-link `[[secrets/orin-betrayed-us]]` in `npcs/orin.md` but no `secrets/orin-betrayed-us.md` exists. Heal by removing the link, or do you want to write the Secret?"

Present the questions as a short numbered list. The GM answers in whatever form is easiest (numbered replies, free prose). Apply each resolution back into the extraction set:

- New names update Reference-note proposals (filename and body).
- Classification answers move items between Thread / Consequence / Beat / "neither — drop it".
- Dedup answers convert "new file" proposals into "update existing" proposals.
- Adventure-transition answers change or drop the proposed frontmatter update.

If the GM's resolution surfaces **new** ambiguities (e.g., "actually call her Sera — and she's the same Sera from the Lost Mines, not a new one"), loop: ask the follow-up questions, then refold. Don't proceed to review until the question list is empty.

If there are no ambiguities, say so and move to Step 4 directly. Don't manufacture questions to look thorough.

## Step 4 — Single proposed-wrap review via staging directory

**This step follows the shared staging-file review pattern at `../../references/staging-pattern.md`** — write proposed final content to a gitignored staging directory, present a chat summary with continue/cancel ask, re-read on continue to capture GM edits, clean up on cancel. Consult that reference for the full lifecycle and invariants before proceeding.

Wrap-session-specific staging shape: write the full proposed change set to `.ttrpg-staging/wrap/` in the campaign repo, mirroring the campaign's directory structure. Each proposed file lands at its eventual relative path *inside* `wrap/`:

| Proposed change | Staging path |
|---|---|
| Drafted Log | `.ttrpg-staging/wrap/sessions/YYYY-MM-DD-session-N/log.md` |
| CREATE Reference note | `.ttrpg-staging/wrap/npcs/<slug>.md` (or `locations/`, `factions/`, `items/`, `pcs/`) |
| UPDATE Reference note | `.ttrpg-staging/wrap/<kind>/<slug>.md` — stage per `../../references/staging-pattern.md` Section 2 (cp the live file, Edit to apply the proposed change so the IDE diff shows the delta) |
| CREATE Thread | `.ttrpg-staging/wrap/threads/<slug>.md` |
| UPDATE Thread (closure) | `.ttrpg-staging/wrap/threads/<slug>.md` — stage per `../../references/staging-pattern.md` Section 2 (cp the live file, Edit to apply the closure change so the IDE diff shows the delta) |
| CREATE Consequence | `.ttrpg-staging/wrap/consequences/<slug>.md` |
| CREATE / DROP / DELIVER Beat | `.ttrpg-staging/wrap/beats/<slug>.md` — CREATEs write the full new file (including `kind:` and `linked_secrets:`); DROP / DELIVER are UPDATEs staged per `../../references/staging-pattern.md` Section 2 (cp the live file, Edit to apply the status flip so the IDE diff shows the delta) |
| CREATE Secret | `.ttrpg-staging/wrap/secrets/<slug>.md` — full new file with `status: hidden`, `belongs_to:`, `revealed_by: []` |
| UPDATE Secret (status flip, new container, body merge) | `.ttrpg-staging/wrap/secrets/<slug>.md` — stage per `../../references/staging-pattern.md` Section 2 (cp the live file, Edit to apply the status flip, container addition, or body merge so the IDE diff shows the delta) |
| Container back-reference (bidi-link write) | `.ttrpg-staging/wrap/<container-path>` — stage per `../../references/staging-pattern.md` Section 2 (cp the live container file, Edit to add the `## Secrets` bullet per `../../references/bidi-link-maintenance.md` so the IDE diff shows the delta) |
| UPDATE Adventure (status transition) | `.ttrpg-staging/wrap/adventures/<slug>/adventure.md` — stage per `../../references/staging-pattern.md` Section 2 (cp the live file, Edit to apply the status transition so the IDE diff shows the delta) |
| New Adventure | `.ttrpg-staging/wrap/adventures/<slug>/adventure.md` — full new file |
| `campaign.md` regen | `.ttrpg-staging/wrap/campaign.md` — stage per `../../references/staging-pattern.md` Section 2: if a live `campaign.md` exists, cp it into staging and Edit to apply the regen so the IDE diff shows the previous-vs-regenerated delta; if the file doesn't exist yet, Write the full new content as a CREATE |

For UPDATEs, follow `../../references/staging-pattern.md` Section 2: `cp` the live file from the campaign repo into staging, then apply the proposed change via the Edit tool against the staged copy. Because the cp made the staged content byte-identical to the live file at that moment, the Edit's diff display surfaces the live → proposed delta — so the GM sees the delta the way Claude Code shows changes for any file edit, not a wall of full-file content to spot the change inside.

Then present a summary in chat listing the staged paths and what each represents:

```
Wrap proposal staged at .ttrpg-staging/wrap/. Edit any file in place in your IDE, then tell me to continue. Or delete a staged file to reject that proposal individually.

Files:
  sessions/2026-05-29-session-5/log.md           — drafted Log
  npcs/sera.md                                   — CREATE (new NPC)
  locations/the-broken-mines.md                  — CREATE (new location)
  npcs/captain-marra.md                          — UPDATE
  npcs/orin.md                                   — UPDATE (disposition change)
  threads/cult-of-the-broken-flame.md            — CREATE (new Thread)
  consequences/marra-owes-favor.md               — CREATE (new Consequence)
  beats/orin-armor.md                            — DROP (status: pending → dropped)
  beats/drop-warfront-news.md                    — CREATE (new Beat; kind: news)
  beats/maren-true-allegiance.md                 — CREATE (new Beat; kind: clue, linked_secrets: [maren-is-the-spy])
  secrets/maren-is-the-spy.md                    — CREATE (new Secret; belongs_to: [npcs/maren.md, adventures/the-prism/])
  npcs/maren.md                                  — UPDATE (## Secrets back-link to maren-is-the-spy)
  adventures/the-prism/adventure.md              — UPDATE (## Secrets back-link to maren-is-the-spy)
  secrets/prism-core-is-cursed.md                — UPDATE (status: hidden → partially-revealed; revealed_by appended)
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

**Before writing any lifecycle-object frontmatter, consult `../../references/frontmatter-schemas.md`** — it is the canonical spec for the Thread, Consequence, Beat, Secret, and Adventure schemas (required fields, optional fields, value formats, defaults at CREATE, and update rules). Use it to write every new file and every status transition.

1. **Write `log.md`** to `sessions/YYYY-MM-DD-session-N/log.md`. Overwrite if confirmed in the re-run guard.
2. **Create or update Reference notes** under `npcs/`, `locations/`, `factions/`, `items/`, `pcs/`. Create parent directories if missing. Folder layout and one-liner body shape: see `../../references/reference-note-extraction.md`.
3. **Create or update Threads** under `threads/`. Schema and defaults: see `../../references/frontmatter-schemas.md` ("Thread" section). On closure, set `status: closed` (or `decayed`) and `closed: <session date>`.
4. **Create Consequences** under `consequences/`. Schema and defaults: see `../../references/frontmatter-schemas.md` ("Consequence" section). `/wrap-session` Pass 5 sets `created: <session date>` precisely.
5. **Create or update Beats** under `beats/`. Schema and defaults: see `../../references/frontmatter-schemas.md` ("Beat" section). On delivery, set `status: delivered`, `delivered: <session date>`. On drop, set `status: dropped` and leave `delivered:` null. Preserve `kind:` and `linked_secrets:` from the staged file — these were classified at Pass 7 and confirmed at Step 4 review; do not strip them.
6. **Create or update Secrets** under `secrets/`. Schema and defaults: see `../../references/frontmatter-schemas.md` ("Secret" section). Two write shapes for `/wrap-session`:

   - **CREATE (Pass 7.5):** write a new `secrets/<slug>.md` with `status: hidden`, GM-confirmed `belongs_to:`, `revealed_by: []`. Before writing, re-run `validate_belongs_to` from `../../references/secret-store.md` against the GM-edited `belongs_to:` (the GM may have edited the staged file) to catch hand-edit damage — empty / all-ephemeral / unknown-folder-root cases. If validation fails, surface the failure verbatim and skip this Secret's write; the GM can re-stage.
   - **UPDATE (Pass 6 side effect or dedup merge):** apply the proposed status transition (`hidden → partially-revealed` on linked-Beat delivery; `partially-revealed → revealed` on GM confirmation at ambiguity clarification) and / or append the new Beat slug to `revealed_by:` and / or extend `belongs_to:` with a new container. Preserve every other frontmatter field and every body byte from the staged file.

7. **Maintain bidirectional Secret↔container symmetry.** For every Secret CREATE or `belongs_to:`-extending UPDATE in step 6, run the `apply_belongs_to` algorithm from `../../references/bidi-link-maintenance.md` against each container in the Secret's `belongs_to:` list:

   - Resolve each container path to its file (Reference-note containers ARE the file; Adventure containers resolve to `adventures/<slug>/adventure.md`).
   - If the container file does not exist, surface to the GM and stop the Secret write — do not silently scaffold a container from a Secret. (This case should have been caught at Step 3 ambiguity clarification or at Pass 7.5 dependency-chain handling; if it slipped through, surface now.)
   - Add a `## Secrets` section with the bullet `- [[secrets/<slug>]] — <summary>` if the container does not already back-link this Secret. The "already back-link" check accepts **either** canonical slug-path form (`[[secrets/<slug>]]`) **or** canonical-title display-name form (`[[<title>]]` where `<title>` is the Secret's H1) per `../../references/bidi-link-maintenance.md` — v0.1/v0.2-era campaigns may have display-name back-references already, and re-running on a display-name back-reference is a no-op (not a duplicate write). The writer authors new back-references in canonical slug-path form only. Idempotent on re-apply (a container that already links does not get a duplicate bullet, in either form).
   - The container file edits land in the same step's write pass; the staged container files (per the staging table's "Container back-reference" entry) carry the final content the GM saw and edited.

   For Secret UPDATEs that do not change `belongs_to:` (a pure status flip or `revealed_by:` append), no bidi-link write is needed — the back-references already exist.

8. **Update Adventure frontmatter** in `adventures/<name>/adventure.md`. Schema: see `../../references/frontmatter-schemas.md` ("Adventure" section). Transitions specific to `/wrap-session`:

   - `introduced → active`: set `status: active`, set `started: <session date>` if currently null. Leave `order:` alone — it's ingest-era data.
   - `active → completed`: set `status: completed`, set `completed: <session date>`.
   - `active → abandoned`: set `status: abandoned`, set `completed: <session date>` (per ADR-0007).
   - New adventure that began this session: write the full file with the GM-approved name and slug, `status: active`, `started: <session date>`, other dates null, `order: ~`.

9. **Regenerate `campaign.md`** at the campaign root using the shared composer spec.

   **Run the composer at `../../references/campaign-overview-composer.md`** — that file is the canonical spec for section ordering, sub-bucket rendering, derivation rules (party location from the just-written Log's closing state), and the determinism contract pinned by `tests/test_wrap_session_idempotency.py::TestCampaignMdRegenerationIsDeterministic`. `/wrap-session` runs the **base composer** with no skill-specific variants: no `## Adventures` history section, no Status / Last event header lines, Consequences truncated to the top 5–10 by recency. See the reference's "Skill-specific variants" section for the full list.

   Wrap-session-specific orchestration on top of the composer:

   - **Source for party location:** the just-written Log's closing state. With `[[wiki link]]` to the location's Reference note if identifiable; *"Party location not stated in this session's Log."* if not.
   - **Hand-edit detection:** if the existing `campaign.md` has GM hand-edits that differ from what the composer would produce, the regeneration overwrites (ADR-0007: "Manual GM edits are reconciled or overwritten with warning at next regeneration"). Surface the warning in Step 6's closing message when hand-edits were detected and overwritten.

**Do not modify `notes.md`.** It is the source of truth and stays unchanged (ADR-0005, ADR-0011).

10. **Commit the wrap.** `/wrap-session` auto-commits its discrete checkpoint, matching `/ingest` and `/prep-session` (ADR-0011 amended — see that ADR's "Amendment" section). Stage **only** the files this run wrote or modified:

   - `sessions/YYYY-MM-DD-session-N/log.md`
   - **Every entry inside `sessions/YYYY-MM-DD-session-N/` with any uncommitted state.** Run `git status sessions/YYYY-MM-DD-session-N/` and stage every entry the command surfaces, regardless of git's status code (`M` modified, `??` untracked, `A` added). This captures `brief.md` (the GM may have hand-edited it mid-session — scratchpad ticks, beats marked landed, carry-forward intent), `notes.md` (the GM's in-play authoring, which may be tracked-and-modified after `/prep-session` committed an empty file, or untracked if the session was created retroactively without `/prep-session`), and `log.md` itself. ADR-0005 specifies the three documents are preserved indefinitely as a coherent unit; the wrap is the canonical moment to checkpoint that unit, so these are never "unrelated GM edits."
   - New and updated files under `npcs/`, `locations/`, `factions/`, `items/`, `pcs/`, `threads/`, `consequences/`, `beats/`, `secrets/` — exactly the ones approved at Step 4.
   - Container files under `npcs/`, `pcs/`, `locations/`, `factions/`, `items/`, `adventures/<slug>/adventure.md` modified by bidi-link maintenance (`## Secrets` back-references added or extended). These are the same container files surfaced in the staging table's "Container back-reference" rows.
   - Updated `adventures/<slug>/adventure.md` files where status transitioned.
   - `campaign.md`

   Commit message format (build incrementally based on counts):

   ```
   Wrap session N (YYYY-MM-DD)
   ```

   Or richer when there's a clearly load-bearing change to call out — e.g., `Wrap session 5: Broken Mines active, Captain Marra owes a favor`. Pick at most 1–2 load-bearing items for the subject line; leave the rest for the body if you include one.

   If the commit fails (git has no user configured, hooks reject, etc.), surface the error verbatim and stop. Files stay written; the GM can commit manually.

   Edge case: if the campaign repo has uncommitted changes from other sources mixed in (the GM was hand-editing other files between sessions), stage **only** the paths this wrap touched plus uncommitted entries inside the target session directory (`brief.md`, `notes.md`, `log.md` per ADR-0005). Don't sweep in unrelated GM edits to files outside that session dir. If you can't isolate (e.g., a file the GM hand-edited and this wrap also modified), surface the conflict to the GM and ask before staging.

## Step 6 — Closing message

Tell the GM, concisely:

- A **count summary** of what changed. Example:

  > Wrap complete for session 5 (2026-05-29):
  > - Log written: `sessions/2026-05-29-session-5/log.md`
  > - 3 new Reference notes (2 NPCs, 1 location)
  > - 1 Reference note updated
  > - 2 Threads opened, 1 closed
  > - 1 Consequence added
  > - 1 Beat delivered (kind: clue), 2 new Beat candidates (1 news, 1 unclassified)
  > - 1 new Secret (*Maren is the spy*; `belongs_to: [npcs/maren.md, adventures/the-prism/]`)
  > - 1 Secret status flip: *Prism core is cursed* → `partially-revealed` (revealed by delivered Clue)
  > - 2 container `## Secrets` back-references written
  > - Adventure status: *The Broken Mines* → `active`
  > - `campaign.md` regenerated

  Multi-arc sessions list each Adventure transition on its own line. A session that touched no arc (pure exploration) omits the "Adventure status" line entirely — don't manufacture a transition to fill the bullet (issue #13). Sessions that produced no new Secrets and no Secret status flips omit the Secret-related lines — same posture as Adventure status.

- If the regenerated `campaign.md` overwrote hand-edits, say so explicitly.
- If the Step 0 bidi-link lint surfaced findings the wrap did not heal (orphans the GM declined to address, missing back-references on Secrets the wrap did not touch), name the residual count and the path to act on them. Findings the wrap did heal (Secrets the wrap touched whose containers got their `## Secrets` back-references written this run) do not need to surface separately.
- **The commit that was just made**: hash and message. Example: *"Committed as `a1b2c3d` — `Wrap session 5 (2026-05-29)`."*
- If the commit was skipped (failure from Step 5#10 or the GM had unrelated uncommitted changes the agent couldn't isolate), say so explicitly and tell the GM what's staged or unstaged for them to handle manually.

## Quick reference: which ADR governs what

- **ADR-0003** — Reference notes are one file per item; default content is a one-liner.
- **ADR-0004** — Threads and Consequences are per-file with status frontmatter, created via Post-session extraction. This is the lifecycle reference for both kinds.
- **ADR-0005** — Session is a directory of three documents. `notes.md` is input, `log.md` is output, `notes.md` is never modified.
- **ADR-0007** — Adventure frontmatter (`status`, `started`, `completed`) and the agent-maintained `campaign.md` — you regenerate it at the end.
- **ADR-0009** — Beats are GM-authored or proposed by `/wrap-session`; status `pending | delivered | dropped`; brief-scratchpad items are a primary creation path. Optional `kind:` discriminator (open enum, starter values include `clue`) and `linked_secrets:` field added alongside ADR-0014.
- **ADR-0011** — This skill's primary spec: sequence, ambiguity-before-review, single-batch grouped review, auto-commit the discrete checkpoint (per the amendment in that ADR — wrap is the third place the plugin commits, alongside ingest and prep).
- **ADR-0012** — Honor `.claude/rules/sessions.md` and `.claude/rules/adventures.md` when present.
- **ADR-0014** — Secrets are the fourth lifecycle object; multi-container `belongs_to:` with bidi-link `## Secrets` sections; `hidden → partially-revealed` auto-flips on linked-Beat delivery; `partially-revealed → revealed` is GM-confirmed via a wrap prompt. Clue Beats are `kind: clue` with `linked_secrets:` populated.

## What to avoid

- Don't modify `notes.md` under any circumstance.
- Don't run `git push`. The plugin auto-commits but never pushes — that's a publication decision the GM owns.
- Don't sweep in unrelated GM edits when staging the wrap commit. Stage only files this run wrote — **with one carve-out**: the three documents inside the target session directory (`brief.md`, `notes.md`, `log.md`) are not "unrelated GM edits"; they're the session itself (ADR-0005), and the wrap is the canonical moment to checkpoint the session as a coherent unit. Stage any uncommitted entries inside `sessions/YYYY-MM-DD-session-N/` regardless of whether this run wrote them.
- Don't write the Log or any extracted file before the GM approves.
- Don't put `[ambiguous]` markers in the proposed-wrap review — clarify before review (ADR-0011).
- Don't invent NPC names, dates, or facts the notes don't support. If the notes don't say, the wrap doesn't say.
- Don't double-write the same fact as both a Thread and a Consequence without explaining the split.
- Don't auto-promote a Secret from `partially-revealed` to `revealed`. That transition is GM judgment — surface the prompt, default to partial if no answer, never promote silently (ADR-0014).
- Don't silently scaffold a container from a Secret write. If a Secret's `belongs_to:` claims a container that doesn't exist, surface to the GM and resolve at ambiguity clarification before writing.
- Don't write a Secret without `belongs_to:` validation. Run `validate_belongs_to` from `../../references/secret-store.md` on the GM-edited final list before promoting — empty / all-ephemeral / unknown-folder-root cases must be caught.
- Don't write duplicate `## Secrets` back-reference bullets. The bidi-link maintenance algorithm is idempotent — a container that already links a Secret does not get a second bullet.
- Don't invent new `kind:` values for Beats. The enum is open, but the agent classifies only the documented starter values (`news | handout | character-moment | set-piece | clue | escalation` or `~`); GM-introduced kinds via hand-edit are GM-owned.
- Don't use the words "DM", "module" (for non-published adventures), "hook" (for Thread), "seed" (for Beat), "recap" / "summary" (for Log), "fact" / "event" (for Consequence), "hidden info" / "spoiler" / "twist" (for Secret). Use the glossary.
- Don't surface every pending Beat in the closing summary — only ones whose status changed.
- Don't dump the entire campaign's Consequence history into `campaign.md`. Keep "Recent significant consequences" glance-readable.
