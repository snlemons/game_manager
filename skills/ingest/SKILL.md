---
name: ingest
description: Extract structure from existing TTRPG campaign notes into a scaffolded campaign repo. In slice 3 of v0.1, three phases are implemented — the scaffolder (writes the root CLAUDE.md, .claude/rules/sessions.md, .claude/rules/adventures.md, and a campaign.md placeholder into the target directory, then runs git init and an initial commit), the survey phase (discover input docs, bounded-skim each, propose one-line descriptions, present diff-style for GM edit, propose a processing order, confirm with GM), and the per-doc extraction loop with multi-doc cross-doc dedup and cross-doc learning (walk docs in confirmed order, extract Reference notes / Adventure / Threads / Consequences per doc, dedup against existing campaign files with confident-update / ambiguous-ask thresholds, carry GM corrections forward as visible lessons applied to subsequent docs). The wrap-up phase is still a stub.
---

# /ingest

`/ingest` is the workflow that turns an existing pile of campaign notes into a structured, agent-navigable campaign repo.

The full workflow has four phases:

1. **Scaffold** — write the plugin's templates into the target directory, `git init`, and make an initial commit. **(Implemented in slice 1.)**
2. **Survey** — discover input docs, bounded-skim each, propose a one-line description per doc as an editable diff-style list, propose a processing order (world info → adventures → session-shaped), confirm both with the GM. **(Implemented in slice 3.)**
3. **Per-doc extraction loop** — for each doc, in the confirmed processing order, extract Reference notes, adventure metadata, Threads, and Consequences; cross-doc dedup against existing campaign files (confident matches propose updates; ambiguous matches surface to the GM); present a per-doc proposed diff; the GM approves; corrections carry forward as visible lessons applied to subsequent docs. **(Single-doc case implemented in slice 2; multi-doc cross-doc dedup and cross-doc learning implemented in slice 3.)**
4. **Wrap-up** — prompt for any missing `order:` values on ingest-era adventures and regenerate `campaign.md`. *(Stub — not yet implemented.)*

In this slice, phases 1, 2, and 3 run. Phase 4 responds "not yet implemented" if the GM tries to advance past it.

Follow the domain vocabulary defined in the plugin's `CONTEXT.md` and the campaign repo's `CLAUDE.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Campaign overview**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, "story"/"game" for Campaign, "world" for Atlas, etc.).

## When to invoke this skill

The GM invokes `/ingest` to start a new campaign repo from existing notes, or to ingest additional source docs into an already-scaffolded campaign. The slice-1 scaffold phase also covers the "fresh start, no source docs yet" path — the GM gets a blank campaign repo to start writing into. The slice-2 per-doc extraction loop covers the "I have one markdown doc I'd like extracted into the campaign" path. The slice-3 survey plus multi-doc per-doc loop covers the "I have a pile of markdown notes from a prior tool and I want them ingested as a batch with cross-doc dedup" path.

## Inputs the GM provides

The GM provides:

- **Target directory** — where the campaign repo should live. May be an empty directory, a not-yet-existing directory, or (with explicit GM confirmation) a directory containing only source notes the GM wants to ingest later. **Never** scaffold over a directory that already contains a campaign repo (presence of `campaign.md`, `.claude/rules/sessions.md`, or a non-trivial `.git/`); abort and tell the GM.
- **Campaign name** — human-readable (e.g. *The Sunless Citadel Revisited*). Used in `CLAUDE.md` and `campaign.md`.
- **System** — the rule system (e.g. *D&D 5e*, *Pathfinder 2e*, *Call of Cthulhu*). Free-form prose.

If any of these are missing, ask the GM for them before doing anything that touches the filesystem. Don't invent campaign names or system labels.

For the per-doc extraction loop, the GM additionally provides:

- **Input directory** — a path containing the source doc(s) to ingest. v0.1 is flat-directory only (no recursion into subdirectories; ADR-0006).
- **Campaign directory** — the already-scaffolded target campaign repo (may be the same path the GM scaffolded earlier; defaults to the current working directory if it is a campaign repo).

## Phase 1: Scaffold (implemented)

### Step 1: Validate the target

1. Resolve the target directory to an absolute path.
2. If it doesn't exist, create it (and any missing parent directories).
3. If it exists and is non-empty, check for any of these markers of an existing campaign:
   - `campaign.md`
   - `.claude/rules/sessions.md`
   - `.claude/rules/adventures.md`
   - a `.git/` directory with any commits beyond an empty initial state
   If any marker is present, **stop** and tell the GM the directory looks like an existing campaign repo. Don't overwrite. Don't merge.
4. If it exists, is non-empty, and has none of those markers (e.g. it has source-doc markdown files the GM wants ingested in a later phase), confirm with the GM before proceeding.

### Step 2: Write the four template files

The plugin ships four templates under `~/.claude/skills/ttrpg-gm/templates/`. For each, read the template, substitute placeholders, and write to the target. Filenames have a `.template` suffix in the plugin; strip the suffix on write.

| Template source | Written to (relative to target) |
|---|---|
| `templates/CLAUDE.md.template` | `CLAUDE.md` |
| `templates/.claude/rules/sessions.md.template` | `.claude/rules/sessions.md` |
| `templates/.claude/rules/adventures.md.template` | `.claude/rules/adventures.md` |
| `templates/campaign.md.template` | `campaign.md` |

Placeholder substitutions to apply to template content before writing:

- `{{CAMPAIGN_NAME}}` → the GM-supplied campaign name, verbatim.
- `{{CAMPAIGN_SYSTEM}}` → the GM-supplied system, verbatim.

Create intermediate directories as needed (notably `.claude/rules/`). Do not write any other files in this slice. In particular, do not create empty `npcs/`, `locations/`, `adventures/`, `sessions/`, `threads/`, `consequences/`, or `beats/` directories — they appear when content first lands in them, not before.

### Step 3: Initialize the git repo and make an initial commit

Run these commands in the target directory:

```
git init
git add CLAUDE.md .claude/rules/sessions.md .claude/rules/adventures.md campaign.md
git commit -m "Scaffold campaign repo via ttrpg-gm /ingest"
```

If `git init` reports the directory is already a git repo, do **not** re-init. Stage and commit on the existing branch only with explicit GM confirmation; otherwise stop and tell the GM.

Do not configure `user.name` or `user.email` from the plugin. Use whatever the GM's git config provides; if the commit fails because git has no identity configured, surface the underlying git error to the GM verbatim and stop.

### Step 4: Report what was written

Tell the GM, concisely:

- the target directory (absolute path),
- the four files that were written,
- the initial commit's hash and message.

Do **not** auto-advance into the survey phase. End the scaffold phase here and wait for the GM to decide whether to proceed.

## Phase 2: Survey

The survey phase runs **before** the per-doc extraction loop whenever the input directory contains **more than one** markdown doc. Its purpose, per ADR-0008, is to pre-label every doc with a GM-confirmed one-line description and to fix a processing order — both of which steer extraction in Phase 3.

The single-doc case is degenerate: with exactly one markdown doc the input has no ordering question and only one description to confirm, so the survey collapses into Phase 3 Step 1 directly. Do not run a separate survey screen for a single-doc input.

### Step 0: Pre-flight checks

Before doing anything visible:

1. **Campaign repo state.** The same campaign-repo invariants from Phase 3 Step 0 apply (`CLAUDE.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, `campaign.md` present; no half-finished prior ingest). If the repo isn't scaffolded or has uncommitted ingest artefacts, stop with the same message Phase 3 uses. Don't survey on top of a broken repo.
2. **Input directory state.** List the input directory (flat; ADR-0006 — no recursion).
   - Count markdown files (`*.md`). If zero, tell the GM: *"No markdown docs in this input directory. Nothing to survey."* Stop.
   - If exactly one, do **not** run the survey. Drop straight into Phase 3 Step 1 (the single-doc degenerate case). Do not present a one-item editable list or ask about processing order — there's nothing to order.
   - If more than one, collect the absolute paths of every markdown doc and continue. Note non-markdown files separately for the closing summary; do not read or process them.

### Step 1: Bounded skim of every discovered doc

For each markdown doc found, read **only** the first heading and the first ~200 words (ADR-0008's "bounded skim"). Do not full-read. Hold the skim text in memory for description-drafting; discard before Phase 3 starts its full reads, so each doc's full read in Phase 3 is unconstrained by earlier skim residue.

If a doc has no heading or is shorter than ~200 words, work with what's there. Don't pad. Don't infer content beyond what's visible in the skim.

### Step 2: Propose a one-line description per doc

For each doc, draft a single-line description that classifies the doc and summarizes what it appears to be about, in the same shape Phase 3 Step 1 uses for the single-doc case. Use these classifications and keep the vocabulary aligned with CONTEXT.md:

- *"Adventure: <short description>."* — the doc reads as a story arc the party would run (published-module-shaped, homebrew-arc-shaped, or a coherent set of scenes tied to a goal).
- *"World info: <short description>."* — Reference-note-dump-shaped (gods, calendar, regions, recurring NPCs) with no Adventure structure.
- *"Session log: <short description>."* — past-facing narrative of one session's events.
- *"Mixed / ambiguous: <surface the ambiguity>."* — the skim doesn't disambiguate (could be Adventure or world info; could be a Session log or a Reference-note dump).

ADR-0008 explicitly prefers surfaced ambiguity over confident wrong commits. If the skim is genuinely unclear, say so in the description rather than guessing — Phase 3 will resolve it once the GM clarifies.

### Step 3: Present descriptions as an editable diff-style list

Show the GM the full list of docs with their proposed descriptions, in a diff-style review screen. Use whatever review affordance Claude Code provides; if no diff preview is available, present an inline numbered list with the relative path and the proposed description on each line. Example formatting:

```
Survey: 4 markdown docs found.

  1. lost-mines.md         — Adventure: a published-module-shaped writeup of the Lost Mines arc.
  2. faerun-gods.md        — World info: notes on the gods and calendar of Faerun, no Adventure structure.
  3. session-1-notes.md    — Session log: the party's first delve into the Citadel, written as narrative.
  4. campaign-overview.md  — Mixed / ambiguous: could be world info or campaign-meta notes; not enough in the skim to tell.

Non-markdown files (skipped): art/map.png, art/sera.jpg.
```

Then ask explicitly: *"Edit any descriptions, accept the list as-is, or cancel?"* Accept these response shapes:

1. **Accept** → record the descriptions verbatim and continue to Step 4.
2. **Edit** → the GM rewrites one or more descriptions (by number, by filename, or by quoting the proposed line). Apply edits to the in-memory list, re-present the affected lines, ask again. Loop until the GM accepts or cancels.
3. **Cancel** → write nothing, leave the filesystem unchanged, exit cleanly (still report the non-markdown skip summary).

GM-corrected descriptions replace the proposed ones verbatim and become the steering input each doc's full read uses in Phase 3 — don't silently re-classify a doc later in extraction. If Phase 3's full read reveals the GM-confirmed description was wrong, surface that to the GM and re-confirm before continuing.

### Step 4: Propose a processing order

Once descriptions are accepted, propose a processing order over the same list. The default order, per ADR-0008, is **world info first, adventures next, session-shaped docs last**. Within each band, preserve the GM-confirmed list order from Step 3 (their order is closer to their mental model than the filesystem order or a re-sort by name).

For docs whose accepted description is *"Mixed / ambiguous: …"*, slot them after world info and before adventures by default — Phase 3 will resolve the ambiguity per-doc, and that's the safest place to do so (world context is in, adventure-shaped extraction hasn't started yet). Surface this placement explicitly in the proposal so the GM can move it if they know better.

Present the proposed order as a numbered list with each doc's relative path and accepted description. Example:

```
Proposed processing order:

  1. faerun-gods.md        — World info: notes on the gods and calendar of Faerun.
  2. campaign-overview.md  — Mixed / ambiguous: could be world info or campaign-meta notes.
  3. lost-mines.md         — Adventure: a published-module-shaped writeup of the Lost Mines arc.
  4. session-1-notes.md    — Session log: the party's first delve into the Citadel.

Rule: world info → adventures → session-shaped. Mixed/ambiguous docs are slotted after world info by default.
```

Then ask explicitly: *"Confirm the order, adjust it, or cancel?"* Accept these response shapes:

1. **Confirm** → freeze the order and continue to Step 5.
2. **Adjust** → the GM gives a revised order (renumbering, moving items, removing items they decided to skip). Apply the adjustment, re-present, ask again. Loop until confirmed or cancelled.
3. **Cancel** → write nothing, exit cleanly.

If the GM removes a doc entirely during ordering, drop it from the survey set — Phase 3 will not process it. Note removed docs in the closing summary so it's visible they were skipped on purpose.

### Step 5: Hand off to Phase 3

Once the GM confirms the order, hand off these **survey results** to Phase 3:

- **Doc list**, in confirmed processing order. Each entry is the doc's absolute path and the GM-confirmed one-line description.
- **Skipped doc list** (any docs the GM removed during ordering, plus the non-markdown files), preserved only for the closing summary at the end of Phase 3.
- An empty **carried-forward lessons** set (Phase 3's cross-doc learning will populate it as each doc's review completes; see Phase 3 Step 0b).

Do not auto-advance into Phase 3's per-doc reading. Tell the GM the survey is complete and Phase 3 will begin with doc #1 on confirmation. This gives the GM a chance to break out before any full read of a source doc happens.

## Phase 3: Per-doc extraction loop

### Slice 3 scope

This slice implements the per-doc loop for **single-doc and multi-doc** inputs, including cross-doc dedup and cross-doc learning:

- **Single-doc** (exactly one markdown file in the input directory) is the degenerate case: skip the survey entirely (Phase 2 Step 0 routes here directly), then run Step 1 through Step 6 below for the one doc. Dedup against existing campaign files still applies; cross-doc learning is a no-op because there's no subsequent doc.
- **Multi-doc** (more than one markdown file) runs after Phase 2 (survey) has confirmed a per-doc description and a processing order. Step 0b sets up the multi-doc loop; Steps 1 through 6 run **per doc, in confirmed order**; cross-doc dedup is applied at Step 3; carried-forward lessons accumulate from each doc's review and feed the next doc's extraction.
- Non-markdown files in the input directory (PDFs, images, etc.) are reported in the closing summary and **skipped without halting**.
- **No Beat extraction.** Per CONTEXT.md and ADR-0009, Beats are GM-authored; ingest is not a listed creation path. Don't propose Beats.

ADR-0008 governs the workflow shape; this slice implements its per-doc loop, dedup, and cross-doc learning verbatim. Slice 3 carve-outs (no wrap-up; no Beat extraction) are intentional, not silent deviations.

### Step 0: Pre-flight checks

Before reading any source doc, verify the campaign repo is in a state where ingest makes sense. The same checks apply in the single-doc and multi-doc cases (the multi-doc case will also have run Phase 2 Step 0's identical campaign-repo check by this point — once is enough; don't re-run).

1. **Campaign repo state.** The campaign directory must contain:
   - `CLAUDE.md`
   - `.claude/rules/sessions.md`
   - `.claude/rules/adventures.md`
   - `campaign.md`

   If any are missing, the repo isn't scaffolded. Tell the GM: *"This directory doesn't look like a scaffolded campaign repo. Run the `/ingest` scaffold phase first."* Stop.

2. **No half-finished prior ingest.** Look for signs of an aborted prior per-doc extraction:
   - Untracked files in `npcs/`, `locations/`, `factions/`, `items/`, `adventures/`, `threads/`, or `consequences/` per `git status --porcelain`.
   - Uncommitted modifications to any of the above.

   If any are present, stop and tell the GM: *"The campaign repo has uncommitted changes from a prior ingest. Commit, stash, or revert them before starting a fresh extraction."* Surface a short list (paths). Do not proceed without explicit GM confirmation that they intend to layer this ingest on top of the prior changes.

3. **Input directory state.** List the input directory (flat; ADR-0006 — no recursion).
   - Count markdown files (`*.md`). If zero, tell the GM: *"No markdown docs in this input directory. Nothing to extract."* Stop.
   - If exactly one markdown file, this is the single-doc degenerate case — skip the survey and continue to Step 1 with that doc.
   - If more than one markdown file, this is the multi-doc case — run Phase 2 (Survey) first to produce GM-confirmed descriptions and a processing order, then continue to Step 0b with those survey results in hand.
   - Collect non-markdown files separately. Note them for the closing summary; do not read or process them.

### Step 0b: Multi-doc loop setup

This step applies only in the multi-doc case. Single-doc skips straight to Step 1.

1. Receive the survey results from Phase 2: an ordered list of `(doc absolute path, GM-confirmed description)` pairs, a skipped-doc list, and an empty **carried-forward lessons** set.
2. Initialise an in-memory **carried-forward lessons** structure. Each lesson has a short shape — what the GM corrected, on which doc, and how it should change the agent's behavior on subsequent docs. Suggested buckets:
   - **Rejections** — kinds of entities the GM dropped from a proposed set (e.g., "do not propose passing innkeepers as Reference notes"; "do not promote one-line rumor mentions to Threads").
   - **Classification preferences** — how the GM resolved a Thread-vs-Consequence-vs-narrative-color call ("the GM treats 'the captain owes them' as a Consequence, not a Thread").
   - **Dedup decisions** — confirmed identity links between names ("the Sera in doc 2 is the same Sera as `npcs/sera.md`"; "the two Johns in docs 3 and 4 are distinct").
   - **Naming and slugging preferences** — canonical-name choices the GM made when given a dedup ambiguity ("call the Court of Veils 'veiled-court'").

   Each lesson records the source doc (so the GM can audit *why* the agent is behaving differently) and a one-line statement of the rule being applied.
3. Walk the doc list in confirmed processing order. For each doc, run Steps 1 through 6 below. Before each doc's Step 1, surface the **carried-forward lessons applied to this doc** inline so the GM sees what's being applied — a short bulleted list at the top of that doc's review screen labelled "Lessons carried from prior docs in this run." Empty for doc 1; populated from doc 2 onward as corrections accumulate.
4. The survey-confirmed description for each doc becomes the steering input for that doc's Step 1 — there is no per-doc bounded-skim re-proposal in the multi-doc path (Phase 2 already did that). The GM may still revise the description at Step 1 if the full read in Step 2 changes their mind, exactly as in the single-doc case.
5. After the last doc completes (or the GM cancels mid-run), discard the carried-forward lessons. They are scoped to one ingest run; they do not persist across `/ingest` invocations.

If the GM cancels during any doc's review, write nothing for the cancelled doc, exit cleanly, and report which docs in the order were completed, which was cancelled, and which were not reached. Already-written approved files from prior docs in the same run stay written — the GM owns the next commit (ADR-0011).

### Step 1: Bounded skim and proposed description

**Single-doc path.** Read **only** the first heading and the first ~200 words of the markdown file (ADR-0008's "bounded skim"). Do not full-read yet. Propose a single-line description that classifies the doc and summarizes what it appears to be about. Examples:

- *"Adventure: a published-module-shaped writeup of the Sunless Citadel arc."*
- *"World info: notes on the gods and calendar of Faerun, no Adventure structure."*
- *"Session log: the party's first delve into the Citadel, written as narrative."*

If the skim is ambiguous (could be Adventure or world info; could be a Session log or a Reference note dump), say so in the description rather than guessing. ADR-0008 explicitly prefers surfaced ambiguity over confident wrong commits.

Present the proposed description to the GM diff-style — show the proposal and ask: *"Edit this description, accept as-is, or cancel?"* Accept three kinds of response:

1. **Accept** → record the description verbatim as extraction context and continue to Step 2.
2. **Edit** → take the GM's revised description, record that, and continue.
3. **Cancel** → write nothing, leave the filesystem unchanged, exit.

**Multi-doc path.** For each doc in the confirmed processing order from Phase 2, the description was already drafted, edited, and accepted during the survey. **Do not re-skim and do not re-propose.** Use the survey-confirmed description as the steering input directly. Surface it at the top of this doc's review along with the "Lessons carried from prior docs in this run" list (per Step 0b), so the GM sees both the description being applied and the carried-forward lessons being applied:

```
Doc 2 of 4: lost-mines.md
Description (from survey): Adventure: a published-module-shaped writeup of the Lost Mines arc.
Lessons carried from prior docs in this run:
  - From faerun-gods.md: do not promote passing innkeepers to Reference notes (GM rejected 2).
  - From faerun-gods.md: the GM treats one-line rumor mentions as narrative color, not Threads.
```

If the GM wants to revise the description before extraction begins on this doc, accept the edit and record it — but do **not** roll it back into the survey or re-propose the order; the order is fixed by the time Phase 3 starts on a given doc.

The agreed description is the steering input for the full read. Don't silently re-classify the doc later in extraction; if Step 2 reveals the description was wrong, surface that to the GM and re-confirm before continuing.

### Step 2: Full read with description as context

Read the full markdown file (the current doc in the multi-doc loop, or the only doc in the single-doc case). Hold the GM-confirmed description as the primary framing — interpret the doc as that kind of thing.

In multi-doc, also hold the **carried-forward lessons** set as a secondary framing: when a lesson says "do not promote passing innkeepers", apply it to candidates this doc surfaces. When a lesson says "the Sera in this run is the campaign's Sera", route the candidate to Step 3b dedup as a pre-confirmed confident match. Don't apply lessons silently to candidates whose match to the lesson is itself ambiguous — fall through to the per-doc review and let the GM confirm.

Identify:

- **Reference notes**: named NPCs, locations, factions, and items the doc introduces or describes substantively. ADR-0003 says one file per Reference note; default content is a one-liner derived from prose, not a filled-out template.
- **Adventure-shape**: does this doc describe a story arc the party will run (a coherent set of scenes, locations, or stages tied together by a goal)? If yes, plan an `adventures/<slug>/adventure.md` file with ADR-0007 frontmatter. If no (it's a Reference note dump, world info, or session-narrative), don't fabricate an Adventure.
- **Threads**: explicit unresolved hooks, promises, foreshadowed dangers — future-facing, party-relevant. ADR-0004 governs file shape and status frontmatter. Only extract Threads that the doc actually surfaces; don't invent them from thin air.
- **Consequences**: explicit persistent facts about the world resulting from prior action ("the temple was destroyed", "the lord owes the party a favor"). Past-facing. Same provenance bar as Threads — only what the doc says.

What **not** to extract:

- **Beats.** GM-authored only (ADR-0009; CONTEXT.md). Skip.
- **Session structure** (`sessions/YYYY-MM-DD-session-N/`). Sessions are created by `/prep-session` and `/wrap-session`; do not synthesize them from a doc even if the doc looks like a session log. If the GM-confirmed description identifies the doc as a session log, surface that to the GM and ask whether it should be filed as an Adventure-side history note (under `adventures/<name>/`) or skipped — don't manufacture a `sessions/` directory.
- **Atlas content.** v0.1 is single-repo (ADR-0006); no cross-repo links into an Atlas. Treat all extracted content as campaign-local.

### Step 3: Draft the proposed changes

Draft each proposed file with full content (frontmatter plus body). Hold them in memory; do **not** write yet.

#### Reference note shape (ADR-0003)

One file per Reference note. Filenames are slugs (lowercase, hyphenated) of the canonical name. Folder by kind:

| Kind | Folder |
|---|---|
| NPC | `npcs/` |
| Location | `locations/` |
| Faction | `factions/` |
| Item | `items/` |

Default body is the one-line description from prose — short, factual, no fabricated detail. Wiki-link to other Reference notes by canonical name when the source doc names them.

Reference notes do not require frontmatter in this slice. If the doc gives you a clear status, role, or other strong fact, you may include light frontmatter (e.g. `kind: npc`) — but do not invent fields the doc doesn't supply, and never produce empty placeholder fields.

Example: `npcs/sera.md`

```markdown
# Sera

Blacksmith in [[Phandalin]] who reports the mines were recently closed.
```

#### Adventure shape (ADR-0007, .claude/rules/adventures.md)

If the doc is adventure-shaped, propose `adventures/<slug>/adventure.md` with this frontmatter exactly:

```yaml
---
status: introduced                   # required: introduced | active | completed | abandoned
order: ~                             # ingest-era sequence; null until the GM provides one in wrap-up
introduced: ~                        # real-world date; null when unknown
started: ~                           # real-world date; null when unknown
completed: ~                         # real-world date; null when unknown
in_world_duration: ~                 # optional, free-form prose
real_world_duration: ~               # optional, free-form prose
---
```

- `status` defaults to `introduced` for ingest-era Adventures — the GM hasn't told you the party has begun running it yet. Only set `active`, `completed`, or `abandoned` if the source doc explicitly says so.
- `order` stays null in slice 2. Wrap-up phase will prompt the GM for it (still a stub).
- Dates stay null unless the source doc explicitly supplies them. Never invent dates (ADR-0007 consequence: "the agent never asks the GM to invent dates it doesn't have").
- Durations stay null unless the source doc explicitly supplies them; if it does, copy the prose verbatim.

Body of `adventure.md` is a short prose summary from the source doc, with `[[wiki links]]` to the Reference notes you're also proposing. Sub-files for scenes/chapters may also be proposed (siblings to `adventure.md` in the same `adventures/<slug>/` directory) when the source doc has clearly distinct sub-sections worth their own files; otherwise keep it to `adventure.md`.

#### Thread shape (ADR-0004)

One file per Thread, in `threads/`. Filename is a slug of a short descriptive name. Frontmatter:

```yaml
---
status: open                         # required: open | closed | decayed
---
```

For ingest-era Threads extracted from a doc, status starts as `open` unless the doc explicitly says the thread is already resolved (then `closed`) or has gone stale (then `decayed`).

Body is one or two sentences describing the hook — what's owed, promised, or foreshadowed — with `[[wiki links]]` to relevant Reference notes.

Example: `threads/find-rulfs-killer.md`

```markdown
---
status: open
---

# Find Rulf's killer

[[Rulf]] was found dead in the [[Cragmaw Hideout]]; the party promised his
sister they would find who killed him.
```

#### Consequence shape (ADR-0004)

One file per Consequence, in `consequences/`. Filename is a slug. Frontmatter is valid YAML; the only field this slice requires is a `created` timestamp captured at write time so future Briefs can order by recency:

```yaml
---
created: YYYY-MM-DD                  # set at write time; real-world date the agent recorded the Consequence
---
```

Body is the persistent fact, one or two sentences, with `[[wiki links]]` to relevant Reference notes. Consequences are past-facing and don't have a status (ADR-0004).

Example: `consequences/lord-protector-owes-the-party.md`

```markdown
---
created: 2026-05-29
---

# The Lord Protector owes the party a favor

After the party recovered the [[Iron Banner]] for [[Sildar Hallwinter]], he
publicly declared he owes them one.
```

### Step 3b: Cross-doc dedup

Before presenting the per-doc review, match every drafted Reference note (NPC, location, faction, item) against existing files in the campaign repo. This applies both within the multi-doc loop (matching against files written by earlier docs in this run) and on the first doc of a multi-doc run (matching against any pre-existing Reference notes already in the campaign repo from a prior `/ingest` invocation). In the single-doc degenerate case, dedup still runs — it just matches only against pre-existing campaign files.

Reference notes are the **only** kind dedup applies to in this slice. Adventures get name-collision handling at Step 5 (the GM resolves; no auto-merge). Threads and Consequences are extracted only from what the doc explicitly says (ADR-0004); cross-doc Thread/Consequence dedup is a deliberate non-goal here — duplicates surface, and the GM trims them at review.

#### Matching procedure

For each drafted Reference note:

1. **Compute the candidate slug** using the same slugification rule used elsewhere in the project: lowercase, ASCII-fold accents, strip leading "the ", collapse whitespace and punctuation to single hyphens, trim leading/trailing hyphens.
2. **List the target folder** (`npcs/`, `locations/`, `factions/`, or `items/`) in the campaign repo. Match the candidate slug against existing filenames (without `.md`) and against the first-heading title inside each candidate file (light-normalised the same way).
3. **Classify the match** into one of three buckets:

   - **No match.** No file with that slug or normalised title exists in the target folder. Proceed as a CREATE — the proposed file lands as drafted.
   - **Confident match.** A file with the same slug **and** the same kind (target folder) exists, AND the role/disposition implied by the drafted body does not contradict what's already in the existing file. Concretely: same canonical name, same kind, no obvious "this is a different person who happens to share a name" signal in the surrounding prose. Propose an **update** to the existing file rather than a CREATE: append the drafted one-liner as a new sentence at the end of the existing body (or, if the drafted body would fully restate what's already there, propose a no-op with a note). Preserve any GM-authored prose in the existing file — never overwrite it.
   - **Ambiguous match.** A file with the same slug or a near-identical name exists, but at least one of these is true:
     - The role or disposition implied by the drafted body looks like it could be a *different* entity (e.g., the existing `npcs/john.md` is "John the innkeeper of Phandalin" and the drafted body is "John, a bandit in the Cragmaw Hideout").
     - The match is by similar-but-not-identical name (e.g., drafted "Sira" vs existing `npcs/sera.md`; "the Veiled Court" vs existing `factions/veiled-court.md` only after stripping "the").
     - The match crosses kinds (e.g., drafted location vs existing NPC of the same name).

     Surface the match to the GM as a **yes/no question** in the review screen. Do not silently pick. The agent's job here is to ask, not to choose.

4. **Apply carried-forward dedup decisions before asking.** If the carried-forward lessons set already contains a confirmed identity link for this candidate ("the Sera in this run is the same Sera as `npcs/sera.md`"), apply it as a confident match without re-asking. If the lessons contain a confirmed split ("the John from doc 3 is distinct from `npcs/john.md`"), drop the proposed dedup question and treat the candidate as a CREATE with a disambiguated slug (e.g., `npcs/john-the-bandit.md`) — confirm the disambiguated slug with the GM at the review screen, not silently.

#### Output of Step 3b

The drafted-proposal set from Step 3 is now annotated, per Reference note, with one of:

- **CREATE** — new file, no existing match.
- **UPDATE** — confident match against an existing file; the agent proposes a specific append-or-edit to that file.
- **ASK** — ambiguous match; the agent has a yes/no question for the GM that must be resolved at the review screen before this Reference note is written.

These annotations feed the per-doc review in Step 4.

### Step 4: Per-doc diff-style review

Present **all** proposed changes from this doc in a single review screen, before writing anything. Use whatever diff-style review affordance Claude Code provides in the current context:

- If a diff-style preview is available (e.g., the file write tool will show a per-file diff), present each proposed file as a creates-this-file or updates-this-file diff.
- Otherwise, show each file's full proposed content inline in fenced markdown blocks labelled with the target relative path, grouped by kind:

  1. Adventure (if any): `adventures/<slug>/adventure.md` and any sub-files.
  2. Reference notes: grouped by folder — NPCs, locations, factions, items. Annotate each as CREATE, UPDATE (with the existing path and the proposed addition shown), or ASK (with the yes/no question stated explicitly).
  3. Threads.
  4. Consequences.

Also list, before the per-file diffs:

- The GM-confirmed description from Step 1 (or carried over from the survey).
- **Lessons carried from prior docs in this run.** A short bulleted list of carried-forward lessons being applied to this doc's extraction. Empty for the first doc; non-empty from doc 2 onward in a multi-doc run. Empty for single-doc.
- A one-line summary count (e.g., *"1 Adventure, 4 Reference notes (3 NPCs CREATE, 1 location UPDATE), 1 ambiguous dedup question, 2 Threads, 1 Consequence"*).
- For multi-doc: the position of this doc in the run (e.g., *"Doc 2 of 4"*).
- The non-markdown files that will be skipped, by relative path (only on the first doc of the run; don't repeat per doc).

Then ask explicitly:

> *Approve all, edit, reject specific items, or reject everything? Also answer any ambiguous-dedup questions in the same response.*

Accept these responses:

1. **Approve all** → all ASK items must have been resolved by the GM in the same response (yes = treat as confident UPDATE; no = treat as CREATE with a disambiguated slug the GM confirms). Then proceed to Step 5 and write every proposed file.
2. **Edit** → the GM names one or more proposed files and supplies revisions (or asks the agent to revise specific fields). Apply edits to the in-memory drafts, re-present the affected items, ask again. Loop until the GM approves or rejects.
3. **Reject specific items** → the GM names items to drop. Remove them from the proposed set. Re-present the trimmed set, ask again. Rejections are first-class signals for cross-doc learning (Step 5b).
4. **Reject everything** → write nothing for this doc, leave the filesystem unchanged for this doc, and (in multi-doc) ask the GM whether to continue to the next doc or exit the run. Already-written approved files from prior docs in the same run stay written.

Rejected items must never be written. Approved items must be written exactly as approved (or as the GM edited them) — no late re-interpretation. Ambiguous-dedup ASK items that the GM doesn't resolve in the response must be re-asked before any write — the agent does not silently pick.

### Step 5: Write approved items

Once the GM approves:

1. Create any needed directories under the campaign repo: `adventures/<slug>/`, `npcs/`, `locations/`, `factions/`, `items/`, `threads/`, `consequences/` — but **only** those needed for approved items. Don't pre-create empty folders for kinds with no content (matches Phase 1 Step 2 rule).
2. For each approved item, dispatch by its Step 3b annotation:
   - **CREATE** — write the proposed file at its proposed path. If a path collision occurs against a Reference note that wasn't surfaced by Step 3b (e.g., because the slug differs from any existing file by some edge case the matching procedure missed), STOP and tell the GM the exact conflicting path. Do not overwrite without explicit GM confirmation.
   - **UPDATE** — modify the existing file as the GM approved. Default behavior is append the new sentence to the body; if the GM edited the proposed update to be an inline change or a frontmatter touch, apply that. Preserve any GM-authored prose; never overwrite a file's body wholesale at this step. If the existing file has changed on disk between Step 3b and Step 5 (race against the GM editing in another window), STOP and re-present the update before writing.
   - **CREATE (disambiguated from ASK)** — when an ambiguous match was resolved "no, distinct entity" and the GM confirmed a disambiguated slug at Step 4, write at the disambiguated path.
   - For **Adventure** name collisions (existing `adventures/<slug>/` directory), STOP and surface to the GM exactly as before. Slice 3 has no Adventure dedup.
3. Do not modify `campaign.md`, `CLAUDE.md`, or anything under `.claude/`. Campaign-overview regeneration belongs to Phase 4 (wrap-up; still a stub in this slice). Don't drift `campaign.md` from its scaffolded state.
4. Do **not** commit. Ongoing git ownership belongs to the GM (ADR-0011). The plugin only commits once, in the scaffold phase.

### Step 5b: Capture cross-doc learning

This step applies only in the multi-doc case. Single-doc has no subsequent doc to inform, so skip.

After the GM's approval/edit/rejection decisions for the current doc are settled (and before moving to the next doc), capture the lessons implied by those decisions into the carried-forward lessons set initialised in Step 0b. The point is to make the agent's behavior on doc N+1 reflect what the GM corrected on doc N, visibly and auditably.

Lessons worth carrying forward include:

- **Rejected kinds.** If the GM rejected one or more Reference notes of a recognisable shape — e.g., "the passing innkeeper", "the named-once-in-prose mercenary" — record a rejection lesson: *"Doc 1: do not propose passing innkeepers as Reference notes."* Apply on subsequent docs by not drafting those candidates, or by drafting them and explicitly flagging them as candidates the prior-doc lesson would drop (GM can override).
- **Classification preferences.** If the GM moved an item from Thread → Consequence, or from Reference note → narrative color (dropped entirely), record the preference: *"Doc 1: the GM treats one-line rumor mentions as narrative color, not Threads."*
- **Confirmed dedup identities.** If the GM confirmed an ambiguous dedup as "yes, same entity", record the identity link: *"`npcs/sera.md` is the campaign's Sera; future mentions consolidate here."* Use these to convert future ambiguous-match candidates into confident updates without re-asking.
- **Confirmed dedup splits.** If the GM said "no, distinct entity" and named a disambiguated slug, record the split: *"`npcs/john.md` (innkeeper) and `npcs/john-the-bandit.md` are distinct; future mentions of 'John' need disambiguation by context."*
- **Naming preferences.** Canonical-name choices the GM made when given a dedup ambiguity ("call them the Veiled Court, slug `veiled-court`").

Do not invent lessons. Only capture what the GM's decisions explicitly support. If a rejection is ambiguous in motive ("rejected this Reference note — was it because of the kind, or just this specific instance?"), note it as a candidate rather than a confirmed lesson and ask the GM at the top of doc N+1's review: *"Carrying forward as a candidate rule: do not promote passing innkeepers. Apply this rule, or was the previous rejection just about that specific innkeeper?"*

Carried-forward lessons are scoped to one ingest run. They do not persist into the next `/ingest` invocation. They are not written to any file — they live only in the agent's in-memory state for the duration of the run.

### Step 6: Closing summary

After the **last** doc in the run completes (or after the only doc, in the single-doc case), tell the GM, concisely:

- The source docs that were extracted, in processing order. For each: the relative path and the GM-confirmed description. In multi-doc, also note any docs the GM dropped during survey ordering and any docs where the GM rejected everything at review.
- A summary of what was written across the whole run (counts by kind, with the campaign-relative paths). Group by kind. For UPDATE operations on existing Reference notes, list those separately from CREATEs so the GM can see what got merged versus what's new.
- The non-markdown files that were skipped (relative paths), framed neutrally — they were ignored, not lost.
- In multi-doc, a short audit of carried-forward lessons that ended up applied during the run (one-line each). The GM can use this to spot any lesson that was over-broadly applied.
- A reminder that `campaign.md` was **not** regenerated (wrap-up phase ships in a later slice), and that the GM owns the next commit. Offer a one-line suggested commit message they can use — `Ingest single doc: <doc basename>` for single-doc, `Ingest <N> docs from <input dir basename>` for multi-doc.

Do not auto-commit. Do not auto-advance into wrap-up. Do not carry the lessons set forward to a future `/ingest` invocation — it dies with the run.

## Phase 4: Wrap-up (stub)

If the GM asks to finalize the ingest, respond:

> The `/ingest` wrap-up phase is not yet implemented. It will land in a later slice of `ttrpg-gm` v0.1.

Do not regenerate `campaign.md`. Do not prompt for `order:` values. Per-doc extraction (Phase 3) does not auto-advance into wrap-up; the GM invokes the wrap-up explicitly when it ships.

## What to avoid

- Don't use the words "DM", "game", "story" (for campaign), "world" (for Atlas), "hero", "hook" (overloaded), or "module" (reserved for *published* adventures only). Use the glossary in this plugin's `CONTEXT.md`.
- Don't auto-commit anything beyond the initial scaffolding commit. Ongoing git ownership belongs to the GM (see ADR-0011).
- Don't write to anywhere outside the target campaign directory.
- Don't ask the GM to fill out forms or pick from long lists. Capture-now-structure-later (ADR-0004).
- Don't invent dates, NPC names, or campaign details the source doc didn't provide.
- Don't extract Beats during ingest (ADR-0009 / CONTEXT.md — GM-authored only).
- Don't synthesize `sessions/YYYY-MM-DD-session-N/` directories from source docs (ADR-0005 — Sessions are created by `/prep-session`).
- Don't recurse into input subdirectories (ADR-0006 — flat directory only in v0.1).
- Don't silently overwrite an existing Reference note. Confident dedup matches propose **updates** (which the GM approves); ambiguous matches surface as yes/no questions; Adventure name collisions still stop and ask. The agent never picks identity silently.
- Don't carry cross-doc lessons across runs. They are scoped to one ingest invocation; the next `/ingest` starts with an empty lessons set.
- Don't apply a carried-forward rejection lesson to a candidate the GM might still want. When in doubt, surface the carried lesson and ask whether it should apply to this specific candidate — over-application is worse than re-asking.

## Quick reference: which ADR governs what

- **ADR-0003** — Reference notes are one file per entity in `npcs/`, `locations/`, `factions/`, `items/`. Default body is a one-liner.
- **ADR-0004** — Threads and Consequences are per-file. Threads have `status: open | closed | decayed`. Consequences have valid YAML frontmatter and persist (no status).
- **ADR-0006** — v0.1 input is flat-directory local markdown only; non-markdown is skipped, no recursion.
- **ADR-0007** — Adventure frontmatter schema (`status` required, `order` optional/ingest-era, dates optional/nullable, durations free-form prose). The agent never invents dates.
- **ADR-0008** — Ingest's full workflow is survey + per-doc + wrap-up; slice 3 implements the survey phase and the per-doc loop for both single-doc and multi-doc, including cross-doc dedup and cross-doc learning. Bounded skim plus GM-edited descriptions plus GM-confirmed processing order steer extraction.
- **ADR-0009** — Beats are GM-authored only; ingest does **not** create them.
- **ADR-0011** — Plugin doesn't own ongoing git operations beyond the scaffold commit.
- **ADR-0013** — Skill packaging (`skills/<name>/SKILL.md`); templates live under `templates/`.
