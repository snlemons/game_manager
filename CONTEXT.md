# Game Manager

A Claude-native plugin for TTRPG GMs to organize campaigns, prep sessions, and track continuity. Campaign data lives in GM-owned markdown repos; this glossary defines the domain language the plugin and its conventions use.

## Language

### Roles and people

**GM** (Game Master):
The user of this system. Runs the campaign, owns the campaign repo, makes all final decisions about content.
_Avoid_: DM, Dungeon Master, referee, storyteller.

**PC** (Player Character):
A character controlled by a player at the table. Lives at `pcs/<slug>.md` in a campaign — one file per PC, same convention as NPCs and other Reference notes (per [ADR-0003](./docs/adr/0003-per-file-reference-notes.md)). PCs are non-ephemeral containers and may own Secrets via `belongs_to`, and may also own cross-extracted Reference notes via `belongs_to` on those notes (per [ADR-0023](./docs/adr/0023-pc-source-doc-ingestion.md)) — backstory NPCs, locations, factions, and items extracted from a `PC source:` doc point back at the PC, and the PC file carries symmetric `## NPCs` / `## Locations` / `## Factions` / `## Items` bidi-link sections to those notes.
The **PC file's body is GM-owned**; the agent appends backstory content from `PC source:` docs additively (never overwriting GM-authored prose) and maintains the agent-maintained bidi-link sections at the end of the file. The ownership boundary is: body prose above the first agent-maintained section is GM-territory; the agent never edits it. The agent-maintained sections (`## NPCs` / `## Locations` / `## Factions` / `## Items` / `## Secrets`) at the end of the file are derived views the agent rewrites on every relevant Reference-note or Secret write. The PC frontmatter is GM-editable; optional `player:` / `class:` / `level:` fields (per [ADR-0023](./docs/adr/0023-pc-source-doc-ingestion.md)) may be populated by the agent from a `PC source:` doc's metadata when supplied, or left absent.
_Avoid_: Hero, party member (use "party" as a collective only).

**NPC** (Non-Player Character):
Any character voiced by the GM. Recurring or one-off. Lives in the `NPCs` page of a campaign.
_Avoid_: Character (which means PC), villain, ally.

### Containers

**Campaign**:
The umbrella unit: one party of PCs, one ongoing run of sessions, one campaign-local truth about the world. Each campaign is its own git repo, owned by the GM.
_Avoid_: Game, story, world (the world is the Atlas).

**Adventure**:
A story arc the party runs *inside* a campaign. May be a published module (e.g. *Curse of Strahd*) or homebrew. Lives under `adventures/<name>/` in a campaign repo. Has a lifecycle: `introduced` → `active` → `completed | abandoned`. Carries frontmatter for `status` (required), `order` (ingest-era reliable sequence), `introduced` / `started` / `completed` dates (optional, null when unknown), and free-form `in_world_duration` / `real_world_duration` annotations.
_Avoid_: Module (reserved for *published* adventures specifically), arc, quest.
_See also_: `references/frontmatter-schemas.md` for the Adventure schema.

**Campaign overview**:
A campaign-root `campaign.md` file, agent-maintained, snapshotting the campaign's current state in human-readable form (active adventures, open threads, recent consequences, party location). Rewritten by `/wrap-session` and `/ingest`. Distinct from `/timeline` (historical) and from GM-editorial files (which live separately).
_Avoid_: Index, README, dashboard.
_See also_: `references/campaign-overview-composer.md` for the live composer spec.

**Writing style guide**:
A campaign's `.claude/rules/style.md` file, **GM-authored** and **agent-read-only**, carrying the campaign's prose voice (formality, narrative tense, vocabulary preferences, PC referencing conventions, narrative voice). Auto-loads via `paths:` frontmatter on every artifact the agent drafts under `sessions/`, `adventures/`, `npcs/`, `pcs/`, `locations/`, `factions/`, `items/`, `threads/`, `consequences/`, `beats/`, `secrets/`, and `.ttrpg-staging/` (so the auto-load also fires during the drafting window for skills that route through the staging pattern). Distinct from the [ADR-0007:41](./docs/adr/0007-temporal-model-and-campaign-overview.md) **GM-editorial unread file** (themes, pitch, house rules — agent doesn't read at all): the style guide is the GM-authored file the agent **does** read, every time it drafts prose into a matching artifact. Also distinct from `campaign.md` and other agent-maintained files (which the agent both reads and writes). Scaffolder ships a stub with placeholder sections; the GM owns the body thereafter.
_Avoid_: voice profile, tone file, style sheet.
_See also_: [ADR-0021](./docs/adr/0021-gm-writing-style-via-claude-rules-style.md) for the rationale and contract.

**Atlas**:
A shared setting repo that holds world content (regions, gods, calendars, recurring NPCs) used across multiple campaigns. Separate git repo from any campaign. Treated as a default; campaigns override it locally.
_Avoid_: Setting, world (use Atlas), lore.

### Content kinds

**Reference note**:
A static, linked-to entry about a thing in the world: an NPC, a location, a faction, an item. **One file per Reference note** (e.g. `npcs/sera.md`), so links and backlinks work natively. Default content is a one-liner; the GM never fills out a form.
_Avoid_: Entity, record, document.
_See also_: `references/reference-note-extraction.md` for the extraction heuristic.

**Session**:
The unit of play. Each session is a directory `sessions/YYYY-MM-DD-session-N/` containing three documents (Brief, In-play notes, Log) with distinct lifecycles. All three are preserved indefinitely.
_Avoid_: Game, run, meeting.

**Brief**:
Pre-session document. Agent-seeded by `/prep-session` (active Threads, Consequences likely to matter, NPCs in the area, recent log). GM-editable — name picks, foreshadowing reminders, branching notes. Preserved after session as evidence of GM intent. Not regenerated.
_Avoid_: Plan, prep, outline.

**In-play notes**:
Messy raw notes the GM types during the session. The source of truth for what happened. Read by `/wrap-session` to produce the Log and propose new Threads, Consequences, and Reference notes. Preserved unchanged after the session.
_Avoid_: Notes, scratch, raw (overloaded terms — say "in-play notes" or just "notes" only inside Session context).

**Log**:
Post-session narrative summary. Agent-drafted from In-play notes during `/wrap-session`, GM-edited and approved. The canonical, human-readable record of what happened. What future Briefs read for "what happened last time."
_Avoid_: Summary, recap, journal.

### Lifecycle objects

**Thread**:
A hook the GM should be reminded about — a promise, an unresolved question, a foreshadowed danger. Future-facing. Has status (`open`, `closed`, `decayed`). One file per thread in `threads/`, created via Post-session extraction.
_Avoid_: Hook, loose end, plot point.
_See also_: `references/frontmatter-schemas.md` for the Thread schema.

**Consequence**:
A persistent fact about the world resulting from the party's actions ("the guard captain owes them a favor"). Past-facing; doesn't close — it just becomes part of the world the agent consults when describing things. One file per consequence in `consequences/`, created via Post-session extraction.
_Avoid_: Fact, state change, event.
_See also_: `references/frontmatter-schemas.md` for the Consequence schema.

**Beat**:
A GM-authored intention to deliver a specific content moment opportunistically — a planned scene, a piece of news, an item to hand out, a character development moment, a puzzle. *A scene the GM has prepped, waiting for an opening to land.* Future-facing. Has status (`pending`, `delivered`, `dropped`). One file per Beat in `beats/`. Created by GM authoring directly, by `/wrap-session` proposal, by promotion from a Brief scratchpad, or by `/ingest` extraction from GM-authored source docs (see ADR-0009 — the source docs are the GM's authoring). Surfaces in pre-session Briefs in an "optional, weave in if possible" section, filtered by relevance to current campaign context. Optional frontmatter: `kind`, `linked_pcs`, `linked_npcs`, `linked_adventures`, `linked_locations`, `linked_secrets`.
_Avoid_: Seed, hook (overloaded with "plot hook"), setup.
_See also_: `references/frontmatter-schemas.md` for the Beat schema.

Contrast with **Thread**: an open hook the party knows about, waiting for resolution. The defining test is *party awareness* — if the party knows the situation exists and may act on it, it's a Thread; if it's GM prep the party hasn't encountered, it's a Beat.

Beats may optionally be classified by `kind:` in frontmatter — an open-enum field with starter values `news | handout | character-moment | set-piece | clue | escalation | puzzle`. Unclassified Beats (no `kind:`) are surfaced normally; classified Beats unlock kind-specific behavior in prep-session. A **Clue** is conventionally a Beat with `kind: clue` and `linked_secrets:` populated pointing to the Secret it reveals; the agent queries Clues per Secret to track revelation progress. An **Escalation** is a Beat with `kind: escalation` — held back as a back-pocket lever for raising stakes mid-session, surfaced separately via the prep-session Escalation Prep question. A **Puzzle** is a Beat with `kind: puzzle` — a one-shot encounter the party reasons through (a riddle, a logic puzzle, a room-bound mechanical trick); the Beat body holds the puzzle text and intended solution, and lifecycle follows the standard `pending → delivered` path. The other kinds align with the original enumeration above (`set-piece` for a planned scene with structural prep, `news` for an info drop, `handout` for an item transfer, `character-moment` for a PC-arc payoff). The enum is open — new kinds may be added as dogfooding reveals distinct prep-surfacing needs.

**Secret**:
A fact about the world the party might not know yet but could learn. Distinct from a **Beat** (which delivers it via a Clue) and a **Consequence** (which is a *past* fact resulting from party action — a Secret is a *latent* fact that may become a Consequence when revealed). Has status (`hidden` → `partially-revealed` → `revealed`). One file per Secret in `secrets/`. Frontmatter `belongs_to` is an unordered set of paths to non-ephemeral containers (Adventure, NPC, PC, Location, Faction, Item) — at least one entry required; no free-floating Secrets. Each container in `belongs_to` carries a `## Secrets` section in its file body wiki-linking back to the Secret (symmetric); the Secret file is the source of truth, the container's section is a derived view the agent maintains. Clue Beats reference the Secrets they reveal via `linked_secrets:` frontmatter; the Secret's `revealed_by:` is populated as those Beats are delivered.
_Avoid_: hidden info (use Secret), spoiler, twist, reveal (the act of revealing, not the fact itself).
_See also_: `references/frontmatter-schemas.md` for the Secret schema.

**Non-ephemeral container**:
A persistent campaign object that can own a Secret via `belongs_to`. The set is: Adventure, NPC, PC, Location, Faction, Item. Excluded as ephemeral: Thread (resolves to `closed` / `decayed`), Beat (delivers and exits), Session / Brief / In-play notes / Log (per-session artifacts). Consequence is persistent but excluded because Consequences are past facts; Secrets are latent facts — a different epistemic status. The set may grow if v0.2+ introduces new persistent containers.

**Post-session extraction**:
The workflow where, after a session, the agent reads in-play session notes and proposes new Threads, Consequences, and Reference notes. The GM approves a batch with minimal friction. This is the structural moment in the system — capture during play is unstructured; structure emerges here.

## Flagged ambiguities

**Character** is ambiguous in TTRPG usage. **In this project, "Character" without qualifier means PC.** When the referent could be either, say "PC" or "NPC." PCs and NPCs live in separate directories (`pcs/` and `npcs/`), one file per character per [ADR-0003](./docs/adr/0003-per-file-reference-notes.md).

**Campaign-local override** is the rule that resolves Atlas-vs-campaign conflicts: a campaign's own content is authoritative within that campaign, even when it contradicts the Atlas. "Waterdeep was destroyed in this campaign" wins over the Atlas's thriving Waterdeep, without disturbing the Atlas itself or other campaigns that reference it. The override is by-name lookup at the Reference note level; granularity (full-replace vs fact-level merge) is not yet decided.

**Menu of next-session options** is a working term (not a new lifecycle object) for the forward-looking surface shared by `campaign.md` and the Brief in open-world / sandbox campaigns: the set of arcs and threads the party could plausibly pick up next session. It draws from `status: active` Adventures (could-continue), `status: introduced` Adventures (could-start), and recent open Threads that could become a session focus. **Available Adventures** is similarly informal — it covers both `active` and `introduced` Adventures, the union the menu reads from. Neither term implies a new Adventure status; the lifecycle (`introduced → active → completed | abandoned`) is unchanged. If these terms harden in practice into something the agent needs to reason about beyond rendering, promote them to a glossary entry then.

## Example dialogue

> **GM**: I want to ingest *Curse of Strahd* into my Faerûn campaign.
>
> **Claude**: I'll add it as an Adventure inside the campaign — `adventures/curse-of-strahd/`. Reference notes for Strahd, Barovia, and the named NPCs will land in the campaign's `npcs/` and `locations/`, not the Atlas, since they're specific to this run.
>
> **GM**: Barovia is in the Atlas though — I've run it before.
>
> **Claude**: Then I'll skip creating a new Barovia and link to the Atlas entry. If anything in this campaign contradicts the Atlas Barovia, you'll want a campaign-local override.
>
> **GM**: Yeah, in this campaign Barovia is in the Underdark, not the Mists.
>
> **Claude**: I'll create `locations/Barovia.md` in the campaign as a campaign-local override. The Atlas's Barovia is untouched.
