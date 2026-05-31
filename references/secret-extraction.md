# Secret extraction heuristic

When does a hint in source content (a session's `notes.md` for `/wrap-session`, a GM-authored source doc for `/ingest`) warrant proposing a new Secret, and what does the proposed file look like? This is the shared spec used by `/wrap-session` (Secret extraction pass) and `/ingest` (Phase 3 extraction over module-shaped or world-shaped source docs). The orchestration around extraction (cross-doc learning in `/ingest`, session-context dedup in `/wrap-session`) stays in each SKILL.md; this reference is just the heuristic and the default file shape.

The corresponding ADR is [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md) (Secret as the fourth lifecycle object). The Secret frontmatter schema lives in [`references/frontmatter-schemas.md`](./frontmatter-schemas.md). The dedup rule (slug normalization, `secrets/`-only scan, near-match prompt) lives in [`references/dedup-matching.md`](./dedup-matching.md). The bidirectional `## Secrets` link writes live in [`references/bidi-link-maintenance.md`](./bidi-link-maintenance.md). The store enumeration / query operations live in [`references/secret-store.md`](./secret-store.md).

## What counts as a Secret

A fragment of prose becomes a candidate Secret when:

- It states a **fact about the world** (not a future intention, not a past completed event the party caused) that the party may not yet know in full.
- The fact has a **non-ephemeral home** — at least one Adventure, NPC, PC, Location, Faction, or Item the fact attaches to. If the only plausible "container" is a Thread, a Beat, a Consequence, or the session itself, it is **not** a Secret per ADR-0014.
- The fact is **revelation-shaped**: there is something to learn that would change the party's understanding when they learn it. Color details that simply enrich a scene (a tavern's smell, an NPC's accent) are not Secrets even if the party doesn't notice them.
- The GM (or the source doc) is treating it as latent — phrased as a backstory note, a "what's really going on", a "secretly", a "the GM knows that…", a "behind the scenes". The shape of the prose is the strongest signal.

The defining test versus the other lifecycle objects:

| If the fragment is… | …it's a |
|---|---|
| A future obligation, question, or foreshadowed danger the party is aware of and may act on | **Thread** |
| A past fact resulting from the party's actions, now part of the world | **Consequence** |
| GM intent to deliver a scene / news / handout / character moment in play | **Beat** (and possibly `kind: clue` with `linked_secrets:` pointing at the Secret it reveals) |
| A latent fact about the world the party may not know, attached to ≥1 non-ephemeral container | **Secret** |

A single fragment may legitimately produce both a Beat and a Secret (the Beat is the planned delivery of a Clue; the Secret is the underlying fact). When that's the right read, propose both and explain the split to the GM at the review step — the same posture as the Thread-vs-Consequence split documented under `/wrap-session` Pass 5.

## Prose shapes that suggest a Secret

In a session's `notes.md`:

- *"The party doesn't know yet that Maren is the cult's contact."*
- *"GM note: the vault key is hidden in the temple's apse."*
- *"Behind the scenes, Jhera survived the purge — she's underground in the Silent Court."*
- *"Set up: the Prism core is cursed. Reveal slowly."*
- *"Save for later — the duke has a half-dragon son."*

In a GM-authored source doc (module-shaped):

- A `## Secrets and Lies` / `## Adventure Background` / `## What's Really Going On` section. Every distinct fact in such a section is a candidate Secret.
- A villain motivation paragraph that says, in effect, "what the antagonist actually wants" as distinct from "what the antagonist appears to want."
- An NPC entry that includes a "Secret:" or "Hidden:" or "Behind the scenes:" labelled fact.
- A location description that includes a "Hidden feature:" or "The party can discover that…" fragment.

When borderline, prefer to **propose** the Secret and let the GM reject or rename it at review than to drop it silently. False positives are cheap (one delete in staging or one "no, that's just narrative color" answer in ambiguity clarification); false negatives are invisible.

## Prose shapes that are NOT Secrets

Reject these even if they look plausible at a glance:

- **Already a Consequence.** "The bridge is destroyed." The party caused it; the party knows; it's a past fact, not a latent one.
- **Already a Thread.** "The party promised the captain they'd look into the missing caravan." Future-facing, party-aware, party-driven — Thread.
- **Just a Beat.** "Land the warfront news next session." That's GM intent to deliver, not a latent fact the world contains. (If the news *itself* is a latent fact — e.g., "the duke is dead and the regent is hiding it" — propose the Beat AND the underlying Secret.)
- **Color without revelation shape.** A tavern's smell, a banner's color, an NPC's accent. Adds flavor; nothing changes when the party "discovers" it.
- **Player-secret rather than world-secret.** "Darius's player hasn't told the rest of the table that his PC is the duke's bastard." That's a PC secret the GM is tracking out-of-character; it doesn't live in the campaign world model and isn't a Secret in this sense. (If the GM wants to track it, that's their call — but `/wrap-session` and `/ingest` don't propose it.)

## Container set (`belongs_to`)

Per ADR-0014 and the Secret schema in `references/frontmatter-schemas.md`, every Secret's `belongs_to:` is a non-empty unordered list of paths to non-ephemeral containers. The canonical set:

- `adventures/<slug>/` — Adventure container (directory form, trailing slash)
- `npcs/<slug>.md` — NPC
- `pcs/<slug>.md` — PC
- `locations/<slug>.md` — Location
- `factions/<slug>.md` — Faction
- `items/<slug>.md` — Item

Ephemeral paths (`threads/`, `beats/`, `consequences/`, `sessions/`, `.ttrpg-staging/`) are rejected — the validation algorithm in `references/secret-store.md` (`validate_belongs_to`) refuses to write a Secret whose `belongs_to:` is empty or contains only ephemeral paths.

### Drafting `belongs_to` at extraction time

The extracting skill drafts a `belongs_to:` list as part of the proposal so the GM has something concrete to confirm or correct, not a blank field to fill from scratch. The draft uses these signals in order:

1. **Named entities in the same sentence / paragraph.** "Maren is the cult's contact" mentions Maren → draft `npcs/maren.md`. "The vault key is hidden in the old temple's apse" mentions the temple → draft `locations/old-temple.md`.
2. **Enclosing structural context.** In a source doc, the heading the fragment lives under names the container — a fact in the `## Curse of the Prism Core` section of an Adventure doc drafts `adventures/curse-of-the-prism-core/`. In session notes, the Adventure the party is running this session (if exactly one is in clear focus) is a reasonable draft for facts that don't name a specific NPC / location.
3. **Backreferences in the prose.** "Behind the scenes for the Prism arc, Jhera survived" names both the Adventure (`adventures/the-prism/`) and Jhera (`npcs/jhera.md`); multi-container draft.
4. **Don't invent containers.** If the draft would require creating a Reference-note file (or an Adventure directory) that doesn't exist yet, surface the dependency to the GM at ambiguity clarification — don't silently scaffold a new container from a Secret write. The GM names the entity (or confirms the slug) first; then the Secret write proceeds.

When in doubt between one container and several, draft **all** the plausible ones — the GM trims at approval. Over-attribution is a one-keystroke fix; under-attribution surfaces only when a later query misses the Secret it should have found.

### Validation

Run the candidate `belongs_to:` list through the validator from `references/secret-store.md` (`validate_belongs_to`) before staging the Secret file. The validator rejects:

- empty lists (no containers proposed),
- all-ephemeral lists (only `threads/`, `beats/`, `consequences/`, `sessions/`, `.ttrpg-staging/` entries),
- unknown folder roots (typos like `npc/maren.md` — missing the `s`).

If validation fails, surface the failure to the GM at ambiguity clarification rather than writing an invalid Secret.

## Filename — slug rule

Filenames are slugs of the canonical Secret name, normalized by the rule in `references/dedup-matching.md`. The Secret's canonical name is the H1 in the file body — usually a short factual statement: *"Maren is the spy"*, *"The Prism core is cursed"*, *"Vault key in the temple"*, *"Jhera survived the purge"*.

Files live at `secrets/<slug>.md`. One file per Secret.

## Default body — fact-shaped

The body opens with the H1 (the canonical name) and is one or two sentences stating the fact for the GM. The Secret file is for the GM, not for the players — write the fact plainly. Use `[[wiki links]]` to the containers in `belongs_to:` and to any other Reference notes the fact touches, so backlinks resolve.

Example:

```markdown
---
status: hidden
belongs_to:
  - npcs/maren.md
  - adventures/the-prism/
revealed_by: []
---

# Maren is the spy

[[Maren]] has been feeding caravan-route intelligence to the cult for two seasons. She's the inside contact the party has been trying to identify since the [[the-prism|Prism arc]] opened. Her cover is impeccable — she sells the party rumors that almost implicate Joran, the obvious red herring.
```

Length scales with how much the source supplies. A one-sentence Secret is fine; do not pad. Do not invent backstory the source doesn't give.

## Dedup at extraction time

**Before staging any new Secret, apply the dedup rule from `references/dedup-matching.md`** scoped to the `secrets/` folder (the rule is `secrets/`-only per ADR-0014). The query operation lives in `references/secret-store.md` (`find_dedup_candidates`); it returns Secrets whose slug or first-heading title normalizes to the same form as the candidate name.

The three buckets:

- **CREATE — no match.** Proceed with a new Secret file at the candidate's slug.
- **Confident UPDATE — same slug, same kind, no contradicting context.** The candidate is the same Secret as an existing one. Two sub-cases:
  - Same `belongs_to:` set. UPDATE the existing Secret's body (append the new fact or merge the prose) — never lose GM-authored prose.
  - **New container in `belongs_to:`.** The candidate extends an existing Secret's ownership. Propose adding the new container to `belongs_to:` rather than creating a duplicate Secret file. The bidi-link maintenance pass then writes the `## Secrets` section into the new container.
- **ASK — near-match or ambiguous.** Surface to the GM with the prompt shape from `references/dedup-matching.md`: *"You may already have this Secret at `secrets/<existing-slug>` — merge, separate, or rename?"* The merge response converts to UPDATE; separate converts to CREATE at a disambiguated slug the GM names; rename converts to UPDATE with the existing file renamed.

The dedup check is what makes `/wrap-session` re-runs and `/ingest` cross-doc passes idempotent against the same Secret material. Skipping it produces duplicate `secrets/` files that drift on subsequent writes.

## What this heuristic does not handle

- **Per-skill orchestration.** When the dedup ASK lands (Step 3 ambiguity clarification in `/wrap-session`, Step 4a inline resolution in `/ingest`), how the response feeds back into the staging set, how cross-doc lessons carry forward in `/ingest` — those stay in each SKILL.md.
- **Secret status transitions.** `hidden → partially-revealed` and the `partially-revealed → revealed` prompt are `/wrap-session` Beat-delivery side effects, not extraction-time decisions. See `skills/wrap-session/SKILL.md`.
- **Bidirectional link writes.** Once the Secret is approved, writing the `## Secrets` section into every container in `belongs_to:` is the bidi-link maintenance algorithm in `references/bidi-link-maintenance.md`. The extraction heuristic stops at the file shape; the link maintenance is its own concern.
- **Cross-Secret queries.** "Which Secrets does this NPC own?" / "Which Secrets are partially revealed?" — those queries live in `references/secret-store.md` and are consumed by `/prep-session` (the Secret Push question) and `/wrap-session` (the Clue-delivery status flip).
