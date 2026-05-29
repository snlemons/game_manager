# Game Manager

A Claude-native plugin for TTRPG GMs to organize campaigns, prep sessions, and track continuity. Campaign data lives in GM-owned markdown repos; this glossary defines the domain language the plugin and its conventions use.

## Language

### Roles and people

**GM** (Game Master):
The user of this system. Runs the campaign, owns the campaign repo, makes all final decisions about content.
_Avoid_: DM, Dungeon Master, referee, storyteller.

**PC** (Player Character):
A character controlled by a player at the table. Lives in the `Characters` page of a campaign.
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

**Campaign overview**:
A campaign-root `campaign.md` file, agent-maintained, snapshotting the campaign's current state in human-readable form (active adventures, open threads, recent consequences, party location). Rewritten by `/wrap-session` and `/ingest`. Distinct from `/timeline` (historical) and from GM-editorial files (which live separately).
_Avoid_: Index, README, dashboard.

**Atlas**:
A shared setting repo that holds world content (regions, gods, calendars, recurring NPCs) used across multiple campaigns. Separate git repo from any campaign. Treated as a default; campaigns override it locally.
_Avoid_: Setting, world (use Atlas), lore.

### Content kinds

**Reference note**:
A static, linked-to entry about a thing in the world: an NPC, a location, a faction, an item. **One file per Reference note** (e.g. `npcs/sera.md`), so links and backlinks work natively. Default content is a one-liner; the GM never fills out a form.
_Avoid_: Entity, record, document.

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

**Consequence**:
A persistent fact about the world resulting from the party's actions ("the guard captain owes them a favor"). Past-facing; doesn't close — it just becomes part of the world the agent consults when describing things. One file per consequence in `consequences/`, created via Post-session extraction.
_Avoid_: Fact, state change, event.

**Beat**:
A GM-authored intention to deliver a specific content moment opportunistically — a planned consequence, a piece of news, an item to hand out, a character development moment. Future-facing. Has status (`pending`, `delivered`, `dropped`). One file per Beat in `beats/`. Created by GM authoring directly, by `/wrap-session` proposal, or by promotion from a Brief scratchpad. Surfaces in pre-session Briefs in an "optional, weave in if possible" section. Referenced from adventures via `[[wiki links]]` when scoped; backlinks tell the agent which adventure a Beat belongs to.
_Avoid_: Seed, hook (overloaded with "plot hook"), setup.

**Post-session extraction**:
The workflow where, after a session, the agent reads in-play session notes and proposes new Threads, Consequences, and Reference notes. The GM approves a batch with minimal friction. This is the structural moment in the system — capture during play is unstructured; structure emerges here.

## Flagged ambiguities

**Character** is ambiguous in TTRPG usage. The brief's recommended `Characters` page holds PCs only, with NPCs in a separate `NPCs` page. **In this project, "Character" without qualifier means PC.** When the referent could be either, say "PC" or "NPC."

**Campaign-local override** is the rule that resolves Atlas-vs-campaign conflicts: a campaign's own content is authoritative within that campaign, even when it contradicts the Atlas. "Waterdeep was destroyed in this campaign" wins over the Atlas's thriving Waterdeep, without disturbing the Atlas itself or other campaigns that reference it. The override is by-name lookup at the Reference note level; granularity (full-replace vs fact-level merge) is not yet decided.

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
