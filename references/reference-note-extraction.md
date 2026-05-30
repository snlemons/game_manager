# Reference-note extraction heuristic

When does a name in a source doc or in-play notes warrant creating a Reference note, and what does the proposed file look like? This is the shared spec used by `/ingest` Phase 3 (extracting from GM-authored source docs) and `/wrap-session` Pass 2 (proposing Reference notes from a session's `notes.md`). The orchestration around extraction (cross-doc learning in `/ingest`, session-context dedup in `/wrap-session`) stays in each SKILL.md; this reference is just the heuristic and the default file shape.

The corresponding ADR is [ADR-0003](../docs/adr/0003-per-file-reference-notes.md) (one file per Reference note; default content is a one-liner).

## What counts as a Reference note

A name mentioned in source content becomes a Reference note when:

- It's a **named** NPC, location, faction, or item. Bare descriptors ("the innkeeper", "a guard") without a proper name don't qualify on their own — see "Missing or unclear names" below.
- The source content **introduces or describes the thing substantively** — gives it a role, a place in the world, a fact the agent will plausibly need to retrieve later by name.

A passing mention without role context is **not** a Reference note. Examples of mentions that *don't* warrant extraction:

- A list item in a roster the source doc enumerates for color but doesn't develop ("…among them Orin, Sera, and Maris, none of whom matter to the arc").
- A name dropped once as flavor with no follow-up ("the bard sang about Old Gristle the dragon").
- Generic NPCs the party interacts with mechanically but who aren't characters in the world ("the party haggled with the merchant").

When borderline, prefer to **propose** the Reference note and let the GM reject it at review than to drop it silently. False positives are cheap (one delete in staging); false negatives are invisible.

## Folder by kind

| Kind | Folder |
|---|---|
| NPC | `npcs/` |
| Location | `locations/` |
| Faction | `factions/` |
| Item | `items/` |

Don't synthesize new kinds. If something doesn't fit one of these four, surface it to the GM rather than inventing a folder.

## Filename — slug rule

Filenames are slugs of the canonical name. Lowercase, ASCII-fold accents, strip leading "the ", collapse whitespace and punctuation to single hyphens, trim leading/trailing hyphens. See `references/dedup-matching.md` for the full normalization rule — Reference-note slugs use the same normalization as dedup matching so that a candidate slug and an existing filename collide cleanly.

Example: *"The Broken Mines"* → `the-broken-mines.md`. Wait — "the" gets stripped — `broken-mines.md`. *"Sera Stoneforge"* → `sera-stoneforge.md`. *"Café du Monde"* → `cafe-du-monde.md`.

## Default body — the one-liner

The default body is **one line** derived from the source content: who/what the thing is, in short factual prose. ADR-0003: the GM never fills out a form. Do **not** generate an "About" template, a stats block, or empty placeholder sections. One sentence, drawn from the source content, is the artifact.

Use `[[wiki links]]` to other Reference notes that the source content names — those resolve to backlinks the agent uses in later passes.

Example, NPC introduced in a session's notes:

```markdown
# Sera

Blacksmith in [[Phandalin]] who reports the mines were recently closed.
```

Example, location introduced in an ingest doc:

```markdown
# The Broken Mines

A network of half-collapsed tunnels east of [[Phandalin]], rumored to be cursed.
```

## Frontmatter — minimal by default

Reference notes **do not require frontmatter** in v0.1. If the source content gives a clear strong fact — kind, role, status — light frontmatter is allowed:

```yaml
---
kind: npc
---
```

But:

- **Do not invent fields the source doesn't supply.** Empty placeholder fields are worse than no frontmatter.
- **Do not invent values.** If the source doesn't say where Sera is or what she does, the one-liner says only what the source said.

When a more specific schema is needed for an extracted object (a Thread, a Consequence, an Adventure, a Beat), that's not a Reference note — see `references/frontmatter-schemas.md`.

## Missing or unclear names

A common case: source content references "the blacksmith" or "the captain" without ever naming them. **Do not invent a name.** Two correct moves:

- **`/ingest`:** surface the unnamed entity at the per-doc review as an ASK: *"The blacksmith in section 2 is unnamed. Propose a Reference note (with a placeholder name), skip, or wait until the GM names them?"*
- **`/wrap-session`:** route the unnamed entity to ambiguity clarification (Step 3) before staging: *"An unnamed blacksmith appears in the notes. Provide a name, or skip creating a Reference note?"*

If the agent can match the unnamed reference to an existing Reference note via clear context ("the captain" used to refer to `npcs/captain-marra.md` in the prior session's Log), that's a confident UPDATE, not a CREATE — see `references/dedup-matching.md`.

## Updates to existing Reference notes

When the source content mentions an entity that already has a Reference note and adds new information, propose an UPDATE rather than a CREATE:

- **Append** for accreted facts ("Sera is now wary of the party").
- **Edit** for changes that contradict the existing line ("Sera moved from the village to the city" — replace the location half).
- **Never lose GM-authored prose.** If overwriting would discard content, surface both versions and flag for review.

Dedup matching (slug + first-heading title, normalized) is what routes a candidate to UPDATE vs CREATE — see `references/dedup-matching.md`.

## What not to do

- **Don't fabricate detail.** If the source doesn't say what kind of blacksmith Sera is, the one-liner doesn't say either.
- **Don't pre-create empty kind folders.** A folder appears when its first file lands.
- **Don't extract Atlas content.** v0.1 is single-repo (ADR-0006); treat everything as campaign-local.
- **Don't fill out a template.** ADR-0003's whole point: capture-now-structure-later. The Reference note's job is to exist and be linkable; the GM enriches it later if needed.
