# Beats are a first-class GM-authored lifecycle object

Beats are planned content moments the GM intends to deliver opportunistically (a consequence to land, an item to hand out, a piece of news to drop). They are a **third lifecycle file type** alongside Threads and Consequences, distinguished by **author** and **direction**: GM-authored, future-facing, with status `pending → delivered | dropped`.

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

## Surfacing at scale (open)

When the campaign has many pending Beats — common immediately after `/ingest` of a long-running campaign with prepped encounter content — the original "list all pending Beats in the Brief" rule doesn't scale. The Brief becomes a wall and the GM tunes it out, defeating the purpose. A relevance-filtered tiered surfacing strategy is needed:

- Beats with `linked_adventures` overlapping `status: active` Adventures → shown in full in the Brief.
- Beats with `linked_pcs` overlapping PCs the agent identifies as in focus → shown in full.
- Beats with `linked_locations` near the party's current location → shown in full.
- Everything else → count + breakdown summary so the Beats are acknowledged but don't overwhelm.
- Unlinked Beats → counted with a "review and tag" nudge so the GM can prioritize triage.

The `linked_adventures` / `linked_locations` frontmatter fields exist specifically to support this filtering. Implementation of the surfacing strategy is a future enhancement (filed as an issue).
