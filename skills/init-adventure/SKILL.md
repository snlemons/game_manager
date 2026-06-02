---
name: init-adventure
description: Author a net-new TTRPG Adventure from scratch by walking the GM through premise, hook, locations, NPCs, secrets and clues, set-pieces, and escalations. Two modes — in-campaign (adds `adventures/<slug>/` to an existing scaffolded campaign) and standalone (scaffolds a campaign-shaped repo with one pre-populated Adventure per ADR-0019). Auto-detects mode from cwd with a GM confirmation prompt before routing. Use when the GM invokes `/init-adventure`, says they want to "start a new adventure" / "draft a one-shot" / "design a new arc", or wants to author Adventure content from scratch rather than ingesting existing notes.
---

# /init-adventure

`/init-adventure` is the workflow for **net-new adventure authoring** — drafting a fresh Adventure from a blank page, as distinct from `/ingest` (which extracts structure from *existing* GM notes) and from `/init-campaign` (which bootstraps a *campaign* from scratch).

The skill runs in one of two modes, auto-detected by the cwd:

1. **In-campaign mode** — cwd is inside a scaffolded campaign repo. The skill adds `adventures/<slug>/` (plus any new Locations, NPCs, Threads, Beats, Secrets the walkthrough produces) to the existing campaign.
2. **Standalone mode** — cwd is NOT inside a scaffolded campaign repo. The skill invokes the shared scaffolder reference first (creating a campaign-shaped repo per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md)), then runs the in-campaign walkthrough against the freshly-scaffolded campaign. Output is structurally identical to `/init-campaign`'s output — a one-shot is a single-Adventure campaign, not a separate repo shape.

Follow the domain vocabulary defined in the plugin's `CONTEXT.md` and (for in-campaign mode) the campaign repo's `CLAUDE.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Secret**, **Non-ephemeral container**, **Campaign overview**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, "story"/"game" for Campaign, "world" for Atlas, etc.).

## When to invoke this skill

The GM invokes `/init-adventure` to author a brand-new Adventure from scratch. Typical phrasings: *"start a new adventure"*, *"draft a one-shot"*, *"design a new arc for the party to pick up"*, *"sketch a heist for next session"*.

If the GM has **existing notes** they want extracted, route them to `/ingest` instead — that skill walks a pile of markdown into structured campaign content. If the GM wants to **start a whole campaign** (multiple Adventures, ongoing arc, full bootstrapping flow), route them to `/init-campaign`. `/init-adventure` is the narrow net-new-adventure case.

The skill is safe to invoke against either an empty directory (standalone mode kicks in) or an already-scaffolded campaign (in-campaign mode kicks in). Mode detection happens before any filesystem writes.

## Inputs the GM provides

The GM provides — at minimum — the **Adventure name** (the human-readable title; e.g., *The Sunless Citadel*, *Heist at the Crimson Ledger*). The walkthrough collects the rest via the shared conversational-refinement-loop reference.

For **standalone mode** the GM additionally provides the **target directory**, the **campaign name** (for one-shots, this is conventionally the same as the Adventure name — the GM can override), and the **system** (e.g., *D&D 5e*, *Call of Cthulhu*).

If any of these are missing, ask the GM for them before doing anything that touches the filesystem. Don't invent names, systems, or paths.

## Step 0 — Mode auto-detection and GM confirmation

Before any work, decide which mode the skill is running in by inspecting the cwd (or a GM-named target directory). The detection is **a check, not a write** — no files change at this step.

### Step 0a — Detect the mode

Check the cwd for the **campaign-repo markers** that identify a scaffolded campaign:

- `CLAUDE.md` at the root
- `.claude/rules/sessions.md`
- `.claude/rules/adventures.md`
- `campaign.md`

Mode resolution:

- **All four markers present in cwd:** in-campaign mode. The cwd is the campaign root for the rest of the workflow.
- **None of the four markers present in cwd, and cwd is empty (or contains only files the GM has confirmed are not a campaign repo, e.g., loose notes the GM has not yet ingested):** standalone mode. The cwd will become the campaign root after the scaffolder runs (or a GM-named subdirectory will).
- **Some markers present, others absent:** the cwd looks like a partially-scaffolded or half-broken campaign. **Stop** and surface to the GM: *"This directory has some campaign markers (`<list present>`) but is missing others (`<list absent>`) — it doesn't look like a fully-scaffolded campaign. Did you mean to run from a different directory? Or is this a broken scaffold I should not write into?"* Wait for explicit GM guidance.
- **Non-campaign content present and not GM-confirmed as safe:** ask before continuing: *"This directory contains files but doesn't look like a scaffolded campaign. Run `/init-adventure` in standalone mode and scaffold a campaign here (alongside the existing files), or did you mean to run from a different directory?"*

### Step 0b — Confirm with the GM before routing

State the detected mode and what it implies, then wait for confirmation before any filesystem write:

- **In-campaign:** *"Detected in-campaign mode — I'll add `adventures/<slug>/` (plus supporting Locations/NPCs/Threads/Beats/Secrets) to the existing campaign at `<absolute cwd>`. Confirm continue, or say 'standalone' if you want a fresh campaign-shaped repo instead."*
- **Standalone:** *"Detected standalone mode — I'll scaffold a fresh campaign-shaped repo at `<absolute target>` (one Adventure pre-populated; structurally identical to `/init-campaign` output per ADR-0019), then walk you through the Adventure content. Confirm continue, or tell me a different target path."*

Two response shapes the confirmation accepts:

1. **Continue / approve** → proceed with the detected mode.
2. **Override** → re-route to the other mode (and re-collect any inputs the new mode needs — e.g., switching standalone → in-campaign requires a campaign root path).

Do not skip this confirmation. Mode auto-detection is a heuristic; the GM owns the final call. The cost of a wrong-mode write is high (scaffolding into an active project, or attaching an Adventure to the wrong campaign), so the explicit confirm-before-write pattern is load-bearing.

## Step 1 — Standalone scaffolding (standalone mode only)

If the GM confirmed standalone mode, run the shared scaffolder reference at `../../references/scaffolder.md` against the target directory before starting the Adventure walkthrough. The scaffolder handles: target-directory validation, the six template writes (`.claude/settings.json`, `CLAUDE.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, `campaign.md`, `.gitignore`) with placeholder substitution, the `git init`, and the initial commit. After the scaffolder finishes, the target directory is a fresh campaign repo and becomes the **campaign root** for the rest of this run.

Two notes specific to standalone mode of `/init-adventure`:

- **Campaign name vs. Adventure name.** A one-shot is structurally a single-Adventure campaign. The GM may want the campaign name and the Adventure name to be the same string (the most common case — *"Heist at the Crimson Ledger"* is both the campaign and the adventure), or may want them distinct (campaign name *"Helly's One-Shots"*, adventure name *"The Whitebridge Job"*). Ask explicitly at Step 0a: *"Should the campaign name be the same as the adventure name (`<adventure name>`), or do you want a different campaign name?"*
- **Pre-populated Adventure.** The scaffolder writes the empty-campaign placeholder for `campaign.md` and does not create `adventures/`. The Adventure content the walkthrough produces in Step 2 lands at `adventures/<slug>/adventure.md` as the *only* Adventure in the freshly-scaffolded campaign. Per ADR-0019, the output is structurally identical to `/init-campaign`'s output — no special "one-shot" markers, no separate repo shape.

If the GM confirmed in-campaign mode, skip this step entirely and go directly to Step 2 — the campaign root is the cwd (or the marker-resolved path from Step 0).

## Step 2 — Adventure content walkthrough (both modes)

The walkthrough drives a multi-turn conversation that elicits the Adventure's content surface from the GM. The **mechanics** of the walkthrough — staging the draft, surfacing follow-up questions, applying revisions via Edit so the GM sees native IDE diffs, accepting verbal-skip exits, treating mid-loop GM hand-edits as authoritative on the next turn's re-read — live in the shared conversational-refinement-loop reference at `../../references/conversational-refinement-loop.md`. This SKILL.md provides the **content** of the walkthrough: the seven Adventure surface elements, in order, with per-element schema notes and per-element file outputs.

The walkthrough produces (subject to GM approval per the loop's continue/cancel contract):

1. **Premise and pitch** → `adventures/<slug>/adventure.md` body.
2. **Hook** → `threads/<slug>.md` (first Thread for the Adventure, `status: open`).
3. **3–5 evocative Locations** → `locations/<slug>.md` (one per Location).
4. **Key NPCs** → `npcs/<slug>.md` (one per NPC).
5. **Secrets and Clues** → `secrets/<slug>.md` (one per Secret) and `beats/<slug>.md` with `kind: clue` (one per Clue Beat) — with `belongs_to:` populated on each Secret per the bidi-link rules below.
6. **Set-pieces and scenes** → `beats/<slug>.md` with `kind: set-piece`.
7. **Escalations** → `beats/<slug>.md` with `kind: escalation`.

Run the steps in order — earlier steps feed later steps. The premise sets the world; the hook lands the party; Locations and NPCs fill the world; Secrets attach to those Locations/NPCs/the Adventure itself; Beats reference all of it.

### Step 2a — Stage the initial Adventure draft

Before the first walkthrough question, create the staging directory `.ttrpg-staging/init-adventure/` at the campaign root and write the empty Adventure scaffold there:

- `.ttrpg-staging/init-adventure/adventures/<slug>/adventure.md` with the Adventure frontmatter (per `../../references/frontmatter-schemas.md` — `status: introduced`, `order: ~`, all dates `~`) and an empty H1 (`# <Adventure name>`).

The `<slug>` is the slug of the Adventure name per the normalization rule documented in `../../references/dedup-matching.md` (lowercase, ASCII-fold, strip leading "the ", collapse non-alphanumerics to hyphens, trim).

Mirror the campaign repo layout under `.ttrpg-staging/init-adventure/` for everything else the walkthrough produces — Locations land at `.ttrpg-staging/init-adventure/locations/<slug>.md`, NPCs at `.ttrpg-staging/init-adventure/npcs/<slug>.md`, etc. — so promotion is path translation per `../../references/staging-pattern.md`.

### Step 2b — Premise and pitch

Ask the GM for a one-paragraph premise: *"In one paragraph, what's this Adventure about? Think pitch — the setup, the central tension, what the party is being drawn into. Three or four sentences."* Edit the premise into the body of the staged `adventure.md` (after the H1, no section heading — it's the intro paragraph).

Do not invent setting details the GM hasn't supplied. If the GM gives a sparse premise, the Adventure body stays sparse — the walkthrough can return to add detail later, and the body is intentionally GM-owned content.

### Step 2c — Hook (becomes the first Thread)

Ask the GM: *"How does the party get pulled into this? What's the inciting hook — the rumor, the contract, the inheritance, the kidnapped patron — that the party hears or is offered?"*

The hook becomes a Thread (per `../../references/frontmatter-schemas.md`'s Thread schema):

- File: `.ttrpg-staging/init-adventure/threads/<hook-slug>.md`.
- Frontmatter: `status: open`, `created: ~` (no session has happened yet — the Thread is authored at design time, not derived from a Log), `closed: ~`.
- Body: the H1 (the hook's short name — e.g., *The Whitebridge Job*, *Letter from Mayor Brennan*) plus a one-line description.

Per CONTEXT.md, **a hook is a Thread, not a "hook"**. Use the canonical vocabulary in the Adventure body too — refer to the Adventure's lead-in as a Thread once it's authored.

### Step 2d — 3–5 evocative Locations

Ask the GM for the Adventure's key Locations: *"Name 3–5 Locations the party will move through — places with a sense of place, not just travel waypoints. For each, give me a name and one sensory or evocative detail (a smell, a sound, an unsettling feature, anything specific) so the Reference note carries a hook the next Brief can recycle (per ADR-0015)."*

For each Location named, follow the Reference-note default shape from `../../references/reference-note-extraction.md`:

- File: `.ttrpg-staging/init-adventure/locations/<slug>.md`.
- Body: H1 (the Location's canonical name) plus a one-line factual description. If the GM supplied a sensory detail, include it as a second sentence (or a separate paragraph) in the body — this is what `/prep-session`'s Locations section will recycle later.
- Frontmatter is optional (minimal-by-default per the reference-note-extraction reference); add `kind: location` only if the GM names a non-obvious case.

If the GM gives only 1–2 Locations, push gently once (*"Do you want to add a couple more, or is this the full set? The Adventure's surface area gets thin under 3"*), then accept the GM's answer — under-counting is preferable to inventing Locations the GM didn't ask for.

### Step 2e — Key NPCs

Ask the GM for the named NPCs the Adventure introduces: *"Who are the named NPCs the party will deal with — the patron, the antagonist, the obstacle, the informant? For each, a name and a one-line role."*

For each NPC named:

- File: `.ttrpg-staging/init-adventure/npcs/<slug>.md`.
- Body: H1 (the NPC's canonical name) plus a one-line role description per `../../references/reference-note-extraction.md`.
- Frontmatter: minimal (per the reference-note-extraction reference); `aliases:` only if the GM mentions a pseudonym, mask, or nickname at this step (per `../../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md`).

PCs are **not** extracted here — `/init-adventure` is the Adventure-content surface, not the party-roster surface. In standalone mode, PC roster is a separate step the GM handles via `/init-campaign` (or by hand-editing `pcs/<slug>.md` after the fact). In in-campaign mode, the PCs already exist under `pcs/`. The walkthrough does not propose PC files.

### Step 2f — Secrets and Clues

Ask the GM for the Adventure's underlying Secrets — the hidden facts the party may learn over the course of running it — and the Clue Beats the GM plans to use to reveal them: *"What's the hidden truth driving this Adventure? List the Secrets — the facts the party doesn't yet know but might discover — and for each, sketch one or two Clue Beats (the scene or moment that reveals part of the truth) the GM is planning."*

For each **Secret** the GM names, follow `../../references/secret-extraction.md` and `../../references/frontmatter-schemas.md`'s Secret schema:

- File: `.ttrpg-staging/init-adventure/secrets/<slug>.md`.
- Frontmatter: `status: hidden`, `belongs_to:` populated with **at minimum** the ingested Adventure (`adventures/<slug>/`, directory form, trailing slash) — the structural link, mandatory per the secret-extraction reference's "Multi-container `belongs_to` population" section. Plus any named NPCs, Locations, or Factions the Secret's prose explicitly names (each as a non-ephemeral container path per the schema's canonical set). `revealed_by: []` at creation time; it grows as Clue Beats are linked.
- Body: H1 (the Secret's short factual name) plus one or two sentences stating the fact for the GM (Secret bodies are GM-eyes — write the fact plainly per the secret-extraction reference).
- **Bidi-link maintenance.** Per `../../references/bidi-link-maintenance.md`, every container listed in `belongs_to:` carries a `## Secrets` back-reference section linking to the Secret. For containers being CREATEd in this same walkthrough (the Adventure file, named Locations / NPCs / Factions from earlier steps), stage the back-reference into the staged container file at this step — `apply_belongs_to` runs against the staged tree, the back-references move to live with the rest of the staging promotion in Step 3. For containers that already exist on disk (in-campaign mode — e.g., the Secret references an existing NPC the GM has from a prior Adventure), follow the staging-pattern wrapper from the bidi-link-maintenance reference: `cp` the live container into staging, Edit the back-reference in, promote on approval.

For each **Clue Beat** the GM sketches, follow `../../references/beat-kind-classification.md` and `../../references/frontmatter-schemas.md`'s Beat schema:

- File: `.ttrpg-staging/init-adventure/beats/<slug>.md`.
- Frontmatter: `kind: clue`, `status: pending`, `created: ~` (design-time, not session-time), `delivered: ~`, `linked_secrets:` populated with the slug of the Secret it reveals (the conventional pairing per the beat-kind-classification reference's "Pairing `clue` with `linked_secrets:`" section), other `linked_*` populated from the same proximity rules the `/ingest` Beat-shape subsection uses (`linked_adventures:` always includes the ingested Adventure, `linked_locations:` for Beats set at a named Location, `linked_npcs:` for Beats involving a named NPC).
- Body: H1 (the Beat's short name) plus one or two sentences describing the scene's intent — what the party learns, how.

If the GM names a Clue Beat that doesn't yet have a Secret backing it, surface as an ambiguity: *"You named a Clue Beat (`<beat name>`) without a Secret it reveals. Want to add a Secret for it, or reclassify the Beat as `news` / `set-piece`?"* Per the beat-kind-classification reference, a `kind: clue` Beat without `linked_secrets:` populated is a known ambiguity case.

### Step 2g — Set-pieces and scenes

Ask the GM: *"What scenes — set-pieces, ambushes, chases, rituals, heist beats — does the GM want to land during this Adventure? For each, a one-line description plus where it happens (which Location) and who's involved (which NPCs)."*

For each set-piece:

- File: `.ttrpg-staging/init-adventure/beats/<slug>.md`.
- Frontmatter: `kind: set-piece`, `status: pending`, `created: ~`, `delivered: ~`, `linked_adventures: [<this-adventure-slug>]` (structural), `linked_locations:` for the Location the scene is set at, `linked_npcs:` for the NPCs involved, `linked_pcs: []` unless the GM scopes a specific PC.
- Body: H1 (the scene's name) plus one or two sentences describing the planned scene.

### Step 2h — Escalations

Ask the GM: *"What's the back-pocket escalation if the party isn't engaging — the reinforcements arriving, the cult succeeding at the ritual, the timer running out? List the levers the GM can pull mid-session to raise stakes."*

For each escalation:

- File: `.ttrpg-staging/init-adventure/beats/<slug>.md`.
- Frontmatter: `kind: escalation`, `status: pending`, `created: ~`, `delivered: ~`, `linked_adventures: [<this-adventure-slug>]` (structural), `linked_*` for other lists populated only when the GM clearly names a Location / NPC / PC the escalation pivots on.
- Body: H1 (the escalation's name) plus a one-line description of the trigger and effect — what happens, when.

### Step 2i — Loop mechanics

The seven content steps above are presented through the shared conversational-refinement-loop reference at `../../references/conversational-refinement-loop.md`. Per that reference, the agent stages the initial draft once, then runs a multi-turn loop where the agent asks one (or a small batched set of) follow-up question(s) per turn, the GM responds, the agent revises the staged files via Edit (so the IDE diff is native), and the loop continues until the GM explicitly approves or cancels.

Practical notes for `/init-adventure` specifically:

- **Question batching.** Closely-related questions (e.g., adding a sensory detail to two Locations) batch into one turn. Unrelated content surfaces in separate turns.
- **Verbal-skip exits.** The GM can say *"looks good"*, *"skip questions"*, *"draft is good"* at any point to exit the question pass and proceed to approval — same as `/prep-session`'s Step 3.5 exit.
- **Mid-loop GM hand-edits.** The GM may open any staged file (Adventure, Location, NPC, Secret, Beat, Thread) and edit it directly in the IDE. Per the conversational-refinement-loop reference, the agent re-reads every staged file at the top of every loop turn and treats those edits as authoritative.
- **GM may skip whole sections.** If the GM doesn't have Secrets in mind for this Adventure yet (or doesn't want any), step 2f produces zero `secrets/` files and zero `kind: clue` Beats. The Adventure can be approved with only premise + hook + Locations + NPCs + set-pieces. Empty Secrets / Escalations are honest defaults; the GM can add them later via hand-edit or a future `/wrap-session` / `/init-adventure` re-run.

If the GM signals cancel at any point in the loop, delete the staging sub-path immediately per the staging-pattern reference's cancel contract — the campaign tree is byte-identical before staging and after cleanup, including in standalone mode (the scaffolder's writes from Step 1 are not rolled back; per the conversational-refinement-loop reference, the scaffolder's commit is its own checkpoint and stays).

## Step 3 — Approval gate (loop exit)

Step 3 is the approve / cancel exit of Step 2's loop, identical in shape to `/prep-session` Step 4's loop exit and following the same staging-file review pattern at `../../references/staging-pattern.md`.

When the GM signals approve, ask:

*"On approve I'll move the staged Adventure (and the Locations / NPCs / Threads / Secrets / Beats) to their final locations under the campaign root. Confirm continue, or cancel to exit cleanly."*

Two response shapes:

1. **Continue** → re-read every file in `.ttrpg-staging/init-adventure/` to capture final GM edits; treat deleted staged files as rejections; proceed to Step 4.
2. **Cancel** → delete `.ttrpg-staging/init-adventure/` (and `.ttrpg-staging/` itself if empty), leave the rest of the filesystem unchanged, exit. In standalone mode the scaffolder's Step 1 commit stays — the GM has a clean scaffolded campaign with no Adventure content yet, and can re-run `/init-adventure` or write the Adventure by hand.

If the GM's loop-exit signal was already unambiguously a continue (*"approve and write it"*, *"ship it"*), the agent may proceed directly to Step 4 without a second confirmation — the loop exit already carried the approve semantic.

## Step 4 — Promote staging to final locations and commit

Once the GM says continue:

1. For each surviving staged file under `.ttrpg-staging/init-adventure/`, translate the staging path to the final path (strip the `.ttrpg-staging/init-adventure/` prefix) and write the file there. Create any missing parent directories (`adventures/<slug>/`, `locations/`, `npcs/`, `threads/`, `secrets/`, `beats/`).
2. After every staged file has moved, run the `apply_belongs_to` algorithm from `../../references/bidi-link-maintenance.md` as a verification pass against the live tree — confirms the bidi-link symmetry the staged writes set up; idempotent no-op if the staged back-references promoted correctly.
3. Delete `.ttrpg-staging/init-adventure/` and `.ttrpg-staging/` (if empty) per the staging-pattern reference's cleanup contract.
4. Regenerate `campaign.md` at the campaign root using the composer reference at `../../references/campaign-overview-composer.md`. In standalone mode this replaces the scaffolder's empty placeholder with a populated overview reflecting the one new Adventure. In in-campaign mode the regen adds the new Adventure to the existing overview.
5. **Make a commit** in the campaign repo capturing this Adventure-authoring's changes. Stage the specific files this run wrote:
   - `adventures/<slug>/adventure.md`
   - `locations/<slug>.md` for every new Location
   - `npcs/<slug>.md` for every new NPC
   - `threads/<slug>.md` for the hook Thread
   - `secrets/<slug>.md` for every new Secret
   - `beats/<slug>.md` for every new Beat
   - Any existing container files whose `## Secrets` sections were updated by the bidi-link maintenance pass (in-campaign mode only — standalone mode's containers are all freshly-CREATEd by this run).
   - `campaign.md` (regenerated in step 4).

   Commit message format:
   - In-campaign mode: `Add adventure: <Adventure name>`
   - Standalone mode: `Initialize one-shot: <Adventure name>` (or `Initialize campaign with adventure: <Adventure name>` when the GM gave a distinct campaign name).

   If the commit fails (e.g., git has no user configured), surface the error verbatim and stop — don't try to repair. The Adventure files stay written; the GM can commit manually.

## Step 5 — Closing message

Tell the GM:

- Which files were written and where (grouped by kind: Adventure, Locations, NPCs, Threads, Secrets, Beats; with counts per kind for batches).
- The commit that was just made (hash and message). If the commit was skipped (Step 4 failure case), say so explicitly and tell the GM what's staged or unstaged for them to handle manually.
- In standalone mode: the next-step hint to run `/prep-session` whenever they're ready to play (which will create `sessions/YYYY-MM-DD-session-1/` and draft a Brief reading from the just-authored Adventure).
- In in-campaign mode: the new Adventure's slug, and that the new Thread (the hook) will surface in the next `/prep-session` run's "Open threads" section.

## Quick reference: which ADR governs what

- **ADR-0007** — Adventure frontmatter schema (`status`, `order`, dates); `campaign.md` as the agent-maintained Campaign overview.
- **ADR-0009** — Beats as GM-authored lifecycle objects; `pending | delivered | dropped`; the optional `kind:` discriminator.
- **ADR-0011** — Skill-side git operations land their own checkpoint commits (the model `/prep-session` and `/wrap-session` follow); `/init-adventure` follows the same shape at Step 4.
- **ADR-0014** — Secrets as multi-container lifecycle objects; `belongs_to:` populated with non-ephemeral containers; bidirectional `## Secrets` link maintenance.
- **ADR-0015** — Conversational-refinement-loop pattern; draft-first-then-converse with the GM through follow-up questions in a multi-turn loop with verbal-skip exits.
- **ADR-0017** — NPC `aliases:` via frontmatter; piped wiki links for in-context rendering.
- **ADR-0019** — Standalone `/init-adventure` produces a campaign-shaped repo (one-shot is a single-Adventure campaign, structurally identical to a regular campaign).
- **ADR-0020** — Modularization via shared `references/` — the scaffolder, the conversational-refinement-loop, the campaign-overview composer, and the frontmatter / secret / beat / bidi-link / reference-note heuristics are all shared references this skill consumes via relative paths.
