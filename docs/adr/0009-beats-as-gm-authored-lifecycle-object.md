# Beats are a first-class GM-authored lifecycle object

Beats are planned content moments the GM intends to deliver opportunistically (a consequence to land, an item to hand out, a piece of news to drop). They are a **third lifecycle file type** alongside Threads and Consequences, distinguished by **author** and **direction**: GM-authored, future-facing, with status `pending → delivered | dropped`.

Files live in `beats/`, one per Beat, with frontmatter for `status`, `created`, `delivered` (null until landed), and optional `linked_pcs` / `linked_npcs` lists. Adventures (or anything else) reference Beats via `[[wiki links]]`; the agent uses backlinks to scope Beats to adventures when relevant.

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

## In Briefs

`/prep-session` includes a "Beats to weave in (optional)" section listing pending Beats relevant to the current adventure context. Framed as optional — the GM picks 0–N to land per session.
