# Extraction pipeline

Canonical spec for `/ingest`'s Phases 2 + 3 + 4 — the **survey** that classifies and orders the input docs, the **per-doc extraction loop** that walks them in confirmed order with cross-doc dedup, carried-forward lessons, and per-doc commits, and the **wrap-up** that backfills missing `order:` values, regenerates `campaign.md`, and commits the campaign-level changes.

Consumed by `/ingest` (its primary job) and `/init-campaign`'s docs-mode branch per [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md). The architectural shape this preserves is pinned by [ADR-0008](../docs/adr/0008-ingest-workflow-survey-then-per-doc.md): survey first, then per-doc with learning, then wrap-up.

This reference contains the **shared** workflow. Two pieces stay outside it:

- The **PC roster proposal** (survey Step 2.5 and the stub-promotion in Step 5a/b/c) lives in `pc-roster-proposal.md` (slice B2). The PC roster steers Phase 3's PC-vs-NPC discriminator and the Step 4a safety-net ASK, but its mechanics are independently shareable — `/init-campaign` may also need to propose PCs without running a full extraction. This reference cites that one for the PC-specific bits.
- The exact wording of GM-visible prompts, response-shape lists, and skill-specific orchestration prose (the "what would you like to do?" branches, the Step 6 closing summary phrasing, the hand-off question at the end of Phase 3) stays in the consuming SKILL.md.

The mechanics here — what files are staged where, what counts as CREATE vs UPDATE vs ASK, how lessons accumulate across docs, when per-doc commits land, what the wrap-up commit's scope is — are the shared substance.

## Pre-approval gate seam

**Structural boundary.** Before the per-doc extraction loop opens any staging file for a given doc — that is, between Step 0c's recovery pre-flight and Step 1's bounded-skim-or-survey-description-handoff for doc 1, and between each doc's commit at Step 5.8 and the next doc's Step 1 — there is a **pre-approval gate seam**. The seam is a documented hook for [#27](https://github.com/snlemons/game_manager/issues/27)'s future pre-approval staging gate (a gate that would surface a *condensed* preview to the GM before any staging file is written, so the GM can cancel cheaper than reading a full staged tree).

In v0.3 the seam carries **no gate logic** — every doc proceeds directly from "ready to extract" to "open staging" without any extra prompt. The seam is visible only as a structural boundary so a future gate can slot in without restructuring the per-doc loop.

The seam's invariants — the properties a future gate has to preserve — are:

- **No staging file has been opened yet for this doc** at the seam point. `.ttrpg-staging/doc-<N>/` may not exist; if it exists (from a prior in-flight run that crashed), the recovery pre-flight at Step 0c has already cleaned it up.
- **No campaign-tree file has been modified yet for this doc.** The seam is upstream of every Edit/Write in this doc's iteration.
- **Carried-forward lessons are read-only at the seam.** A gate could surface them as context to the GM but does not modify them.
- **Cancellation at the seam is the cheapest cancel point** — equivalent to the cancel branch of Step 4b before any staging is written. The campaign tree is byte-identical before and after.

The seam is also bounded-length-discipline-friendly for future [#11](https://github.com/snlemons/game_manager/issues/11) context-management work: a gate's preview content sits between Step 0c and Step 1, scoped to one doc at a time, and does not require the agent to hold any state beyond what the seam already requires.

A future implementation of #27 specifies the gate's behavior (preview shape, decline branches, accept-or-cancel response handling). The seam is just where it slots in.

## Phase 2: Survey

The survey phase runs **before** the per-doc extraction loop whenever the input directory contains **one or more** markdown docs. Its purpose, per ADR-0008, is to pre-label every doc with a GM-confirmed one-line description and (for multi-doc runs) fix a processing order — both of which steer extraction in Phase 3. The PC-roster step that sits alongside description-proposal in the same review batch is specified in `pc-roster-proposal.md`; this reference's survey sub-sections name it as Step 2.5 and Step 5a/b/c but defer the mechanics there.

The single-doc case is **stripped, not skipped**: with exactly one markdown doc the input has no ordering question, but the PC roster review is still load-bearing. The single-doc path runs the bounded skim, drafts one description, drafts the PC roster (per `pc-roster-proposal.md`), and hands those off in one review batch (no ordering screen), then drops into the per-doc loop at Step 1. Zero-doc scaffold-only invocations skip survey entirely.

### Step 0: Pre-flight checks

Before doing anything visible:

1. **Campaign repo state.** The same campaign-repo invariants from the per-doc loop's Step 0 apply (`CLAUDE.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, `campaign.md` present; no half-finished prior ingest). If the repo isn't scaffolded or has uncommitted ingest artefacts, stop with the same message the per-doc loop uses.
2. **Input directory state.** List the input directory (flat; ADR-0006 — no recursion).
   - Count markdown files (`*.md`). If zero, tell the GM: *"No markdown docs in this input directory. Nothing to survey."* Stop. This is the scaffold-only path; the PC roster step also defers.
   - If exactly one, run the **stripped survey**: the bounded skim (Step 1), the one-description proposal (Step 2), and the PC roster proposal (Step 2.5, per `pc-roster-proposal.md`) all run; the description+roster staging review (Step 3) runs as a single review batch with one description entry; the ordering step (Step 4) is skipped. Hand off to the per-doc loop via Step 5.
   - If more than one, collect the absolute paths of every markdown doc and continue. Note non-markdown files separately for the closing summary; do not read or process them.

### Step 1: Bounded skim of every discovered doc

For each markdown doc found, read **only** the first heading and the first ~200 words (ADR-0008's "bounded skim"). Do not full-read. Hold the skim text in memory for description-drafting and PC-candidate collection (the same skim text feeds both Step 2's description proposal and Step 2.5's PC roster proposal); discard before Phase 3 starts its full reads, so each doc's full read in Phase 3 is unconstrained by earlier skim residue.

PC-candidate collection from skim signals is specified in `pc-roster-proposal.md`. The bounded-skim discipline above is the *shared* part: ~200 words per doc, no full reads, drop after Phase 2 ends.

If a doc has no heading or is shorter than ~200 words, work with what's there. Don't pad. Don't infer content beyond what's visible in the skim.

### Step 2: Propose a one-line description per doc

For each doc, draft a single-line description that classifies the doc and summarizes what it appears to be about. Use these classifications and keep the vocabulary aligned with CONTEXT.md:

- *"Adventure: <short description>."* — the doc reads as a story arc the party would run (published-module-shaped, homebrew-arc-shaped, or a coherent set of scenes tied to a goal).
- *"World info: <short description>."* — Reference-note-dump-shaped (gods, calendar, regions, recurring NPCs) with no Adventure structure.
- *"Session log: <short description>."* — past-facing narrative of one session's events.
- *"PC source: <slug>'s backstory."* — the doc is a single PC's backstory or character-doc: a first-person or close-third narrative whose subject is one named character, naming family / mentors / hometowns / orders / heirlooms that feed cross-extraction. The `<slug>` is the PC's slug (per `dedup-matching.md` normalization). When this classification fires, the survey hand-off auto-adds `<slug>` to `survey-pcs.md` per `pc-roster-proposal.md`. See "PC source: classification rules" below.
- *"Mixed / ambiguous: <surface the ambiguity>."* — the skim doesn't disambiguate (could be Adventure or world info; could be a Session log or a Reference-note dump).

ADR-0008 explicitly prefers surfaced ambiguity over confident wrong commits. If the skim is genuinely unclear, say so in the description rather than guessing — the per-doc loop will resolve it once the GM clarifies.

#### PC source: classification rules

**When to propose `PC source: <slug>'s backstory`.** The bounded skim *strongly* suggests this classification when the skimmed prose shows backstory-shape signals:

- **Single-named-subject narrative.** The skimmed text centers on one named character — first-person (*"I was born…"*, *"My father…"*) or close-third (*"Aldric grew up in…"*) — and the named subject is not yet known to the campaign roster as an NPC.
- **Backstory-typical heading vocabulary.** Headings like *"Background"*, *"Backstory"*, *"Origin"*, *"History"*, *"Before the Campaign"*, *"Family"*, *"Childhood"* — with the named subject the heading's focus.
- **PC-doc structural signals.** Filename or first heading naming a single character (e.g., `aldric-backstory.md`, `# Aldric of Highmoor`); reference-note-style metadata that fits a single character (class, level, family lineage, hometown), absent the world-info structure of a Reference-note dump.
- **Distinguishes from Session log.** A Session log narrates a *play session* and surfaces multiple PCs as actors; a PC source surfaces *one* PC as the subject of their pre-campaign story. When the skim is genuinely ambiguous between Session log and PC source — e.g., a session narrated in close-third on one PC — surface as `Mixed / ambiguous:` and let the GM disambiguate at Step 3 review.
- **Distinguishes from NPC reference dump.** A bounded skim that shows one named character treated as a Reference-note-dump entry (a paragraph or two of "who this NPC is" inside a roster of NPCs) is *World info:*, not *PC source:*. The PC source classification's signal is that the doc is *about* the character (their story), not a roster entry the doc lists them in.

**When the skim is uncertain.** Propose the closest fit; if the doc's single-named-subject narrative could plausibly be the GM's own PC backstory or a deep NPC writeup, the agent does **not** silently commit — surface the uncertainty in the description (`Mixed / ambiguous: appears to be a backstory for <name>, but may be an NPC writeup. Confirm at review.`). The GM edits to `PC source: <slug>'s backstory` at Step 3 if the named character is a PC; otherwise stays in their preferred bucket.

**Slug derivation.** The `<slug>` is derived from the named-subject's canonical name per the `dedup-matching.md` normalization rule (lowercase, strip "the ", collapse non-alphanumerics to hyphens, trim). The agent picks the slug from the first-heading H1 or the leading proper-name reference in the skim; the GM may edit at Step 3 review (the agent owns the *classification* prefix and the slug shape; the GM owns the trailing description and may correct the slug if the agent guessed wrong).

**Composition with the PC roster.** Per `pc-roster-proposal.md` and ADR-0022, `PC source: <slug>` classifications auto-populate the `## Auto-added from PC source: docs` section of `.ttrpg-staging/survey-pcs.md` at hand-off. Step 5 stages a `pcs/<slug>.md` stub for the slug (unless one already exists, in which case the existing file is pre-seeded and the auto-add is a no-op). The slug from the classification *is* the slug of the stub. If the GM edits the classification's slug at Step 3, the edited slug flows through to both the roster and the stub.

### Step 2.5: Propose a PC roster

See `pc-roster-proposal.md`. The roster proposal aggregates per-doc PC candidates collected during Step 1, classifies them ("Likely PC" / "Possible NPC"), and stages them alongside the description list in Step 3.

### Step 3: Stage the description list and PC roster

Use the campaign repo's `.ttrpg-staging/` directory as the review surface (gitignored by Phase 1; purpose-built for review). Create it if it doesn't exist. Follow `staging-pattern.md` for the staging lifecycle.

Phase 2 stages **two files in a single review batch**: `.ttrpg-staging/survey-descriptions.md` (carries the description list from Step 2) and `.ttrpg-staging/survey-pcs.md` (carries the PC roster from Step 2.5). One continue/cancel ask covers both files; one verbal-refinement loop revises either file in place.

#### Step 3a: Stage the description list

Write the proposed descriptions to `.ttrpg-staging/survey-descriptions.md` using the Write tool. Format each doc as a path header line followed by its description on the next line, with a blank line between entries, and a short header explaining the edit contract (one entry per doc; path lines are fixed; the agent owns the path lines and the GM owns the descriptions). Append a non-editable footer listing any non-markdown files that were skipped.

#### Step 3b: Stage the PC roster

Per `pc-roster-proposal.md`.

#### Step 3c: Ask for the continue/cancel decision (covers both staged files)

Both staged files are presented in the **same review batch** — one continue/cancel ask covers them both. Accept three response shapes:

1. **Continue** → re-read **both** staged files from disk to capture any GM edits. Parse `survey-descriptions.md` lines (record verbatim; surface contract violations if path lines were added/removed). Parse `survey-pcs.md` lines per `pc-roster-proposal.md`. Continue to Step 4 (multi-doc) or Step 5 (single-doc).
2. **Cancel** → delete `.ttrpg-staging/survey-descriptions.md`, `.ttrpg-staging/survey-pcs.md`, and any staged `.ttrpg-staging/pcs/` directory. Write nothing else. Exit cleanly (still report the non-markdown skip summary).
3. **Verbal refinement** → apply each requested change to the named staged file using the **Edit** tool, one surgical edit per change so the IDE shows a native hunk diff per [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). Do **not** rewrite the whole file with Write. After the edits, name in your reply which entries changed and re-ask the same continue / refine-more / cancel prompt.

GM-corrected descriptions become the steering input each doc's full read uses in the per-doc loop — don't silently re-classify a doc later in extraction. If the full read reveals the GM-confirmed description was wrong, surface that to the GM and re-confirm before continuing.

### Step 4: Propose a processing order

**Single-doc skip.** When the input directory has exactly one markdown doc, skip this step entirely. Proceed directly to Step 5 with the description+roster results from Step 3.

Once descriptions and the PC roster are accepted (multi-doc), propose a processing order over the same doc list. The default order, per ADR-0008, is **world info first, adventures next, session-shaped docs last**. Within each band, preserve the GM-confirmed list order from Step 3.

For docs whose accepted description is *"Mixed / ambiguous: …"*, slot them after world info and before adventures by default — the per-doc loop will resolve the ambiguity per-doc. Surface this placement explicitly in the proposal so the GM can move it if they know better.

Write the proposed order to `.ttrpg-staging/survey-order.md` using the Write tool. The IDE shows the diff; the GM edits in place.

Accept three response shapes:

1. **Continue** → re-read `.ttrpg-staging/survey-order.md` to capture GM edits, parse the order, renumber to match the GM's arrangement (the agent owns the integer indices; the GM owns the sequence). Continue to Step 5.
2. **Cancel** → delete `.ttrpg-staging/`, write nothing else, exit cleanly.
3. **Verbal refinement** → apply each requested change via the **Edit** tool (one surgical edit per change) per [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). Loop until the GM says continue or cancel.

If the GM removed a doc entirely during ordering, drop it from the survey set — the per-doc loop will not process it. Note removed docs in the closing summary so it's visible they were skipped on purpose.

### Step 5: Hand off to the per-doc loop (with PC stub promotion)

Once the GM confirms the order (multi-doc) or the description+roster review (single-doc), hand off these **survey results** to the per-doc loop:

- **Doc list**, in confirmed processing order. Each entry is the doc's absolute path and the GM-confirmed one-line description.
- **PC roster**, as the list of `(slug, optional one-line body, aliases)` tuples per `pc-roster-proposal.md`.
- **Skipped doc list** (any docs the GM removed during ordering, plus the non-markdown files), preserved only for the closing summary at the end of Phase 3.
- An empty **carried-forward lessons** set (the per-doc loop's cross-doc learning will populate it as each doc's review completes; see Step 0b below).

#### Step 5a/b/c: PC stub staging, promotion, and survey cleanup

PC stub staging and promotion mechanics live in `pc-roster-proposal.md`. The shared part is the survey-staging cleanup at Step 5c:

**Delete the surviving survey staging files** — `.ttrpg-staging/survey-descriptions.md`, `.ttrpg-staging/survey-pcs.md`, and `.ttrpg-staging/survey-order.md` (multi-doc only). If `.ttrpg-staging/` is now empty, remove the directory; if other workflows have staged content there, leave the directory alone. This way, the per-doc loop's cancel paths and Phase 4's hold paths don't have to worry about lingering survey artifacts.

Then continue directly into the per-doc loop with doc #1. No confirmation prompt — the GM just edited and accepted the order list and the PC roster, so asking again is redundant. Per-doc review is the real break point.

## Phase 3: Per-doc extraction loop

### Step 0: Pre-flight checks

Before reading any source doc, verify the campaign repo is in a state where ingest makes sense. The same checks apply in the single-doc and multi-doc cases (the multi-doc case will also have run Phase 2 Step 0's identical campaign-repo check by this point — once is enough; don't re-run).

1. **Campaign repo state.** The campaign directory must contain `CLAUDE.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, `campaign.md`. If any are missing, the repo isn't scaffolded. Stop.
2. **No half-finished prior ingest.** Look for signs of an aborted prior per-doc extraction (untracked or modified files in `npcs/`, `pcs/`, `locations/`, `factions/`, `items/`, `adventures/`, `threads/`, `consequences/`, `beats/`, `secrets/` per `git status --porcelain`). If any are present, surface a short list (paths). Do not proceed without explicit GM confirmation that they intend to layer this ingest on top of the prior changes.
3. **Input directory state.** Per Phase 2 Step 0 (already enforced at survey time in the multi-doc case).

### Step 0b: Multi-doc loop setup

This step applies only in the multi-doc case. Single-doc skips straight to Step 1.

1. Receive the survey results from Phase 2.
2. Initialise an in-memory **carried-forward lessons** structure. Each lesson has a short shape — what the GM corrected, on which doc, and how it should change the agent's behavior on subsequent docs. Suggested buckets:
   - **Rejections** — kinds of entities the GM dropped from a proposed set (e.g., "do not propose passing innkeepers as Reference notes").
   - **Classification preferences** — how the GM resolved a Thread-vs-Consequence-vs-narrative-color call.
   - **Dedup decisions** — confirmed identity links between names ("the Sera in doc 2 is the same Sera as `npcs/sera.md`").
   - **Naming and slugging preferences** — canonical-name choices the GM made when given a dedup ambiguity.

   Each lesson records the source doc (so the GM can audit *why* the agent is behaving differently) and a one-line statement of the rule being applied.
3. Walk the doc list in confirmed processing order. For each doc, run Steps 1 through 6 below. Before each doc's Step 1, surface the **carried-forward lessons applied to this doc** inline so the GM sees what's being applied — a short bulleted list at the top of that doc's review screen labelled "Lessons carried from prior docs in this run." Empty for doc 1; populated from doc 2 onward as corrections accumulate.
4. The survey-confirmed description for each doc becomes the steering input for that doc's Step 1 — there is no per-doc bounded-skim re-proposal in the multi-doc path. The GM may still revise the description at Step 1 if the full read in Step 2 changes their mind.
5. After the last doc completes (or the GM cancels mid-run), discard the carried-forward lessons. They are scoped to one ingest run; they do not persist across `/ingest` invocations.

### Step 0c: Recovery pre-flight (resume-after-crash)

This step runs once at the top of Phase 3 (before doc 1's Step 1), on every invocation. It detects the **resume-after-crash / resume-after-keep-all-cancel** state that the per-doc commits enable.

1. Run `git log --grep '^/ingest doc ' --reverse --format='%H %s'` in the campaign repo. If the output is empty, this is a fresh Phase 3 run — proceed to Step 1 with doc 1. Otherwise the campaign already has per-doc commits from a prior `/ingest` invocation.
2. Check whether the prior run completed Phase 4. The Phase 4 wrap-up commit's subject starts with `/ingest wrap-up` (per Phase 4 Step 3b's message format). Run `git log --grep '^/ingest wrap-up' --format='%H'` and look for any wrap-up commit landing **after** the most recent per-doc commit. If one exists, the prior run completed cleanly — there's nothing to resume. Proceed to Step 1 with doc 1 of *this* run's survey.
3. If per-doc commits exist but no subsequent wrap-up commit does, the prior run crashed or was cancelled with **keep all** mid-Phase-3. Count the per-doc commits (N) and surface to the GM:

   > *"This campaign has N committed Phase 3 docs from a prior `/ingest` run but no wrap-up. Resume at doc N+1, or abandon and re-scaffold?"*

   - **Resume** → skip Phase 2 entirely (the survey already ran in the prior invocation, and Phase 2's staging artifacts were deleted at the end of survey — there's nothing to re-edit). Skip the first N docs of *this* invocation's survey (or surface a mismatch if the input set changed and ask whether to abandon-and-rescan). Continue Phase 3 from doc N+1; carried-forward lessons start empty (the in-memory lessons from the prior run died with that invocation).
   - **Abandon and re-scaffold** → look up the Phase 1 scaffold commit (subject `Scaffold campaign repo via ttrpg-gm /ingest`). Run `git reset --hard <scaffold-sha>`. Proceed with a fresh Phase 2 → Phase 3 against the input directory.

   The resume path is implementation-light because the per-doc loop already iterates by index — starting at doc N+1 instead of doc 1 is a matter of skipping the first N iterations.

### Pre-approval gate seam — per-doc boundary

**Before opening any staging file for the upcoming doc** — i.e., immediately after Step 0c on doc 1, or immediately after Step 5.8's commit for the previous doc — the per-doc loop crosses the pre-approval gate seam (see "Pre-approval gate seam" above). In v0.3 the seam is a no-op pass-through; a future #27 implementation slots its preview logic in here.

### Step 1: Bounded skim and proposed description

**Single-doc path.** Read **only** the first heading and the first ~200 words of the markdown file (ADR-0008's "bounded skim"). Do not full-read yet. Propose a single-line description that classifies the doc and summarizes what it appears to be about.

Present the proposed description to the GM diff-style. Accept Accept / Edit / Cancel.

**Multi-doc path.** For each doc in the confirmed processing order from Phase 2, the description was already drafted, edited, and accepted during the survey. **Do not re-skim and do not re-propose.** Use the survey-confirmed description as the steering input directly. Surface it at the top of this doc's review along with the "Lessons carried from prior docs in this run" list.

If the GM wants to revise the description before extraction begins on this doc, accept the edit and record it — but do **not** roll it back into the survey or re-propose the order; the order is fixed by the time Phase 3 starts on a given doc.

The agreed description is the steering input for the full read. Don't silently re-classify the doc later in extraction; if Step 2 reveals the description was wrong, surface that to the GM and re-confirm before continuing.

### Step 2: Full read with description as context

Read the full markdown file (the current doc in the multi-doc loop, or the only doc in the single-doc case). Hold the GM-confirmed description as the primary framing. In multi-doc, also hold the **carried-forward lessons** set as a secondary framing.

**Doc-classification routing.** The GM-confirmed description's classification prefix routes Step 2 into one of two extraction branches:

- **`Adventure: …` / `World info: …` / `Session log: …` / `Mixed / ambiguous: …`** — the general extraction branch (identify lifecycle objects + Reference notes per the list below).
- **`PC source: <slug>'s backstory`** — the PC-source extraction branch. The doc is one PC's backstory; the named PC (`<slug>`) is the doc's primary subject. Drive PC body enrichment + cross-extraction from backstory prose per the "PC source: extraction branch" subsection below. Reference notes, Threads, Consequences, Beats, and Secrets still extract through their normal heuristics — the PC-source branch *adds* PC body enrichment + the PC-as-container bidi-link extension on top of the general branch's outputs.

#### General extraction branch

Identify:

- **Reference notes** — named NPCs, locations, factions, items the doc introduces or describes substantively. Apply `reference-note-extraction.md`.
- **Adventure-shape** — does this doc describe a story arc the party will run? If yes, plan an `adventures/<slug>/adventure.md` with ADR-0007 frontmatter.
- **Threads** — explicit unresolved hooks the party *knows about*. Future-facing, party-aware. ADR-0004 governs file shape.
- **Consequences** — explicit persistent facts about the world resulting from prior action. Past-facing.
- **Beats** — GM-prepped scenes the party doesn't yet know about. Future-facing, GM-authored. ADR-0009 frontmatter; classify `kind:` from source-section headings per `beat-kind-classification.md`. *Threads vs Beats test*: if the party knows about it, it's a Thread; if it's the GM's prep, it's a Beat. Populate `linked_*` per the proximity rules in Step 3's Beat shape subsection.
- **Secrets** — GM-only facts the party may not know but could discover. Apply `secret-extraction.md`. Each extracted Secret gets its own `secrets/<slug>.md` with ADR-0014 frontmatter and `belongs_to:` populated per the multi-container rule. On write, maintain bidirectional `## Secrets` section per `bidi-link-maintenance.md`.

#### PC source: extraction branch

When the GM-confirmed description is `PC source: <slug>'s backstory`, run the general extraction branch *and* the PC-source-specific work below. Per ADR-0023, the PC source branch composes with — does not replace — the general branch.

- **Resolve the PC slug.** The `<slug>` from the classification is the PC. Verify the PC stub exists at `pcs/<slug>.md` (it will, because Phase 2 Step 5 staged and promoted any new PC stubs from the auto-add roster section before Phase 3 began). If the PC stub is missing at this point, surface to the GM and stop — the PC source doc names a PC the roster did not promote, which is an upstream contract violation.
- **PC body enrichment** per `reference-note-extraction.md` "PC source body enrichment" subsection. The backstory prose becomes the body of `pcs/<slug>.md`, *appended* to any existing GM-authored body content. The agent never overwrites GM-authored body prose — per the GM-owned-body / agent-maintained-bidi-sections boundary (ADR-0023), the body is GM-owned and the agent's appends are additive only. If the live `pcs/<slug>.md` has GM-authored prose beyond the H1, propose the enrichment as an append (visible as a hunk diff) — the GM can edit at Step 4b review.
- **Cross-extraction of named entities from backstory** per `reference-note-extraction.md` "PC source: cross-extraction" subsection. Named NPCs (parents, mentors, rivals), Locations (hometown, training grounds, ancestral seat), Factions (orders, guilds, family lines), and Items (heirlooms, signature gear) in the backstory prose become Reference notes with `belongs_to:` containing the PC. **This is the load-bearing extension** — backstory-extracted Reference notes carry the PC in `belongs_to:` so the PC-as-container bidi-link pattern fires at write time.
- **Bidi-link extension — PC as container.** Per `bidi-link-maintenance.md` "PC as container" subsection, the PC file (`pcs/<slug>.md`) gains `## NPCs`, `## Locations`, `## Factions`, and `## Items` sections wiki-linking to each cross-extracted Reference note. The Reference notes maintain a symmetric `## PCs` section wiki-linking back. Same shape as Secrets bidi-links per ADR-0014 — the section names differ; the symmetry pattern is identical.
- **Optional frontmatter slice.** When the backstory doc supplies them explicitly, populate `player:`, `class:`, and/or `level:` in the PC's frontmatter per `frontmatter-schemas.md` PC schema. Omit any field the source doesn't supply; do not invent. These fields are optional — a PC stub without them is valid.

What **not** to extract from a PC source doc:

- **The PC as their own NPC.** The named subject is a PC, not an NPC — do not propose an `npcs/<slug>.md` for them.
- **In-campaign Threads / Consequences from a pre-campaign narrative.** A backstory describes events *before* the campaign began. Backstory events become Reference-note prose + PC body, not Threads (which are future-facing, party-aware) or Consequences (which are past facts resulting from *party* action — pre-campaign backstory is not a party action).
- **Beats.** A backstory is not GM intent to deliver a scene. A *hook the GM wrote for delivery in play* alongside the backstory might be a Beat (e.g., a "GM aside: the family heirloom shows up in session 4" line) — extract it normally. Backstory prose itself is not Beat-shaped.
- **Secrets the player wrote about their own PC.** Per `secret-extraction.md` "Player-secret rather than world-secret" exclusion, a PC's narrative quirk that the player is tracking out-of-character is not a Secret. If the GM wants to mark a backstory element as a Secret (a hidden fact about the PC's family the PC doesn't yet know), that surfaces through the normal Secret extraction heuristic — usually surfaced as ASK at Step 4a.

**Date honesty for lifecycle objects.** Per ADR-0007 for Adventures: the agent never invents dates. For every Thread, Consequence, and Beat extracted during ingest, `created:` is left null unless the source doc explicitly provides a date the agent can attribute. Do **not** use the ingest date as a stand-in for an unknown source date.

What **not** to extract: session structure (`sessions/YYYY-MM-DD-session-N/` — created by `/prep-session` and `/wrap-session`); Atlas content (out of scope in v0.1 per ADR-0006).

### Step 3: Draft the proposed changes

Draft each proposed file with full content (frontmatter plus body). Hold them in memory; do **not** write yet.

**Before writing any lifecycle-object frontmatter, consult `frontmatter-schemas.md`** — the canonical spec for Adventure, Thread, Consequence, Beat, and Secret schemas. The ingest-era defaults documented in that reference (`status: introduced` for Adventures, `created: ~` for everything since the agent doesn't know past dates) apply here directly.

#### Reference note shape

See `reference-note-extraction.md` for what counts as a Reference note, folder by kind, the slug rule for filenames, the one-line default body, and the minimal-frontmatter convention. The ingest-specific orchestration: extract from the source doc's prose; wiki-link to other Reference notes you're also proposing from the same doc.

#### Adventure shape (ADR-0007, .claude/rules/adventures.md)

If the doc is adventure-shaped, propose `adventures/<slug>/adventure.md`. **Schema:** see `frontmatter-schemas.md` ("Adventure" section). Ingest-specific defaults:

- `status: introduced` — the GM hasn't told you the party has begun running it. Only set `active`, `completed`, or `abandoned` if the source doc explicitly says so.
- `order: ~` unless the source doc has explicit numeric sequencing (e.g., "Adventure 1: …", "Chapter 3: …") that you can copy directly. When null, Phase 4 will bulk-prompt the GM during wrap-up.
- All date fields null unless the source explicitly supplies them. Never invent dates (ADR-0007).
- Durations null unless the source explicitly supplies; if it does, copy the prose verbatim.

Body of `adventure.md` is a short prose summary from the source doc, with `[[wiki links]]` to the Reference notes you're also proposing. Sub-files for scenes/chapters may also be proposed (siblings to `adventure.md` in the same `adventures/<slug>/` directory) when the source doc has clearly distinct sub-sections worth their own files.

#### Thread shape (ADR-0004)

One file per Thread, in `threads/`. **Schema:** see `frontmatter-schemas.md` ("Thread" section). Ingest-specific defaults: `status: open` unless the source doc explicitly says the thread is already resolved (then `closed`) or has gone stale (then `decayed`); `created: ~` unless the source supplies a date. Body is one or two sentences describing the hook with `[[wiki links]]` to relevant Reference notes.

#### Consequence shape (ADR-0004)

One file per Consequence, in `consequences/`. **Schema:** see `frontmatter-schemas.md` ("Consequence" section). For ingest, `created:` is null unless the source supplies a specific date the agent can attribute — don't use the ingest date as a stand-in. Body is the persistent fact, one or two sentences, with `[[wiki links]]` to relevant Reference notes.

#### Beat shape (ADR-0009)

One file per Beat, in `beats/`. **Schema:** see `frontmatter-schemas.md` ("Beat" section). Ingest-specific defaults: `status: pending`; `created: ~`; `delivered: ~`; `kind:` classified by source-section heading per `beat-kind-classification.md`; `linked_secrets:` populated when the Beat is a Clue paired with an extracted Secret; `linked_*` populated per the proximity rules below.

Body is one or two sentences describing the GM's prep, with `[[wiki links]]` to relevant Reference notes mentioned inside the prep.

##### Classifying `kind:` from source-section headings

`/ingest` is the strongest case for `kind:` classification because module-shaped source docs label their content by section heading. **Apply `beat-kind-classification.md`** — that reference is the canonical mapping from module section headings to `kind:` values, and the order-of-precedence rule (section heading > body content > unset).

Ingest-specific orchestration on top of the shared reference:

- **Heading is the primary signal.** When a Beat is extracted from prose under a known section heading (e.g., `## Scenes`, `## Lore`, `## Handouts`, `## Hidden Information for the DM`, `## Triggers`), set `kind:` per the heading-mapping table. Don't override from body-content guessing.
- **Subsection refines.** When a subsection's content reads as a different kind from its parent heading (an item labeled "Rumor:" under `## Scenes`), surface as an ASK at Step 4a.
- **Unknown heading → body-content fallback.** When the enclosing heading doesn't match any known pattern, fall back to body-content classification. Leave `kind:` unset (`~`) if body content also doesn't yield a confident classification.
- **GM-supplied kind values.** The enum is open. If the GM corrects a proposed kind to a string outside the starter set at review, accept it verbatim and record the value in a carried-forward lesson.
- **Hidden Information for the DM → `kind: clue` with `linked_secrets:`.** Extract paired Beat–Secret pairs and populate the Clue Beat's `linked_secrets:` with the matching Secret's slug. When alignment is ambiguous, surface as ASK at Step 4a.

##### Populating `linked_*` at extraction time

These four fields exist specifically so `/prep-session` can surface a Beat in the right tier for the next session. Beats extracted without `linked_*` populated end up in the "unlinked, review and tag" tier and force the GM into a manual backfill. **Populate them at extraction time when the source clearly supports it.** Be conservative: empty is honest; wrong is harmful.

Use these rules, in order:

1. **`linked_adventures` — strong rule, adventure-shaped doc.** If the current doc is being ingested as `adventures/<slug>/`, every Beat extracted from it gets `linked_adventures: [<slug>]` automatically. The link is structural, not inferred.
2. **`linked_adventures` — weak rule, world-info doc.** If the current doc is world-info-shaped and a Beat-shaped passage explicitly names an Adventure inside the Beat's own paragraph/bullet/enclosing heading, link to that Adventure (matching against Adventures already in `adventures/`, being created from earlier docs this run, or being created from this same doc). If multiple Adventures are named in proximity, surface as ASK at Step 4a.
3. **`linked_locations` — proximity rule.** Locations mentioned in the Beat's own paragraph or bullet are linked. "Same paragraph / same bullet / same scene block" is the "near" radius. Match against existing `locations/` files, locations being created earlier in this run, or locations being created from this same doc. Ambiguous matches → ASK.
4. **`linked_locations` — heading rule.** If a Beat-shaped passage sits under a heading that names a location, link the Beat to that location even if the Beat's own bullet doesn't repeat the name.
5. **`linked_pcs` — explicit attribution.** Link a PC only when the Beat content explicitly names the PC as the target or subject (*"for Darius: …"*, *"Darius's hook: …"*). Generic mentions ("the party") do not justify a link.
6. **`linked_npcs` — content-mention rule.** Link an NPC when the NPC is the actor or subject inside the Beat's content. A passing name-drop without role context is not enough.
7. **Default to empty list, not omission.** If a field has no confident link, write it as `[]` in frontmatter — the YAML key is preserved so `/prep-session` and `/wrap-session` can read it without conditional logic.
8. **All linked-field values are slugs**, using the same slugification rule as Reference-note dedup.

##### Carried-forward lessons for Beat linkage and kind

The Step 5b carried-forward lessons set tracks linkage decisions and kind classifications just like dedup decisions. If the GM corrects a `linked_*` field or a proposed `kind:` at review, record it. Subsequent docs that propose similar Beats get the GM's correction applied automatically (with the lesson surfaced at the top of the next doc's review).

#### Secret shape (ADR-0014)

If the source doc has a "Secrets and Lies," "Adventure Background," "DM-Only," "Hidden Information," or analogous GM-only section, propose one file per Secret under `secrets/`. **Schema:** see `frontmatter-schemas.md` ("Secret" section). **Extraction heuristic:** `secret-extraction.md` is the canonical spec for what counts as a Secret, file shape, section-heading signals, and the multi-container `belongs_to:` population rule.

Ingest-specific defaults:

- `status: hidden` unless the source content explicitly says some part of the Secret has already been revealed.
- `belongs_to:` populated per the rules below — at minimum, the ingested Adventure.
- `revealed_by: []` at CREATE. Do not pre-populate from Beats extracted in this same doc; the symmetric `revealed_by:` will be reconciled by `/wrap-session` when the Beat flips to `delivered`.

Body of the Secret file is the **fact itself**, one or two sentences written for the GM (not GM instructions). Use `[[wiki links]]` to any Reference notes named in the fact.

##### Populating `belongs_to:` at extraction time

Use these rules, in order:

1. **Adventure container is automatic — strong rule.** When the current doc is being ingested as `adventures/<slug>/`, every Secret extracted from that doc gets `belongs_to:` containing **at minimum** `adventures/<slug>/`. Do not skip this entry even when the Secret's own prose doesn't name the Adventure.
2. **Named-entity expansion — proximity rule.** Scan the Secret's prose for **named** NPCs, Locations, Factions, and Items. For each named entity that resolves to a Reference note (already in the repo, being created earlier in this run, or being created from this same doc), add that entity's container path to `belongs_to:`. Matching uses the same slugification rule as `dedup-matching.md`.
3. **Subsection-heading expansion — heading rule.** When a Secret is extracted from a subsection whose heading names a container, add that container to `belongs_to:` even if the body doesn't repeat the name.
4. **PC containers — explicit attribution only.** A Secret may belong to a PC when the source *explicitly* names the PC as the subject. Generic mentions do not justify a PC container — surface as ASK if ambiguous.
5. **Cross-kind ambiguity → ASK.** A name matching Reference notes in multiple kind folders surfaces as an ASK at Step 4a.
6. **Container set validation.** Before staging, validate `belongs_to:` per `secret-store.md`: non-empty, at least one entry under a non-ephemeral folder root, no unknown folder roots. A Secret that fails validation surfaces as ASK at Step 4a; do not write a Secret whose `belongs_to:` would fail.
7. **Default to a smaller set on doubt.** If the proximity rule would expand `belongs_to:` to many containers and one or more are uncertain, surface those as an ASK alongside the Secret in the per-doc review.
8. **All `belongs_to:` paths use the canonical form** — `npcs/<slug>.md` / `pcs/<slug>.md` / `locations/<slug>.md` / `factions/<slug>.md` / `items/<slug>.md` for file-shaped containers, `adventures/<slug>/` (with trailing slash) for Adventures.

##### Carried-forward lessons for Secret extraction and `belongs_to:`

The Step 5b carried-forward lessons set tracks:

- **Section-heading interpretation.** If the GM corrects a section that the agent treated as Secret-bearing (or didn't), record the lesson.
- **`belongs_to:` choices.** If the GM trimmed or expanded a proposed `belongs_to:`, record the lesson.
- **Merge vs. separate decisions for cross-doc Secret dedup.** When a candidate Secret dedups against a prior Secret and the GM resolves "merge — add the new containers," record the identity for the rest of the run.

### Step 3b: Cross-doc dedup

Before presenting the per-doc review, match every drafted Reference note (NPC, location, faction, item) **and every drafted Secret** against existing files in the campaign repo. This applies both within the multi-doc loop (matching against files written by earlier docs in this run) and on the first doc of a multi-doc run (matching against pre-existing Reference notes / Secrets from a prior `/ingest`). In the single-doc degenerate case, dedup still runs — it just matches only against pre-existing campaign files.

Reference notes and Secrets are the kinds dedup applies to. Adventures get name-collision handling at Step 5 (GM resolves; no auto-merge). Threads, Consequences, and Beats are extracted only from what the doc explicitly says; cross-doc Thread / Consequence / Beat dedup is a deliberate non-goal — duplicates surface, and the GM trims them at review.

#### Matching procedure

**Apply the matching rule at `dedup-matching.md`** — normalization, what to match against (filenames + first-heading title + `aliases:` for Reference notes), and the three buckets (CREATE / UPDATE confident-match / ASK ambiguous-match).

Ingest-specific orchestration on top of the shared rule:

- **Apply carried-forward dedup decisions before asking.** Confirmed identity links apply as confident matches without re-asking. Confirmed splits drop the proposed dedup question and treat the candidate as a CREATE at a disambiguated slug — confirm the slug at the next per-doc review, not silently.
- **Target folder is the kind's folder.** Match Reference-note candidates only within the same kind (`npcs/`, `locations/`, `factions/`, `items/`). Cross-kind matches surface as ASK per the shared rule. Secret candidates match within the `secrets/` folder per `secret-store.md`.
- **Secret dedup → multi-container reconciliation, not generic UPDATE.** A confident Secret slug match doesn't propose a generic body UPDATE — the resolution shape for Secrets is *merge the new container set into the existing Secret's `belongs_to:`*. Per `secret-extraction.md`: prompt is "merge, separate, or rename?"
- **Restated Secrets across chapters.** A common module pattern: chapter 1 introduces a Secret, chapter 4 restates it. Cross-doc dedup against earlier-doc Secrets catches this. On *merge*, expand `belongs_to:` to include any new containers chapter 4 named.

#### Output of Step 3b

The drafted-proposal set from Step 3 is now annotated, per Reference note and per Secret, with one of CREATE, UPDATE, or ASK. These annotations feed Step 4.

### Step 4: Per-doc review via staging directory

This step has two parts. First, resolve any ambiguous-dedup ASK items inline in chat. Second, write the resolved set of proposed files to a per-doc staging directory the GM edits in their IDE.

#### Step 4a: Resolve ambiguous-dedup questions inline (including PC-vs-NPC safety net)

Per `pc-roster-proposal.md`, Step 4a is also where the **PC-vs-NPC safety net** fires for late-addition PCs the survey missed. The safety-net ASK shape, response handling, and downstream PC-stub promotion are specified there.

If Step 3b produced any ASK items (ambiguous Reference-note matches, Reference-note alias relationships per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md), Secret multi-container reconciliations, Beat–Secret pairing ambiguities, Beat `linked_*` ambiguities, Beat `kind:` ambiguities, `belongs_to:` expansion uncertainties, or PC-vs-NPC safety-net ASKs), surface them in chat as a short numbered list of questions. Group by ASK kind so the GM can scan.

When the GM resolves, apply per ASK kind:

- **Reference-note dedup**: convert to confident UPDATE (yes) or CREATE at a disambiguated slug (no).
- **Reference-note alias relationship** per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md): *merge into existing canonical* → propose an UPDATE on the existing canonical that appends the alias to `aliases:` and routes prose mentions through piped wiki links. *Separate* → propose two CREATEs at distinct slugs. *Pick canonical from two new candidates* → propose one CREATE at the chosen slug with the other name in `aliases:`.
- **Secret reconciliation**: *merge* → set `belongs_to:` to the union; treat as UPDATE on the existing Secret. *Separate* → CREATE the candidate at the disambiguated slug. *Rename* → CREATE at the GM-supplied slug.
- **Secret `belongs_to:` expansion**: trim or expand per the GM's answer; the validated set feeds the Secret CREATE / UPDATE.
- **Clue–Secret pairing**: set the Beat's `linked_secrets:` to the GM-confirmed Secret slug(s).
- **Beat `linked_*` and `kind:` ASKs**: set the field per the GM's answer.
- **PC vs NPC safety net** per `pc-roster-proposal.md`.

Record every resolution in the carried-forward lessons set (Step 5b will keep these for subsequent docs in the run). If the GM resolves only some ASK items, re-ask the unresolved ones — don't proceed to staging until every ASK has a decision.

#### Step 4b: Stage proposed files for IDE-based edit

**This step follows the shared staging-file review pattern at `staging-pattern.md`** — write proposed final content to a gitignored staging directory, present a chat summary with continue/cancel ask, re-read on continue to capture GM edits, clean up on cancel.

Ingest-specific staging shape: write every proposed file to `.ttrpg-staging/doc-<N>/` in the campaign repo, mirroring the campaign's directory structure. For multi-doc runs, `<N>` is the doc's position in the processing order (1, 2, 3…). For single-doc, use `doc-1/`. Each proposed file lands at its eventual relative path *inside* `doc-<N>/`:

| Proposed change | Staging path |
|---|---|
| Adventure (CREATE) | `.ttrpg-staging/doc-<N>/adventures/<slug>/adventure.md` (+ sub-files) |
| Reference note (CREATE / UPDATE / disambiguated CREATE) | `.ttrpg-staging/doc-<N>/<kind>/<slug>.md` |
| PC stub (CREATE — safety-net promotion) | `.ttrpg-staging/doc-<N>/pcs/<slug>.md` |
| PC body enrichment (UPDATE — `PC source:` branch, append body) | `.ttrpg-staging/doc-<N>/pcs/<slug>.md` |
| Thread / Consequence / Beat / Secret (CREATE / UPDATE / disambiguated) | `.ttrpg-staging/doc-<N>/<kind>/<slug>.md` |
| Container back-reference (UPDATE — added `## Secrets` section bullet) | `.ttrpg-staging/doc-<N>/<container-path>` |
| PC container back-reference (UPDATE — added `## NPCs` / `## Locations` / `## Factions` / `## Items` section bullets on the PC, `## PCs` section bullets on cross-extracted Reference notes) | `.ttrpg-staging/doc-<N>/<container-path>` |

For UPDATE items, follow `staging-pattern.md` Section 2: `cp` the live file from the campaign repo into staging, then apply the proposed change via the Edit tool against the staged copy. This surfaces the live → proposed delta the way Claude Code shows changes for any file edit.

**Bidi link staging for Secrets.** Every Secret CREATE or UPDATE drags container back-reference UPDATEs along with it: for each container in the Secret's `belongs_to:`, if that container's body doesn't already have a `## Secrets` section wiki-linking the Secret, stage an UPDATE to that container file too (per `bidi-link-maintenance.md`). Deleting a back-reference UPDATE without also adjusting the Secret's `belongs_to:` is a contract violation the agent surfaces at re-read time.

**Bidi link staging for PC-as-container (PC source: branch).** Every cross-extracted Reference note from a `PC source:` doc whose `belongs_to:` contains the PC drags two back-reference UPDATEs along with it: (1) the PC file gains a `## NPCs` / `## Locations` / `## Factions` / `## Items` section bullet (per the Reference note's kind) wiki-linking the new note; (2) the Reference note carries a `## PCs` section bullet wiki-linking the PC. Per `bidi-link-maintenance.md` "PC as container," the pattern is symmetric to Secrets — the PC source's body enrichment is staged alongside, and deleting either back-reference UPDATE without also adjusting the cross-extracted Reference note's `belongs_to:` is the same contract violation as Secret back-reference deletion.

Present a chat summary listing what's staged with metadata (description, lessons applied, summary counts, per-file CREATE/UPDATE annotations).

Accept these response shapes:

1. **Continue** → re-read every file remaining in `.ttrpg-staging/doc-<N>/` to capture GM edits. Treat any staged file the GM deleted as rejection. Proceed to Step 5.
2. **Redo this doc** → discard the in-flight staging and re-run from Step 1 against the same doc. Delete `.ttrpg-staging/doc-<N>/`; drop every carried-forward lesson **accumulated by this doc** (lessons whose source-doc index equals <N>); re-enter Step 1.
3. **Reject everything** → delete `.ttrpg-staging/doc-<N>/`. Write nothing for this doc. In multi-doc, ask the GM whether to continue to the next doc or exit. Already-committed approved files from prior docs stay committed.
4. **Cancel** → run the **refined cancel-prompt** below.

#### Refined cancel-mid-Phase-3 prompt

Whenever the GM cancels mid-Phase-3, branch on whether any per-doc commits have landed in *this* `/ingest` run.

- **No prior per-doc commits this run**: existing cancel behavior — delete `.ttrpg-staging/doc-<N>/` (and `.ttrpg-staging/` if empty), exit cleanly. Campaign tree byte-identical to pre-Phase-3 state.
- **One or more docs already committed this run**: surface this prompt verbatim (substituting N and the doc count):
  > *"You've committed N of <total> docs. What would you like to do?*
  > *1. **Keep all** — exit; resume later at doc N+1.*
  > *2. **Reset to before doc <K>** — roll back doc K and everything after; re-enter Phase 3 at doc K with a clean slate. (Tell me which doc to reset to.)*
  > *3. **Abandon entirely** — roll back all per-doc commits; exit with a freshly-scaffolded campaign."*

  - **Keep all** → delete `.ttrpg-staging/doc-<N>/`; exit cleanly. The next invocation's Step 0c detects this and offers to resume at doc N+1.
  - **Reset to before doc K** → look up the SHA of doc K's predecessor (the doc-(K-1) commit for K > 1; the Phase 1 scaffold commit for K = 1) via `git log --grep '^/ingest doc '` (or `^Scaffold campaign repo` for K = 1). Run `git reset --hard <sha>`. Drop every carried-forward lesson whose source-doc index is ≥ K (lessons 1..K-1 are preserved — their underlying work is still in the tree). Delete `.ttrpg-staging/doc-<N>/`. Re-enter Step 1 at doc K.
  - **Abandon entirely** → look up the Phase 1 scaffold commit SHA. Run `git reset --hard <sha>`. Drop **all** carried-forward lessons. Delete `.ttrpg-staging/`. Exit cleanly.

  On any `git reset --hard` failure (working-tree dirty for files outside the lifecycle/reference folders, signing failure on a hook, etc.), surface the git error verbatim and stop — do not retry; do not try a partial reset.

Rejected items (whether per-file via deletion or per-doc via reject-everything) must never be written to final locations. Approved items must be written exactly as the GM left them — no late re-interpretation.

### Step 5: Move approved items from staging to final locations

Once the GM says continue in Step 4b, move every file remaining in `.ttrpg-staging/doc-<N>/` to its corresponding final location in the campaign repo. Paths inside `doc-<N>/` mirror the campaign repo, so the move is a path translation.

1. Create any needed directories under the campaign repo (only those needed for approved items; don't pre-create empty folders).
2. **Move order matters for Secrets and PC-as-container bidi.** Move container files (Reference notes, Adventures, PCs) **before** Secret files, and move cross-extracted Reference notes (from `PC source:` docs) before the PC body enrichment, so the bidi back-references resolve against containers that exist at the final location. Specifically:
   - Move Reference-note CREATEs and UPDATEs first (including cross-extracted Reference notes from `PC source:` docs).
   - Move Adventure CREATEs (including sub-files) next.
   - Move PC body enrichments (`PC source:` branch) — append-only UPDATEs on `pcs/<slug>.md`.
   - Move container back-reference UPDATEs to existing-in-campaign-repo Reference notes / Adventures / PCs (the `## Secrets` / `## NPCs` / `## Locations` / `## Factions` / `## Items` / `## PCs` section updates).
   - Move Secret files last.
   - Move Threads, Consequences, and Beats in any order — they have no bidi dependency.
3. For each surviving staged file, dispatch by its Step 3b annotation. On path collisions not surfaced by Step 3b, STOP and tell the GM the exact conflicting path. Do not overwrite without explicit GM confirmation.
4. **Validate Secret `belongs_to:` before writing the Secret file.** Per `secret-store.md` (`validate_belongs_to`): non-empty, ≥1 non-ephemeral entry, no unknown folder roots. On validation failure, STOP and re-present that Secret for re-edit.
5. **Run bidi maintenance after each Secret write.** Per `bidi-link-maintenance.md`'s `apply_belongs_to`.
5a. **Run bidi maintenance after each cross-extracted Reference note write (PC source: branch).** Per `bidi-link-maintenance.md` "PC as container," each cross-extracted Reference note whose `belongs_to:` contains the PC triggers a symmetric pair of back-reference writes: the PC file gains a `## NPCs` / `## Locations` / `## Factions` / `## Items` bullet (per the Reference note's kind), and the Reference note gains a `## PCs` bullet wiki-linking the PC. The maintenance is idempotent — re-running on an already-linked pair is a no-op.
6. After each file is moved, delete it from staging. When `.ttrpg-staging/doc-<N>/` is empty, remove the directory. If `.ttrpg-staging/` is empty, remove that too.
7. Do not modify `campaign.md`, `CLAUDE.md`, or anything under `.claude/` from inside Phase 3. Campaign-overview regeneration belongs to Phase 4.
8. **Per-doc commit.** After every approved file from this doc has been moved into the campaign tree, make a single git commit checkpointing this doc's promotion. The commit's purpose is *forward-resilience* (crash-resume / cancel-and-resume), not a per-doc revert unit.

   **Staging scope.** Stage only the paths this doc wrote or modified — never sweep in unrelated GM edits. Compute the set with `git status --porcelain` filtered to entries inside the lifecycle/reference folders (`npcs/`, `pcs/`, `locations/`, `factions/`, `items/`, `adventures/`, `threads/`, `consequences/`, `beats/`, `secrets/`). Pass each path explicitly to `git add` (`git add npcs/foo.md npcs/bar.md secrets/baz.md ...`) — prefer explicit paths over `git add -A` so the scope is auditable.

   If the staging scope is empty (the GM rejected every proposed file for this doc), skip the commit entirely. Continue to Step 5b / the next doc.

   **Commit message format.** Single-line subject in the form:

   ```
   /ingest doc <N>/<total>: <doc-name> (<one-line summary of what was extracted>)
   ```

   Examples:

   - `/ingest doc 1/12: faerun-gods.md (5 Reference notes, 2 Secrets)`
   - `/ingest doc 2/12: lost-mines.md (Adventure, 12 Reference notes, 4 Beats)`
   - `/ingest doc 12/12: session-1-notes.md (3 Threads, 2 Consequences)`

   `<N>` is the doc's 1-based position in the confirmed processing order; `<total>` is the count of docs that survived survey ordering. `<doc-name>` is the doc's basename. The parenthetical summary mirrors the same kind-count shorthand Phase 4 uses; group by kind. Drop kinds with zero counts. UPDATE counts may be folded into the same parenthetical when non-trivial (e.g., `(Adventure, 8 NPCs, 1 NPC UPDATE, 3 Secrets)`).

   **On git failure** (no user configured, pre-commit hook rejection, signing failure, anything else): surface the underlying git error verbatim to the GM and stop. Do not retry. Do not amend a prior per-doc commit. The GM resolves the underlying issue and re-invokes `/ingest`, which will detect the per-doc-committed state via Step 0c and resume at doc N+1.

   This is the *per-doc bookend* — analogous to Phase 1's scaffold commit and Phase 4's wrap-up commit. The full commit sequence for a typical 12-doc run is:

   ```
   Scaffold campaign repo via ttrpg-gm /ingest
   /ingest doc 1/12: faerun-gods.md (5 Reference notes, 2 Secrets)
   /ingest doc 2/12: lost-mines.md (Adventure, 12 Reference notes, 4 Beats)
   ...
   /ingest doc 12/12: session-1-notes.md (3 Threads, 2 Consequences)
   /ingest wrap-up (campaign.md regen, 3 Adventures backfilled with order: 1/2/3)
   ```

### Step 5b: Capture cross-doc learning

This step applies only in the multi-doc case. Single-doc has no subsequent doc to inform, so skip.

After the GM's approval/edit/rejection decisions for the current doc are settled (and before moving to the next doc), capture the lessons implied by those decisions into the carried-forward lessons set initialised in Step 0b. The point is to make the agent's behavior on doc N+1 reflect what the GM corrected on doc N, visibly and auditably.

Lessons worth carrying forward (each lesson tagged with its source-doc index so reset-to-before-doc-K can drop them deterministically):

- **Rejected kinds.** Reference notes the GM rejected of a recognizable shape (passing innkeepers, named-once-in-prose mercenaries). Apply on subsequent docs by not drafting those candidates, or by drafting them and explicitly flagging them as candidates the prior-doc lesson would drop.
- **Classification preferences.** Thread → Consequence moves, Reference note → narrative-color drops.
- **Confirmed dedup identities.** Convert future ambiguous-match candidates into confident updates without re-asking.
- **Confirmed dedup splits.** Drop the proposed dedup question and treat as CREATE at the GM-named disambiguated slug; confirm the slug at the next review screen.
- **Confirmed alias relationships** per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md). On later docs the extended dedup-matching rule (scanning each candidate file's `aliases:`) catches the alias as a confident UPDATE without re-prompting.
- **Confirmed alias splits.** When the GM resolves "separate — these are distinct entities despite the dual-name pattern."
- **Naming preferences.** Canonical-name choices.
- **Section-heading interpretation for Secrets and Beats.** Sections the GM treated differently from the agent's default classification.
- **Secret `belongs_to:` policy.** Conventions the GM established about which containers belong in `belongs_to:`.
- **Secret merge / separate decisions.**
- **Secret partial-reveal recognition.** GM confirmations that a candidate Secret was already partially revealed in past play. (The four-piece extraction-time partial-reveal pattern is specified in `secret-extraction.md` under "Extraction-time partial-reveal handling." **Never carry forward the anti-pattern** — splitting a partially-revealed Secret into a Consequence + tightened Secret — as a learned rule.)
- **Beat `kind:` classifications.** GM corrections to proposed `kind:`.
- **Clue–Secret pairings.**
- **PC identity confirmations** per `pc-roster-proposal.md`.

Do not invent lessons. Only capture what the GM's decisions explicitly support. If a rejection is ambiguous in motive, note it as a candidate rather than a confirmed lesson and ask the GM at the top of doc N+1's review.

Carried-forward lessons are scoped to one ingest run. They do not persist into the next `/ingest` invocation. They are not written to any file — they live only in the agent's in-memory state for the duration of the run.

### Step 6: Closing summary

After the **last** doc in the run completes (or after the only doc, in the single-doc case), tell the GM, concisely: source docs extracted (in processing order, with descriptions); a summary of what was written across the whole run (counts by kind, including Beat `kind:` breakdown and Secret `belongs_to:` container-count breakdown when non-trivial); non-markdown files skipped; in multi-doc, a short audit of carried-forward lessons that ended up applied; a reminder that `campaign.md` has not yet been regenerated and no commit has been made yet either; an explicit hand-off prompt for Phase 4 ("Run wrap-up now, or hold?").

Do not auto-advance into Phase 4 silently — the hand-off prompt is the gate. Do not carry the lessons set forward to a future `/ingest` invocation — it dies with the run.

## Phase 4: Wrap-up

The wrap-up phase runs **after** the last doc's Step 5 / Step 5b completes (Phase 3 Step 6 still runs; wrap-up follows it), or when the GM explicitly invokes the wrap-up against an already-populated campaign repo. It does three things, in order:

1. **Order prompt** — bulk-ask the GM for any missing `order:` values on Adventures whose order wasn't reliably inferable from source.
2. **`campaign.md` composer** — regenerate the campaign-root Campaign overview per ADR-0007, replacing the placeholder written by Phase 1.
3. **Wrap-up commit** — capture the wrap-up's own changes (`campaign.md` regen and any Adventure `order:` backfill) in a single follow-up commit; Phase 3's per-doc commits already cover the lifecycle/reference content.

### Step 0: Pre-flight check

1. **Campaign repo state.** Same invariants from Phase 3 Step 0.
2. **Confirm wrap-up is wanted.** If Phase 4 is being invoked at the end of a Phase 3 run, ask explicitly: *"Run wrap-up now (order prompt, regenerate `campaign.md`, commit), or hold and let you inspect the repo first?"* Accept wrap up / go ahead / hold / cancel.
3. **Surface uncommitted state — but only when it actually warrants attention.** Run `git status --porcelain`. Sort entries into **expected** (untracked / modified files in lifecycle/reference folders, modified `campaign.md`, stale scaffolder artifacts under `.claude/` that match the current Phase 1 template set except `.claude/settings.json` which is gitignored, untracked `.gitignore` matching the Phase 1 template) and **unexpected** (uncommitted files outside the expected set, anything under `.ttrpg-staging/`, modified files outside `campaign.md` and lifecycle/reference folders). Surface only the unexpected entries and ask whether to proceed, exit, or have the GM resolve them first.

   Post-issue-#61: in the fresh-ingest path Phase 3's per-doc commits already captured every lifecycle/reference write before Phase 4 begins, so `git status --porcelain` at this preflight will typically be **empty** at the lifecycle-folder level.

### Step 1: Order prompt for missing `order:` values

Walk every `adventures/<slug>/adventure.md` file under the campaign repo.

1. **Read frontmatter** for each Adventure. Collect the slug, the H1 title (canonical name), the current `status`, and the current `order:` value.
2. **Identify the missing-order set.** An Adventure needs the order prompt **only** if both of these are true:
   - Its `order:` is null (Phase 3 left it null because the source doc didn't supply an inferable sequence).
   - Its source doc did not use explicit numeric Adventure sequencing the agent could have copied. Phase 4 trusts that signal.

   Adventures whose `order:` was already filled in by Phase 3 skip this prompt.

3. **If the missing-order set is empty**, skip to Step 2. Tell the GM: *"All Adventures have an `order:` value already; skipping order prompt."*

4. **Write the order prompt to a staging file** at `.ttrpg-staging/adventure-order.md`. Use the Write tool. Format as a simple key-value list, one line per missing-order Adventure, with a header that explains the edit contract (1 = earliest, duplicates allowed if the GM truly believes two Adventures ran in parallel, null/blank to skip). The comments on each line carry the Adventure's H1 title and status so the GM can identify each entry without opening the source file.

5. **Wait for the GM**, then re-read the staging file to capture edits. Parse each non-blank, non-comment line as `<slug> : <value>`. Acceptable values: positive integer, `null`/blank, or "anything else → flag and ask the GM to clarify rather than guessing." If the GM removed/added lines, surface a contract violation and re-ask. If the GM cancelled, delete the staging file and skip to Step 2 with a one-line note that no `order:` values were filled in.

6. **Validate.** Positive integers; duplicates require explicit confirmation; apply only after confirmation.

7. **Write the `order:` values into Adventure frontmatter.** Edit the `order:` line in each `adventures/<slug>/adventure.md` frontmatter from `~` to the integer. Preserve every other field. On malformed frontmatter, surface the path and skip the write.

8. **Delete the staging file.**

### Step 2: `campaign.md` composer

Replace the campaign-root `campaign.md` (currently the Phase 1 placeholder or a prior Phase 4 output) with a generated overview.

**Run the composer at `campaign-overview-composer.md`** — that file is the canonical spec for section ordering, sub-bucket rendering, derivation rules, and the determinism contract. Phase 4 runs the composer with the **ingest-only variants** documented under that reference's "Skill-specific variants" section:

- Adds two header lines below `**System:**`: `- **Status:** active` and `- **Last event:** YYYY-MM-DD (ingest)` (today's date suffixed `(ingest)`).
- Renders the full `## Adventures` history section between the menu and `## Open threads`, listing every Adventure (sorted by `order:` ascending, null-order Adventures alphabetical by slug at the end).
- Shows **every** Consequence under `## Recent significant consequences` — no top-N truncation.

Write `campaign.md` from scratch. Do not preserve manual GM edits to the prior `campaign.md` content — per ADR-0007, manual edits are reconciled or overwritten with warning at regeneration, and Phase 4 chooses overwrite.

Phase 4 source for the party-location line (per the composer's `/ingest` derivation rules): among `status: active` Adventures, pick the highest-`order:`; fall back to highest-`order:` overall if none are active, then alphabetically-last Adventure slug if `order:` is null across the board. Read that Adventure's `adventure.md` body for an explicit location reference. Never invent a location.

### Step 3: Wrap-up commit

After Step 1 (any `order:` writes) and Step 2 (the `campaign.md` regeneration) have both landed on disk, make a single follow-up git commit in the campaign repo capturing **only** the wrap-up's own changes. Everything Phase 3 wrote is already committed in the per-doc commit chain.

This is the deliberate exception to the no-auto-commit rule. `/wrap-session` does not auto-commit (ADR-0011); the GM owns ongoing commits with their own messages. **But** `/ingest` Phase 1 already broke that pattern, Phase 3 broke it again with per-doc commits, and Phase 4 is the closing bookend. The pattern is *the plugin owns commits inside `/ingest` only*.

#### Step 3a: Compute counts

The wrap-up commit's scope is **narrow** — just `campaign.md` and any Adventure frontmatter touched by Step 1. Phase 3's per-doc commits already captured the lifecycle/reference content; this commit is the campaign-level cleanup. Use `git status --porcelain` to enumerate the uncommitted set. Typically you'll see:

- `campaign.md` — modified (the Phase 4 Step 2 regen).
- `adventures/<slug>/adventure.md` — modified (Step 1's `order:` backfill — one entry per Adventure that got an integer assigned).
- Possibly stale scaffolder artifacts (the pre-flight Step 0 #3 carve-out — `.gitignore`, `.claude/<file>` rewrites, etc.) — these get absorbed by the wrap-up commit too.

Count Adventures backfilled and surface the slugs in the proposed message. Do **not** re-count the Phase 3 content — it's already in history.

#### Step 3b: Propose the commit message

Present the proposed commit message to the GM, with the reasoning for the auto-commit framed once explicitly. Subject shape: `/ingest wrap-up (<short summary>)`. Examples:

- `/ingest wrap-up (campaign.md regen, 3 Adventures backfilled with order: 1/2/3)`
- `/ingest wrap-up (campaign.md regen)` — when no Adventures needed backfilling.
- `/ingest wrap-up (campaign.md regen, 3 Adventures backfilled, scaffolder artifacts absorbed)` — when Step 0 #3 absorbed stale scaffolder artifacts.

Keep the subject under ~100 characters; spill detail into the body if needed.

Accept Approve / Edit the message / Edit the staged set / Skip the commit. Don't drop the `campaign.md` regen unless the GM explicitly says so — it's load-bearing.

#### Step 3c: Stage and commit

Once the GM approves: stage exactly the file set the GM approved (prefer naming files explicitly over `git add -A`). Run `git commit -m <message>`. Do not configure git user.name / user.email from the plugin. On commit failure for any reason, surface the underlying git error verbatim and stop. Do not retry. Do not amend.

### Step 4: Closing summary

First, **clean up `.ttrpg-staging/`** in the campaign repo (`rm -rf` if present). Then tell the GM, concisely: order prompt outcome; `campaign.md` regenerated (with manual-edit warning if applicable per ADR-0007); counts of what landed (mirroring Phase 3 Step 6's grouping); bidi link health (run `bidi-link-maintenance.md`'s `lint` algorithm once; surface non-empty findings as "to investigate," don't auto-heal post-commit); commit status (hash + message, or copy-paste-ready commit command if skipped); `git status` output (clean working tree confirmation); what's next (`/prep-session` or `/wrap-session`).

End cleanly. Do not loop back into Phase 3.

### v0.1 boundaries

- **Re-run semantics are out of scope.** Phase 4 specifically does **not** include a confirm-before-overwrite guard against a prior Phase 4 output; if the GM bypasses Phase 1 and jumps straight to wrap-up on an already-ingested repo, behavior is undefined.
- **Single auto-commit.** Phase 4 makes exactly one follow-up commit.
- **No `campaign.md` reconciliation.** Phase 4 overwrites the placeholder unconditionally.

## Determinism and idempotence

- The Phase 4 `campaign.md` regen is a deterministic function of current campaign state per `campaign-overview-composer.md`'s determinism contract.
- The recovery pre-flight at Step 0c is idempotent — running it on an already-completed campaign (per-doc commits + wrap-up) detects the wrap-up and proceeds without a prompt.
- Per-doc commits are idempotent within a run: a doc whose Step 5.8 commit succeeded does not get re-committed if the loop somehow re-iterates over it (e.g., a Reset-to-before-doc-K branch reset to a SHA *after* this doc); the next iteration that touches this doc starts from a clean staging.

## What this pipeline does not handle

- **PC-roster proposal mechanics** — see `pc-roster-proposal.md`.
- **Atlas content** — out of scope for v0.1 (ADR-0006). Single-repo only.
- **Subdirectory recursion** — flat input directory only (ADR-0006).
- **Non-markdown files** — reported in the closing summary, never read.
- **Sessions** — not synthesized from source docs; Sessions are created by `/prep-session` and `/wrap-session` (ADR-0005).
- **Cross-run lesson persistence** — carried-forward lessons die with the run.
