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
4. **`/ingest` extraction** — agent extracts Beats from GM-authored source docs (encounter tables, planned scenes, per-PC personal hooks, "if X then Y" contingent deliveries, tagged adventure content). The GM-authored constraint still holds: the source docs *are* the GM's authoring, just retroactively. The agent is preserving prep content, not inferring intent from session events.

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
