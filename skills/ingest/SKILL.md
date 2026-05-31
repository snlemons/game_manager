---
name: ingest
description: Extract structure from existing TTRPG campaign notes into a scaffolded campaign repo. In slice 4 of v0.1, all four phases are implemented — the scaffolder (writes the root CLAUDE.md, .claude/rules/sessions.md, .claude/rules/adventures.md, and a campaign.md placeholder into the target directory, then runs git init and an initial commit), the survey phase (discover input docs, bounded-skim each, propose one-line descriptions, present diff-style for GM edit, propose a processing order, confirm with GM), the per-doc extraction loop with multi-doc cross-doc dedup and cross-doc learning (walk docs in confirmed order, extract Reference notes / Adventure / Threads / Consequences / Beats / Secrets per doc — classifying Beats by `kind:` from section headings and populating Secret `belongs_to:` from the ingested Adventure plus any named NPCs/Locations/Factions; dedup against existing campaign files with confident-update / ambiguous-ask thresholds; carry GM corrections forward as visible lessons applied to subsequent docs), and the wrap-up phase (bulk-prompt the GM for any missing Adventure `order:` values, regenerate `campaign.md` as the agent-maintained Campaign overview per ADR-0007, and make a follow-up git commit with a count-summary message capturing everything ingested since the scaffolder's initial commit).
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

## Settings preflight (run once before any phase touches an existing campaign)

Before any other work, follow the procedure in `~/.claude/skills/ttrpg-gm/references/preflight.md` against the campaign root the GM named (or cwd if the GM didn't name one and cwd is a scaffolded campaign repo). The preflight is a no-op when `.claude/settings.json` is absent — which is the normal Phase 1 fresh-scaffold case — so running it unconditionally at the top of the invocation is safe. For Phase 2 / Phase 3 / Phase 4 invocations against an already-scaffolded campaign, the preflight catches the moved-campaign case and offers the GM a regenerate-or-proceed prompt. If the GM declines regeneration, continue with the current settings — do not warn again this run. If the GM accepts, the file is rewritten and `/ingest` continues with no further preflight output.

Run the preflight exactly once per `/ingest` invocation; cache the result across all phases of the run.

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

### Step 2: Write the six template files

The plugin ships six templates under `~/.claude/skills/ttrpg-gm/templates/`. For each, read the template from its **absolute install path** (the agent's cwd is the *campaign* directory, not the plugin install — relative paths like `templates/foo` will not resolve), substitute placeholders, and write to the target. Filenames have a `.template` suffix in the plugin; strip the suffix on write.

**Order matters: `.claude/settings.json` is written FIRST so its permission rules are in effect before the remaining five writes.** The agent's first write of `.claude/settings.json` will prompt the GM for permission (the file doesn't exist yet, so no campaign-scoped permissions apply yet — this is unavoidable). After the GM accepts, the freshly-written `permissions.allow` array covers the remaining five template writes (`CLAUDE.md`, `.claude/rules/*`, `campaign.md`, `.gitignore` are all in the allow list), and the rest of Phase 1 proceeds without further prompts. The file is written first even though it isn't committed (see Step 3) — it's gitignored from the start because it carries machine-local absolute paths.

Write the templates in this exact order:

| # | Template source (read from this absolute path) | Written to (relative to target) |
|---|---|---|
| 1 | `~/.claude/skills/ttrpg-gm/templates/.claude/settings.json.template` | `.claude/settings.json` |
| 2 | `~/.claude/skills/ttrpg-gm/templates/CLAUDE.md.template` | `CLAUDE.md` |
| 3 | `~/.claude/skills/ttrpg-gm/templates/.claude/rules/sessions.md.template` | `.claude/rules/sessions.md` |
| 4 | `~/.claude/skills/ttrpg-gm/templates/.claude/rules/adventures.md.template` | `.claude/rules/adventures.md` |
| 5 | `~/.claude/skills/ttrpg-gm/templates/campaign.md.template` | `campaign.md` |
| 6 | `~/.claude/skills/ttrpg-gm/templates/.gitignore.template` | `.gitignore` |

The `.gitignore` excludes `.ttrpg-staging/`, which the skills use as a scratchpad for diff-style review surfaces (proposed descriptions, brief drafts, wrap proposals) that the GM edits in their IDE before approval. Staging contents are never committed.

The `.claude/settings.json` pre-approves the standard Edit/Write/MultiEdit operations the plugin's skills perform on the campaign's structured folders (`npcs/`, `locations/`, etc.) so the GM isn't prompted for every file the agent writes during routine extraction. It also pre-approves a few read-only git commands the skills run for state inspection. The file is **gitignored** (the scaffolder's `.gitignore` excludes `.claude/settings.json`) because it carries absolute paths baked in at scaffold time — committing it would just guarantee drift on clone. The convention (which paths the plugin pre-approves) follows the campaign via the scaffolder template, not via a committed file; a fresh clone regenerates the file by re-running `/ingest` Phase 1 against the clone's location.

Placeholder substitutions to apply to template content before writing:

- `{{CAMPAIGN_NAME}}` → the GM-supplied campaign name, verbatim.
- `{{CAMPAIGN_SYSTEM}}` → the GM-supplied system, verbatim.
- `{{CAMPAIGN_PATH}}` → the resolved absolute path of the target campaign directory (e.g. `/Users/sofia/Documents/my-campaign`), **without** a trailing slash. The template uses this to bake absolute-path permission rules into `.claude/settings.json` (with a leading `/` already present in the template so the result is the `//absolute/path` form Claude Code's permission matcher requires). This makes permission grants survive any cwd or project-root resolution oddities. The cost is that moving the campaign directory invalidates the paths — the GM would need to regenerate or hand-edit `.claude/settings.json` after a move.
- `{{HOME}}` → the resolved absolute home directory path of the user running `/ingest` (e.g. `/Users/sofia`), **without** a trailing slash. Resolve via `pathlib.Path.home()` or the shell `$HOME`. The template uses this to bake the absolute path of the plugin install (`~/.claude/skills/ttrpg-gm/**`) into the `Read(...)` permission rule, because Claude Code's permission matcher does not expand `~` at match time — the matcher compares the agent's resolved-absolute Read target against the rule string verbatim, so `Read(~/...)` alone fails to match a Read of `/Users/sofia/.claude/...` (issue #63, replacing the broken assumption in commit 8f64219). The template ships both forms: the literal `~/...` rule (harmless if redundant; load-bearing if a future Claude Code version expands `~` in some scenarios) and the substituted `{{HOME}}/...` rule (the one empirically required). Moving the home directory or migrating to a new machine invalidates the baked path the same way moving the campaign does — the preflight catches this on next skill run.

Create intermediate directories as needed (notably `.claude/rules/`). Do not write any other files in this slice. In particular, do not create empty `npcs/`, `locations/`, `adventures/`, `sessions/`, `threads/`, `consequences/`, or `beats/` directories — they appear when content first lands in them, not before.

### Step 3: Initialize the git repo and make an initial commit

Run these commands in the target directory:

```
git init
git add CLAUDE.md .claude/rules/sessions.md .claude/rules/adventures.md campaign.md .gitignore
git commit -m "Scaffold campaign repo via ttrpg-gm /ingest"
```

`.claude/settings.json` is **not** included in the `git add` argument list — it was written in Step 2 (so its permissions are in effect for the rest of Phase 1) but it's gitignored by the `.gitignore` Phase 1 just wrote, so it stays untracked. Five files committed; six files written.

If `git init` reports the directory is already a git repo, do **not** re-init. Stage and commit on the existing branch only with explicit GM confirmation; otherwise stop and tell the GM.

Do not configure `user.name` or `user.email` from the plugin. Use whatever the GM's git config provides; if the commit fails because git has no identity configured, surface the underlying git error to the GM verbatim and stop.

### Step 4: Report what was written

Tell the GM, concisely:

- the target directory (absolute path),
- the five files committed in the initial commit (the four content templates plus `.gitignore`); note `.claude/settings.json` was also written but is intentionally gitignored (machine-local absolute paths),
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

Write the proposed descriptions to `.ttrpg-staging/survey-descriptions.md` using the Write tool, so Claude Code's standard file-write diff shows the GM the full proposed list in their IDE. Format each doc as a path header line followed by its description on the next line, with a blank line between entries, and a short header explaining the edit contract:

```markdown
# Survey: proposed descriptions

Edit any description below to refine it. Each entry is a relative path on
its own line, followed by `<classification>: <short summary>` on the next
line. Keep one entry per doc and don't add or remove path lines (those
reflect the docs discovered in the input directory). When done, save the
file and tell me to continue.

lost-mines.md
Adventure: a published-module-shaped writeup of the Lost Mines arc.

faerun-gods.md
World info: notes on the gods and calendar of Faerun, no Adventure structure.

session-1-notes.md
Session log: the party's first delve into the Citadel, written as narrative.

campaign-overview.md
Mixed / ambiguous: could be world info or campaign-meta notes; not enough in the skim to tell.
```

Below the description block, append a non-editable footer summary listing any non-markdown files that were skipped, so the GM has full context:

```markdown
---
Non-markdown files (skipped): art/map.png, art/sera.jpg.
```

Then ask explicitly: *"Edit the descriptions in `.ttrpg-staging/survey-descriptions.md` if you want changes, then tell me to continue. Or say cancel to exit cleanly."* Accept three response shapes:

1. **Continue** → re-read `.ttrpg-staging/survey-descriptions.md` from disk to capture any GM edits, parse the description lines, record them verbatim, continue to Step 4. If the GM removed or added lines (a contract violation), surface that and re-ask before proceeding.
2. **Cancel** → delete `.ttrpg-staging/`, write nothing else, exit cleanly (still report the non-markdown skip summary).
3. **Verbal refinement** ("rephrase X to Y", "the Foo description should mention Bar", etc.) → apply each requested change to `.ttrpg-staging/survey-descriptions.md` using the **Edit** tool, one surgical edit per change so the IDE shows a native hunk diff per [ADR-0015](../../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). Do **not** rewrite the whole file with Write (the bulk overwrite buries the diff) and do **not** use Bash redirects (no diff surfaces at all). After the edits, name in your reply which entries changed and re-ask the same continue / refine-more / cancel prompt. Loop until the GM says continue or cancel.

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

Then ask explicitly: *"Edit the order in `.ttrpg-staging/survey-order.md` if you want changes, then tell me to continue. Or say cancel to exit cleanly."* Accept three response shapes:

1. **Continue** → re-read `.ttrpg-staging/survey-order.md` to capture GM edits, parse the order, renumber to match the GM's arrangement (the agent owns the integer indices; the GM owns the sequence). Continue to Step 5.
2. **Cancel** → delete `.ttrpg-staging/`, write nothing else, exit cleanly.
3. **Verbal refinement** ("move X above Y", "drop the session log", or a refinement to a description in `.ttrpg-staging/survey-descriptions.md` that's still on disk) → apply each requested change to the named staging file using the **Edit** tool, one surgical edit per change so the IDE shows a native hunk diff per [ADR-0015](../../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). Do **not** rewrite the whole file with Write (the bulk overwrite buries the diff) and do **not** use Bash redirects (no diff surfaces at all). After the edits, name in your reply which entries changed and re-ask the same continue / refine-more / cancel prompt. Loop until the GM says continue or cancel.

If the GM removed a doc entirely during ordering, drop it from the survey set — Phase 3 will not process it. Note removed docs in the closing summary so it's visible they were skipped on purpose.

### Step 5: Hand off to Phase 3

Once the GM confirms the order, hand off these **survey results** to Phase 3:

- **Doc list**, in confirmed processing order. Each entry is the doc's absolute path and the GM-confirmed one-line description.
- **Skipped doc list** (any docs the GM removed during ordering, plus the non-markdown files), preserved only for the closing summary at the end of Phase 3.
- An empty **carried-forward lessons** set (Phase 3's cross-doc learning will populate it as each doc's review completes; see Phase 3 Step 0b).

Then **delete the survey staging files** — `.ttrpg-staging/survey-descriptions.md` and `.ttrpg-staging/survey-order.md`. They've served their purpose (the GM's edits are now captured in the in-memory hand-off above). If `.ttrpg-staging/` is now empty, remove the directory; if other workflows have staged content there, leave the directory alone. This way, Phase 3 cancel paths and Phase 4 hold paths don't have to worry about lingering survey artifacts.

Tell the GM the survey is complete (a short one-line summary of the confirmed order is enough), then continue directly into Phase 3 with doc #1. No confirmation prompt — the GM just edited and accepted the order list, so asking again is redundant. Phase 3 has per-doc review for each doc's extraction, which is the real break point if the GM wants to bail.

## Phase 3: Per-doc extraction loop

### Slice 3 scope

This slice implements the per-doc loop for **single-doc and multi-doc** inputs, including cross-doc dedup and cross-doc learning:

- **Single-doc** (exactly one markdown file in the input directory) is the degenerate case: skip the survey entirely (Phase 2 Step 0 routes here directly), then run Step 1 through Step 6 below for the one doc. Dedup against existing campaign files still applies; cross-doc learning is a no-op because there's no subsequent doc.
- **Multi-doc** (more than one markdown file) runs after Phase 2 (survey) has confirmed a per-doc description and a processing order. Step 0b sets up the multi-doc loop; Steps 1 through 6 run **per doc, in confirmed order**; cross-doc dedup is applied at Step 3; carried-forward lessons accumulate from each doc's review and feed the next doc's extraction.
- Non-markdown files in the input directory (PDFs, images, etc.) are reported in the closing summary and **skipped without halting**.
- **Beat extraction is allowed during ingest** (ADR-0009 creation path #4). The source docs *are* the GM's authoring; the agent is preserving GM-prepped scenes, not inferring intent. See Step 2 below for what Beat-shaped content looks like.

ADR-0008 governs the workflow shape; this slice implements its per-doc loop, dedup, and cross-doc learning verbatim.

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

- **Reference notes**: named NPCs, locations, factions, and items the doc introduces or describes substantively. **Consult `~/.claude/skills/ttrpg-gm/references/reference-note-extraction.md` for the heuristic before drafting** — it defines what counts as a Reference note vs. a passing mention, folder by kind, slug filenames, the one-liner default body, missing-name handling, and the minimal-frontmatter convention.
- **Adventure-shape**: does this doc describe a story arc the party will run (a coherent set of scenes, locations, or stages tied together by a goal)? If yes, plan an `adventures/<slug>/adventure.md` file with ADR-0007 frontmatter. If no (it's a Reference note dump, world info, or session-narrative), don't fabricate an Adventure.
- **Threads**: explicit unresolved hooks the party *knows about* — promises the party made, questions they asked, dangers they were warned about. Future-facing, party-aware. ADR-0004 governs file shape and status frontmatter. Only extract Threads that the doc actually surfaces as party-aware; don't invent them.
- **Consequences**: explicit persistent facts about the world resulting from prior action ("the temple was destroyed", "the lord owes the party a favor"). Past-facing. Same provenance bar as Threads — only what the doc says.
- **Beats**: GM-prepped scenes the party doesn't yet know about — unchecked encounter lists, planned scenes, per-PC personal hooks ("for Darius: a test of discipline"), adventure-tagged scene ideas, "if X then Y" contingent deliveries. Future-facing, GM-authored. ADR-0009 frontmatter: `status: pending`, `created: ~` (null — ingest doesn't know when the GM wrote the prep down), optional `kind:` classified by source-section heading per `~/.claude/skills/ttrpg-gm/references/beat-kind-classification.md` (a Beat extracted from a "Scenes" / "Set Pieces" / "Encounters" section → `kind: set-piece`; from "Lore" / "Rumors" / "What the Party Hears" → `kind: news`; from "Handouts" → `kind: handout`; from "Hidden Information for the DM" → `kind: clue` with `linked_secrets:` pointing at the paired Secret; from "Triggers" / "What Happens If…" → `kind: escalation`; from a PC-attributed hook section → `kind: character-moment`), optional `linked_secrets:` for `kind: clue` Beats, optional `linked_pcs` / `linked_npcs` / `linked_adventures` / `linked_locations` populated from the source per the rules in the **Beat shape** subsection of Step 3 below. *Threads vs Beats test*: if the party knows about it, it's a Thread; if it's the GM's prep, it's a Beat. When the source is ambiguous about awareness, default to Beat and the GM can re-classify in the per-doc review. **Populate `linked_*` fields conservatively at extraction time** — `linked_adventures` and `linked_locations` are what `/prep-session` will use to surface Beats relevantly; leaving them empty at ingest forces a downstream manual backfill. Empty is still preferable to wrong, but a confident link the source clearly supports is exactly what these fields are for. See the Beat shape subsection for the proximity heuristics.
- **Secrets**: GM-only facts the party may not know but could discover. The discriminator from `~/.claude/skills/ttrpg-gm/references/secret-extraction.md`: a *fact about the world*, *possibly unknown to the party*, *anchored to ≥1 non-ephemeral container*, *discoverable* by some plausible path. Modules surface these explicitly under "Secrets and Lies" / "Adventure Background" / "DM-Only" / "Hidden Information" / "What's Really Going On" sections; treat those section headings as strong extraction signals. Each extracted Secret gets its own `secrets/<slug>.md` with ADR-0014 frontmatter: `status: hidden`, `belongs_to:` containing the ingested Adventure (`adventures/<slug>/`) **plus** any NPCs / Locations / Factions / Items named in the Secret's own prose (the multi-container population rule in the **Secret shape** subsection of Step 3 below), `revealed_by: []`. On write, the agent maintains a bidirectional `## Secrets` section in each container in `belongs_to:` per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`. *Beat vs Secret test*: a Beat is *intent to deliver* (GM action); a Secret is *fact to be discovered* (world truth). The "Hidden Information for the DM" pairing — Secrets in one section, Clue Beats in another — is the canonical module structure and is extracted as paired Secret + `kind: clue` Beats with `linked_secrets:` populated.

**Date honesty for lifecycle objects.** Same principle as ADR-0007 for Adventures: the agent never invents dates. For every Thread, Consequence, and Beat extracted during ingest, `created:` is left null unless the source doc explicitly provides a date the agent can attribute. Do **not** use the ingest date as a stand-in for an unknown source date — Consequences ingested from past adventures are not "created today"; they came into being whenever those past sessions happened. Future Briefs and `campaign.md` regens handle null `created:` values by falling back to slug or insertion order; that's intentional. Dates get filled in precisely going forward by `/wrap-session`.

What **not** to extract:

- **Session structure** (`sessions/YYYY-MM-DD-session-N/`). Sessions are created by `/prep-session` and `/wrap-session`; do not synthesize them from a doc even if the doc looks like a session log. If the GM-confirmed description identifies the doc as a session log, surface that to the GM and ask whether it should be filed as an Adventure-side history note (under `adventures/<name>/`) or skipped — don't manufacture a `sessions/` directory.
- **Atlas content.** v0.1 is single-repo (ADR-0006); no cross-repo links into an Atlas. Treat all extracted content as campaign-local.

### Step 3: Draft the proposed changes

Draft each proposed file with full content (frontmatter plus body). Hold them in memory; do **not** write yet.

**Before writing any lifecycle-object frontmatter, consult `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md`** — it is the canonical spec for the Adventure, Thread, Consequence, and Beat schemas (required fields, optional fields, value formats, defaults at CREATE). The ingest-era defaults documented in that reference (`status: introduced` for Adventures, `created: ~` for everything since the agent doesn't know past dates, etc.) apply here directly.

#### Reference note shape

See `~/.claude/skills/ttrpg-gm/references/reference-note-extraction.md` for what counts as a Reference note, folder by kind, the slug rule for filenames, the one-line default body, and the minimal-frontmatter convention. The ingest-specific orchestration: extract from the source doc's prose; wiki-link to other Reference notes you're also proposing from the same doc.

#### Adventure shape (ADR-0007, .claude/rules/adventures.md)

If the doc is adventure-shaped, propose `adventures/<slug>/adventure.md`. **Schema:** see `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md` ("Adventure" section). Ingest-specific defaults:

- `status: introduced` — the GM hasn't told you the party has begun running it. Only set `active`, `completed`, or `abandoned` if the source doc explicitly says so.
- `order: ~` unless the source doc has explicit numeric sequencing (e.g., "Adventure 1: …", "Chapter 3: …") that you can copy directly. When null, Phase 4 will bulk-prompt the GM during wrap-up. (Phase 4 reads the frontmatter to decide: a non-null `order:` means Phase 3 found one in the source and the prompt is skipped.)
- All date fields null unless the source explicitly supplies them. Never invent dates (ADR-0007).
- Durations null unless the source explicitly supplies; if it does, copy the prose verbatim.

Body of `adventure.md` is a short prose summary from the source doc, with `[[wiki links]]` to the Reference notes you're also proposing. Sub-files for scenes/chapters may also be proposed (siblings to `adventure.md` in the same `adventures/<slug>/` directory) when the source doc has clearly distinct sub-sections worth their own files; otherwise keep it to `adventure.md`.

#### Thread shape (ADR-0004)

One file per Thread, in `threads/`. **Schema:** see `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md` ("Thread" section). Ingest-specific defaults: `status: open` unless the source doc explicitly says the thread is already resolved (then `closed`) or has gone stale (then `decayed`); `created: ~` unless the source supplies a date.

Body is one or two sentences describing the hook — what's owed, promised, or foreshadowed — with `[[wiki links]]` to relevant Reference notes.

Example: `threads/find-rulfs-killer.md`

```markdown
---
status: open
created: ~
closed: ~
---

# Find Rulf's killer

[[Rulf]] was found dead in the [[Cragmaw Hideout]]; the party promised his
sister they would find who killed him.
```

#### Consequence shape (ADR-0004)

One file per Consequence, in `consequences/`. **Schema:** see `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md` ("Consequence" section). For ingest, `created:` is null unless the source supplies a specific date the agent can attribute — don't use the ingest date as a stand-in (date-honesty rule). Future `/wrap-session` Consequences will carry precise dates.

Body is the persistent fact, one or two sentences, with `[[wiki links]]` to relevant Reference notes.

Example: `consequences/lord-protector-owes-the-party.md`

```markdown
---
created: ~
---

# The Lord Protector owes the party a favor

After the party recovered the [[Iron Banner]] for [[Sildar Hallwinter]], he
publicly declared he owes them one.
```

#### Beat shape (ADR-0009)

One file per Beat, in `beats/`. **Schema:** see `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md` ("Beat" section). Ingest-specific defaults: `status: pending` (a `delivered` or `dropped` Beat is past-tense and would be a Consequence or simply not-extracted); `created: ~`; `delivered: ~`; `kind:` classified by source-section heading per `~/.claude/skills/ttrpg-gm/references/beat-kind-classification.md` (see "Classifying `kind:` from source-section headings" below); `linked_secrets:` populated when the Beat is a Clue paired with an extracted Secret (see same subsection); `linked_*` populated per the proximity rules in "Populating `linked_*` at extraction time" below (the heuristics are ingest-specific orchestration, not part of the shared schema).

Body is one or two sentences describing the GM's prep — the scene, the encounter, the news to drop, the hook to land — with `[[wiki links]]` to relevant Reference notes mentioned inside the prep.

##### Classifying `kind:` from source-section headings

`/ingest` is the strongest case for `kind:` classification because module-shaped source docs label their content by section heading. **Apply `~/.claude/skills/ttrpg-gm/references/beat-kind-classification.md`** — that reference is the canonical mapping from module section headings to `kind:` values, and the order-of-precedence rule (section heading > body content > unset).

Ingest-specific orchestration on top of the shared reference:

- **Heading is the primary signal.** When a Beat is extracted from prose under a known section heading (e.g., `## Scenes`, `## Lore`, `## Handouts`, `## Hidden Information for the DM`, `## Triggers`), set `kind:` per the heading-mapping table in `~/.claude/skills/ttrpg-gm/references/beat-kind-classification.md` Section "Heading → `kind` mapping." The heading is the source author's intent declaration; don't override it from body-content guessing.
- **Subsection refines.** A `### The Ambush at the Bridge` under `## Scenes` is still `kind: set-piece`; the subsection just names the scene. When a subsection's content reads as a different kind from its parent heading (an item labeled "Rumor:" under `## Scenes`), surface as an ASK at Step 4a.
- **Unknown heading → body-content fallback.** When the enclosing heading doesn't match any known pattern, fall back to body-content classification per the same reference. Leave `kind:` unset (`~`) if body content also doesn't yield a confident classification — unclassified Beats surface normally.
- **GM-supplied kind values.** The enum is open (ADR-0014, ADR-0009). If the GM corrects a proposed kind to a string outside the starter set at review, accept it verbatim and record the value in a carried-forward lesson for the rest of the run: *"Doc 2: GM-supplied kind value 'foreshadow' applied to Beats with prophecy-shaped body content."*
- **Hidden Information for the DM → `kind: clue` with `linked_secrets:`.** When the source doc has both a Secret-bearing section (per `~/.claude/skills/ttrpg-gm/references/secret-extraction.md`) and a "Hidden Information for the DM" (or analogous) section, the paired structure is canonical: Secrets in one section, Clue Beats in the other. Extract paired Beat–Secret pairs and populate the Clue Beat's `linked_secrets:` with the matching Secret's slug. When the alignment is ambiguous (the chapter has three Secrets and four Hidden Information items with no clear one-to-one mapping), surface as ASK at Step 4a: *"Hidden Information item X — link to which Secret(s)? `mayor-funds-cult`, `mayor-was-blackmailed`, or both?"*

##### Populating `linked_*` at extraction time

These four fields exist specifically so `/prep-session` can surface a Beat in the right tier for the next session (ADR-0009 surfacing-at-scale design: Beats with `linked_adventures` overlapping active Adventures, `linked_pcs` overlapping focus PCs, or `linked_locations` near the party are surfaced in full; everything else is summarised in counts). Beats extracted without `linked_*` populated end up in the "unlinked, review and tag" tier and force the GM into a manual backfill. **Populate them at extraction time when the source clearly supports it.** Be conservative: empty is honest; wrong is harmful.

Use these rules, in order:

1. **`linked_adventures` — strong rule, adventure-shaped doc.** If the current doc is being ingested as `adventures/<slug>/` (the GM-confirmed description from Phase 2 / Step 1 classified it as an Adventure), every Beat extracted from it gets `linked_adventures: [<slug>]` automatically. The Beat lives inside the GM's prep for that Adventure; the link is structural, not inferred.

2. **`linked_adventures` — weak rule, world-info doc.** If the current doc is world-info-shaped and a Beat-shaped passage explicitly names an Adventure (by title, by wiki link like `[[Lost Mines]]`, or by the Adventure's slug) inside the Beat's own paragraph, bullet, or the enclosing heading section, link to that Adventure. Match against:
   - Adventures already present in `adventures/` in the campaign repo.
   - Adventures being created from earlier docs in this same `/ingest` run (use the slug the earlier doc landed at).
   - Adventures being created from this same doc (rare for a world-info doc, but possible).

   If multiple Adventures are named in proximity to the Beat (e.g., a "scenes I might drop in" section that references three Adventures), surface as an ASK in Step 4a alongside the Beat: *"Beat 'lost letter from Iarno' was extracted near mentions of both `lost-mines` and `cragmaw-castle`. Link to which? (one, both, neither)"* Don't guess.

3. **`linked_locations` — proximity rule.** Locations mentioned in the Beat's own paragraph or bullet are linked. "Same paragraph / same bullet / same scene block" is the "near" radius — narrower than the Adventure-proximity rule because locations are often listed in a roster the GM would expect specifically tagged.

   Match against:
   - Reference notes already present in `locations/` in the campaign repo.
   - Locations being created from earlier docs in this same `/ingest` run.
   - Locations being created (proposed as CREATE in Step 3) from this same doc.

   If a location name matches multiple existing Reference notes after slugification (e.g., "the keep" could be `locations/sundered-keep.md` or `locations/ravenloft-keep.md`), surface as an ASK in Step 4a — same shape as the dedup ASKs.

4. **`linked_locations` — heading rule.** If a Beat-shaped passage sits under a heading that names a location (e.g., `### The Sunless Citadel\n- random encounter table\n- ...`), link the Beat to that location even if the Beat's own bullet doesn't repeat the name. The enclosing heading is the GM's implicit scope tag.

5. **`linked_pcs` — explicit attribution.** Link a PC only when the Beat content explicitly names the PC as the target or subject — common patterns: *"for Darius: …"*, *"Darius's hook: …"*, *"when Sera dreams: …"*. Match against the campaign's PCs (Phase 3 has access to existing `CLAUDE.md` and any party roster the GM has authored; otherwise, the PC names will surface as ASKs at review time if there's no roster yet). Generic mentions ("the party", "one of the PCs") do not justify a link.

6. **`linked_npcs` — content-mention rule.** Link an NPC when the NPC is the actor or subject inside the Beat's content (an NPC delivers news, an NPC encounter, an NPC's death). Match against:
   - Reference notes already in `npcs/`.
   - NPCs being created from earlier docs in this same `/ingest` run.
   - NPCs being created from this same doc.

   Conservative: a passing name-drop without role context is not enough. The NPC has to *do* or *be* something in the Beat.

7. **Default to empty list, not omission.** If a field has no confident link, write it as `[]` in frontmatter — the YAML key is preserved so `/prep-session` and `/wrap-session` can read it without conditional logic, and the GM can see at a glance that the field was considered and left empty rather than forgotten.

8. **All linked-field values are slugs**, using the same slugification rule used for Reference note dedup (lowercase, ASCII-fold accents, strip leading "the ", collapse whitespace and punctuation to single hyphens, trim leading/trailing hyphens). For `linked_pcs` where no `pcs/` folder yet exists, use the PC's canonical name slugified the same way; `/prep-session` will resolve.

##### Carried-forward lessons for Beat linkage and kind

The Step 5b carried-forward lessons set tracks linkage decisions and kind classifications just like dedup decisions. If the GM corrects a `linked_*` field at review (e.g., "Beat 'Rulf's body' should link to `cragmaw-hideout`, not `cragmaw-castle`"), record it. If the GM corrects a proposed `kind:` (e.g., the agent proposed `set-piece` for an item under a `## Scenes` heading but the GM reclassified to `news` because the item was a one-line rumor drop the source author miscategorized), record that too. Subsequent docs that propose similar Beats with the same ambiguity get the GM's correction applied automatically (with the lesson surfaced at the top of the next doc's review, per Step 0b).

##### Example: `beats/dream-of-the-veiled-court.md`

```markdown
---
status: pending
created: ~
kind: character-moment
linked_pcs: [sera]
linked_npcs: []
linked_adventures: [lost-mines]
linked_locations: [phandalin]
linked_secrets: []
---

# Sera's dream of the Veiled Court

When [[Sera]] sleeps in [[Phandalin]], drop a fragment of the [[Veiled Court]]
dream — silver masks turning toward her, one of them speaking her mother's name.
```

(In this example the source doc was the `lost-mines.md` adventure writeup under a `## Personal Hooks → ### For Sera` subsection, so `kind: character-moment` is heading-driven and `linked_adventures: [lost-mines]` is the strong-rule link. The Beat text names Sera explicitly — `linked_pcs: [sera]`. It names Phandalin in the Beat's own paragraph — `linked_locations: [phandalin]`. The Veiled Court is mentioned but not as an NPC role — `linked_npcs: []` because it's a faction wiki link, not an NPC subject. No Secret is paired with this Beat — `linked_secrets: []`.)

##### Example: `beats/ledgers-in-mayors-office.md` — a Clue Beat paired with a Secret

```markdown
---
status: pending
created: ~
kind: clue
linked_pcs: []
linked_npcs: [mayor-brennan]
linked_adventures: [the-prism]
linked_locations: [town-hall]
linked_secrets: [mayor-funds-cult]
---

# Ledgers in the mayor's office

If the party investigates [[Mayor Brennan]]'s office in [[Town Hall]], they
find ledgers showing payments to a shell merchant the [[Silent Court]] uses.
```

(Extracted from a "Hidden Information for the DM" section under the same chapter that had a "Secrets and Lies" entry "The mayor secretly funds the cult." The section heading drives `kind: clue`; the paired Secret extracted from the same chapter populates `linked_secrets: [mayor-funds-cult]`.)

#### Secret shape (ADR-0014)

If the source doc has a "Secrets and Lies," "Adventure Background," "DM-Only," "Hidden Information," or analogous GM-only section, propose one file per Secret under `secrets/`. **Schema:** see `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md` ("Secret" section). **Extraction heuristic:** `~/.claude/skills/ttrpg-gm/references/secret-extraction.md` is the canonical spec for what counts as a Secret, file shape, section-heading signals for ingest, and the multi-container `belongs_to:` population rule from named entities in the Secret's prose. Apply that reference; the orchestration below is ingest-specific scaffolding on top of it.

Ingest-specific defaults:

- `status: hidden` unless the source content explicitly says some part of the Secret has already been revealed.
- `belongs_to:` populated per the rules in "Populating `belongs_to:` at extraction time" below — at minimum, the ingested Adventure (`adventures/<slug>/`).
- `revealed_by: []` at CREATE — the list grows as Clue Beats land pointing at this Secret. Do not pre-populate from Beats extracted in this same doc; the Beat–Secret pairing is captured on the *Beat's* `linked_secrets:` (per the Beat shape's "Hidden Information for the DM" subsection above), and the symmetric `revealed_by:` will be reconciled by `/wrap-session` when the Beat flips to `delivered`.

Body of the Secret file is the **fact itself**, one or two sentences written for the GM (not GM instructions — the fact, not how to reveal it). Use `[[wiki links]]` to any Reference notes (NPCs, Locations, Factions, Items, Adventures) named in the fact.

##### Populating `belongs_to:` at extraction time

`belongs_to:` is the load-bearing structural decision for an extracted Secret. Get it right and the bidi back-references (per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`), per-container Secret queries from `/prep-session`, and multi-container reconciliation at dedup all work automatically. Get it wrong and the GM hand-edits to repair the symmetry.

Use these rules, in order (mirrors the Beat-shape rules above, scoped to Secrets):

1. **Adventure container is automatic — strong rule.** When the current doc is being ingested as `adventures/<slug>/` (the GM-confirmed description from Phase 2 / Step 1 classified it as an Adventure), every Secret extracted from that doc gets `belongs_to:` containing **at minimum** `adventures/<slug>/`. The Secret was found inside the Adventure's source doc; the Adventure is its container by construction. Do not skip this entry even when the Secret's own prose doesn't name the Adventure.

2. **Named-entity expansion — proximity rule.** Scan the Secret's prose (the body the extractor will write) for **named** NPCs, Locations, Factions, and Items. For each named entity that resolves to:
   - A Reference note already present in the campaign repo (under `npcs/`, `locations/`, `factions/`, or `items/`), **or**
   - A Reference note being CREATEd from earlier docs in this same `/ingest` run, **or**
   - A Reference note being CREATEd from this same doc,

   add that entity's container path to `belongs_to:`. The matching uses the same slugification rule as `~/.claude/skills/ttrpg-gm/references/dedup-matching.md`. The proximity radius is *the Secret's own body* — the prose the extractor is writing for the Secret file. Worked example: a Secret with body *"Mayor Brennan diverts town funds to the [[Silent Court]] through a shell merchant in the [[Old Temple]] district"* gets `belongs_to: [adventures/the-prism/, npcs/mayor-brennan.md, factions/silent-court.md, locations/old-temple.md]`.

3. **Subsection-heading expansion — heading rule.** When a Secret is extracted from a subsection whose heading names a container (e.g., `### About the Mayor` under `## Secrets and Lies`), add that container to `belongs_to:` even if the Secret's own body doesn't repeat the name. The enclosing heading is the GM's implicit scope tag.

4. **PC containers — explicit attribution only.** A Secret may belong to a PC (`pcs/<slug>.md`) when the source material *explicitly* names the PC as the subject (*"the truth about Sera's brother"*, *"Darius's hidden parentage"*). Generic mentions do not justify a PC container — surface as ASK if the source is ambiguous.

5. **Cross-kind ambiguity → ASK.** A name matching Reference notes in multiple kind folders (e.g., "Veil" → `npcs/veil.md` and `factions/the-veil.md`) surfaces as an ASK at Step 4a, same shape as cross-kind dedup ASKs.

6. **Container set validation.** Before staging, validate `belongs_to:` per `~/.claude/skills/ttrpg-gm/references/secret-store.md` (which mirrors `tests/test_secret_store.py::TestValidateBelongsTo`): non-empty, at least one entry under a non-ephemeral folder root (`adventures/`, `npcs/`, `pcs/`, `locations/`, `factions/`, `items/`), no unknown folder roots (typos like `npc/maren.md` are rejected so the GM catches them). A Secret that fails validation surfaces as ASK at Step 4a with the GM picking a corrected set; do not write a Secret whose `belongs_to:` would fail the validator.

7. **Default to a smaller set on doubt.** If the proximity rule would expand `belongs_to:` to many containers and the extractor is uncertain about the structural justification for one or more, surface those as an ASK alongside the Secret in the per-doc review: *"Secret 'Mayor secretly funds the cult' was extracted near mentions of the Silent Court (faction), the Old Temple (location), and the council chambers (location). Include any/all in `belongs_to:`?"* Don't guess.

8. **All `belongs_to:` paths use the canonical form** — `npcs/<slug>.md` / `pcs/<slug>.md` / `locations/<slug>.md` / `factions/<slug>.md` / `items/<slug>.md` for file-shaped containers, `adventures/<slug>/` (with trailing slash) for Adventures. The slug rule is the dedup normalization (lowercase, ASCII-fold accents, strip leading "the ", collapse non-alphanumerics to hyphens, trim).

##### Carried-forward lessons for Secret extraction and `belongs_to:`

The Step 5b carried-forward lessons set tracks Secret extraction decisions:

- **Section-heading interpretation.** If the GM corrects a section that the agent treated as Secret-bearing (e.g., a "Notes" section the agent classified as DM-Only but the GM clarified is player-facing), record the lesson: *"Doc 2: GM treats sections labeled 'Notes' in this campaign as player-facing context, not Secret-bearing — do not extract Secrets from them."*
- **`belongs_to:` choices.** If the GM trimmed or expanded a proposed `belongs_to:` (e.g., dropped the location container because the named place was incidental color, not structurally part of the Secret), record the lesson: *"Doc 1: GM excludes incidental-mention locations from `belongs_to:` — limit to entities the Secret is structurally about."*
- **Merge vs. separate decisions for cross-doc Secret dedup.** When a candidate Secret in doc 4 dedups against a Secret extracted from doc 1 and the GM resolves "merge — add the doc 4 containers to the existing Secret's `belongs_to:`," record the identity for the rest of the run.

##### Example: `secrets/mayor-funds-cult.md`

```markdown
---
status: hidden
belongs_to:
  - adventures/the-prism/
  - npcs/mayor-brennan.md
  - factions/silent-court.md
  - locations/old-temple.md
revealed_by: []
---

# The mayor secretly funds the cult

[[Mayor Brennan]] diverts town funds to the [[Silent Court]] through a shell
merchant in the [[Old Temple]] district. He joined willingly after his daughter
was promised an audience with the Court's matriarch.
```

(Extracted from a "Secrets and Lies" section in the `the-prism.md` adventure source. The Adventure container is automatic; the three Reference-note containers come from named entities in the Secret's body via the proximity rule. The paired Clue Beat in the same chapter — `beats/ledgers-in-mayors-office.md` — has `linked_secrets: [mayor-funds-cult]`.)

### Step 3b: Cross-doc dedup

Before presenting the per-doc review, match every drafted Reference note (NPC, location, faction, item) **and every drafted Secret** against existing files in the campaign repo. This applies both within the multi-doc loop (matching against files written by earlier docs in this run) and on the first doc of a multi-doc run (matching against any pre-existing Reference notes / Secrets already in the campaign repo from a prior `/ingest` invocation). In the single-doc degenerate case, dedup still runs — it just matches only against pre-existing campaign files.

Reference notes and Secrets are the kinds dedup applies to in this slice. Adventures get name-collision handling at Step 5 (the GM resolves; no auto-merge). Threads, Consequences, and Beats are extracted only from what the doc explicitly says (ADR-0004, ADR-0009); cross-doc Thread / Consequence / Beat dedup is a deliberate non-goal here — duplicates surface, and the GM trims them at review.

#### Matching procedure

**Apply the matching rule at `~/.claude/skills/ttrpg-gm/references/dedup-matching.md`** — it defines the normalization (lowercase, ASCII-fold accents, strip leading "the ", collapse whitespace and punctuation to single hyphens, trim leading/trailing hyphens), what to match against (existing filenames and the first-heading title inside each candidate file), and the three buckets (CREATE / UPDATE confident-match / ASK ambiguous-match). Apply the same rule consistently across every drafted Reference note and Secret in this doc.

Ingest-specific orchestration on top of the shared rule:

- **Apply carried-forward dedup decisions before asking.** If the carried-forward lessons set already contains a confirmed identity link for this candidate ("the Sera in this run is the same Sera as `npcs/sera.md`"), apply it as a confident match without re-asking. If the lessons contain a confirmed split ("the John from doc 3 is distinct from `npcs/john.md`"), drop the proposed dedup question and treat the candidate as a CREATE with a disambiguated slug (e.g., `npcs/john-the-bandit.md`) — confirm the disambiguated slug with the GM at the review screen, not silently.
- **Target folder is the kind's folder.** Per `~/.claude/skills/ttrpg-gm/references/reference-note-extraction.md`, match Reference-note candidates only within the same kind (`npcs/`, `locations/`, `factions/`, or `items/`). Cross-kind matches surface as ASK per the shared rule. Secret candidates match within the `secrets/` folder per `~/.claude/skills/ttrpg-gm/references/secret-store.md`.
- **Secret dedup → multi-container reconciliation, not generic UPDATE.** A confident Secret slug match doesn't propose a generic body UPDATE the way a Reference note does — the resolution shape for Secrets is *merge the new container set into the existing Secret's `belongs_to:`*. Per `~/.claude/skills/ttrpg-gm/references/secret-extraction.md`: the prompt is "merge, separate, or rename?" When the GM resolves *merge*, the existing Secret's `belongs_to:` is union'd with the candidate's `belongs_to:` and the existing body is preserved (or the candidate's body is appended if the GM wants — surface that subdecision at the same prompt). When *separate*, create the new Secret at a disambiguated slug. When *rename*, the GM supplies the new slug.
- **Restated Secrets across chapters.** A common module pattern: chapter 1 introduces a Secret, chapter 4 restates it ("as established in chapter 1, the mayor funds the cult"). The cross-doc dedup against earlier-doc Secrets catches this; without dedup the agent would write a duplicate `secrets/mayor-funds-cult-1.md` slug-collision. When the GM resolves *merge* on a restated Secret, also expand `belongs_to:` to include any new containers chapter 4 named.

#### Output of Step 3b

The drafted-proposal set from Step 3 is now annotated, per Reference note and per Secret, with one of:

- **CREATE** — new file, no existing match.
- **UPDATE** — confident match against an existing file; the agent proposes a specific append-or-edit to that file. For Secrets, UPDATE specifically means *merge containers into the existing Secret's `belongs_to:`* (and optionally append body content if the GM wants — surfaced as a sub-question).
- **ASK** — ambiguous match; the agent has a yes/no question for the GM that must be resolved at the review screen before this Reference note or Secret is written. For Secrets, the ASK shape is the multi-container reconciliation prompt — merge / separate / rename.

These annotations feed the per-doc review in Step 4.

### Step 4: Per-doc review via staging directory

This step has two parts. First, resolve any ambiguous-dedup ASK items inline in chat (those need GM decisions before staging makes sense). Second, write the resolved set of proposed files to a per-doc staging directory the GM edits in their IDE.

#### Step 4a: Resolve ambiguous-dedup questions inline

If Step 3b produced any ASK items (ambiguous Reference-note matches, Secret multi-container reconciliations, Beat–Secret pairing ambiguities, Beat `linked_*` ambiguities, Beat `kind:` ambiguities, or `belongs_to:` expansion uncertainties), surface them in chat as a short numbered list of questions. Group by ASK kind so the GM can scan:

```
Doc 2 of 3: The Prism.md — 5 questions to resolve before review:

Reference-note dedup (yes/no):
  1. Sera (proposed NPC): possible match to existing `npcs/sera.md` ("Sera the blacksmith from Lost Mines"). Same person?
  2. The Citadel (proposed location): possible match to existing `locations/the-citadel.md` ("Mountain fortress in the north"). Same place?

Secret reconciliation (merge / separate / rename):
  3. "The mayor secretly funds the cult" (proposed Secret): matches existing `secrets/mayor-funds-cult.md` (extracted from doc 1). Merge the new containers [factions/silent-court.md, locations/old-temple.md] into the existing Secret's belongs_to, or create as a separate Secret at a disambiguated slug?

Secret belongs_to expansion:
  4. "Maren is the cult's inside contact" (proposed Secret) was extracted with the Silent Court (faction) and the Old Temple (location) named in incidental context, not the Secret's core fact. Include both, only the Silent Court, or only the Adventure container?

Clue–Secret pairing:
  5. Hidden Information item "ledgers in mayor's office" — link to which Secret(s)? `mayor-funds-cult`, `mayor-was-blackmailed`, or both?

Reply with answers (e.g., "1 yes, 2 no — call it 'the-citadel-of-glass', 3 merge, 4 only-court, 5 mayor-funds-cult").
For Reference-note "no", supply a disambiguated slug.
For Secret "separate" or "rename", supply the disambiguated slug.
```

When the GM resolves, apply per ASK kind:
- Reference-note dedup: convert to confident UPDATE (yes) or CREATE at a disambiguated slug (no).
- Secret reconciliation: *merge* → set `belongs_to:` to the union of existing and candidate containers; treat as UPDATE on the existing Secret. *Separate* → CREATE the candidate Secret at the disambiguated slug. *Rename* → CREATE at the GM-supplied slug.
- Secret `belongs_to:` expansion: trim or expand the proposed `belongs_to:` per the GM's answer; the validated set feeds the Secret CREATE / UPDATE.
- Clue–Secret pairing: set the Beat's `linked_secrets:` to the GM-confirmed Secret slug(s).
- Beat `linked_*` and `kind:` ASKs: set the field per the GM's answer.

Record every resolution in the carried-forward lessons set (Step 5b will keep these for subsequent docs in the run). Then proceed to Step 4b.

If the GM resolves only some ASK items, re-ask the unresolved ones — don't proceed to staging until every ASK has a decision.

#### Step 4b: Stage proposed files for IDE-based edit

**This step follows the shared staging-file review pattern at `~/.claude/skills/ttrpg-gm/references/staging-pattern.md`** — write proposed final content to a gitignored staging directory, present a chat summary with continue/cancel ask, re-read on continue to capture GM edits, clean up on cancel. Consult that reference for the full lifecycle and invariants.

Ingest-specific staging shape: write every proposed file to `.ttrpg-staging/doc-<N>/` in the campaign repo, mirroring the campaign's directory structure. For multi-doc runs, `<N>` is the doc's position in the processing order (1, 2, 3…). For single-doc, use `doc-1/`. Each proposed file lands at its eventual relative path *inside* `doc-<N>/`:

| Proposed change | Staging path |
|---|---|
| Adventure (CREATE) | `.ttrpg-staging/doc-<N>/adventures/<slug>/adventure.md` and any sub-files |
| Reference note (CREATE) | `.ttrpg-staging/doc-<N>/<kind>/<slug>.md` (kind = `npcs`, `locations`, `factions`, `items`) |
| Reference note (UPDATE) | `.ttrpg-staging/doc-<N>/<kind>/<slug>.md` — stage per `~/.claude/skills/ttrpg-gm/references/staging-pattern.md` Section 2 (cp the live file, Edit to apply the proposed change so the IDE diff shows the delta) |
| Reference note (CREATE-disambiguated from ASK) | `.ttrpg-staging/doc-<N>/<kind>/<disambiguated-slug>.md` |
| Thread (CREATE) | `.ttrpg-staging/doc-<N>/threads/<slug>.md` |
| Consequence (CREATE) | `.ttrpg-staging/doc-<N>/consequences/<slug>.md` |
| Beat (CREATE) | `.ttrpg-staging/doc-<N>/beats/<slug>.md` |
| Secret (CREATE) | `.ttrpg-staging/doc-<N>/secrets/<slug>.md` |
| Secret (UPDATE — merged containers) | `.ttrpg-staging/doc-<N>/secrets/<slug>.md` — stage per `~/.claude/skills/ttrpg-gm/references/staging-pattern.md` Section 2 (cp the live Secret file, Edit to apply the union'd `belongs_to:` and any GM-approved body changes so the IDE diff shows the delta) |
| Secret (CREATE-disambiguated from ASK) | `.ttrpg-staging/doc-<N>/secrets/<disambiguated-slug>.md` |
| Container back-reference (UPDATE — added `## Secrets` section bullet) | `.ttrpg-staging/doc-<N>/<container-path>` — stage per `~/.claude/skills/ttrpg-gm/references/staging-pattern.md` Section 2 (cp the live container file — NPC / Location / Faction / Item / `adventures/<slug>/adventure.md` — and Edit to insert the proposed `## Secrets` section bullet per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md` so the IDE diff shows the delta) |

For UPDATE items, follow `~/.claude/skills/ttrpg-gm/references/staging-pattern.md` Section 2: `cp` the live file from the campaign repo into staging, then apply the proposed change via the Edit tool against the staged copy. Because the cp made the staged content byte-identical to the live file at that moment, the Edit's diff display surfaces the live → proposed delta — the same way Claude Code shows changes for any file edit, so the GM sees the delta rather than re-reading the whole file to spot the addition.

**Bidi link staging for Secrets.** Every Secret CREATE or UPDATE drags container back-reference UPDATEs along with it: for each container in the Secret's `belongs_to:`, if that container's body doesn't already have a `## Secrets` section wiki-linking the Secret, stage an UPDATE to that container file too (per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`). The GM sees the back-reference UPDATEs alongside the Secret in the staging summary; deleting a back-reference UPDATE without also adjusting the Secret's `belongs_to:` is a contract violation the agent surfaces at re-read time (*"You deleted the back-reference UPDATE for `npcs/maren.md` but left `npcs/maren.md` in the Secret's `belongs_to:`. Re-add the back-reference, drop the container from `belongs_to:`, or cancel?"*). For container files that don't exist (a Secret's `belongs_to:` names a Reference note that this same doc is CREATEing), the back-reference is staged against the CREATEd container's staged content — so the GM sees the full final state of the new container file including the `## Secrets` section, not just the agent's split-write.

Then present a chat summary listing what's staged, with the same metadata Step 4 used to surface before:

```
Doc 2 of 3: The Prism.md — proposed changes staged at .ttrpg-staging/doc-2/

Description: Adventure: a published-module-shaped writeup of the Prism arc.
Lessons applied:
  - Skip passing innkeepers as NPCs (from doc 1 rejections).

Summary: 1 Adventure, 5 Reference notes (3 NPCs CREATE, 1 location UPDATE, 1 faction CREATE), 2 Threads, 1 Consequence, 4 Beats (2 set-piece, 1 clue, 1 character-moment), 2 Secrets, 3 container back-references.

Files:
  adventures/the-prism/adventure.md            — CREATE
  npcs/mayor-brennan.md                        — CREATE  (gains ## Secrets section)
  npcs/maren.md                                — CREATE  (gains ## Secrets section)
  npcs/sera.md                                 — UPDATE
  locations/old-temple.md                      — CREATE  (gains ## Secrets section)
  factions/silent-court.md                     — CREATE
  threads/find-the-spy.md                      — CREATE
  consequences/temple-was-purged.md            — CREATE
  beats/ambush-at-the-bridge.md                — CREATE  (kind: set-piece)
  beats/ledgers-in-mayors-office.md            — CREATE  (kind: clue → linked_secrets: [mayor-funds-cult])
  beats/sera-dream.md                          — CREATE  (kind: character-moment)
  beats/random-encounter-table.md              — CREATE  (kind: set-piece)
  secrets/mayor-funds-cult.md                  — CREATE  (belongs_to: 4 containers)
  secrets/maren-is-the-spy.md                  — CREATE  (belongs_to: 2 containers)

Edit any file in `.ttrpg-staging/doc-2/`, delete any file to reject that proposal, then tell me to continue. Or say cancel to exit cleanly.

(In a multi-doc run: skipped non-markdown files are listed on doc 1's review only; not repeated per doc.)

Note: deleting a Secret's staged file also drops the paired container back-reference UPDATEs (the agent re-stages without them); deleting a back-reference UPDATE without adjusting the Secret's `belongs_to:` surfaces a contract-violation prompt at continue time.
```

Accept these response shapes:

1. **Continue** → re-read every file remaining in `.ttrpg-staging/doc-<N>/` to capture GM edits. Treat any staged file the GM deleted as rejection (don't write that one; record the rejection for Step 5b's lessons capture). Proceed to Step 5 to move surviving staged files to their final locations.
2. **Reject everything** → delete `.ttrpg-staging/doc-<N>/`. Write nothing for this doc. In multi-doc, ask the GM whether to continue to the next doc or exit the run. Already-written approved files from prior docs in the same run stay written.
3. **Cancel** → delete `.ttrpg-staging/doc-<N>/` (and `.ttrpg-staging/` if it's now empty), leave the rest of the filesystem unchanged, exit cleanly. Already-written approved files from prior docs in the same run stay written.

Rejected items (whether per-file via deletion or per-doc via reject-everything) must never be written to final locations. Approved items must be written exactly as the GM left them in the staging file — no late re-interpretation.

### Step 5: Move approved items from staging to final locations

Once the GM says continue in Step 4b, move every file remaining in `.ttrpg-staging/doc-<N>/` to its corresponding final location in the campaign repo. Paths inside `doc-<N>/` mirror the campaign repo, so the move is a path translation — strip the `.ttrpg-staging/doc-<N>/` prefix to get the final path.

1. Create any needed directories under the campaign repo: `adventures/<slug>/`, `npcs/`, `locations/`, `factions/`, `items/`, `threads/`, `consequences/`, `beats/`, `secrets/` — but **only** those needed for approved items. Don't pre-create empty folders for kinds with no content (matches Phase 1 Step 2 rule).
2. **Move order matters for Secrets.** Move container files (Reference notes, Adventures) **before** Secret files, so the bidi back-references in the Secrets' `belongs_to:` resolve against containers that exist at the final location. Specifically:
   - Move Reference-note CREATEs and UPDATEs first.
   - Move Adventure CREATEs (including sub-files) next.
   - Move container back-reference UPDATEs to existing-in-campaign-repo Reference notes / Adventures (those weren't in this doc's CREATE set but received a `## Secrets` section bullet from a Secret extracted from this doc).
   - Move Secret files last.
   - Move Threads, Consequences, and Beats in any order — they have no bidi dependency on this step.
3. For each surviving staged file, dispatch by its Step 3b annotation (preserved from before staging):
   - **CREATE** — write the staged content to the proposed path. If a path collision occurs against a Reference note or Secret that wasn't surfaced by Step 3b (e.g., because the slug differs from any existing file by some edge case the matching procedure missed), STOP and tell the GM the exact conflicting path. Do not overwrite without explicit GM confirmation.
   - **UPDATE** — replace the existing file with the staged content (which already contains the GM-edited final state of the file). If the existing file has changed on disk between Step 4b's stage-write and Step 5's read-back (race against the GM editing the live file in another window), STOP and re-present the update before writing.
   - **CREATE (disambiguated from ASK)** — write the staged content to the GM-confirmed disambiguated path.
   - For **Adventure** name collisions (existing `adventures/<slug>/` directory), STOP and surface to the GM exactly as before. Slice 3 has no Adventure dedup.
4. **Validate Secret `belongs_to:` before writing the Secret file.** Per `~/.claude/skills/ttrpg-gm/references/secret-store.md` (`validate_belongs_to`): non-empty, ≥1 non-ephemeral entry, no unknown folder roots. If validation fails for any Secret at this step (the GM hand-edited the Secret's frontmatter in staging to an invalid `belongs_to:`), STOP and re-present that Secret for re-edit; don't write a Secret that fails the validator. The reference Python `tests/test_secret_store.py::TestValidateBelongsTo` enforces the rule.
5. **Run bidi maintenance after each Secret write.** Per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`'s `apply_belongs_to`: for each container in the Secret's `belongs_to:`, confirm the container's file body now contains the `## Secrets` section wiki-link. If a container is missing the back-reference (the GM deleted the staged container back-reference UPDATE but the contract-violation prompt was overridden, or the container is a pre-existing file whose back-reference wasn't staged because it was already present at stage time but has since been edited), surface it to the GM as a post-write reconciliation prompt. The algorithm is idempotent — re-running on an already-linked container is a no-op (`tests/test_bidi_link.py::TestApplyBelongsTo::test_is_idempotent_on_rerun`).
6. After each file is moved, delete it from staging. When `.ttrpg-staging/doc-<N>/` is empty, remove the directory. If `.ttrpg-staging/` is now empty (no other workflows' staging present), remove that too.
7. Do not modify `campaign.md`, `CLAUDE.md`, or anything under `.claude/` from inside Phase 3. Campaign-overview regeneration belongs to Phase 4. Don't drift `campaign.md` from its scaffolded state during the per-doc loop.
8. Do **not** commit. Ongoing git ownership belongs to the GM (ADR-0011). The plugin only commits once, in the scaffold phase (and once again at Phase 4 wrap-up).

### Step 5b: Capture cross-doc learning

This step applies only in the multi-doc case. Single-doc has no subsequent doc to inform, so skip.

After the GM's approval/edit/rejection decisions for the current doc are settled (and before moving to the next doc), capture the lessons implied by those decisions into the carried-forward lessons set initialised in Step 0b. The point is to make the agent's behavior on doc N+1 reflect what the GM corrected on doc N, visibly and auditably.

Lessons worth carrying forward include:

- **Rejected kinds.** If the GM rejected one or more Reference notes of a recognisable shape — e.g., "the passing innkeeper", "the named-once-in-prose mercenary" — record a rejection lesson: *"Doc 1: do not propose passing innkeepers as Reference notes."* Apply on subsequent docs by not drafting those candidates, or by drafting them and explicitly flagging them as candidates the prior-doc lesson would drop (GM can override).
- **Classification preferences.** If the GM moved an item from Thread → Consequence, or from Reference note → narrative color (dropped entirely), record the preference: *"Doc 1: the GM treats one-line rumor mentions as narrative color, not Threads."*
- **Confirmed dedup identities.** If the GM confirmed an ambiguous dedup as "yes, same entity", record the identity link: *"`npcs/sera.md` is the campaign's Sera; future mentions consolidate here."* Use these to convert future ambiguous-match candidates into confident updates without re-asking.
- **Confirmed dedup splits.** If the GM said "no, distinct entity" and named a disambiguated slug, record the split: *"`npcs/john.md` (innkeeper) and `npcs/john-the-bandit.md` are distinct; future mentions of 'John' need disambiguation by context."*
- **Naming preferences.** Canonical-name choices the GM made when given a dedup ambiguity ("call them the Veiled Court, slug `veiled-court`").
- **Section-heading interpretation for Secrets and Beats.** Sections the GM treated differently from the agent's default classification (e.g., "GM treats sections labeled 'Notes' as player-facing context, not Secret-bearing"; "GM treats items under `## Scenes` as `news` when body is one-liner rumor-shaped, not `set-piece`"). Apply on subsequent docs by classifying matching sections per the GM's correction.
- **Secret `belongs_to:` policy.** Conventions the GM established about which containers belong in `belongs_to:` (e.g., "GM excludes incidental-mention locations from `belongs_to:` — limit to entities the Secret is structurally about"). Apply on subsequent docs by being more or less aggressive about the named-entity expansion rule per the GM's policy.
- **Secret merge / separate decisions.** When a candidate Secret in doc N dedups against an earlier Secret and the GM resolves "merge — add the new containers to the existing Secret," record the identity for the rest of the run; subsequent doc-N+1 candidates with the same Secret name go directly to a confident UPDATE (merge containers) without re-asking.
- **Secret partial-reveal recognition.** GM confirmations that a candidate Secret was already partially revealed in past play ("the party learned in session 3 that the mayor's involved") — record the prose-shape signal so subsequent docs with the same shape get the four-piece extraction-time partial-reveal pattern applied automatically. The pattern itself (Secret body intact + delivered Clue Beat + `revealed_by:` populated + `status: partially-revealed`) is specified in `~/.claude/skills/ttrpg-gm/references/secret-extraction.md` under "Extraction-time partial-reveal handling." **Never carry forward the anti-pattern** — splitting a partially-revealed Secret into a Consequence (revealed portion) + tightened Secret (still-hidden portion) — as a learned rule; that reference also documents why the split breaks the Secret lifecycle. If a prior review accidentally captured the split shape, drop the lesson at the next review and reconstruct the four-piece shape.
- **Beat `kind:` classifications.** GM corrections to proposed `kind:` (e.g., "GM-supplied kind value 'foreshadow' applied to Beats with prophecy-shaped body content"; "items under `## Lore` should be `kind: news` not unclassified"). Apply on subsequent docs.
- **Clue–Secret pairings.** GM confirmations of ambiguous Beat–Secret pairings ("Hidden Information item X links to Secret `mayor-funds-cult`, not `mayor-was-blackmailed`"). Apply on subsequent docs facing the same ambiguity shape.

Do not invent lessons. Only capture what the GM's decisions explicitly support. If a rejection is ambiguous in motive ("rejected this Reference note — was it because of the kind, or just this specific instance?"), note it as a candidate rather than a confirmed lesson and ask the GM at the top of doc N+1's review: *"Carrying forward as a candidate rule: do not promote passing innkeepers. Apply this rule, or was the previous rejection just about that specific innkeeper?"*

Carried-forward lessons are scoped to one ingest run. They do not persist into the next `/ingest` invocation. They are not written to any file — they live only in the agent's in-memory state for the duration of the run.

### Step 6: Closing summary

After the **last** doc in the run completes (or after the only doc, in the single-doc case), tell the GM, concisely:

- The source docs that were extracted, in processing order. For each: the relative path and the GM-confirmed description. In multi-doc, also note any docs the GM dropped during survey ordering and any docs where the GM rejected everything at review.
- A summary of what was written across the whole run (counts by kind, with the campaign-relative paths). Group by kind — including Beats (with `kind:` breakdown when non-trivial: 3 set-piece, 2 clue, 1 news, etc.), Secrets (with `belongs_to:` container-count breakdown when non-trivial: 4 single-container, 2 multi-container), and container back-references touched (the `## Secrets` section bullets added to NPC / Location / Faction / Item / Adventure files). For UPDATE operations on existing Reference notes and Secrets, list those separately from CREATEs so the GM can see what got merged versus what's new.
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
3. **Surface uncommitted state — but only when it actually warrants attention.** Run `git status --porcelain` in the campaign repo. Sort the entries into **expected** and **unexpected** before prompting the GM. Don't ask about expected files.

   **Expected** (proceed silently; these go into the wrap-up commit):
   - Untracked files under the lifecycle/reference folders: `npcs/`, `locations/`, `factions/`, `items/`, `adventures/`, `threads/`, `consequences/`, `beats/`, `secrets/`. These are Phase 3's output.
   - Modified Reference notes and Adventure files in the same lifecycle folders. Phase 3 writes `## Secrets` section back-references into containers when Secrets are extracted, which appears as a modification (M-status) on existing container files. Treat those modifications as expected — they're paired with the new `secrets/` files in the same wrap-up commit.
   - Untracked files under `sessions/` (rare during fresh ingest, but allowed — Phase 3 may have proposed Adventure-side history under `adventures/<slug>/` rather than synthetic sessions; still, accept).
   - Untracked scaffolder artifacts inside `.claude/` that the plugin's current Phase 1 templates list write but older plugin versions didn't include in the initial commit; the wrap-up commit absorbs them. Treat any `.claude/<file>` that matches the current Phase 1 template set as expected — **except** `.claude/settings.json`, which is intentionally gitignored (machine-local absolute paths) and must **not** be swept into the wrap-up commit even if it appears in `git status --porcelain` (which it shouldn't, since it's gitignored, but on legacy campaigns where it was committed before this convention changed, leave it alone and let the GM migrate per the issue tracker).
   - Untracked `.gitignore` at the campaign root — same staleness reason; matches the Phase 1 template set.
   - Modified `campaign.md` (after Phase 4 Step 2 regenerates it — at *this* pre-flight check it should still be the Phase 1 placeholder, but a modified entry here is also expected if the GM is re-running wrap-up after a partial Phase 4).

   **Unexpected** (surface a short list to the GM and ask before proceeding):
   - Uncommitted files at paths *outside* the expected set — e.g., the GM hand-authored a file at the campaign root, or a prior run was interrupted and left half-state somewhere unusual.
   - Anything under `.ttrpg-staging/` (it's gitignored, so this should never show up in `git status` — if it does, the gitignore is broken; flag it).
   - Modified files (M-status) outside `campaign.md` *and* outside the lifecycle/reference folders — Phase 3 creates new files and modifies container files for Secret bidi back-references, but modifications to existing tracked content outside those folders suggest the GM (or another run) touched something unrelated.

   If everything is expected, proceed silently to Step 1. If anything is unexpected, surface a short list of just the unexpected entries (not the expected ones — the GM doesn't need a wall of "yes this is fine"), and ask whether to proceed with those included in the wrap-up commit, exit cleanly, or have the GM resolve them first.

### Step 1: Order prompt for missing `order:` values

Walk every `adventures/<slug>/adventure.md` file under the campaign repo.

1. **Read frontmatter** for each Adventure. Collect the slug, the H1 title (canonical name), the current `status`, and the current `order:` value.
2. **Identify the missing-order set.** An Adventure needs the order prompt **only** if both of these are true:
   - Its `order:` is null (Phase 3 left it null because the source doc didn't supply an inferable sequence).
   - Its source doc did not use explicit numeric Adventure sequencing the agent could have copied (e.g., the doc didn't say "Adventure 1: …", "Chapter 3: …", or the equivalent). In Phase 3, this manifested as the agent leaving `order:` null at write time; Phase 4 trusts that signal.

   Adventures whose `order:` was already filled in by Phase 3 (because the source doc had inferable sequencing) skip this prompt. Do not re-ask. Adventures whose source doc explicitly said "first run" or "earliest arc" but didn't supply a number still go in the missing-order set — the prompt is the right place to turn prose hints into a number.

3. **If the missing-order set is empty**, skip to Step 2. Tell the GM: *"All Adventures have an `order:` value already; skipping order prompt."*

4. **Write the order prompt to a staging file** at `.ttrpg-staging/adventure-order.md`. Use the Write tool — Claude Code's standard file-write diff shows the full proposed list to the GM in their IDE. Create `.ttrpg-staging/` if it doesn't exist; it's gitignored by the scaffolder.

   Format the staging file as a simple key-value list, one line per missing-order Adventure, with a header that explains the edit contract:

   ```
   # Adventure order prompt

   The Adventures below don't have an `order:` value set, and their source docs
   didn't have explicit "Adventure N" numbering for me to copy. Edit the integer
   after each slug to set the sequence each Adventure ran in your campaign.

   1 = earliest in the campaign's history. Duplicates are allowed if two
   Adventures ran in parallel (the agent will confirm before applying).
   Leave a value as `null` to skip that Adventure (its `order:` stays null).

   When done, save the file and tell me to continue. Or say cancel to exit
   without changes.

   lost-mines       : null   # Lost Mines of Phandelver (status: completed)
   cragmaw-castle   : null   # Cragmaw Castle (status: completed)
   wave-echo-cave   : null   # Wave Echo Cave (status: active)
   ```

   The comments on each line carry the Adventure's H1 title and status so the GM can identify each entry without opening the source file.

5. **Wait for the GM**, then re-read the staging file to capture edits. Parse each non-blank, non-comment line as `<slug> : <value>`. Acceptable values:

   - A positive integer → the new `order:`.
   - `null` or blank → leave the Adventure's `order:` null.
   - Anything else (string, decimal, etc.) → flag that line and ask the GM to clarify rather than guessing.

   If the GM removed or added lines (a contract violation — the list reflects the missing-order set discovered in Step 2), surface that and re-ask before proceeding. If the GM said cancel, delete `.ttrpg-staging/adventure-order.md` and skip to Step 2 with a one-line note in the closing summary that no `order:` values were filled in.

6. **Validate.** Sequence numbers should be positive integers. Duplicates are allowed if the GM truly believes two Adventures ran in parallel, but flag duplicates explicitly in chat: *"Two Adventures will share `order: 2` — is that intentional, or did you mean to split them?"* Apply only after explicit confirmation. Don't re-write the staging file for this confirmation — chat is the right channel since it's a single yes/no.

7. **Write the `order:` values into Adventure frontmatter.** For each Adventure with a confirmed new order, edit the `order:` line in its `adventures/<slug>/adventure.md` frontmatter from `~` to the integer. Preserve every other frontmatter field, every existing body byte, and the YAML shape from Phase 3. If an Adventure's frontmatter is malformed for any reason, surface the path to the GM and skip the write — don't try to repair it.

8. **Delete the staging file.** Remove `.ttrpg-staging/adventure-order.md`. If `.ttrpg-staging/` is now empty, remove the directory. (Step 4's final cleanup is the backstop; this step's deletion keeps staging clean as the workflow progresses.)

The carried-forward lessons set from Phase 3 is irrelevant here; the order prompt is a one-shot question against current Adventure frontmatter and doesn't consult lessons.

### Step 2: `campaign.md` composer

Replace the campaign-root `campaign.md` (currently the Phase 1 placeholder or a prior Phase 4 output) with a generated overview.

**Run the composer at `~/.claude/skills/ttrpg-gm/references/campaign-overview-composer.md`** — that file is the canonical spec for section ordering, sub-bucket rendering, derivation rules, and the determinism contract. Phase 4 runs the composer with the **ingest-only variants** documented under that reference's "Skill-specific variants" section:

- Adds two header lines below `**System:**`: `- **Status:** active` and `- **Last event:** YYYY-MM-DD (ingest)` (today's date suffixed `(ingest)`; future `/wrap-session` runs may replace this line with the wrapped session's date).
- Renders the full `## Adventures` history section between the menu and `## Open threads`, listing every Adventure (sorted by `order:` ascending, null-order Adventures alphabetical by slug at the end). At ingest time the full history is load-bearing context; session-to-session it would be noise.
- Shows **every** Consequence under `## Recent significant consequences` — no top-N truncation. Everything just landed; truncation would hide the just-ingested history the GM is about to commit.

Write `campaign.md` from scratch. Do not preserve manual GM edits to the prior `campaign.md` content — per ADR-0007, manual edits are reconciled or overwritten with warning at regeneration, and Phase 4 chooses overwrite. (If the GM has campaign-editorial content like themes, pitch, or house rules, that lives in a separate file the agent doesn't touch — see `CLAUDE.md.template`.)

Phase 4 source for the party-location line (per the composer's `/ingest` derivation rules): among `status: active` Adventures, pick the highest-`order:`; fall back to highest-`order:` overall if none are active, then alphabetically-last Adventure slug if `order:` is null across the board (explicitly calling that out in the prose). Read that Adventure's `adventure.md` body for an explicit location reference (wiki link to a `locations/<slug>.md` is the strongest signal; failing that, a clearly-named place in prose). Never invent a location.

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
- `beats/` — count of new Beat files (ADR-0009 path #4: ingest extracts Beats from GM-authored prep). Optionally break down by `kind:` when the count is non-trivial (e.g., "2 set-piece, 1 clue, 1 character-moment, 0 news / handout / escalation / unclassified").
- `secrets/` — count of new Secret files (ADR-0014: ingest extracts Secrets from module "Adventure Background" / "Secrets and Lies" / etc.).
- `campaign.md` — modified (the Phase 4 Step 2 regen).
- Anything else — count it but note it as "other" in the proposed message.

Modified files from Phase 3 (UPDATEs to existing Reference notes, and `## Secrets` section back-references added to container files when Secrets were extracted) are counted under "Reference notes updated" and "container back-references added" separately from new ones, mirroring Phase 3 Step 6's closing-summary distinction.

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
                    2 Adventures, 4 Threads, 3 Consequences,
                    5 Beats (2 set-piece, 1 clue, 1 character-moment, 1 news),
                    3 Secrets

Files that will be staged and committed:
  - npcs/ (8 new; 3 modified with ## Secrets back-references)
  - locations/ (3 new; 1 modified with ## Secrets back-reference)
  - factions/ (1 new; 1 modified with ## Secrets back-reference)
  - adventures/lost-mines/, adventures/cragmaw-castle/ (2 new)
  - threads/ (4 new)
  - consequences/ (3 new)
  - beats/ (5 new)
  - secrets/ (3 new)
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

1. Stage exactly the file set the GM approved. Prefer naming files and directories explicitly (e.g., `git add npcs/ locations/ factions/ items/ adventures/ threads/ consequences/ beats/ secrets/ campaign.md`) over `git add -A` so the GM can see what's staged. Include modified container files (Reference notes with new `## Secrets` section back-references) — those are tracked under their respective `<kind>/` directories, so the directory-form `git add` picks them up naturally.
2. Run `git commit -m <message>` with the approved message. Multi-line messages should be passed via `-m` per paragraph or via a heredoc — whichever the tool affordance supports.
3. Do **not** configure `git config user.name` or `git config user.email` from the plugin. Use whatever the GM's git config provides; if the commit fails because git has no identity configured, surface the underlying git error to the GM verbatim and stop without retrying.
4. After commit, run `git status` and surface its output to the GM in the closing summary — they should see a clean working tree.

If the commit fails for any other reason (pre-commit hook failure, signing failure, etc.), surface the underlying git error verbatim and stop. Do not retry. Do not amend. The GM will resolve and either re-invoke wrap-up or finish the commit themselves.

### Step 4: Closing summary

First, **clean up `.ttrpg-staging/`** in the campaign repo (`rm -rf` the directory if present). Staging held the survey artifacts the GM edited in Phase 2; ingest is now complete and the directory has served its purpose. Cleanup also avoids leaving a confusing artifact for `/prep-session` or `/wrap-session` to trip over.

Then, after the commit lands (or after the GM skips the commit), tell the GM, concisely:

- **Order prompt outcome.** Adventures whose `order:` was set in Step 1 (with the assigned numbers). Adventures left null (if the GM skipped or partially answered). Adventures that already had `order:` (and were not prompted).
- **`campaign.md` regenerated.** Note that the prior placeholder was overwritten. If the prior `campaign.md` had detectable manual GM edits (content that differed from the scaffolder's placeholder before Phase 4 ran), surface that as a warning per ADR-0007. In the fresh-ingest path this should be rare — the only way to have hand-edited `campaign.md` between Phase 1 and Phase 4 is for the GM to have done it during Phase 3.
- **Counts of what landed.** Reference notes by kind (NPCs / locations / factions / items, broken down CREATE vs UPDATE), Adventures, Threads, Consequences, Beats (broken down by `kind:` when non-trivial), Secrets (broken down by single-container vs multi-container `belongs_to:` when non-trivial). Mirror Phase 3 Step 6's grouping so the two summaries are comparable.
- **Bidi link health.** Run `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`'s `lint` algorithm once against the just-committed campaign state and surface any findings (`orphan` wiki-links to missing Secrets, `missing-back-reference` cases where a Secret claims a container that doesn't link back). In the fresh-ingest path this should be clean — the agent maintained bidi throughout Phase 3. Surface non-empty findings as a "to investigate" note in the closing summary; do not auto-heal post-commit, since the lint state is already in committed history. If clean, mention briefly: *"Secret bidi links: clean."*
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
- Don't extract a Thread for content the party isn't aware of in the source doc — that's a Beat (ADR-0009 path #4; the Thread/Beat awareness test). When the source is ambiguous, default to Beat and surface to the GM for re-classification.
- Don't leave a Beat's `linked_adventures` empty when the source doc is itself adventure-shaped — the structural link is unambiguous and skipping it forces a downstream manual backfill (this is the issue-#15 regression). Conversely, don't *guess* a link the source doesn't support: if two Adventures or two Locations are equally near a Beat, surface as ASK at review per Step 3's Beat shape rules.
- Don't synthesize `sessions/YYYY-MM-DD-session-N/` directories from source docs (ADR-0005 — Sessions are created by `/prep-session`).
- Don't recurse into input subdirectories (ADR-0006 — flat directory only in v0.1).
- Don't silently overwrite an existing Reference note. Confident dedup matches propose **updates** (which the GM approves); ambiguous matches surface as yes/no questions; Adventure name collisions still stop and ask. The agent never picks identity silently.
- Don't carry cross-doc lessons across runs. They are scoped to one ingest invocation; the next `/ingest` starts with an empty lessons set.
- Don't apply a carried-forward rejection lesson to a candidate the GM might still want. When in doubt, surface the carried lesson and ask whether it should apply to this specific candidate — over-application is worse than re-asking.
- Don't ask the GM for `order:` one Adventure at a time when more than one is missing. Phase 4's order prompt is a single bulk question covering the whole missing-order set; one-at-a-time prompting is the form the slice spec explicitly avoids.
- Don't invent a party location in the Phase 4 `campaign.md` regen. If the source docs don't supply one, the section reads as a "GM to update" placeholder.
- Don't truncate the Phase 4 Consequence list. At ingest time, every Consequence is "recent" — truncation belongs to `/wrap-session`'s regen, not `/ingest`'s.
- Don't re-prompt for `order:` on Adventures whose source docs already supplied it (i.e., where Phase 3 wrote a non-null `order:`). The order prompt's whole point is to fill *missing* values, not re-litigate inferred ones.
- Don't extract a Secret with empty `belongs_to:` or only-ephemeral `belongs_to:` paths — the agent refuses to write either (ADR-0014; `tests/test_secret_store.py::TestValidateBelongsTo`). If the source content reads as Secret-bearing but the extractor can't justify any non-ephemeral container, surface as ASK and have the GM pick the container set rather than writing an invalid Secret.
- Don't skip the bidi-link maintenance step when a Secret is written. Every container in a Secret's `belongs_to:` must end up carrying a `## Secrets` section wiki-linking back to the Secret (`~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`). The maintenance is idempotent — re-running on an already-linked container is a no-op — so it is safe to run on every Secret write without checking state first.
- Don't auto-create a container from a Secret write. If a Secret's `belongs_to:` names a container file that does not exist (an NPC or Location the agent didn't extract a Reference note for), surface to the GM — the GM owns container creation explicitly, not as a side effect of a Secret write.
- Don't extract surface-plot facts as Secrets. A module's player-facing chapter prose is not Secret-bearing by default (`~/.claude/skills/ttrpg-gm/references/secret-extraction.md`); extract Reference notes and Beats from it. Reserve Secret extraction for content under known GM-only section headings ("Secrets and Lies" / "Adventure Background" / "DM-Only" / "Hidden Information") or content the GM-confirmed description identifies as GM-only.
- Don't classify a Beat's `kind:` from body content when a section heading already classifies it (`~/.claude/skills/ttrpg-gm/references/beat-kind-classification.md` order of precedence: section heading > body content > unset). The heading is the source author's intent declaration; the body content is the fallback when the heading is unknown.
- Don't pre-populate a Secret's `revealed_by:` from Beats extracted in this same doc. The Beat–Secret pairing is captured on the *Beat's* `linked_secrets:` (per the Beat shape's "Hidden Information for the DM" subsection); the symmetric `revealed_by:` on the Secret is reconciled later by `/wrap-session` when the Beat flips to `delivered`. Pre-populating both sides during ingest creates drift the linter would have to chase.

## Quick reference: which ADR governs what

- **ADR-0003** — Reference notes are one file per entity in `npcs/`, `locations/`, `factions/`, `items/`. Default body is a one-liner.
- **ADR-0004** — Threads and Consequences are per-file. Threads have `status: open | closed | decayed`. Consequences have valid YAML frontmatter and persist (no status).
- **ADR-0006** — v0.1 input is flat-directory local markdown only; non-markdown is skipped, no recursion.
- **ADR-0007** — Adventure frontmatter schema (`status` required, `order` optional/ingest-era, dates optional/nullable, durations free-form prose) and the agent-maintained `campaign.md` Campaign overview shape that Phase 4 Step 2 composes. The agent never invents dates.
- **ADR-0008** — Ingest's full workflow is survey + per-doc + wrap-up; slice 4 implements all four phases (survey, per-doc loop with cross-doc dedup and learning, and wrap-up with the bulk order prompt, `campaign.md` composer, and follow-up commit). Bounded skim plus GM-edited descriptions plus GM-confirmed processing order steer extraction.
- **ADR-0009** — Beats are GM-authored. Ingest is the fourth creation path (source docs are the GM's prior authoring). Extract Beat-shaped content (encounter lists, planned scenes, per-PC hooks, adventure-tagged ideas). Threads vs Beats is the party-awareness test: party knows → Thread; GM prep → Beat. Populate `linked_adventures`, `linked_locations`, `linked_pcs`, `linked_npcs` at extraction time per the proximity rules in Step 3's Beat shape subsection — these fields feed `/prep-session`'s tiered surfacing and leaving them empty forces a manual backfill. Phase 4's `campaign.md` lists pending Beats explicitly. Beat `kind:` (open enum) is classified primarily by source-section heading per `~/.claude/skills/ttrpg-gm/references/beat-kind-classification.md` (Scenes → set-piece; Lore/Rumors → news; Handouts → handout; Hidden Information for the DM → clue with `linked_secrets:`; Triggers → escalation; PC-attributed hooks → character-moment).
- **ADR-0011** — Plugin doesn't own ongoing git operations beyond `/ingest`'s two bookend commits (the scaffolder's initial commit and Phase 4's follow-up commit). `/wrap-session` and every workflow downstream of `/ingest` does not auto-commit. The follow-up commit is `/ingest`'s symmetric bookend, not a precedent for steady-state auto-commit.
- **ADR-0013** — Skill packaging (`skills/<name>/SKILL.md`); templates live under `templates/`.
- **ADR-0014** — Secrets are a fourth lifecycle object: GM-only facts the party may not know but could discover. Stored at `secrets/<slug>.md` with required `belongs_to:` (non-empty list of non-ephemeral container paths — Adventure, NPC, PC, Location, Faction, Item). `/ingest` extracts Secrets from module GM-only sections ("Secrets and Lies" / "Adventure Background" / "DM-Only" / "Hidden Information" / equivalents — per `~/.claude/skills/ttrpg-gm/references/secret-extraction.md`). The Adventure container is automatic (the ingested doc's slug); additional containers come from named NPCs / Locations / Factions / Items in the Secret's own prose (proximity rule). Every container in `belongs_to:` carries a symmetric `## Secrets` section wiki-linking back to the Secret per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`. Secret slug dedup is `secrets/`-scoped per `~/.claude/skills/ttrpg-gm/references/dedup-matching.md`; the resolution shape for collisions is *merge containers / separate / rename*. Reference Python for the four query operations lives at `tests/test_secret_store.py`; for the bidi maintenance, `tests/test_bidi_link.py`.
