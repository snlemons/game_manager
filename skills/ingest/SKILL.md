---
name: ingest
description: Extract structure from existing TTRPG campaign notes into a scaffolded campaign repo. In slice 1 of v0.1, only the scaffolder phase is implemented — it writes the root CLAUDE.md, .claude/rules/sessions.md, .claude/rules/adventures.md, and a campaign.md placeholder into the target directory, then runs git init and an initial commit. Survey, per-doc extraction, and wrap-up phases are stubs in this slice.
---

# /ingest

`/ingest` is the workflow that turns an existing pile of campaign notes into a structured, agent-navigable campaign repo.

The full workflow has four phases:

1. **Scaffold** — write the plugin's templates into the target directory, `git init`, and make an initial commit. **(Implemented in slice 1.)**
2. **Survey** — discover input docs, propose a one-line description per doc, confirm processing order with the GM. *(Stub — not yet implemented.)*
3. **Per-doc extraction loop** — for each doc, extract Reference notes, adventure metadata, Threads, and Consequences; present a per-doc proposed diff; the GM approves; corrections inform the next doc. *(Stub — not yet implemented.)*
4. **Wrap-up** — prompt for any missing `order:` values on ingest-era adventures and regenerate `campaign.md`. *(Stub — not yet implemented.)*

In this slice, only phase 1 runs. The other phases respond "not yet implemented" if the GM tries to advance past the scaffold.

## When to invoke this skill

The GM invokes `/ingest` to start a new campaign repo from existing notes. The slice-1 scaffold phase also covers the "fresh start, no source docs yet" path — the GM gets a blank campaign repo to start writing into.

## Inputs the GM provides

The GM provides:

- **Target directory** — where the campaign repo should live. May be an empty directory, a not-yet-existing directory, or (with explicit GM confirmation) a directory containing only source notes the GM wants to ingest later. **Never** scaffold over a directory that already contains a campaign repo (presence of `campaign.md`, `.claude/rules/sessions.md`, or a non-trivial `.git/`); abort and tell the GM.
- **Campaign name** — human-readable (e.g. *The Sunless Citadel Revisited*). Used in `CLAUDE.md` and `campaign.md`.
- **System** — the rule system (e.g. *D&D 5e*, *Pathfinder 2e*, *Call of Cthulhu*). Free-form prose.

If any of these are missing, ask the GM for them before doing anything that touches the filesystem. Don't invent campaign names or system labels.

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

If the GM asks to continue past the scaffold (e.g. "now ingest these docs", "run the survey"), respond:

> The `/ingest` survey phase is not yet implemented. It will land in a later slice of `ttrpg-gm` v0.1. For now, the scaffolded repo is ready for the GM to start writing into directly, or to wait for the per-doc extraction loop to ship.

Do not list, read, or skim source documents. Do not propose descriptions. Do not write any further files.

## Phase 3: Per-doc extraction loop (stub)

If the GM asks to extract from a doc, respond:

> The `/ingest` per-doc extraction loop is not yet implemented. It will land in a later slice of `ttrpg-gm` v0.1.

Do not read input docs. Do not propose Reference notes, Threads, Consequences, or adventure metadata. Do not modify any files in the campaign repo.

## Phase 4: Wrap-up (stub)

If the GM asks to finalize the ingest, respond:

> The `/ingest` wrap-up phase is not yet implemented. It will land in a later slice of `ttrpg-gm` v0.1.

Do not regenerate `campaign.md`. Do not prompt for `order:` values.

## What to avoid

- Don't use the words "DM", "game", "story" (for campaign), "world" (for Atlas), "hero", "hook" (overloaded), or "module" (reserved for *published* adventures only). Use the glossary in this plugin's `CONTEXT.md`.
- Don't auto-commit anything beyond the initial scaffolding commit. Ongoing git ownership belongs to the GM (see ADR-0011).
- Don't write to anywhere outside the target directory.
- Don't ask the GM to fill out forms or pick from long lists. Capture-now-structure-later (ADR-0004).
- Don't invent dates, NPC names, or campaign details the GM didn't provide.
