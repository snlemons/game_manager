---
name: init-campaign
description: Bootstrap a brand-new TTRPG campaign repo. Two modes — from-scratch (collect campaign name + system, elicit a pitch/theme/tone via a conversational refinement loop, optionally collect a PC roster, optionally compose a first Adventure via `/init-adventure`'s in-campaign walkthrough, then scaffold the campaign repo with the pitch landing in `campaign.md` as a GM-authored opener) and docs (point at an existing directory of markdown notes, scaffold the campaign repo, then invoke the shared extraction pipeline — survey + per-doc extraction loop + wrap-up — against the input directory so the docs supply the campaign content). Use when the GM invokes `/init-campaign`, says they want to "start a new campaign" / "spin up a fresh campaign" / "bootstrap a campaign from nothing" / "ingest these notes into a new campaign", or when the GM has *no* existing scaffolded campaign and is starting clean. For extending an already-scaffolded campaign with new content, route to `/ingest` (existing notes) or `/init-adventure` (net-new Adventure).
---

# /init-campaign

`/init-campaign` is the bootstrap entry point for **net-new campaigns** per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md). It replaces the old "invoke `/ingest` to start a fresh campaign" path with a workflow that knows the GM is starting from scratch (or from a small pile of notes) and adapts accordingly.

The skill runs in one of two modes, chosen at Step 3 from a GM-facing prompt:

1. **From-scratch mode** — the GM has no existing notes and wants to bootstrap the campaign through a guided conversation. The skill collects campaign name + system, elicits a pitch via the shared conversational-refinement-loop reference, optionally collects a PC roster, optionally composes a first Adventure by handing off to `/init-adventure`'s in-campaign walkthrough, then scaffolds the campaign repo with the pitch landing in `campaign.md` as a GM-authored opener block the composer preserves verbatim across regens.
2. **Docs mode** — the GM points at an existing directory of markdown notes they want extracted. The skill collects campaign name + system, scaffolds the campaign repo via the shared scaffolder reference, then hands the input directory to the shared extraction pipeline (survey + per-doc extraction loop + wrap-up). Pitch elicitation is **skipped** in docs mode — the docs themselves supply the campaign content and the Phase 4 `campaign.md` regen surfaces the picture. If the GM later wants a curated pitch on top, they can hand-edit `campaign.md`'s GM-authored opener block (the composer preserves whatever the GM authors between the markers verbatim across future regens; see Step 8 of the from-scratch flow for the marker shape).

Follow the domain vocabulary defined in the plugin's `CONTEXT.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Secret**, **Non-ephemeral container**, **Campaign overview**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, "story"/"game" for Campaign, "world" for Atlas, etc.).

## When to invoke this skill

The GM invokes `/init-campaign` to start a brand-new campaign. Typical phrasings: *"start a new campaign"*, *"spin up a fresh campaign repo"*, *"bootstrap a campaign from nothing"*, *"I want to design a new D&D campaign"*.

Route elsewhere if the GM's intent is something different:

- **GM has existing markdown notes they want extracted into an already-scaffolded campaign** → `/ingest` (it walks a pile of docs into structured campaign content; `/ingest` requires a pre-scaffolded campaign and hard-stops otherwise per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md)). If the campaign isn't yet scaffolded, route to `/init-campaign` docs mode (Step 3 below) — it scaffolds first and then composes the same extraction pipeline `/ingest` runs.
- **GM wants to author a single net-new Adventure inside an already-scaffolded campaign** → `/init-adventure` in-campaign mode.
- **GM wants to author a standalone one-shot** → `/init-adventure` standalone mode (it scaffolds a campaign-shaped repo with one pre-populated Adventure per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md)).

`/init-campaign`'s value-add is the **guided bootstrapping conversation** — pitch elicitation, PC roster, optional first Adventure — that's overkill for the `/init-adventure` and `/ingest` cases.

## Inputs the GM provides

At minimum:

- **Target directory** — where the campaign repo should live (e.g., `~/campaigns/my-faerun/`). May be an empty directory or a not-yet-existing directory. The scaffolder reference (Step 1) handles the validation and refuses to overwrite an existing scaffolded campaign.
- **Campaign name** — the human-readable title (e.g., *Faerûn Campaign*, *The Sunless Citadel Revisited*). Used in `CLAUDE.md` and `campaign.md`.
- **System** — the rule system (e.g., *D&D 5e*, *Pathfinder 2e*, *Call of Cthulhu*). Free-form prose.

For the from-scratch branch, the skill additionally elicits:

- **Pitch / theme / tone** — a short paragraph the GM owns describing what the campaign is about. Elicited via the shared conversational-refinement-loop. The GM can supply a polished pitch up front or a freeform description for the agent to polish.
- **PC roster** *(optional)* — names of player characters, with optional one-line descriptions and nicknames. The GM can skip this step entirely per [ADR-0018](../../docs/adr/0018-pc-roster-as-survey-deliverable.md) (empty roster is honest; PCs land later by hand-edit or via `/ingest` against a PC-roster doc).
- **First Adventure** *(optional)* — if the GM wants to author the campaign's first Adventure as part of bootstrapping, the skill hands off to `/init-adventure`'s in-campaign walkthrough as a continuation. Clear skip path: *"just scaffold the campaign, I'll add adventures later"*.

If any of the required inputs are missing, ask the GM for them before doing anything that touches the filesystem. Don't invent campaign names, systems, or paths.

## Step 1 — Collect the campaign name

Ask the GM: *"What's the campaign called?"* (or *"What name should this campaign live under?"*).

Accept any non-empty string. Don't slugify — the campaign name is human-readable prose used verbatim in `CLAUDE.md`'s H1 and `campaign.md`'s header line. If the GM is uncertain, offer a placeholder pattern (*"e.g., 'Faerûn Campaign', 'The Sunless Citadel Revisited', or the name of the central Adventure if it's a one-shot"*) rather than inventing one.

Don't proceed to Step 2 until the GM has named the campaign. The name is load-bearing — it appears in scaffolded files and in every `campaign.md` regen.

## Step 2 — Collect the system

Ask the GM: *"What system?"* — accepting free-form prose (the scaffolder's `{{CAMPAIGN_SYSTEM}}` substitution is a literal string replacement).

Examples to offer if the GM hesitates: *"D&D 5e", "Pathfinder 2e", "Call of Cthulhu 7e", "Blades in the Dark", "homebrew d20"*.

Like the name, the system isn't slugified. Don't proceed without it — it's part of every `campaign.md` regen's header.

## Step 3 — Mode prompt (from-scratch vs. docs)

Ask the GM: *"Do you have a directory of existing notes you want extracted, or are you bootstrapping the campaign from scratch?"* — accepting two response shapes:

- **"From scratch" / "no notes" / "just bootstrap"** → from-scratch branch (Steps 4–9 below).
- **"I have docs at <path>"** → docs branch (Steps D1–D3 below). Collect the input directory path before proceeding; resolve it to an absolute path and confirm it exists and contains at least one markdown file. If the path is missing or empty, ask again or offer to drop into the from-scratch branch; do not invent a docs directory and do not silently fall through to from-scratch.

The mode prompt is **before** any filesystem write. Mode auto-detection from the target directory's contents is **not** the contract here — `/init-adventure`'s cwd-based auto-detection is a different shape (it auto-routes between in-campaign and standalone modes based on existing campaign markers). `/init-campaign` always asks because the docs-vs-scratch distinction is about the GM's authoring intent, not about disk state.

## Docs mode — Steps D1–D3

In docs mode the skill scaffolds the campaign first, then composes the shared extraction pipeline against the input directory. This is mechanically the same workflow `/ingest` runs in Phases 2–4, with `/init-campaign` owning the upfront scaffold (since `/ingest` requires a pre-scaffolded campaign and hard-stops otherwise per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md)).

Pitch elicitation, the PC-roster step from the from-scratch branch (Step 5), and the optional first-Adventure sub-flow (Step 6) are **all skipped** in docs mode. The docs supply the campaign content directly:

- The **PC roster** is established by the extraction pipeline's Phase 2 Step 2.5 (the same shared `../../references/pc-roster-proposal.md` reference, applied against the input docs' skim signals — not against a hand-authored roster the way Step 5 of the from-scratch branch does).
- The **Adventures** land via the per-doc extraction loop's Phase 3 Step 3 Adventure-shape extraction whenever a doc's GM-confirmed description reads as Adventure-shaped.
- The **pitch** is implicit in the source docs; Phase 4's `campaign.md` regen surfaces the picture. The GM-authored opener block (from the from-scratch branch's Step 8) is **not** auto-created in docs mode — there's nothing to put in it. If the GM later wants a curated pitch on top of the docs-derived campaign, they hand-edit `campaign.md` and bracket the prose with the `<!-- gm-opener:start -->` / `<!-- gm-opener:end -->` markers; the composer (per `../../references/campaign-overview-composer.md` "GM-authored opener block preservation") preserves whatever the GM authors between the markers verbatim across every future regen. The pitch-persistence rule from the from-scratch branch (Step 8 #1) applies identically whenever the markers appear — the composer doesn't care which mode created them.

### Step D1 — Scaffold the campaign repo

Apply the **Already-scaffolded?** shape from `../../references/campaign-locate.md` — the same shape Step 7 uses in from-scratch mode. The scaffolder's Step 1 marker check decides whether the target already has a scaffolded campaign (refuse to clobber) or is empty / non-campaign-content (proceed). Docs mode differs from from-scratch mode only in what runs *after* the scaffold (the extraction pipeline, not pitch elicitation); the scaffold itself is identical.

Run the shared scaffolder reference at `../../references/scaffolder.md` against the target directory. Inputs are the campaign name (Step 1), the system (Step 2), and the target directory. The scaffolder handles target-directory validation, the seven template writes with placeholder substitution, `git init`, and the initial commit (*"Scaffold campaign repo via ttrpg-gm /ingest"* — the commit message is stable across consumers per the scaffolder reference's Step 3 note).

The scaffolder's Step 1 (target validation) is the only place docs-mode-specific guidance applies: when the target directory already contains source docs the GM wants extracted, the scaffolder's "exists but non-empty without markers" branch fires (Step 1.4) and asks for GM confirmation before scaffolding alongside the existing files. Confirm with the GM, then proceed. The scaffolder will leave the input docs untouched (they aren't in its `git add` set) and land the campaign-shape files alongside them.

If the input directory and the target directory are **distinct** paths (the common case — the GM points at `~/notes/old-campaign/` for docs and wants the campaign at `~/campaigns/new-campaign/`), the scaffolder's Step 1.4 branch doesn't fire and the scaffold runs cleanly. The input directory is read-only throughout the extraction pipeline; nothing in this skill ever writes to the input path.

After the scaffolder's initial commit lands, the target directory is a fresh campaign repo and becomes the **campaign root** for the rest of this run.

### Step D2 — Run the shared extraction pipeline

Hand the scaffolded campaign root and the input directory to the shared extraction pipeline at `../../references/extraction-pipeline.md`. That reference is the canonical spec for Phases 2 (survey: bounded skim, description + PC-roster proposal, processing-order proposal), 3 (per-doc extraction loop with cross-doc dedup, carried-forward lessons, per-doc commits), and 4 (wrap-up: bulk-prompt for missing Adventure `order:` values, regenerate `campaign.md` per the composer, follow-up commit). All three phases run identically to the way `/ingest` consumes the same reference — `/init-campaign`'s only addition in docs mode is the upfront scaffold (Step D1 above).

The pipeline owns its own staging files (`.ttrpg-staging/survey-descriptions.md`, `.ttrpg-staging/survey-pcs.md`, `.ttrpg-staging/survey-order.md`, per-doc `.ttrpg-staging/doc-<N>/` trees, `.ttrpg-staging/adventure-order.md`), per-doc commits (`/ingest doc <N>/<total>: …`), and wrap-up commit (`/ingest wrap-up (…)`). The agent does **not** re-implement any of that here — the reference is the spec.

The pipeline's commit-subject prefixes still read `/ingest doc …` and `/ingest wrap-up …` even when run from `/init-campaign` — the prefix is the *workflow's* identifier (the extraction pipeline), not the invoking skill, so the commit log stays consistent whether the pipeline ran via `/ingest` or via `/init-campaign` docs mode. This is the same shape Phase 1's scaffold commit follows (*"Scaffold campaign repo via ttrpg-gm /ingest"* regardless of consumer per the scaffolder reference's Step 3 note).

#### Cancel paths within Step D2

The extraction pipeline owns its own cancel surfaces (Phase 2's continue/cancel ask covering both staged files; Phase 3's refined cancel-mid-Phase-3 prompt with Keep all / Reset to before doc K / Abandon entirely; Phase 4's hold-or-proceed pre-flight). `/init-campaign` does not interpose additional cancel prompts during Step D2 — the pipeline's cancel branches handle the lifecycle.

The Step D1 scaffold commit is the lower bound of *Abandon entirely*: if the GM picks Abandon at Phase 3, the pipeline's `git reset --hard` resets to the scaffold commit (the same lower bound `/ingest` uses), leaving the GM with a freshly-scaffolded but otherwise empty campaign. `/init-campaign`'s docs-mode run is then complete — the scaffold survives, the GM can re-run `/init-campaign` against a different input directory or hand-edit from the scaffold.

### Step D3 — Closing message

After the extraction pipeline's Phase 4 closing summary, add `/init-campaign`'s own one-line closing note: tell the GM the docs-mode run is complete, the target directory is at *(absolute path)*, the input directory was *(absolute path)*, and that the commit chain in the campaign repo now reads `Scaffold campaign repo via ttrpg-gm /ingest` → per-doc commits → `/ingest wrap-up (…)`. A next-step hint: *"Run `/prep-session` whenever you're ready to play, or `/init-adventure` to add a net-new Adventure on top of what the docs supplied."* If the GM later wants to add a GM-authored pitch opener, point them at the marker shape documented under Step 8 #1 below.

The from-scratch mode's Steps 4–9 (pitch elicitation, optional PC roster, optional first-Adventure sub-flow, scaffold, promote staging, closing message) do **not** run in docs mode — the docs-mode flow ends here at Step D3.

## Step 4 — Collect and refine the pitch (from-scratch mode)

The pitch is a short paragraph the GM owns describing what the campaign is about — premise, theme, tone, the central question, anything load-bearing for downstream Briefs and Adventures.

### Step 4a — Ask the GM for a starting pitch

Open with: *"In a paragraph or two, what's this campaign about? Pitch it to me — premise, theme, tone, what the party is being drawn into. If you already have something polished, send it whole; if you have a rough idea, sketch it and I'll help shape it into a pitch."*

Accept two response shapes:

- **Polished pitch** — the GM sends a full paragraph (or two) they're happy with. Treat it as the starting draft.
- **Freeform description** — the GM sketches the idea loosely (a tone word, a premise sentence, a couple of bullets). The agent polishes the description into a draft pitch paragraph. **Do not invent setting details the GM didn't supply** — polishing means tightening prose and surfacing structure, not adding worldbuilding the GM hasn't asked for.

### Step 4b — Stage the pitch and run the refinement loop

Once a starting draft exists, run the shared conversational refinement loop from `../../references/conversational-refinement-loop.md` against the pitch. The `/init-campaign`-specific bindings to the shared loop:

- **Staging path.** `.ttrpg-staging/init-campaign/pitch.md` at the target directory. Create the staging directory lazily if it doesn't exist. *(For from-scratch mode the target directory may not yet exist — create it on first staged write, but do not run the scaffolder yet. Cancel cleanup deletes the staging directory and, if the target was created by this run, also removes the empty target.)*
- **Initial-draft content.** The polished-or-freeform pitch the GM supplied (or the agent polished), rendered as a single H1 (`# <Campaign name> — Pitch`) followed by the pitch paragraph(s).
- **Final-location target.** The pitch lands in `campaign.md`'s GM-authored opener block (see Step 7 below). Do **not** write `campaign.md` at this step — the scaffolder hasn't run yet.
- **Loop preamble text.** *"Pitch draft is at `.ttrpg-staging/init-campaign/pitch.md`. I have `N` follow-up question(s) to help you sharpen it — or say 'looks good' / 'skip questions' to finalize as-is."*
- **Question queue.** Computed per the categories below.

### Step 4c — Question categories for pitch refinement

Evaluate each category against the staged pitch draft. Each category whose predicate fires contributes one (or a small batched set of) question(s) to the loop's queue. Closely-related questions batch into the same turn; unrelated categories surface in separate turns; the catch-all runs last (per the shared loop reference).

1. **Tone-and-genre check.** Fire if the pitch doesn't name a tone or genre framing (no words like *gritty*, *high-fantasy*, *noir*, *horror*, *hopeful*, *political*, *survival*, *heist*, etc.). Ask: *"What's the tone? One or two words — what feeling should the table walk away with after a session?"*. Accept-shape: append the tone descriptor as a short sentence in the pitch (e.g., *"Tone: gritty noir with a thread of dark comedy."*).

2. **Central tension check.** Fire if the pitch doesn't surface a central tension or driving question (no antagonist, no goal, no stakes named). Ask: *"What's the central tension — the conflict or driving question the campaign keeps coming back to?"*. Accept-shape: add a sentence naming the tension to the pitch body.

3. **Stakes check.** Fire if the pitch names a tension but no stakes (no "if the party fails, X" framing implied). Ask: *"What's at stake if the party doesn't engage? A city falls, a god wakes, a friend dies — what's the consequence the campaign is daring the party to prevent?"*. Accept-shape: weave a stakes clause into the central-tension sentence (or add a follow-up sentence).

4. **Setting anchor check.** Fire if the pitch names no place, region, or setting hook (no city, no map, no setting concept like *frontier*, *the planes*, *post-collapse*). Ask: *"Where does this campaign live geographically — a city, a region, a setting concept? Just a name or a phrase, the GM-authored opener is the GM's voice, not a wiki entry."*. Accept-shape: add a setting anchor sentence near the start of the pitch.

5. **Catch-all "anything else".** Always fires; runs **last**. Ask: *"Anything else you want in the opener — a campaign-specific house rule note, a content warning the table agreed on, a vibe phrase you'd open every session with? Skip if not."*. Accept-shape: append a short paragraph below the main pitch.

If none of the predicates fire (the GM supplied a polished pitch that already names tone, tension, stakes, and setting), the loop skips directly to Step 5 — but the loop preamble still mentions the staging path so the GM knows where the pitch lives and can hand-edit it.

Per the shared loop reference: re-read the staged pitch at the top of every turn, treat mid-loop GM hand-edits as authoritative, use Edit (not Write) for revisions, accept verbal-skip exits at any turn, no re-prompting within a run.

### Step 4d — Approval gate (loop exit)

When the GM signals approve at any point in the loop, ask:

*"On approve I'll fold this pitch into the scaffolded `campaign.md` as a GM-authored opener block — the composer will preserve it verbatim across future regens. Confirm continue, or cancel to exit cleanly."*

Accept two response shapes:

1. **Continue** → re-read `.ttrpg-staging/init-campaign/pitch.md` to capture final GM edits, then proceed to Step 5.
2. **Cancel** → delete `.ttrpg-staging/init-campaign/pitch.md` (and `.ttrpg-staging/init-campaign/` if empty; and `.ttrpg-staging/` if empty; and the target directory if this run created it and it's now empty), exit without writing.

## Step 5 — Optional PC roster

After the pitch is approved (still in staging), ask the GM: *"Want to register the party now, or skip? If you have PCs in mind, list their names (one per line, with optional one-line descriptions or nicknames). Empty is fine — you can add PCs later by hand-editing `pcs/` or by running `/ingest` against a PC-roster doc per ADR-0018."*

Two response shapes:

- **GM provides one or more PC entries** → consume the lines as PC roster entries per the shared PC roster proposal reference at `../../references/pc-roster-proposal.md`. Skim signals don't apply here (no source docs to skim) — the GM is hand-authoring the roster. Stage each PC stub at `.ttrpg-staging/init-campaign/pcs/<slug>.md` per the reference's stub-staging shape (frontmatter `kind: pc`, optional `aliases:`, H1 + optional one-line body). Slug per `../../references/dedup-matching.md`'s normalization rule.
- **GM skips** *(per [ADR-0018](../../docs/adr/0018-pc-roster-as-survey-deliverable.md): empty roster is the honest default)* → no PC stubs staged. Proceed to Step 6.

No collision check is needed for this run — the campaign repo doesn't exist yet, so every PC stub is a CREATE. Step 8's promotion (see below) writes the stubs to `pcs/<slug>.md`.

## Step 6 — Optional first-Adventure sub-flow

Ask the GM: *"Want to draft a first Adventure now — premise, hook, locations, NPCs, secrets, set-pieces — or just scaffold the campaign and add adventures later?"* Two response shapes:

- **"Skip" / "just scaffold" / "add adventures later"** → no first Adventure. Proceed to Step 7.
- **"Yes, draft a first Adventure"** → compose `/init-adventure`'s in-campaign-mode walkthrough as a continuation of this run.

When the GM opts in to a first Adventure, the workflow runs in this order:

1. **Scaffold the campaign first** (Step 7 below). The in-campaign walkthrough from `../init-adventure/SKILL.md` requires a scaffolded campaign root — its Step 0a marker check expects `CLAUDE.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, and `campaign.md` already present.
2. **Promote the pitch and PC stubs first** (Step 8 below) so the campaign is fully bootstrapped before the Adventure sub-flow lands its content.
3. **Then hand off to `/init-adventure`'s in-campaign Step 2 walkthrough** — skip its Step 0 (mode detection) and Step 1 (standalone scaffolding) since we already know we're in-campaign mode and have just scaffolded. The Adventure-content walkthrough is the conversational-refinement-loop pass that elicits premise, hook, Locations, NPCs, Secrets, Clues, set-pieces, and escalations. Its Step 3 (approval gate) and Step 4 (promotion + commit) handle the rest.
4. **The Adventure's commit becomes the second commit** in the campaign repo (after the scaffolder's initial commit). Per `/init-adventure` Step 4's commit-message format, in-campaign mode uses *"Add adventure: <Adventure name>"*.

If the GM cancels mid-Adventure-sub-flow, the cancel-path semantics of `/init-adventure` apply — the staged Adventure content is deleted, but the scaffolded campaign (and any promoted pitch + PC stubs) stays. The GM has a clean scaffolded campaign with the pitch landed and no Adventure content yet, and can re-run `/init-adventure` or write the Adventure by hand later.

The two-skill composition is intentional per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md) — the first-Adventure surface lives in `/init-adventure` so the same prose serves both bootstrapping and net-new-Adventure-in-existing-campaign cases.

## Step 7 — Scaffold the campaign repo

Apply the **Already-scaffolded?** shape from `../../references/campaign-locate.md` — that reference is the canonical spec for the four-marker check that decides whether the target already has a scaffolded campaign (in which case the scaffolder refuses to clobber) or is empty / non-campaign-content (in which case the scaffolder proceeds). The check is delegated to the scaffolder reference's Step 1; `/init-campaign` does not re-implement the marker inspection.

Run the shared scaffolder reference at `../../references/scaffolder.md` against the target directory. The scaffolder handles: target-directory validation (Step 1 — refuse to overwrite an existing scaffolded campaign), the six template writes with placeholder substitution (`{{CAMPAIGN_NAME}}` from Step 1, `{{CAMPAIGN_SYSTEM}}` from Step 2, `{{CAMPAIGN_PATH}}` from the resolved target path), `git init`, and the initial commit (*"Scaffold campaign repo via ttrpg-gm /ingest"* — the commit message is stable across consumers per the scaffolder reference's Step 3 note).

After the scaffolder finishes, the target directory is a fresh campaign repo and becomes the **campaign root** for the rest of this run.

A note on ordering: the pitch refinement loop (Step 4) and the PC roster collection (Step 5) both run **before** the scaffolder, because both surfaces need GM-supplied input the scaffolder uses (the pitch lands in `campaign.md`, the PCs land in `pcs/`). The scaffolder's idempotency contract is strong (it refuses to re-scaffold a populated campaign), so running it once at this point is safe.

## Step 8 — Promote staging to the scaffolded campaign

Once the scaffolder's initial commit lands, promote the staged pitch and PC stubs into the scaffolded campaign:

1. **Promote the pitch into `campaign.md` as a GM-authored opener block.** Read the live `campaign.md` (the scaffolder's placeholder), Edit in a GM-authored opener block between the header (`**System:**` line) and the first agent-managed section (`## Where the party might go next session` in the placeholder, `## Party` once the composer runs). The block uses HTML-comment markers the composer recognizes:

   ```markdown
   <!-- gm-opener:start -->

   <pitch content from `.ttrpg-staging/init-campaign/pitch.md`, with H1 dropped — the pitch's H1 is redundant with `campaign.md`'s header>

   <!-- gm-opener:end -->
   ```

   Per the composer rule extended in `../../references/campaign-overview-composer.md` "GM-authored opener block preservation", the composer preserves the content between these markers verbatim across every future regen (`/wrap-session`, `/prep-session`, `/ingest` Phase 4). The GM can hand-edit the block freely — the composer never touches what's between the markers.

2. **Promote PC stubs from staging to `pcs/<slug>.md`.** Per `../../references/pc-roster-proposal.md`'s "Promotion" section, translate each staged `.ttrpg-staging/init-campaign/pcs/<slug>.md` path to `pcs/<slug>.md` in the campaign root. Create the `pcs/` directory if it doesn't exist. Delete each staged stub after promotion. If the roster was empty (the GM skipped Step 5), no PC promotion happens and `pcs/` stays absent (per [ADR-0018](../../docs/adr/0018-pc-roster-as-survey-deliverable.md)).

3. **Clean up staging.** Delete `.ttrpg-staging/init-campaign/` and `.ttrpg-staging/` (if empty) per the staging-pattern reference's cleanup contract.

4. **Make a follow-up commit.** Stage the specific files this step wrote:

   - `campaign.md` (the pitch landed in the GM-authored opener block).
   - `pcs/<slug>.md` for every PC promoted (skip if the roster was empty).

   Commit message: *"Initialize campaign with pitch (and PC roster)"* — drop the *"(and PC roster)"* parenthetical if no PCs were promoted.

   If the commit fails (e.g., git has no user configured), surface the error verbatim and stop — don't try to repair. The files stay written; the GM can commit manually.

If Step 6 opted in to a first-Adventure sub-flow, the Adventure walkthrough's Step 4 commit (*"Add adventure: <Adventure name>"*) becomes the third commit in the campaign repo, landing after this run's Step 8 commit.

## Step 9 — Closing message

Tell the GM:

- The target directory (absolute path) and the commits that landed (the scaffolder's initial commit, this run's Step 8 commit, and — if applicable — the Adventure sub-flow's Step 4 commit). For each commit, include the hash and message.
- The PC count (or *"no PCs yet — add them later via hand-edit or `/ingest`"* if the roster was empty).
- A next-step hint:
  - If a first Adventure was authored: *"Run `/prep-session` whenever you're ready to play — it'll draft a Brief reading from the just-authored Adventure as session 1."*
  - If no first Adventure was authored: *"Run `/init-adventure` to draft your first Adventure, or `/ingest <docs path>` if you have existing notes you want extracted. Then `/prep-session` once an Adventure is in place."*

## Cancel paths

The skill follows the staging-pattern reference's cancel contract — no file outside `.ttrpg-staging/` (or the not-yet-created target directory) is touched until Step 7's scaffolder runs and Step 8's promotion+commit lands.

### From-scratch mode

- **Cancel at Step 1–3 (before any staging write):** exit cleanly. Nothing on disk changes.
- **Cancel during Step 4's refinement loop (pitch staging exists):** delete `.ttrpg-staging/init-campaign/` and (if empty) `.ttrpg-staging/`; remove the target directory if this run created it and it's now empty. Exit.
- **Cancel during Step 5 (PC roster collection):** delete the staged pitch and any PC stubs that were partially staged. Same cleanup as above.
- **Cancel during Step 6 (first-Adventure sub-flow), before Step 7's scaffolder:** delete all staging. Same cleanup as above.
- **Cancel after Step 7's scaffolder commit:** the scaffolder's commit stays (per the conversational-refinement-loop reference, the scaffolder's commit is its own checkpoint). The GM has a clean scaffolded campaign with no pitch landed yet, and can re-run `/init-campaign` (which will refuse to re-scaffold per the scaffolder's idempotency check — tell the GM to use `/ingest` or hand-edit if they want to continue against the half-bootstrapped repo).
- **Cancel during the Adventure sub-flow (post-scaffolder, post-pitch-promotion):** per `/init-adventure`'s cancel-path semantics, the staged Adventure content is deleted. The scaffolded campaign + pitch + PC roster stay. The GM has a fully-bootstrapped campaign with no Adventure yet.

### Docs mode

- **Cancel at Step 1–3 (before Step D1's scaffolder):** exit cleanly. Nothing on disk changes.
- **Cancel at Step D1 (mid-scaffolder):** the scaffolder reference's own cancel semantics apply; no further `/init-campaign` cleanup is needed.
- **Cancel during Step D2 (extraction pipeline):** the extraction pipeline owns its cancel surfaces (Phase 2's continue/cancel, Phase 3's refined cancel-mid-Phase-3 prompt with Keep all / Reset to before doc K / Abandon entirely, Phase 4's hold-or-proceed). On *Abandon entirely* the pipeline's `git reset --hard` rolls back to the Step D1 scaffold commit — leaving the GM with a freshly-scaffolded campaign and an unaltered input directory. `/init-campaign`'s docs-mode run is then complete.

## Quick reference: which ADR governs what

- **ADR-0007** — `campaign.md` as the agent-maintained Campaign overview; the GM-authored opener block extension (from slice D, still applied in docs mode only if the GM hand-authors the markers later) lives there too via the composer reference.
- **ADR-0008** — Survey + per-doc + wrap-up workflow; docs mode (Step D2) composes the shared extraction pipeline reference that pins this shape.
- **ADR-0011** — Skill-side git operations land their own checkpoint commits (the model `/prep-session`, `/wrap-session`, `/init-adventure` follow); `/init-campaign` follows the same shape at Step 8 in from-scratch mode and inherits the scaffolder + per-doc + wrap-up commit chain in docs mode via the extraction pipeline.
- **ADR-0015** — Conversational-refinement-loop pattern; the pitch elicitation in Step 4 runs on top of the shared loop reference. Docs mode skips Step 4 entirely.
- **ADR-0018** — PC roster collection; Step 5 (from-scratch) consumes the shared `pc-roster-proposal.md` reference with the empty-roster skip path. Docs mode handles PC roster via the extraction pipeline's Phase 2 Step 2.5 instead.
- **ADR-0019** — `/init-campaign` as the bootstrapping front door; this skill is the implementation of that decision. Docs mode is the front-door equivalent of *"scaffold then `/ingest`"*, composed as one workflow.
- **ADR-0020** — Modularization via shared `references/` — the scaffolder, the conversational-refinement-loop, the PC roster proposal, the campaign-overview composer, the extraction pipeline, and `/init-adventure` (composed as a sub-flow) are all shared surfaces this skill consumes via relative paths.
