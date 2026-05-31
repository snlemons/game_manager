# Frontmatter schemas

Canonical YAML for the four lifecycle objects: Adventure, Thread, Consequence, Beat. CONTEXT.md is the concept-level glossary; this reference is the spec-level (exact fields, types, value formats, defaults). All three skills (`/ingest`, `/prep-session`, `/wrap-session`) write these schemas; this is the single source of truth.

The corresponding ADRs are [ADR-0007](../docs/adr/0007-temporal-model-and-campaign-overview.md) (Adventure), [ADR-0004](../docs/adr/0004-threads-consequences-via-post-session-extraction.md) (Threads and Consequences), and [ADR-0009](../docs/adr/0009-beats-as-gm-authored-lifecycle-object.md) (Beats).

## Conventions

- **Dates** are real-world `YYYY-MM-DD` strings unless otherwise noted. Never invent dates — ADR-0007: "the agent never asks the GM to invent dates it doesn't have." Null is written as `~` (YAML null literal). Empty strings are never used in place of null.
- **Slugs** (used in `linked_*` lists and as filenames) are produced by the normalization rule in `references/dedup-matching.md`: lowercase, ASCII-fold accents, strip leading "the ", collapse whitespace and punctuation to single hyphens, trim leading/trailing hyphens.
- **Status enums** are lowercase string literals from the enumerated set listed per schema below. Values outside the enum are a bug.
- **Optional list fields** default to `[]` (empty list with the YAML key present), not omission of the key. Downstream skills read these fields without conditional logic; an absent key forces a fallback that masks the "field considered, left empty" signal.
- **Filename** is a slug of the canonical name + `.md`. One file per object. Files live in the folder named for their kind: `adventures/<slug>/adventure.md`, `threads/<slug>.md`, `consequences/<slug>.md`, `beats/<slug>.md`.

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
kind: ~                              # optional open-enum string; starter values news | handout | character-moment | set-piece | clue | escalation
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
- **`kind`** — optional, open-enum string. Classifies the Beat for kind-specific surfacing in `/prep-session` (see ADR-0014 for the Clue/Escalation cases). Starter values: `news | handout | character-moment | set-piece | clue | escalation`. The enum is intentionally **open** — any string is accepted at schema-validation time, and new kinds may be added as dogfooding reveals distinct prep-surfacing needs without a schema change. Absent or `~` means "unclassified"; unclassified Beats surface normally.
- **`linked_secrets`** — optional list of Secret slugs. Populated on Beats whose intent (or incidental content) reveals one or more Secrets — see ADR-0014. A Beat with `kind: clue` conventionally has `linked_secrets:` populated pointing to the Secret it reveals; the agent queries Clues per Secret to track revelation progress. A Beat with `linked_secrets:` populated but `kind:` other than `clue` (or unset) is a Beat that incidentally touches a Secret. Values are Secret slugs, slugified per the same rule as `references/dedup-matching.md`.
- **`linked_*`** — optional lists of slugs. These feed `/prep-session`'s tiered surfacing (ADR-0009 surfacing-at-scale). Empty `[]` is honest; missing keys are a schema violation. **Populate at extraction time when the source clearly supports it** — the `/ingest` SKILL.md has detailed proximity heuristics (Step 3, **Beat shape** subsection) for which links the source justifies. Empty is better than wrong.

  - `linked_pcs` — PC canonical names the Beat is for or about. Explicit attribution required ("for Darius:", "Darius's hook:"); generic "the party" does not justify a link.
  - `linked_npcs` — NPC canonical names the Beat involves as actor or subject. A passing name-drop without role context is not enough.
  - `linked_adventures` — Adventure slugs this Beat belongs to. For ingest, if the source doc is itself adventure-shaped, every Beat from it links to that Adventure automatically (structural link). For world-info-shaped sources, require explicit naming in the Beat's own paragraph or enclosing heading.
  - `linked_locations` — Location slugs the Beat is set at or near. The "near" radius is the Beat's own paragraph / bullet or the enclosing heading.

  All `linked_*` values are slugs using the same normalization rule as `references/dedup-matching.md`.

### Defaults at creation

- `/wrap-session` Pass 7 CREATE: `status: pending`, `created: <session date>`, `delivered: ~`, all `linked_*: []` unless the scratchpad scoped them. `kind:` and `linked_secrets:` are optional — omitted unless the scratchpad classifies the Beat or names a Secret it reveals.
- `/ingest` Phase 3 CREATE: `status: pending`, `created: ~`, `delivered: ~`, `linked_*` populated per the Beat-shape proximity rules in `skills/ingest/SKILL.md` Step 3. `kind:` and `linked_secrets:` are populated when the source doc clearly classifies the Beat (e.g., the source labels it a clue, handout, or set-piece) or names the Secret(s) it reveals; otherwise omitted.

## Validation rules

These hold across every schema:

- **No empty-string nulls.** `key: ""` is a bug; use `key: ~`.
- **No invented dates.** If the source doesn't supply, the value is `~`.
- **Enum violations stop.** A `status:` outside its enum is an error — surface to the GM rather than silently coercing.
- **Slug fields are slugs.** Reject "human readable name" in a `linked_*` list; slugify on extraction.
- **One file per object.** A schema applies to exactly one file; never serialize multiple objects per file.

## Reading the schemas

When updating a single field (e.g., `/wrap-session` transitioning an Adventure's `status:`), preserve every other frontmatter field, every existing body byte, and the YAML shape Phase 3 / Phase 4 wrote. If frontmatter is malformed for any reason, surface the path to the GM and skip the write — don't try to repair it. The schema's job is to be regular; the GM owns repair when irregular.
