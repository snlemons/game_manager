# Beats are a first-class GM-authored lifecycle object

Beats are planned content moments the GM intends to deliver opportunistically (a consequence to land, an item to hand out, a piece of news to drop). They are a **third lifecycle file type** alongside Threads and Consequences, distinguished by **author** and **direction**: GM-authored, future-facing, with status `pending → delivered | dropped`.

> **Live spec:** the canonical Beat frontmatter schema (fields, types, defaults) is `references/frontmatter-schemas.md`. The "Surfacing at scale" section in this ADR describes the Brief-time relevance tiers; the schema part defers to the reference.

Files live in `beats/`, one per Beat, with frontmatter for `status`, `created`, `delivered` (null until landed), and optional `linked_pcs` / `linked_npcs` / `linked_adventures` / `linked_locations` lists. Adventures (or anything else) reference Beats via `[[wiki links]]`; the agent uses backlinks to scope Beats to adventures when relevant.

## Why distinct from Threads and Consequences

|  | Author | Direction | Lifecycle |
|---|---|---|---|
| **Thread** | Party-driven | Future-facing | `open → closed/decayed` |
| **Consequence** | Past-derived | Past-facing | exists (no close) |
| **Beat** | GM-authored | Future-facing | `pending → delivered/dropped` |

A Thread is something the *party* is pursuing or owes. A Beat is something the *GM* wants to land. They surface differently in Briefs (Threads are likely-to-come-up; Beats are weave-in-if-possible) and have different decay semantics (Threads decay if neglected; Beats get explicitly dropped when no longer desired).

## Creation paths

1. **GM direct authoring** — the GM writes a Beat file (or invokes `/add-beat` if such a command ships).
2. **`/wrap-session` proposal** — agent reads in-play notes and proposes Beats from things like "I want to set up X next time" or scratchpad items.
3. **Brief scratchpad promotion** — items the GM jots in the Brief's scratchpad get offered as Beat candidates by the next `/wrap-session`.
4. **`/ingest` extraction** — agent extracts Beats from GM-authored source docs (encounter tables, planned scenes, per-PC personal hooks, "if X then Y" contingent deliveries, tagged adventure content). The GM-authored constraint still holds: the source docs *are* the GM's authoring, just retroactively. The agent is preserving prep content, not inferring intent from session events. Per ADR-0007's date-honesty rule, ingest-era Beats carry `created: ~` (null) unless the source provides an explicit date — the agent does not stand in the ingest date for unknown authoring dates.

   **Linked-field population at extraction time.** `/ingest` populates `linked_adventures`, `linked_locations`, `linked_pcs`, and `linked_npcs` on each extracted Beat using proximity heuristics in the source doc — *not* leaving them empty for downstream backfill. These fields exist specifically to feed the surfacing-at-scale tiers below, and an unpopulated Beat ends up in the "unlinked, review and tag" tier where it adds friction without informing the Brief. The skill's authoritative rules live in `skills/ingest/SKILL.md` (Step 3, **Beat shape** subsection); the heuristics, in summary:

   - If the source doc is adventure-shaped (being ingested as `adventures/<slug>/`), every Beat from it gets `linked_adventures: [<slug>]` automatically — the link is structural, not inferred.
   - If the source doc is world-info-shaped, link to an Adventure only when a Beat-shaped passage explicitly names one in its own paragraph, bullet, or enclosing heading section.
   - For `linked_locations`, link locations named in the Beat's own paragraph or bullet, or named in the enclosing heading. The "near" radius is narrower than for Adventures because locations are usually tagged precisely.
   - For `linked_pcs`, require explicit attribution (*"for Darius:"*, *"Darius's hook:"*). Generic party references don't justify a PC link.
   - For `linked_npcs`, require the NPC to be the actor or subject of the Beat — name-drops without role context aren't enough.
   - When proximity is ambiguous (multiple Adventures named near a Beat; two Locations matching the same name), surface as an ASK in the per-doc review rather than guessing.
   - Default to `[]` (empty list with the YAML key present), not omission of the key — downstream skills read these fields without conditional logic.

   This behavior was added in response to a dogfooding regression (issue #15) where ingest extracted Beats with empty `linked_*` fields, forcing a manual 22-Beat backfill and breaking `/prep-session`'s relevance filtering.

Heuristics for an item being Beat-shaped in a source doc: unchecked encounter lists, sections labelled "scenes I want to drop in," personal-hook bullets attributed to a specific PC, content the party doesn't know about yet but the GM wants to land. Threads (party-aware hooks) and Consequences (past-derived facts) are extracted under their own rules — Beats fill the third lifecycle slot.

## In Briefs

`/prep-session` includes a "Beats to weave in (optional)" section listing pending Beats relevant to the current campaign context. Framed as optional — the GM picks 0–N to land per session.

## Surfacing at scale (implemented)

When the campaign has many pending Beats — common immediately after `/ingest` of a long-running campaign with prepped encounter content — the original "list all pending Beats in the Brief" rule doesn't scale. The Brief becomes a wall and the GM tunes it out, defeating the purpose. `/prep-session` filters pending Beats through relevance tiers; only the **in-focus** ones land in the Brief as full bullets, and the rest are summarized as counts so they're acknowledged without overwhelming the GM.

**Tiers, evaluated per pending Beat:**

- **In-focus — shown in full.** Hits at least one of:
  - `linked_adventures` overlaps any Adventure in the **in-focus Adventure set** (defined below), or
  - `linked_pcs` overlaps the PCs the agent identifies as in focus (prior Log foregrounded them, in-focus Adventures reference them, or they're named in an open Thread / pending Beat already being surfaced), or
  - `linked_locations` overlaps locations "near" the party's current location (same location, one step away in the Reference-note graph, or named as a likely next stop by an in-focus Adventure's geography), or
  - `linked_npcs` overlaps NPCs the party may encounter (the same set the Brief's NPCs section is computing — a secondary signal in support of the three primary tiers).
  - As a legacy fallback, a Beat with no `linked_*` fields populated but that is backlinked from an in-focus Adventure file (via `[[wiki link]]`) is also in-focus. That backlink predated the `linked_*` frontmatter; honor it.

  In-focus Beats render in the "Beats to weave in (optional, weave in if possible)" section as full bullets with a short `*(scope: …)*` hint identifying the signal that hit.

  **In-focus Adventure set.** The original rule keyed on `status: active` Adventures only, which broke for open-world / sandbox campaigns where the party has multiple available arcs and none currently running (issue #13). The set now includes:

  - every Adventure with `status: active`, **and**
  - every Adventure with `status: introduced` that the Brief surfaced in its **"Menu of next-session options"** section.

  The menu is the open-world equivalent of "this arc might come up next session," so its Beats should be in scope. `introduced` Adventures not in the menu remain out of focus on the Adventure signal — they're available in principle, but the GM hasn't elevated them to next-session candidates. `completed` and `abandoned` Adventures are never in-focus.

- **Out-of-focus, linked but not in focus — counted only.** At least one `linked_*` field is populated, but none of the populated fields overlap any in-focus signal. The Brief renders a single count line with a one-line breakdown by scope (e.g., *"Plus 14 more pending Beats linked to other Adventures / PCs / locations not in focus this session (6 in Curse of Strahd, 5 around Neverwinter, 3 elsewhere)"*).

- **Unlinked — counted with a "review and tag" nudge.** No `linked_*` fields populated and no active-Adventure backlink. The Brief renders a count line plus the nudge so the GM can triage later (e.g., *"Plus 3 pending Beats with no `linked_*` tags — review and tag them so future prep can surface them when relevant"*).

**Empty cases.** If the in-focus list is empty but a count line is non-zero, render the count line(s) and skip the bullets — the GM still needs to know Beats exist and weren't surfaced. If everything is empty, render `_None._` under the heading. The "optional, weave in if possible" framing is preserved in either case.

**Why this works as a Brief-time concern only.** The Beat lifecycle (`pending → delivered | dropped`) is unchanged. The frontmatter schema is unchanged. The `campaign.md` (Campaign overview) still lists every pending Beat — it's the state snapshot, not a curated reading list (see the `/ingest` campaign-overview composer's note on this). Only the Brief filters. Future prep automatically re-evaluates relevance when the in-focus set shifts (a new Adventure becomes active, the party moves, a new PC enters focus), so out-of-focus Beats surface when the time comes without GM intervention.

**Implementation lives in `skills/prep-session/SKILL.md`** under "Tiered Beat surfacing" (Step 2) and the Beats-section template + drafting rules in Step 3.
