---
name: ingest
description: Extract structure from existing TTRPG campaign notes into a scaffolded campaign repo. In slice 4 of v0.1, all four phases are implemented — the scaffolder (writes the root CLAUDE.md, .claude/rules/sessions.md, .claude/rules/adventures.md, and a campaign.md placeholder into the target directory, then runs git init and an initial commit), the survey phase (discover input docs, bounded-skim each, propose one-line descriptions, present diff-style for GM edit, propose a processing order, confirm with GM), the per-doc extraction loop with multi-doc cross-doc dedup and cross-doc learning (walk docs in confirmed order, extract Reference notes / Adventure / Threads / Consequences per doc, dedup against existing campaign files with confident-update / ambiguous-ask thresholds, carry GM corrections forward as visible lessons applied to subsequent docs), and the wrap-up phase (bulk-prompt the GM for any missing Adventure `order:` values, regenerate `campaign.md` as the agent-maintained Campaign overview per ADR-0007, and make a follow-up git commit with a count-summary message capturing everything ingested since the scaffolder's initial commit).
---

# /ingest

`/ingest` is the workflow that turns an existing pile of campaign notes into a structured, agent-navigable campaign repo.

The full workflow has four phases:

1. **Scaffold** — write the plugin's templates into the target directory, `git init`, and make an initial commit. **(Implemented in slice 1.)**
2. **Survey** — discover input docs, bounded-skim each, propose a one-line description per doc as an editable diff-style list, propose a processing order (world info → adventures → session-shaped), confirm both with the GM. **(Implemented in slice 3.)**
3. **Per-doc extraction loop** — for each doc, in the confirmed processing order, extract Reference notes, adventure metadata, Threads, and Consequences; cross-doc dedup against existing campaign files (confident matches propose updates; ambiguous matches surface to the GM); present a per-doc proposed diff; the GM approves; corrections carry forward as visible lessons applied to subsequent docs. **(Single-doc case implemented in slice 2; multi-doc cross-doc dedup and cross-doc learning implemented in slice 3.)**
4. **Wrap-up** — bulk-prompt the GM for any missing `order:` values on ingest-era Adventures, regenerate the campaign-root `campaign.md` as the agent-maintained Campaign overview, and make a follow-up git commit capturing everything ingested since the scaffolder's initial commit. **(Implemented in slice 4.)**

In this slice, all four phases run end-to-end. Phase 4 runs after the per-doc loop completes (or, if the GM invokes `/ingest` on an already-populated repo just to finalize, runs against current campaign state).

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

### Step 2: Write the five template files

The plugin ships five templates under `~/.claude/skills/ttrpg-gm/templates/`. For each, read the template, substitute placeholders, and write to the target. Filenames have a `.template` suffix in the plugin; strip the suffix on write.

| Template source | Written to (relative to target) |
|---|---|
| `templates/CLAUDE.md.template` | `CLAUDE.md` |
| `templates/.claude/rules/sessions.md.template` | `.claude/rules/sessions.md` |
| `templates/.claude/rules/adventures.md.template` | `.claude/rules/adventures.md` |
| `templates/campaign.md.template` | `campaign.md` |
| `templates/.gitignore.template` | `.gitignore` |

The `.gitignore` excludes `.ttrpg-staging/`, which the skills use as a scratchpad for diff-style review surfaces (proposed descriptions, brief drafts, wrap proposals) that the GM edits in their IDE before approval. Staging contents are never committed.

Placeholder substitutions to apply to template content before writing:

- `{{CAMPAIGN_NAME}}` → the GM-supplied campaign name, verbatim.
- `{{CAMPAIGN_SYSTEM}}` → the GM-supplied system, verbatim.

Create intermediate directories as needed (notably `.claude/rules/`). Do not write any other files in this slice. In particular, do not create empty `npcs/`, `locations/`, `adventures/`, `sessions/`, `threads/`, `consequences/`, or `beats/` directories — they appear when content first lands in them, not before.

### Step 3: Initialize the git repo and make an initial commit

Run these commands in the target directory:

```
git init
git add CLAUDE.md .claude/rules/sessions.md .claude/rules/adventures.md campaign.md .gitignore
git commit -m "Scaffold campaign repo via ttrpg-gm /ingest"
```

If `git init` reports the directory is already a git repo, do **not** re-init. Stage and commit on the existing branch only with explicit GM confirmation; otherwise stop and tell the GM.

Do not configure `user.name` or `user.email` from the plugin. Use whatever the GM's git config provides; if the commit fails because git has no identity configured, surface the underlying git error to the GM verbatim and stop.

### Step 4: Report what was written

Tell the GM, concisely:

- the target directory (absolute path),
- the five files that were written (the four templates plus `.gitignore`),
- the initial commit's hash and message.

If the GM provided an input directory of source docs, continue directly into Phase 2. If `/ingest` was invoked scaffold-only (no input directory), the workflow ends here. Either way, no confirmation prompt — Phase 2 has its own review gates (description list, processing order), and Phase 3 has per-doc approval, so the GM has natural break points downstream.

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

### Step 3: Write the description list to a staging file for GM edit

Use the campaign repo's `.ttrpg-staging/` directory as the review surface — it's gitignored (Phase 1 Step 2) and is purpose-built for exactly this. Create it if it doesn't exist.

Write the proposed descriptions to `.ttrpg-staging/survey-descriptions.md` using the Write tool, so Claude Code's standard file-write diff shows the GM the full proposed list in their IDE. Format the file as one editable line per doc, with a short header explaining the edit contract:

```markdown
# Survey: proposed descriptions

Edit any line below to refine the description. Lines have the shape
`<relative path> — <classification>: <short summary>`. Keep one line per doc.
Don't add or remove lines (those reflect the docs discovered in the input
directory). When done, save the file and tell me to continue.

lost-mines.md         — Adventure: a published-module-shaped writeup of the Lost Mines arc.
faerun-gods.md        — World info: notes on the gods and calendar of Faerun, no Adventure structure.
session-1-notes.md    — Session log: the party's first delve into the Citadel, written as narrative.
campaign-overview.md  — Mixed / ambiguous: could be world info or campaign-meta notes; not enough in the skim to tell.
```

Below the description block, append a non-editable footer summary listing any non-markdown files that were skipped, so the GM has full context:

```markdown
---
Non-markdown files (skipped): art/map.png, art/sera.jpg.
```

Then ask explicitly: *"Edit the descriptions in `.ttrpg-staging/survey-descriptions.md` if you want changes, then tell me to continue. Or say cancel to exit cleanly."* Accept two response shapes:

1. **Continue** → re-read `.ttrpg-staging/survey-descriptions.md` from disk to capture any GM edits, parse the description lines, record them verbatim, continue to Step 4. If the GM removed or added lines (a contract violation), surface that and re-ask before proceeding.
2. **Cancel** → delete `.ttrpg-staging/`, write nothing else, exit cleanly (still report the non-markdown skip summary).

GM-corrected descriptions become the steering input each doc's full read uses in Phase 3 — don't silently re-classify a doc later in extraction. If Phase 3's full read reveals the GM-confirmed description was wrong, surface that to the GM and re-confirm before continuing.

### Step 4: Propose a processing order

Once descriptions are accepted, propose a processing order over the same list. The default order, per ADR-0008, is **world info first, adventures next, session-shaped docs last**. Within each band, preserve the GM-confirmed list order from Step 3 (their order is closer to their mental model than the filesystem order or a re-sort by name).

For docs whose accepted description is *"Mixed / ambiguous: …"*, slot them after world info and before adventures by default — Phase 3 will resolve the ambiguity per-doc, and that's the safest place to do so (world context is in, adventure-shaped extraction hasn't started yet). Surface this placement explicitly in the proposal so the GM can move it if they know better.

Write the proposed order to `.ttrpg-staging/survey-order.md` using the Write tool. The IDE shows the diff; the GM edits in place. Format:

```markdown
# Survey: proposed processing order

Edit the order below by rearranging lines. To skip a doc from extraction
entirely, delete its line — it will be reported in the closing summary as
intentionally skipped. When done, save the file and tell me to continue.

Default rule: world info → adventures → session-shaped. Mixed/ambiguous
docs are slotted after world info by default.

1. faerun-gods.md        — World info: notes on the gods and calendar of Faerun.
2. campaign-overview.md  — Mixed / ambiguous: could be world info or campaign-meta notes.
3. lost-mines.md         — Adventure: a published-module-shaped writeup of the Lost Mines arc.
4. session-1-notes.md    — Session log: the party's first delve into the Citadel.
```

Then ask explicitly: *"Edit the order in `.ttrpg-staging/survey-order.md` if you want changes, then tell me to continue. Or say cancel to exit cleanly."* Accept two response shapes:

1. **Continue** → re-read `.ttrpg-staging/survey-order.md` to capture GM edits, parse the order, renumber to match the GM's arrangement (the agent owns the integer indices; the GM owns the sequence). Continue to Step 5.
2. **Cancel** → delete `.ttrpg-staging/`, write nothing else, exit cleanly.

If the GM removed a doc entirely during ordering, drop it from the survey set — Phase 3 will not process it. Note removed docs in the closing summary so it's visible they were skipped on purpose.

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
- `order` stays null at the per-doc step unless the source doc has explicit numeric sequencing (e.g., "Adventure 1: …", "Chapter 3: …") that you can copy directly. When the source doc has no inferable sequence, leave `order:` null and Phase 4 will bulk-prompt the GM for it during wrap-up. (Phase 4 reads the frontmatter to decide: a non-null `order:` means Phase 3 found one in the source and the prompt is skipped; null means the GM needs to supply it.)
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
3. Do not modify `campaign.md`, `CLAUDE.md`, or anything under `.claude/` from inside Phase 3. Campaign-overview regeneration belongs to Phase 4. Don't drift `campaign.md` from its scaffolded state during the per-doc loop.
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
- A reminder that `campaign.md` has **not** yet been regenerated — Phase 4 (wrap-up) will do that — and that no commit has been made yet either. Phase 4 will propose the commit at the end of wrap-up.
- An explicit hand-off prompt: *"Run wrap-up now (order prompt for missing `order:` values, regenerate `campaign.md`, propose the ingest commit), or hold and let you inspect what landed first?"* Accept "wrap up", "go ahead", "hold", "cancel". On "wrap up" / "go ahead", continue into Phase 4 Step 0. On "hold" / "cancel", exit Phase 3 cleanly — the already-written approved files stay on disk; the GM can invoke wrap-up later.

Do not auto-advance into Phase 4 silently — the hand-off prompt is the gate. Do not carry the lessons set forward to a future `/ingest` invocation — it dies with the run.

## Phase 4: Wrap-up

The wrap-up phase runs **after** the last doc's Step 5 / Step 5b completes (Phase 3 Step 6 still runs; wrap-up follows it), or when the GM explicitly invokes the wrap-up against an already-populated campaign repo. It does three things, in order:

1. **Order prompt** — bulk-ask the GM for any missing `order:` values on Adventures whose order wasn't reliably inferable from source.
2. **`campaign.md` composer** — regenerate the campaign-root Campaign overview per ADR-0007, replacing the placeholder written by Phase 1.
3. **Secondary commit** — capture everything that landed in the campaign repo since the scaffolder's initial commit as a single follow-up commit, with a count-summary message the GM can override.

### Slice 4 scope

This slice implements Phase 4 for the **fresh-ingest** path (the GM has just run Phases 1 → 2 → 3 and is finalizing). Behavior on a **re-run** against an already-ingested campaign (e.g., the GM runs `/ingest` again after a prior wrap-up) is **undefined** for this slice — see the v0.1 boundaries note at the end of this Phase. Phase 4 is not idempotent in slice 4 and does not include a confirm-before-overwrite guard against a previously-generated `campaign.md`; the regeneration runs unconditionally because the only `campaign.md` Phase 4 expects to find is either the scaffolder's placeholder or a prior Phase 4 output, both of which it is the canonical author of.

### Step 0: Pre-flight check

Before doing any GM-visible prompting:

1. **Campaign repo state.** The same invariants from Phase 3 Step 0 must hold (`CLAUDE.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, `campaign.md` all present). If any are missing, stop and tell the GM the repo isn't scaffolded — Phase 4 cannot wrap up a repo that hasn't been scaffolded.
2. **Confirm wrap-up is wanted.** If Phase 4 is being invoked at the end of a Phase 3 run, tell the GM the per-doc loop is complete and ask explicitly: *"Run wrap-up now (order prompt, regenerate `campaign.md`, commit), or hold and let you inspect the repo first?"* Accept "wrap up", "go ahead", "hold", "cancel" as response shapes. If the GM holds or cancels, exit cleanly — the already-written files from Phase 3 stay on disk; the GM can invoke wrap-up later or commit themselves.
3. **Surface uncommitted state.** Run `git status --porcelain` in the campaign repo. The expected state at this point is "lots of new untracked files from Phase 3 plus a modified `campaign.md` once Phase 4 Step 2 regenerates it." If anything looks anomalous — e.g., uncommitted changes that *predate* Phase 3 because a prior run was interrupted — surface a short list and ask the GM to confirm before continuing. Don't silently swallow pre-existing state into the wrap-up commit.

### Step 1: Order prompt for missing `order:` values

Walk every `adventures/<slug>/adventure.md` file under the campaign repo.

1. **Read frontmatter** for each Adventure. Collect the slug, the H1 title (canonical name), the current `status`, and the current `order:` value.
2. **Identify the missing-order set.** An Adventure needs the order prompt **only** if both of these are true:
   - Its `order:` is null (Phase 3 left it null because the source doc didn't supply an inferable sequence).
   - Its source doc did not use explicit numeric Adventure sequencing the agent could have copied (e.g., the doc didn't say "Adventure 1: …", "Chapter 3: …", or the equivalent). In Phase 3, this manifested as the agent leaving `order:` null at write time; Phase 4 trusts that signal.

   Adventures whose `order:` was already filled in by Phase 3 (because the source doc had inferable sequencing) skip this prompt. Do not re-ask. Adventures whose source doc explicitly said "first run" or "earliest arc" but didn't supply a number still go in the missing-order set — the prompt is the right place to turn prose hints into a number.

3. **If the missing-order set is empty**, skip to Step 2. Tell the GM: *"All Adventures have an `order:` value already; skipping order prompt."*

4. **If the missing-order set has exactly one Adventure**, ask the simpler form: *"`adventures/<slug>/adventure.md` doesn't have an `order:` set. What sequence number should it have (1 = earliest in the campaign's history)?"* Accept a single integer.

5. **If the missing-order set has more than one Adventure**, present them as a single bulk prompt with the GM filling in the whole sequence at once — **not** one prompt per Adventure. Example formatting:

   ```
   The following Adventures don't have an `order:` value set, and their
   source docs didn't have explicit "Adventure N" numbering for me to copy.
   In what order did they run? (1 = earliest in the campaign's history.)

     a. adventures/lost-mines/             — Lost Mines of Phandelver
                                              (status: completed)
     b. adventures/cragmaw-castle/         — Cragmaw Castle
                                              (status: completed)
     c. adventures/wave-echo-cave/         — Wave Echo Cave
                                              (status: active)

   Reply with the order — e.g., "a=1, b=2, c=3" or just "a, b, c" or
   "b, a, c" — or "skip" to leave them null for now.
   ```

   Use letters (a, b, c, …) for the prompt list, not numbers, so the GM's *answer* (the actual sequence numbers) isn't visually conflated with the prompt's labels.

6. **Parse the GM's reply tolerantly.** Accept these shapes:

   - Explicit assignments: `a=1, b=2, c=3` or `a:1 b:2 c:3`.
   - Implicit sequence (letters in order): `a, b, c` means a=1, b=2, c=3. `b, a, c` means b=1, a=2, c=3.
   - Numeric list matching the prompt order: `1, 2, 3` means the first-listed Adventure (a) is order 1, second (b) is order 2, etc.
   - "skip" (or "leave null", "don't know") → leave the whole set null and continue to Step 2 with a one-line note in the closing summary.
   - Partial answer (GM gives orders for some but not all): apply the given orders, leave the others null, and note which were left null in the closing summary. Do not re-prompt for the remainder unless the GM asks.

   If the reply doesn't parse, show what you understood and ask the GM to clarify rather than guessing. Don't apply a partial parse silently.

7. **Validate.** Sequence numbers should be positive integers. Duplicates are allowed if the GM truly believes two Adventures ran in parallel ("they were both active at the same time"), but flag duplicates explicitly: *"Two Adventures will share `order: 2` — is that intentional, or did you mean to split them?"* Apply only after explicit confirmation.

8. **Write the `order:` values into Adventure frontmatter.** For each Adventure with a confirmed new order, edit the `order:` line in its `adventures/<slug>/adventure.md` frontmatter from `~` to the integer. Preserve every other frontmatter field, every existing body byte, and the YAML shape from Phase 3. If the Adventure's frontmatter is malformed for any reason, surface the path to the GM and skip the write — don't try to repair it.

The carried-forward lessons set from Phase 3 is irrelevant here; the order prompt is a one-shot question against current Adventure frontmatter and doesn't consult lessons.

### Step 2: `campaign.md` composer

Replace the campaign-root `campaign.md` (currently the Phase 1 placeholder or a prior Phase 4 output) with a generated overview per ADR-0007.

This composer's section shape and tone must match `/wrap-session`'s Step 5.7 (`skills/wrap-session/SKILL.md`) so the two produce a consistent campaign overview from the same campaign state. Skills don't share code; consistency is by alignment of these specs. If the two drift, treat that as a documentation bug to fix in both places. Slice-4 ingest differs from `/wrap-session` regen in two visible ways, both flowing from what's true at ingest time:

- Ingest lists **every** Adventure (ordered by `order:`), not only `status: active` ones. At ingest time, "the campaign's whole history through today" is what the GM is finalizing; restricting to active Adventures would hide most of what just got written. `/wrap-session` shows only active Adventures because by then the static history is established and the GM cares about what's live.
- Ingest treats every Consequence as "recent significant" (because there is no session-tracked recency yet; everything just landed). `/wrap-session` filters Consequences by recency.

#### Sections, in this order

Write `campaign.md` from scratch. Do not preserve manual GM edits to the prior `campaign.md` content — per ADR-0007, manual edits to `campaign.md` are reconciled or overwritten with warning at regeneration, and Phase 4 chooses overwrite. (If the GM has campaign-editorial content like themes, pitch, or house rules, that lives in a separate file the agent doesn't touch — see CLAUDE.md.template.)

```markdown
# {{CAMPAIGN_NAME}} — Campaign Overview

*This file is agent-maintained. It snapshots the campaign's current state in glance-readable form and is rewritten by `/wrap-session` and `/ingest`. Manual edits will be reconciled (or overwritten with warning) at the next regeneration. For editorial campaign notes (themes, pitch, house rules), use a separate file the agent doesn't touch.*

- **Campaign:** {{CAMPAIGN_NAME}}
- **System:** {{CAMPAIGN_SYSTEM}}
- **Status:** active
- **Last event:** {{TODAY_YYYY-MM-DD}} (ingest)

## Adventures

<every Adventure, ordered by `order:` ascending with null-order Adventures at the end, one bullet each>

## Open threads

<every Thread with `status: open`, one bullet each>

## Recent significant consequences

<every Consequence, one bullet each>

## Party location

<best-effort short prose, derived from the most recently active Adventure>

## Pending beats

*None yet. Beats are GM-authored or proposed by `/wrap-session`.*
```

The header comment paragraph (the italics block) is preserved verbatim from the template — it tells the GM the file is agent-maintained, which is true for both Phase 4 and future `/wrap-session` regens.

#### Header

- `{{CAMPAIGN_NAME}}` — read from the existing `campaign.md`'s H1 or `**Campaign:**` line, whichever Phase 1 wrote. Don't re-prompt the GM. If neither is parseable for some reason, surface the path and ask before continuing — do not invent a name.
- `{{CAMPAIGN_SYSTEM}}` — same source as Phase 1 wrote.
- **Status:** always `active` at the end of a fresh ingest. The campaign object as a whole doesn't have a status frontmatter in v0.1; this line is human-readable text. If the GM later abandons the whole campaign, that becomes a manual edit (and gets overwritten by future regens unless `/wrap-session` learns a Campaign-status field, which is out of scope here).
- **Last event:** today's date in `YYYY-MM-DD` (the ingest date), suffixed `(ingest)`. After a `/wrap-session` run lands, that workflow will replace this line with the wrapped session's date.

#### Adventures

List **every** Adventure in the campaign, in this order:

1. Sort by `order:` ascending. Null-order Adventures (those the GM skipped at Step 1) go after numbered ones, in alphabetical slug order.
2. For each Adventure, render a bullet:

   ```
   - **[[<Adventure title>]]** (order N) — <status>. <lifecycle annotations from frontmatter>.
   ```

   - `<Adventure title>` is the H1 from `adventure.md`. The wiki link points at the Adventure (resolves to `adventures/<slug>/` by name).
   - `(order N)` is shown only if `order:` is set; omit the parenthetical otherwise.
   - `<status>` is the literal frontmatter `status` value: `introduced`, `active`, `completed`, or `abandoned`.
   - **Lifecycle annotations** are the optional frontmatter fields, joined as a short comma-separated phrase:
     - `in_world_duration` rendered verbatim if set (e.g., "~3 in-game months").
     - `real_world_duration` rendered verbatim if set (e.g., "~6 sessions").
     - `started` rendered as "started YYYY-MM-DD" if set; ingest-era usually null.
     - `completed` rendered as "completed YYYY-MM-DD" if set; ingest-era usually null.

     If all four are null, omit the annotations clause entirely — don't write a trailing period after nothing.

   Example bullets:

   ```
   - **[[Lost Mines of Phandelver]]** (order 1) — completed. ~6 sessions, ~3 in-game months.
   - **[[Cragmaw Castle]]** (order 2) — completed. ~4 sessions.
   - **[[Wave Echo Cave]]** (order 3) — active.
   - **[[Side Mystery: The Veiled Court]]** — introduced.
   ```

3. If there are zero Adventures, write `*None yet.*` under the Adventures heading. (Possible but unusual at end of ingest — would mean the source corpus was world-info-only.)

#### Open threads

For every `threads/<slug>.md` with frontmatter `status: open`, render a bullet:

```
- **[[<Thread title>]]** — <one-line body excerpt>.
```

- `<Thread title>` is the file's H1.
- `<one-line body excerpt>` is the first sentence of the Thread's body (after the H1 and blank line). Truncate at the first period for terseness if the body is multi-sentence. Preserve wiki links inside the excerpt verbatim (don't strip `[[...]]`).
- Order: descending by `created:` if frontmatter `created:` is set (most recent first); for ingest-era Threads where `created:` may be absent, fall back to lexicographic slug order. Don't invent a `created:` value.

If there are zero open Threads, write `*None._`.

#### Recent significant consequences

For every `consequences/<slug>.md`, render a bullet:

```
- **[[<Consequence title>]]** — <one-line body excerpt>.
```

Same excerpt rules as Threads. Order: descending by `created:` (which Phase 3 sets at write time). At ingest time, all Consequences just landed today, so the order will effectively be slug order — that's fine.

At ingest time, this list shows **every** Consequence. Do not truncate to a top-N. Future `/wrap-session` runs filter to most-recent-N for glance-readability; ingest's "everything just landed" semantics mean truncation would hide the just-ingested history the GM is about to commit.

If there are zero Consequences, write `*None._`.

#### Party location

Best-effort short prose, one or two sentences. Derive as follows:

1. Among `status: active` Adventures, pick the one with the **highest `order:`** (the most recently started, per ADR-0007's "ingest-era ordering"). If multiple Adventures tie or none are active, fall back to the highest-`order:` Adventure overall regardless of status. If `order:` is null across the board, fall back to the alphabetically-last Adventure slug — and explicitly call this out in the prose ("best-effort guess; no `order:` set").
2. Read that Adventure's `adventure.md` body for any explicit location reference: a wiki link to a `locations/<slug>.md` file is the strongest signal; failing that, a clearly-named place mentioned in prose.
3. If a location is identifiable, write: *"The party is at [[<Location>]], most recently engaged with [[<Adventure>]]."* (Or a close variant; this is prose, not a template — match the campaign's tone if the GM's input docs had a clear voice.)
4. If no location is identifiable but an Adventure is, write: *"The party's most recent activity is [[<Adventure>]]; current location not stated in source docs — GM to update."*
5. If neither is identifiable (zero Adventures, or all are introduced-status with no location prose), write: *"Party location not yet established — GM to update."*

Do **not** invent a location. The "best-effort" framing in the issue spec explicitly carves out a placeholder for the GM to fill in. ADR-0007 is clear: the agent never asks the GM to invent facts it doesn't have.

#### Pending beats

Always renders as the literal placeholder:

```
*None yet. Beats are GM-authored or proposed by `/wrap-session`.*
```

Per ADR-0009 and CONTEXT.md, Beats are GM-authored only; ingest does not create them. The section appears (so the shape matches `/wrap-session`'s regen) but is trivially empty at ingest time. Don't omit the heading — the GM needs to know the agent looked.

### Step 3: Secondary commit

After Step 1 (any `order:` writes) and Step 2 (the `campaign.md` regeneration) have both landed on disk, make a single follow-up git commit in the campaign repo capturing everything that's changed since the scaffolder's initial commit.

This is the deliberate exception to the no-auto-commit rule. `/wrap-session` does not auto-commit (ADR-0011); the GM owns ongoing commits with their own messages. **But** `/ingest` Phase 1 already broke that pattern once by making the scaffolder's initial commit, and Phase 4 is the symmetric bookend: the scaffolder committed the templates, and wrap-up commits the populated campaign that the rest of `/ingest` just produced. The pattern is *the plugin owns commits at the bookends of `/ingest` only*; ADR-0011 governs every commit *after* `/ingest` has finished. The issue spec explicitly asks for this commit; ADR-0011 is about the steady state.

Surface this reasoning to the GM in the same exchange as the proposed commit message — see Step 3b below — so it's auditable, not hidden.

#### Step 3a: Compute counts

Walk the working tree from the campaign repo root. For each kind, count files that are **new since the scaffolder's initial commit** (use `git status --porcelain` plus `git diff --name-status <scaffold-commit>..HEAD` if anything was already committed, plus the new untracked files). For the wrap-up commit, this will typically be everything in:

- `npcs/` — count of new files, broken down isn't required but call out by kind if non-trivial: NPCs, locations, factions, items each as their own count.
- `locations/`, `factions/`, `items/` — same.
- `adventures/` — count of new `adventures/<slug>/adventure.md` files (one per Adventure; don't count sub-files separately for the headline count, but mention sub-files in the body if any exist).
- `threads/` — count of new Thread files.
- `consequences/` — count of new Consequence files.
- `campaign.md` — modified (the Phase 4 Step 2 regen).
- Anything else (e.g., the GM authored Beats during ingest, which is not the standard path but possible if they hand-wrote one before invoking wrap-up) — count it but note it as "other" in the proposed message.

Modified files from Phase 3 (UPDATEs to existing Reference notes) are counted under "Reference notes updated" separately from new ones, mirroring Phase 3 Step 6's closing-summary distinction.

#### Step 3b: Propose the commit message

Present the proposed commit message to the GM, with the reasoning for the auto-commit framed once explicitly, and let the GM edit or override before the commit lands. Example:

```
Phase 4 will make a single follow-up commit capturing the ingest. This is
the symmetric bookend to the scaffolder's initial commit — Phase 1 committed
the templates, Phase 4 commits the populated campaign. After this commit,
the plugin doesn't make further commits on its own (ADR-0011); you own every
subsequent commit.

Proposed commit message:

    Initial ingest: 12 Reference notes (8 NPCs, 3 locations, 1 faction),
                    2 Adventures, 4 Threads, 3 Consequences

Files that will be staged and committed:
  - npcs/ (8 new)
  - locations/ (3 new)
  - factions/ (1 new)
  - adventures/lost-mines/, adventures/cragmaw-castle/ (2 new)
  - threads/ (4 new)
  - consequences/ (3 new)
  - campaign.md (modified — Phase 4 regen)

Approve, edit the message, edit the staged set, or skip the commit?
```

Accept these responses:

1. **Approve** → proceed to Step 3c and make the commit with the proposed message.
2. **Edit the message** → the GM supplies a replacement message (any form — git's standard rules apply, multi-line is fine). Use the GM's message verbatim. Re-present the file list with the new message; ask again.
3. **Edit the staged set** → the GM names files or directories to drop from the commit (e.g., they want to commit Adventures separately from Reference notes). Remove them from the staged set; re-present; ask again. Don't drop the `campaign.md` regen unless the GM explicitly says so — it's load-bearing.
4. **Skip the commit** → make no commit. Leave the working tree as-is (files written by Phase 3 and Phase 4 stay on disk, just uncommitted). Tell the GM in the closing summary that the commit was skipped and surface a copy-paste-ready `git add ... && git commit -m '...'` block. The GM owns the next commit.

#### Step 3c: Stage and commit

Once the GM approves:

1. Stage exactly the file set the GM approved. Prefer naming files and directories explicitly (e.g., `git add npcs/ locations/ adventures/ threads/ consequences/ campaign.md`) over `git add -A` so the GM can see what's staged.
2. Run `git commit -m <message>` with the approved message. Multi-line messages should be passed via `-m` per paragraph or via a heredoc — whichever the tool affordance supports.
3. Do **not** configure `git config user.name` or `git config user.email` from the plugin. Use whatever the GM's git config provides; if the commit fails because git has no identity configured, surface the underlying git error to the GM verbatim and stop without retrying.
4. After commit, run `git status` and surface its output to the GM in the closing summary — they should see a clean working tree.

If the commit fails for any other reason (pre-commit hook failure, signing failure, etc.), surface the underlying git error verbatim and stop. Do not retry. Do not amend. The GM will resolve and either re-invoke wrap-up or finish the commit themselves.

### Step 4: Closing summary

First, **clean up `.ttrpg-staging/`** in the campaign repo (`rm -rf` the directory if present). Staging held the survey artifacts the GM edited in Phase 2; ingest is now complete and the directory has served its purpose. Cleanup also avoids leaving a confusing artifact for `/prep-session` or `/wrap-session` to trip over.

Then, after the commit lands (or after the GM skips the commit), tell the GM, concisely:

- **Order prompt outcome.** Adventures whose `order:` was set in Step 1 (with the assigned numbers). Adventures left null (if the GM skipped or partially answered). Adventures that already had `order:` (and were not prompted).
- **`campaign.md` regenerated.** Note that the prior placeholder was overwritten. If the prior `campaign.md` had detectable manual GM edits (content that differed from the scaffolder's placeholder before Phase 4 ran), surface that as a warning per ADR-0007. In the fresh-ingest path this should be rare — the only way to have hand-edited `campaign.md` between Phase 1 and Phase 4 is for the GM to have done it during Phase 3.
- **Counts of what landed.** Reference notes by kind (NPCs / locations / factions / items, broken down CREATE vs UPDATE), Adventures, Threads, Consequences. Mirror Phase 3 Step 6's grouping so the two summaries are comparable.
- **Commit status.** The commit hash and the message (or, if skipped, a copy-paste-ready commit command).
- **`git status` output.** Confirm the working tree is clean (or, if the GM skipped the commit, surface the uncommitted file list).
- **What's next.** Briefly: the GM can now invoke `/prep-session` to start the session loop, or `/wrap-session` if they have a session's `notes.md` already in place. Don't auto-invoke either.

End cleanly. Do not loop back into Phase 3.

### v0.1 boundaries

- **Re-run semantics are out of scope.** If the GM re-invokes `/ingest` against an already-ingested campaign repo (a `campaign.md` that's already been Phase-4-regenerated, plus existing Reference notes / Adventures / etc.), Phase 1's existing-campaign guard will catch it at the scaffolder step. Phase 4 specifically does **not** include a confirm-before-overwrite guard against a prior Phase 4 output; if the GM bypasses Phase 1 and jumps straight to wrap-up on an already-ingested repo, behavior is undefined. ADR-0011's confirm-before-overwrite pattern is a template for the follow-up slice that handles this case.
- **Single auto-commit.** Phase 4 makes exactly one follow-up commit. Subsequent `/ingest` invocations (when re-run lands) will have their own bookend commit logic; that's a future slice's problem.
- **No `campaign.md` reconciliation.** Phase 4 overwrites the placeholder unconditionally. Future `/wrap-session` regens follow ADR-0007's "reconciled or overwritten with warning" rule, but for the first regen Phase 4 always overwrites.

## What to avoid

- Don't use the words "DM", "game", "story" (for campaign), "world" (for Atlas), "hero", "hook" (overloaded), or "module" (reserved for *published* adventures only). Use the glossary in this plugin's `CONTEXT.md`.
- Don't auto-commit anything beyond `/ingest`'s two bookend commits — the scaffolder's initial commit (Phase 1 Step 3) and the wrap-up's follow-up commit (Phase 4 Step 3). Ongoing git ownership belongs to the GM thereafter (see ADR-0011). `/wrap-session` and every other workflow downstream of `/ingest` does not auto-commit.
- Don't write to anywhere outside the target campaign directory.
- Don't ask the GM to fill out forms or pick from long lists. Capture-now-structure-later (ADR-0004).
- Don't invent dates, NPC names, or campaign details the source doc didn't provide.
- Don't extract Beats during ingest (ADR-0009 / CONTEXT.md — GM-authored only).
- Don't synthesize `sessions/YYYY-MM-DD-session-N/` directories from source docs (ADR-0005 — Sessions are created by `/prep-session`).
- Don't recurse into input subdirectories (ADR-0006 — flat directory only in v0.1).
- Don't silently overwrite an existing Reference note. Confident dedup matches propose **updates** (which the GM approves); ambiguous matches surface as yes/no questions; Adventure name collisions still stop and ask. The agent never picks identity silently.
- Don't carry cross-doc lessons across runs. They are scoped to one ingest invocation; the next `/ingest` starts with an empty lessons set.
- Don't apply a carried-forward rejection lesson to a candidate the GM might still want. When in doubt, surface the carried lesson and ask whether it should apply to this specific candidate — over-application is worse than re-asking.
- Don't ask the GM for `order:` one Adventure at a time when more than one is missing. Phase 4's order prompt is a single bulk question covering the whole missing-order set; one-at-a-time prompting is the form the slice spec explicitly avoids.
- Don't invent a party location in the Phase 4 `campaign.md` regen. If the source docs don't supply one, the section reads as a "GM to update" placeholder.
- Don't truncate the Phase 4 Consequence list. At ingest time, every Consequence is "recent" — truncation belongs to `/wrap-session`'s regen, not `/ingest`'s.
- Don't re-prompt for `order:` on Adventures whose source docs already supplied it (i.e., where Phase 3 wrote a non-null `order:`). The order prompt's whole point is to fill *missing* values, not re-litigate inferred ones.

## Quick reference: which ADR governs what

- **ADR-0003** — Reference notes are one file per entity in `npcs/`, `locations/`, `factions/`, `items/`. Default body is a one-liner.
- **ADR-0004** — Threads and Consequences are per-file. Threads have `status: open | closed | decayed`. Consequences have valid YAML frontmatter and persist (no status).
- **ADR-0006** — v0.1 input is flat-directory local markdown only; non-markdown is skipped, no recursion.
- **ADR-0007** — Adventure frontmatter schema (`status` required, `order` optional/ingest-era, dates optional/nullable, durations free-form prose) and the agent-maintained `campaign.md` Campaign overview shape that Phase 4 Step 2 composes. The agent never invents dates.
- **ADR-0008** — Ingest's full workflow is survey + per-doc + wrap-up; slice 4 implements all four phases (survey, per-doc loop with cross-doc dedup and learning, and wrap-up with the bulk order prompt, `campaign.md` composer, and follow-up commit). Bounded skim plus GM-edited descriptions plus GM-confirmed processing order steer extraction.
- **ADR-0009** — Beats are GM-authored only; ingest does **not** create them. Phase 4's `campaign.md` renders the "Pending beats" section as a literal "none yet" placeholder.
- **ADR-0011** — Plugin doesn't own ongoing git operations beyond `/ingest`'s two bookend commits (the scaffolder's initial commit and Phase 4's follow-up commit). `/wrap-session` and every workflow downstream of `/ingest` does not auto-commit. The follow-up commit is `/ingest`'s symmetric bookend, not a precedent for steady-state auto-commit.
- **ADR-0013** — Skill packaging (`skills/<name>/SKILL.md`); templates live under `templates/`.
