# Dedup name matching

When the agent has a candidate name (a proposed new Reference note, Thread, Consequence, Beat, Secret, or Adventure) and needs to decide whether it collides with an existing file, this is the rule it applies. Used by `/wrap-session` (Step 2 "Dedup" — re-run safety) and `/ingest` (Phase 3 Step 3b — cross-doc dedup).

The rule is pinned by `tests/test_wrap_session_idempotency.py::TestDedupOnRerun`; changes here must keep that suite green.

## Normalization rule

Apply these transformations in order, to both the candidate name and every existing filename/first-heading-title the agent is matching against:

1. **Lowercase** all letters.
2. **Strip the `.md` suffix** if the input ends with one (so candidate names and existing filenames normalize to the same form).
3. **ASCII-fold accents** (`Café` → `cafe`, `Sère` → `sere`).
4. **Strip a leading "the "** (or `the-`, or `the_`) prefix. The match for "the" is case-insensitive and consumes the immediately-following whitespace, hyphen, or underscore.
5. **Collapse runs of non-alphanumeric characters** (whitespace, punctuation, hyphens, underscores, anything) into single hyphens.
6. **Trim leading and trailing hyphens**.

Examples:

| Input | Normalized |
|---|---|
| `Deliver the letter` | `deliver-the-letter` |
| `deliver the letter` | `deliver-the-letter` |
| `Deliver  The  Letter` | `deliver-the-letter` |
| `The Broken Mines` | `broken-mines` |
| `the-broken-mines.md` | `broken-mines` |
| `Captain Marra owes the party a favor` | `captain-marra-owes-the-party-a-favor` |
| `captain-marra-owes-favor` | `captain-marra-owes-favor` |
| `Orin's armor` | `orin-s-armor` |
| `Café du Monde` | `cafe-du-monde` |

Note: "Deliver **the** letter" keeps the internal "the" (only the *leading* "the " is stripped). The trailing apostrophe handling falls out of step 5 — punctuation collapses to a hyphen — so `Orin's` becomes `orin-s`. This is intentional: the same input yields the same output regardless of which file the input originated from, which is the dedup property the rule needs.

## What to match against

For each candidate name:

- **Match against existing filenames** in the target folder (`npcs/`, `locations/`, `threads/`, `consequences/`, `beats/`, `secrets/`, etc.), with the `.md` stripped and the normalization rule applied to both sides.
- **And match against the first-heading title (H1)** inside each existing file, normalized the same way. The first heading is the file's canonical name as the GM sees it; a candidate matching either the slug or the title is a hit.
- **And, for Reference notes, match against each existing file's frontmatter `aliases:` entries**, normalized the same way. Per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md), Reference notes carry an optional `aliases:` list of other names the entity goes by; a candidate that normalizes to any entry in that list is a hit on the same file as a hit on the slug or H1 would be. Missing or empty `aliases:` reads as `[]` (no alias hits; the slug + H1 match still applies).

`first_heading` is the first line of the form `# <text>` after frontmatter (if any). Files without an H1 only get matched by filename. Files without frontmatter, or with frontmatter that has no `aliases:` key, only get matched by filename and H1.

### Worked example — alias match

The campaign has `npcs/maren.md`:

```yaml
---
kind: npc
aliases: [The Shadow, Maren the Dockworker]
---

# Maren

Dock worker by day, cartel fixer at night.
```

A source doc names "The Shadow." The candidate normalizes to `shadow` (leading "the " stripped). The match scan:

| Existing file | Match site | Normalized | Hit? |
|---|---|---|---|
| `npcs/maren.md` | filename slug | `maren` | no |
| `npcs/maren.md` | H1 | `maren` | no |
| `npcs/maren.md` | `aliases[0]` "The Shadow" | `shadow` | **yes** |
| `npcs/maren.md` | `aliases[1]` "Maren the Dockworker" | `maren-the-dockworker` | no |

Hit on alias → confident UPDATE on `npcs/maren.md` (not a CREATE at `npcs/the-shadow.md`). The GM still sees the UPDATE in the per-doc review summary; alias matches are not silent merges. If the surrounding prose contradicts the alias match — "The Shadow, a separate cartel fixer not to be confused with Maren" — the existing dedup rules' ASK route absorbs the case (the surrounding prose contradicts the existing file's identity; see the ASK bullet below).

## Match classification

Each candidate falls into one of three buckets:

### CREATE — no match

No file with the normalized slug or normalized title exists in the target folder. Proceed as a new file at the candidate's slugified filename.

### Confident match — propose UPDATE (or no-op)

A file with the same normalized slug **and** the same kind (target folder) exists, AND nothing in the surrounding context contradicts the existing file's identity. Specifically:

- Same canonical name.
- Same kind (the folder matches).
- No obvious "this is a different person who happens to share a name" signal in the surrounding prose.
- For Threads / Consequences / Beats: recent provenance — the existing file's `created:` (or the session referenced in its body) is recent (within the last few sessions). A new candidate that name-matches an existing **open** Thread created last session is almost certainly the same Thread.
- For Secrets: name normalization is the same rule, scoped to the `secrets/` folder. Per [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md), dedup is a `secrets/`-only scan: when `/wrap-session` or `/ingest` proposes a new Secret, the agent normalizes the candidate slug and matches it against the existing `secrets/<slug>.md` filenames (and their first-heading titles). A confident match proposes an UPDATE on the same Secret file; a near-match surfaces the multi-container reconciliation prompt — *"You may already have this Secret at `secrets/<existing-slug>` — merge, separate, or rename?"* — so the GM resolves whether the new container belongs in `belongs_to` of the existing Secret or whether the candidate is a distinct Secret that happens to share a name.

Propose an UPDATE: append the candidate's content as a new sentence to the existing body, or if the candidate would fully restate what's already there, propose a no-op with a note. Preserve any GM-authored prose — never overwrite.

### ASK — ambiguous match

A file with the same slug or a near-identical name exists, but at least one of these is true:

- The role or disposition implied by the candidate could be a *different* entity (existing `npcs/john.md` is "John the innkeeper of Phandalin" and the candidate is "John, a bandit in the Cragmaw Hideout").
- The match is by similar-but-not-identical name (drafted "Sira" vs existing `npcs/sera.md`; "the Veiled Court" vs `factions/veiled-court.md` only after stripping "the").
- The match crosses kinds (drafted location vs existing NPC of the same name).
- The candidate normalizes to one file's slug or H1 **and** another file's `aliases:` entry (alias collision — two distinct existing canonicals both claim the same alias; the GM picks which canonical the new mention belongs to, or whether the alias relationship is wrong on one of them).

Do **not** silently pick. Surface to the GM as a yes/no question. The agent's job is to ask, not to choose.

- **`/wrap-session`:** route to Step 3 (ambiguity clarification, before the staging review).
- **`/ingest`:** route to Step 4a (resolve inline before staging the per-doc review).

When the GM resolves "yes, same entity," convert to UPDATE. When the GM resolves "no, distinct entity," convert to CREATE at a disambiguated slug the GM names (e.g., `npcs/john-the-bandit.md`).

## Carried-forward dedup decisions (ingest-only)

`/ingest` Phase 3 tracks dedup decisions in its carried-forward lessons set (Step 5b). On subsequent docs:

- A confirmed identity (yes, same entity) is applied as a confident UPDATE without re-asking.
- A confirmed split (no, distinct entity) drops the proposed dedup question and treats the candidate as a CREATE at the GM-named disambiguated slug — confirm the slug at the next per-doc review screen, not silently.

These lessons are scoped to a single ingest run; the next `/ingest` invocation starts with an empty set.

## Adventure name collisions

Adventures don't auto-merge. If a candidate Adventure slug collides with an existing `adventures/<slug>/` directory, **STOP** and surface the collision to the GM. Both `/ingest` and `/wrap-session` defer to the GM for these — there's no confident-update path for Adventures in v0.1.

## What this rule does not handle

- **Cross-kind matches** are flagged as ASK; the agent doesn't promote a Location candidate into an NPC's body or vice versa, even if names normalize identically.
- **Fuzzy phonetic matching** ("Sera" vs "Sira") is not in the rule. The agent should still flag suspiciously similar names as ASK based on the surrounding prose; the rule is the floor, not the ceiling.
- **Atlas content** is not in scope for v0.1 (ADR-0006). Single-repo only; campaign-local everywhere.

## Why this rule, not a more aggressive one

The rule trades a little precision for a lot of predictability. The agent applies it deterministically; the GM can predict whether a candidate will collide just by slugifying in their head. ASK-on-doubt absorbs the edge cases the rule deliberately can't catch. The cost is occasional false-positive dedup (one extra UPDATE the GM could correct at review) and occasional false-negative dedup (one ASK question per ambiguous match) — both cheap. Silent wrong dedup is the failure mode the rule avoids; that's the one the GM wouldn't easily catch.
