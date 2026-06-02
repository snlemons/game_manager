# Frontmatter schemas

Canonical YAML for the five lifecycle objects (Adventure, Thread, Consequence, Beat, Secret) plus the optional Reference-note `aliases:` field. CONTEXT.md is the concept-level glossary; this reference is the spec-level (exact fields, types, value formats, defaults). All three skills (`/ingest`, `/prep-session`, `/wrap-session`) write these schemas; this is the single source of truth.

The corresponding ADRs are [ADR-0007](../docs/adr/0007-temporal-model-and-campaign-overview.md) (Adventure), [ADR-0004](../docs/adr/0004-threads-consequences-via-post-session-extraction.md) (Threads and Consequences), [ADR-0009](../docs/adr/0009-beats-as-gm-authored-lifecycle-object.md) (Beats), [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md) (Secrets), and [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md) (Reference-note `aliases:`).

## Conventions

- **Dates** are real-world `YYYY-MM-DD` strings unless otherwise noted. Never invent dates — ADR-0007: "the agent never asks the GM to invent dates it doesn't have." Null is written as `~` (YAML null literal). Empty strings are never used in place of null.
- **Slugs** (used in `linked_*` lists and as filenames) are produced by the normalization rule in `dedup-matching.md`: lowercase, ASCII-fold accents, strip leading "the ", collapse whitespace and punctuation to single hyphens, trim leading/trailing hyphens.
- **Status enums** are lowercase string literals from the enumerated set listed per schema below. Values outside the enum are a bug.
- **Optional list fields** default to `[]` (empty list with the YAML key present), not omission of the key. Downstream skills read these fields without conditional logic; an absent key forces a fallback that masks the "field considered, left empty" signal.
- **Filename** is a slug of the canonical name + `.md`. One file per object. Files live in the folder named for their kind: `adventures/<slug>/adventure.md`, `threads/<slug>.md`, `consequences/<slug>.md`, `beats/<slug>.md`, `secrets/<slug>.md`.

## Reference note

File: `<kind>/<slug>.md` where `<kind>` is `npcs`, `locations`, `factions`, `items`, or `pcs`.

Reference notes do not require frontmatter (per `reference-note-extraction.md` — minimal-by-default). When frontmatter is present, the following fields are recognized; all are optional. The schema applies to every Reference-note kind, with three extra optional fields available only on PCs (per ADR-0023).

```yaml
---
kind: npc                            # optional: npc | location | faction | item | pc
aliases: []                          # optional: list of other names this entity goes by
belongs_to: []                       # optional: list of PC container paths (PC-source cross-extraction; ADR-0023)
player: ""                           # optional, PC only: player at the table
class: ""                            # optional, PC only: character class
level: 1                             # optional, PC only: character level (positive integer)
---
```

### Field semantics

- **`kind`** — optional, lowercase string. Redundant with the file's folder (an NPC lives in `npcs/`); the field exists for callers that read the file without context, and as a hand-edit hook the GM may use to declare kind for a Reference note whose folder is ambiguous. Absent is the common case.
- **`aliases`** — optional, list of strings. Other names this entity goes by — pseudonyms, titles, masks, given-vs-order names — per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md). The canonical name is the file's slug + H1; `aliases:` lists the others. Each entry is a human-readable string (e.g. `"The Shadow"`, `"Captain Marra"`); the dedup-matching pass normalizes each entry through the same slug rule that normalizes filenames and titles (`dedup-matching.md`), so a source-doc mention of "the shadow" or "The Shadow" routes to the canonical file as a confident UPDATE.

  Default: empty list (or the key may be omitted entirely; absent reads as `[]`).

  The field is most load-bearing for NPCs (double identities, pseudonyms, pre-reveal masks) but is available on every Reference-note kind. PC aliases (nickname-vs-given-name) use the same field; Location aliases (a city's historical and current names) and Item aliases (a sword's true name vs the name a faction gave it) work the same way.
- **`belongs_to`** — optional, list of strings. Paths to PC containers that this Reference note was cross-extracted from per ADR-0023. Each entry is a `pcs/<slug>.md` path. Populated when the Reference note was extracted from a `PC source: <pc-slug>` doc and the PC is the cross-extraction owner; absent (or empty list) otherwise. The field's source of truth is the Reference note; the symmetric `## NPCs` / `## Locations` / `## Factions` / `## Items` section on the PC and the `## PCs` section on the Reference note are derived views the agent maintains per `bidi-link-maintenance.md` § "PC as container."

  Default: empty list (or the key may be omitted entirely; absent reads as `[]`).

  This field deliberately reuses the same name as Secrets' `belongs_to:` — the semantic is parallel ("this Reference note is owned by these PCs as containers"), and the bidi-link maintenance reuses the symmetric-section pattern. The two `belongs_to:` fields don't collide because they appear on different file kinds (Secrets vs Reference notes).

### PC-only optional fields (ADR-0023)

These three fields are valid only on `pcs/<slug>.md` files. They appear when the source supplies them (typically a `PC source:` doc with player/class/level metadata) and are omitted otherwise. None are required; an `pcs/<slug>.md` file without any of them is the minimal stub shape per ADR-0022.

- **`player`** — optional, string. The name (or handle) of the player at the table who controls this PC. Useful for GMs who manage rotating tables or want player-facing prep to address a player by name. The agent never invents this — it is populated only when the source doc supplies it explicitly (a metadata block, a "Player: <name>" line, etc.). Absent is fine.
- **`class`** — optional, string. The PC's character class (or multi-class composite — *"Fighter / Cleric"* is valid). Populated only when the source doc supplies it explicitly. Multi-class entries are written as a single string verbatim from the source. Absent is fine.
- **`level`** — optional, positive integer. The PC's character level. Populated only when the source doc supplies it explicitly. The agent never increments the value as sessions progress — level changes are GM-owned. Absent is fine.

The three fields are independently optional — supplying `level:` without `class:` is valid; supplying `player:` alone is valid. They do not collectively form a "stat block" — they are the **selective B frontmatter slice** per [issue #57](https://github.com/snlemons/game_manager/issues/57)'s scoping. The full PC stat schema (HP, AC, abilities, proficiencies, equipment, spells, features) is **deferred** out of v0.3 scope per ADR-0023 (deferred-stats rationale).

### Defaults at creation

- `/ingest` Phase 3 CREATE: omit `aliases:` (or write `aliases: []`) unless the source doc names both the canonical and at least one alias and the GM confirms the relationship at the per-doc review per `reference-note-extraction.md`. The agent's first proposal follows the canonical-choice heuristic in ADR-0017; the GM picks canonical at review. Omit `belongs_to:` unless the source doc is a `PC source: <slug>` doc and the entity was cross-extracted from PC backstory (per ADR-0023); on PC source cross-extraction, populate `belongs_to: [pcs/<slug>.md]`. Omit `player:` / `class:` / `level:` (PC-only fields) unless the source supplies them explicitly.
- `/wrap-session` Pass 2 CREATE: omit `aliases:` unless the session notes name both the canonical and an alias and the GM confirms the relationship at Step 3 ambiguity clarification. Omit `belongs_to:` (`/wrap-session` does not extract from PC source docs).
- UPDATE (alias added to an existing Reference note): append the new alias to the existing `aliases:` list (do not replace); preserve every other frontmatter field byte-for-byte. The same rule applies to `belongs_to:` updates — append new PC paths, never replace.
- `/ingest` Phase 2 PC stub CREATE (per [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md) + [ADR-0022](../docs/adr/0022-pc-roster-via-explicit-classification.md)): write `kind: pc` explicitly so the file is unambiguous on read, include `aliases:` only when the survey roster line captured nicknames (`— alias: <name>` suffixes), and write an optional one-line body if the GM enriched the staged annotation — otherwise leave the file as frontmatter + H1 only. The stub shape is intentionally minimal; `player:` / `class:` / `level:` are **not** populated at Phase 2 stub creation, even when the roster line came from a `PC source:` auto-add — those fields land during Phase 3's PC source extraction branch when the source doc is read in full.
- `/ingest` Phase 3 PC source UPDATE (per [ADR-0023](../docs/adr/0023-pc-source-doc-ingestion.md)): when a `PC source: <slug>` doc supplies `player:` / `class:` / `level:` explicitly in its backstory metadata, populate the corresponding fields on `pcs/<slug>.md`. Omit each field whose value the source doesn't supply. If a field already exists with a different value on the live PC file, surface the discrepancy as an ASK at Step 4a rather than overwriting (the GM's prior value wins by default).

### Worked example: PC stub

The Phase 2 PC roster promotion writes a minimal stub. Example for *Helerel* (nickname *Helly*), enriched at staging with a one-line role description:

```yaml
---
kind: pc
aliases: [Helly]
---

# Helerel

Dwarf cleric.
```

Example for *Silas*, no nickname captured at survey time, no one-line body (the GM didn't enrich the annotation — the agent leaves the body empty rather than inventing):

```yaml
---
kind: pc
---

# Silas
```

Both shapes are valid. Downstream skills read `kind: pc` to disambiguate from NPCs; the `aliases:` field (when present) feeds the same dedup-matching pass that handles NPC aliases per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md).

### Worked example: PC after PC source extraction

After Phase 3 runs against a `PC source: aldric` doc that supplied player / class / level metadata and a backstory naming a hometown, family, and an order, the file looks like:

```yaml
---
kind: pc
player: Sam
class: Paladin
level: 5
---

# Aldric of Highmoor

Aldric was born in [[locations/highmoor]] to [[npcs/caelir-of-highmoor|Caelir]],
a knight of the [[factions/order-of-the-ember|Order of the Ember]]…

## NPCs

- [[npcs/caelir-of-highmoor]] — Aldric's father

## Locations

- [[locations/highmoor]] — Aldric's hometown

## Factions

- [[factions/order-of-the-ember]] — the order Aldric serves
```

The `## NPCs` / `## Locations` / `## Factions` / `## Items` sections are agent-maintained per `bidi-link-maintenance.md` § "PC as container"; the body above them is GM-owned and may include backstory appended during the Phase 3 PC source branch. The `belongs_to:` field on the cross-extracted Reference notes (e.g., `npcs/caelir-of-highmoor.md`) carries `pcs/aldric.md` as the symmetric back-link.

### Validation

- **No duplicate aliases.** An entry that normalizes to the canonical slug, the H1 of the same file, or another entry in the same `aliases:` list is a duplicate; surface to the GM at review and drop the duplicate.
- **No cross-file alias collisions.** An alias whose normalized form collides with another canonical file's slug, H1, or `aliases:` entry in the same kind folder is an ambiguous match per `dedup-matching.md`; surface as ASK rather than silently picking one.

## Adventure

File: `adventures/<slug>/adventure.md`.

```yaml
---
status: introduced                   # required: introduced | active | completed | abandoned
order: ~                             # integer; ingest-era sequence; null for session-tracked
introduced: ~                        # YYYY-MM-DD; null when unknown
started: ~                           # YYYY-MM-DD; null when unknown
completed: ~                         # YYYY-MM-DD; null when unknown
in_world_duration: ~                 # optional free-form prose
real_world_duration: ~               # optional free-form prose
---
```

### Field semantics

- **`status`** — required. The Adventure lifecycle: `introduced` (known to the party but not started), `active` (the party is running it), `completed` (resolved), `abandoned` (the party walked away or the GM dropped it). Transitions:
  - `introduced → active` — `/wrap-session` Pass 1 when the party began running it this session. Sets `started:` to the session date.
  - `active → completed` — `/wrap-session` Pass 1 when the party resolved it. Sets `completed:` to the session date.
  - `active → abandoned` — `/wrap-session` Pass 1 when the party walked away. Sets `completed:` to the session date (per ADR-0007, abandoned still records a completion date with abandoned semantics).
- **`order`** — integer or null. Ingest-era reliable GM-supplied sequence: 1 = earliest in the campaign's history. For session-tracked Adventures, `order` is unnecessary (`started:` is the precise signal); leave null. For ingest-era Adventures whose source doc didn't have explicit numeric sequencing the agent could copy, leave null at extraction time — `/ingest` Phase 4's bulk order prompt fills it in. Duplicates are allowed if two Adventures ran in parallel (confirmed at the prompt).
- **`introduced` / `started` / `completed`** — real-world dates. Never invented. For session-tracked Adventures `/wrap-session` fills these precisely from the session directory's date. For ingest-era Adventures, null unless the source doc explicitly supplies a date the agent can attribute.
- **`in_world_duration` / `real_world_duration`** — free-form prose annotations. Examples: `"3 in-game months"`, `"~6 sessions"`. Copy verbatim from source content when supplied; never invented.

### Defaults at creation

- Ingest-era CREATE: `status: introduced`, `order: ~` (unless the source doc had explicit numbering), all dates null, durations null unless source supplied.
- `/wrap-session` CREATE (new Adventure that began this session): `status: active`, `started: <session date>`, other dates null, `order: ~`.

## Thread

File: `threads/<slug>.md`.

```yaml
---
status: open                         # required: open | closed | decayed
created: 2026-05-29                  # YYYY-MM-DD of the session that opened it; ~ for ingest-era
closed: ~                            # YYYY-MM-DD; null until status transitions to closed/decayed
---
```

### Field semantics

- **`status`** — required. `open` (still owed/asked/foreshadowed), `closed` (resolved), `decayed` (the GM is letting it go because too much in-fiction time passed).
- **`created`** — YYYY-MM-DD of the session that opened the Thread. For Threads `/wrap-session` proposes, this is the session date (from the session directory name). For ingest-era Threads, null unless the source doc explicitly provides a date the agent can attribute — do not stand in the ingest date for unknown source dates.
- **`closed`** — YYYY-MM-DD when the Thread transitioned to `closed` or `decayed`. Null until the transition lands.

### Defaults at creation

- `/wrap-session` Pass 4 CREATE: `status: open`, `created: <session date>`, `closed: ~`.
- `/ingest` Phase 3 CREATE: `status: open` unless the source doc says the Thread is already resolved (`closed`) or stale (`decayed`); `created: ~`; `closed: ~` (or a date if the source supplies one).

## Consequence

File: `consequences/<slug>.md`.

```yaml
---
created: 2026-05-29                  # YYYY-MM-DD of the session that caused it; ~ for ingest-era
---
```

### Field semantics

- **`created`** — YYYY-MM-DD of the session whose events produced this persistent fact. Consequences are past-facing; they don't close — they just become part of the world the agent consults (ADR-0004). For Consequences `/wrap-session` proposes, this is the session date. For ingest-era Consequences, null unless the source doc explicitly provides a date — the agent does not stand in the ingest date for past events.

Consequences have no `status` (intentional; they exist as world facts).

### Defaults at creation

- `/wrap-session` Pass 5 CREATE: `created: <session date>`.
- `/ingest` Phase 3 CREATE: `created: ~` (unless source supplies a real date).

## Beat

File: `beats/<slug>.md`.

```yaml
---
status: pending                      # required: pending | delivered | dropped
created: 2026-05-29                  # YYYY-MM-DD of when the GM (or the agent on behalf of the GM) authored the Beat; ~ for ingest-era
delivered: ~                         # YYYY-MM-DD; null until status transitions to delivered
kind: ~                              # optional open-enum string; starter values news | handout | character-moment | set-piece | clue | escalation | puzzle
linked_pcs: []                       # optional list of PC slugs
linked_npcs: []                      # optional list of NPC slugs
linked_adventures: []                # optional list of Adventure slugs
linked_locations: []                 # optional list of Location slugs
linked_secrets: []                   # optional list of Secret slugs
---
```

### Field semantics

- **`status`** — required. `pending` (waiting for an opening to land), `delivered` (the scene played out), `dropped` (the GM is abandoning it; NPC died, location gone, no longer wanted).
- **`created`** — YYYY-MM-DD. For Beats `/wrap-session` proposes, the session date when the GM scratched it down. For ingest-era Beats, null unless the source supplies a date.
- **`delivered`** — YYYY-MM-DD of the session that landed the Beat. Null until status transitions to `delivered`. On `dropped`, leave `delivered:` null — the lifecycle terminates without a delivery date.
- **`kind`** — optional, open-enum string. Classifies the Beat for kind-specific surfacing in `/prep-session` (see ADR-0014 for the Clue/Escalation cases). Starter values: `news | handout | character-moment | set-piece | clue | escalation | puzzle`. The enum is intentionally **open** — any string is accepted at schema-validation time, and new kinds may be added as dogfooding reveals distinct prep-surfacing needs without a schema change. Absent or `~` means "unclassified"; unclassified Beats surface normally.
- **`linked_secrets`** — optional list of Secret slugs. Populated on Beats whose intent (or incidental content) reveals one or more Secrets — see ADR-0014. A Beat with `kind: clue` conventionally has `linked_secrets:` populated pointing to the Secret it reveals; the agent queries Clues per Secret to track revelation progress. A Beat with `linked_secrets:` populated but `kind:` other than `clue` (or unset) is a Beat that incidentally touches a Secret. Values are Secret slugs, slugified per the same rule as `dedup-matching.md`.
- **`linked_*`** — optional lists of slugs. These feed `/prep-session`'s tiered surfacing (ADR-0009 surfacing-at-scale). Empty `[]` is honest; missing keys are a schema violation. **Populate at extraction time when the source clearly supports it** — the `/ingest` SKILL.md has detailed proximity heuristics (Step 3, **Beat shape** subsection) for which links the source justifies. Empty is better than wrong.

  - `linked_pcs` — PC canonical names the Beat is for or about. Explicit attribution required ("for Darius:", "Darius's hook:"); generic "the party" does not justify a link.
  - `linked_npcs` — NPC canonical names the Beat involves as actor or subject. A passing name-drop without role context is not enough.
  - `linked_adventures` — Adventure slugs this Beat belongs to. For ingest, if the source doc is itself adventure-shaped, every Beat from it links to that Adventure automatically (structural link). For world-info-shaped sources, require explicit naming in the Beat's own paragraph or enclosing heading.
  - `linked_locations` — Location slugs the Beat is set at or near. The "near" radius is the Beat's own paragraph / bullet or the enclosing heading.

  All `linked_*` values are slugs using the same normalization rule as `dedup-matching.md`.

### Defaults at creation

- `/wrap-session` Pass 7 CREATE: `status: pending`, `created: <session date>`, `delivered: ~`, all `linked_*: []` unless the scratchpad scoped them. `kind:` and `linked_secrets:` are optional — omitted unless the scratchpad classifies the Beat or names a Secret it reveals.
- `/ingest` Phase 3 CREATE: `status: pending`, `created: ~`, `delivered: ~`, `linked_*` populated per the Beat-shape proximity rules in `skills/ingest/SKILL.md` Step 3. `kind:` and `linked_secrets:` are populated when the source doc clearly classifies the Beat (e.g., the source labels it a clue, handout, or set-piece) or names the Secret(s) it reveals; otherwise omitted.

## Secret

File: `secrets/<slug>.md`.

```yaml
---
status: hidden                       # required: hidden | partially-revealed | revealed
belongs_to:                          # required: non-empty list of non-ephemeral container paths
  - npcs/maren.md
  - adventures/the-prism/
revealed_by: []                      # list of Beat slugs that reveal (part of) this Secret
---
```

### Field semantics

- **`status`** — required. The Secret's revelation lifecycle: `hidden` (no Clue Beats have landed yet), `partially-revealed` (at least one Clue Beat in `revealed_by` has flipped to `delivered`; the party has *some* of the picture), `revealed` (the GM has judged the party knows the Secret). Transitions:
  - `hidden → partially-revealed` — automatic on `/wrap-session` when the first Beat listed in `revealed_by` flips to `status: delivered`.
  - `partially-revealed → revealed` — GM judgement, surfaced as a `/wrap-session` prompt when relevant Clues land.
  - Backward transitions are not supported by the agent; the GM hand-edits the file if a retcon is required.
- **`belongs_to`** — required, non-empty list of paths to **non-ephemeral containers**. The canonical set is: `adventures/<slug>/`, `npcs/<slug>.md`, `pcs/<slug>.md`, `locations/<slug>.md`, `factions/<slug>.md`, `items/<slug>.md`. Ephemeral container paths (`threads/`, `beats/`, `consequences/`, `sessions/`, `.ttrpg-staging/`) are rejected — the agent refuses to write a Secret whose `belongs_to:` is empty or contains only ephemeral paths (ADR-0014). The set is unordered: no "primary" container. Each path here must round-trip with a `## Secrets` wiki-link back to the Secret file in that container's body (the agent maintains this symmetry on every Secret write; orphan / missing-back-reference cases are lint findings).
- **`revealed_by`** — list of Beat slugs (the same slugs that appear as `beats/<slug>.md` filenames). Empty list at creation time is the honest default; the list grows as Clue Beats are authored pointing at this Secret. Slugs follow the same normalization rule as the other slug fields.

### Defaults at creation

- `/wrap-session` Pass (Secret extraction) CREATE: `status: hidden`, `belongs_to` populated by GM during approval (the extraction proposes containers; the GM confirms), `revealed_by: []`.
- `/ingest` Phase 3 CREATE: `status: hidden`, `belongs_to: [<ingested-adventure>/]` when the source doc is an Adventure-shaped module with a "Secrets and Lies" / "Adventure Background" section, otherwise GM resolves the container set at the per-doc review screen; `revealed_by: []`.

## Validation rules

These hold across every schema:

- **No empty-string nulls.** `key: ""` is a bug; use `key: ~`.
- **No invented dates.** If the source doesn't supply, the value is `~`.
- **Enum violations stop.** A `status:` outside its enum is an error — surface to the GM rather than silently coercing.
- **Slug fields are slugs.** Reject "human readable name" in a `linked_*` list; slugify on extraction.
- **One file per object.** A schema applies to exactly one file; never serialize multiple objects per file.

## Reading the schemas

When updating a single field (e.g., `/wrap-session` transitioning an Adventure's `status:`), preserve every other frontmatter field, every existing body byte, and the YAML shape Phase 3 / Phase 4 wrote. If frontmatter is malformed for any reason, surface the path to the GM and skip the write — don't try to repair it. The schema's job is to be regular; the GM owns repair when irregular.
