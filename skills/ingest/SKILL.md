---
name: ingest
description: Extract structure from existing TTRPG campaign notes into a scaffolded campaign repo. In slice 2 of v0.1, two phases are implemented — the scaffolder (writes the root CLAUDE.md, .claude/rules/sessions.md, .claude/rules/adventures.md, and a campaign.md placeholder into the target directory, then runs git init and an initial commit) and a single-doc per-doc extraction loop (bounded-skim plus full read of one markdown source doc, propose Reference notes, an Adventure if doc is adventure-shaped, Threads, and Consequences, present a per-doc diff, and write GM-approved items). Survey, multi-doc dedup, cross-doc learning, and wrap-up phases are stubs in this slice.
---

# /ingest

`/ingest` is the workflow that turns an existing pile of campaign notes into a structured, agent-navigable campaign repo.

The full workflow has four phases:

1. **Scaffold** — write the plugin's templates into the target directory, `git init`, and make an initial commit. **(Implemented in slice 1.)**
2. **Survey** — discover input docs, propose a one-line description per doc, confirm processing order with the GM. *(Stub — not yet implemented.)*
3. **Per-doc extraction loop** — for each doc, extract Reference notes, adventure metadata, Threads, and Consequences; present a per-doc proposed diff; the GM approves; corrections inform the next doc. **(Single-doc case implemented in slice 2; multi-doc dedup and cross-doc learning are still stubs.)**
4. **Wrap-up** — prompt for any missing `order:` values on ingest-era adventures and regenerate `campaign.md`. *(Stub — not yet implemented.)*

In this slice, phases 1 and 3-single-doc run. The other phases respond "not yet implemented" if the GM tries to advance past them.

Follow the domain vocabulary defined in the plugin's `CONTEXT.md` and the campaign repo's `CLAUDE.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Campaign overview**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, "story"/"game" for Campaign, "world" for Atlas, etc.).

## When to invoke this skill

The GM invokes `/ingest` to start a new campaign repo from existing notes, or to ingest an additional source doc into an already-scaffolded campaign. The slice-1 scaffold phase also covers the "fresh start, no source docs yet" path — the GM gets a blank campaign repo to start writing into. The slice-2 per-doc extraction loop covers the "I have one markdown doc I'd like extracted into the campaign" path.

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

## Phase 2: Survey (stub)

If the GM asks to continue past the scaffold with **multiple** source docs (e.g. "now ingest these docs", "run the survey", or points at an input directory containing more than one markdown doc), respond:

> The `/ingest` survey phase is not yet implemented. It will land in a later slice of `ttrpg-gm` v0.1. For now, you can ingest a single markdown doc at a time via the per-doc extraction loop, or wait for the multi-doc survey to ship.

Do not list, read, or skim multi-doc input directories beyond the count of markdown files. Do not propose descriptions for any but the single-doc case (Phase 3). Do not write any further files in the survey path.

## Phase 3: Per-doc extraction loop

### Slice 2 scope

This slice implements the **single-doc** case only:

- Input directory contains **exactly one** markdown file.
- Non-markdown files in the input directory (PDFs, images, etc.) are reported in a summary and **skipped without halting**.
- Multi-doc inputs (more than one markdown file) are deferred to Phase 2 (survey) plus its follow-on multi-doc per-doc loop — respond with the Phase 2 stub message above.
- **No deduplication** against existing campaign files yet. **No cross-doc learning** — corrections in this run do not get carried forward to a next doc.
- **No Beat extraction.** Per CONTEXT.md and ADR-0009, Beats are GM-authored; ingest is not a listed creation path. Don't propose Beats.

Multi-doc dedup, cross-doc learning, and survey-driven processing order will land in Slice 3 (see issue #4). Slice-2 carve-outs from ADR-0008 are intentional, not silent deviations.

### Step 0: Pre-flight checks

Before reading any source doc, verify the campaign repo is in a state where single-doc ingest makes sense.

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
   - If more than one markdown file, this is a multi-doc case — respond with the Phase 2 (survey) stub message and stop.
   - Collect non-markdown files separately. Note them for the summary; do not read or process them.

### Step 1: Bounded skim and proposed description

Read **only** the first heading and the first ~200 words of the single markdown file (ADR-0008's "bounded skim"). Do not full-read yet.

Propose a single-line description that classifies the doc and summarizes what it appears to be about. Examples:

- *"Adventure: a published-module-shaped writeup of the Sunless Citadel arc."*
- *"World info: notes on the gods and calendar of Faerun, no Adventure structure."*
- *"Session log: the party's first delve into the Citadel, written as narrative."*

If the skim is ambiguous (could be Adventure or world info; could be a Session log or a Reference note dump), say so in the description rather than guessing. ADR-0008 explicitly prefers surfaced ambiguity over confident wrong commits.

Present the proposed description to the GM diff-style — show the proposal and ask: *"Edit this description, accept as-is, or cancel?"* Accept three kinds of response:

1. **Accept** → record the description verbatim as extraction context and continue to Step 2.
2. **Edit** → take the GM's revised description, record that, and continue.
3. **Cancel** → write nothing, leave the filesystem unchanged, exit.

The agreed description is the steering input for the full read. Don't silently re-classify the doc later in extraction; if Step 2 reveals the description was wrong, surface that to the GM and re-confirm before continuing.

### Step 2: Full read with description as context

Read the full markdown file. Hold the GM-confirmed description as the primary framing — interpret the doc as that kind of thing.

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

### Step 4: Per-doc diff-style review

Present **all** proposed changes from this doc in a single review screen, before writing anything. Use whatever diff-style review affordance Claude Code provides in the current context:

- If a diff-style preview is available (e.g., the file write tool will show a per-file diff), present each proposed file as a creates-this-file diff.
- Otherwise, show each file's full proposed content inline in fenced markdown blocks labelled with the target relative path, grouped by kind:

  1. Adventure (if any): `adventures/<slug>/adventure.md` and any sub-files.
  2. Reference notes: grouped by folder — NPCs, locations, factions, items.
  3. Threads.
  4. Consequences.

Also list, before the per-file diffs:

- The GM-confirmed description from Step 1.
- A one-line summary count (e.g., *"1 Adventure, 4 Reference notes (3 NPCs, 1 location), 2 Threads, 1 Consequence"*).
- The non-markdown files that will be skipped, by relative path.

Then ask explicitly:

> *Approve all, edit, reject specific items, or reject everything?*

Accept these responses:

1. **Approve all** → proceed to Step 5 and write every proposed file.
2. **Edit** → the GM names one or more proposed files and supplies revisions (or asks the agent to revise specific fields). Apply edits to the in-memory drafts, re-present the affected items, ask again. Loop until the GM approves or rejects.
3. **Reject specific items** → the GM names items to drop. Remove them from the proposed set. Re-present the trimmed set, ask again.
4. **Reject everything** → write nothing, leave the filesystem unchanged, exit cleanly (still report the non-markdown skip summary).

Rejected items must never be written. Approved items must be written exactly as approved (or as the GM edited them) — no late re-interpretation.

### Step 5: Write approved items

Once the GM approves:

1. Create any needed directories under the campaign repo: `adventures/<slug>/`, `npcs/`, `locations/`, `factions/`, `items/`, `threads/`, `consequences/` — but **only** those needed for approved items. Don't pre-create empty folders for kinds with no content (matches Phase 1 Step 2 rule).
2. Write each approved file at its proposed path. If a path collision occurs (e.g., a file with that slug already exists), STOP and tell the GM the exact conflicting path. Do not overwrite. This slice has no dedup; resolving a name collision is the GM's call. The GM may rename the proposed file or reject it; either way, get explicit confirmation before any overwrite.
3. Do not modify `campaign.md`, `CLAUDE.md`, or anything under `.claude/`. Campaign-overview regeneration belongs to Phase 4 (wrap-up; still a stub in this slice). Don't drift `campaign.md` from its scaffolded state in slice 2.
4. Do **not** commit. Ongoing git ownership belongs to the GM (ADR-0011). The plugin only commits once, in the scaffold phase.

### Step 6: Closing summary

Tell the GM, concisely:

- The single source doc that was extracted (relative path and the GM-confirmed description).
- A summary of what was written (counts by kind, with the campaign-relative paths). Group by kind.
- The non-markdown files that were skipped (relative paths), framed neutrally — they were ignored, not lost.
- A reminder that `campaign.md` was **not** regenerated (wrap-up phase ships in a later slice), and that the GM owns the next commit. Offer a one-line suggested commit message they can use, e.g., `Ingest single doc: <doc basename>`.

Do not auto-commit. Do not auto-advance into wrap-up.

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
- Don't overwrite an existing Reference note, Adventure, Thread, or Consequence file. Slice 2 has no dedup; collisions are surfaced to the GM, not auto-resolved.

## Quick reference: which ADR governs what

- **ADR-0003** — Reference notes are one file per entity in `npcs/`, `locations/`, `factions/`, `items/`. Default body is a one-liner.
- **ADR-0004** — Threads and Consequences are per-file. Threads have `status: open | closed | decayed`. Consequences have valid YAML frontmatter and persist (no status).
- **ADR-0006** — v0.1 input is flat-directory local markdown only; non-markdown is skipped, no recursion.
- **ADR-0007** — Adventure frontmatter schema (`status` required, `order` optional/ingest-era, dates optional/nullable, durations free-form prose). The agent never invents dates.
- **ADR-0008** — Ingest's full workflow is survey + per-doc + wrap-up; slice 2 implements the per-doc loop for the single-doc case. Bounded skim plus GM-edited description steers extraction.
- **ADR-0009** — Beats are GM-authored only; ingest does **not** create them.
- **ADR-0011** — Plugin doesn't own ongoing git operations beyond the scaffold commit.
- **ADR-0013** — Skill packaging (`skills/<name>/SKILL.md`); templates live under `templates/`.
