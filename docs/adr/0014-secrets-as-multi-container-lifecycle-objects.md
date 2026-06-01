# Secrets are a multi-container lifecycle object

Secrets are facts about the world the party might not know yet but could learn. They are a **fourth lifecycle object** alongside Threads, Consequences, and Beats — distinguished by **epistemic status** (latent — possibly unknown to the party) and a **multi-container ownership constraint** that has no analog in the other lifecycle objects.

> **Live spec:** the canonical Secret frontmatter schema (fields, types, defaults) lives in `references/frontmatter-schemas.md` alongside Adventure / Thread / Consequence / Beat. This ADR captures the design reasoning; the schema part defers to the reference.

Files live in `secrets/<slug>.md`, one per Secret, with frontmatter for `status`, `belongs_to`, and `revealed_by`. The Secret's body is the fact itself, written for the GM.

## Why distinct from the other lifecycle objects

|  | Author | Direction | Epistemic | Container |
|---|---|---|---|---|
| **Thread** | Party-driven | Future-facing | Known to party | Self-contained file |
| **Consequence** | Past-derived | Past-facing | Known (it happened) | Self-contained file |
| **Beat** | GM-authored | Future-facing | Unknown to party until delivered | Self-contained file |
| **Secret** | GM-authored | Latent | Possibly unknown to party; world contains it | **Must belong to ≥1 non-ephemeral container** |

A Beat is *intent to deliver*. A Secret is *fact to be discovered*. The same Secret may be revealed by many Beats (Clues); one Beat may reveal at most one Secret. A Secret may become a Consequence when fully revealed and acted upon — but it isn't a Consequence while still hidden, because Consequences are past-facing facts that already happened.

## The multi-container ownership constraint

Frontmatter `belongs_to` is an **unordered set of paths to non-ephemeral containers**. At least one entry required; agent refuses to write a Secret with empty or all-ephemeral `belongs_to`.

**Non-ephemeral containers** (per CONTEXT.md): Adventure, NPC, PC, Location, Faction, Item. Excluded as ephemeral: Thread, Beat, Session/Brief/In-play notes/Log. Consequence is persistent but excluded because of the epistemic-status difference above.

The set is unordered — no "primary" container. A Secret about Maren the NPC and the Prism Adventure equally belongs to both; forcing one as primary would lose the symmetry of the graph.

## Bidirectional linking

Every container listed in `belongs_to` carries a `## Secrets` section in its file body wiki-linking back to the Secret file:

```markdown
# npcs/maren.md
...
## Secrets
- [[secrets/maren-is-the-spy]] — informant for the cult
```

The Secret file is the source of truth for content; the container's `## Secrets` section is a derived view the agent maintains on every Secret write. Manual GM edits that break the symmetry get flagged at the next `/prep-session` or `/wrap-session` run as a lint case.

The writer authors back-reference bullets in canonical slug-path form (`[[secrets/<slug>]]`) — the disambiguating form, load-bearing when entity titles collide across kinds (e.g., an Adventure and an Item both titled "Lore of Lurue" — the slug-path prefix `adventures/` vs `items/` picks the target unambiguously). The linker accepts either canonical-slug-path or canonical-title (display-name) form on reads — see [`~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`](../../references/bidi-link-maintenance.md) — for backward compatibility with v0.1/v0.2-era campaigns whose `/ingest` runs preserved source-doc display-name wiki links. Mixed-form campaigns are valid indefinitely; spec convergence happens at writer-touched containers over time, not via bulk migration.

This symmetry makes the "secrets relevant to this NPC the party is looking for" query a cheap backlink read, not a full-campaign scan.

## Status transitions

Three-state status (`hidden | partially-revealed | revealed`):

| From → To | Trigger |
|---|---|
| `hidden` → `partially-revealed` | Automatic when first Beat in `revealed_by` flips to `status: delivered` via `/wrap-session`. |
| `partially-revealed` → `revealed` | GM judgement, surfaced as a `/wrap-session` prompt when relevant Clues land. |
| Backward transitions | Not supported. Manual edit if needed. |

The three-state form (rather than binary `hidden | revealed`) carries the GM-meaningful distinction between "Clues have started landing but the full picture isn't out yet" and "party has it." Prep-session uses `partially-revealed` as a strong signal for the Secret Push dialogue question — these are the Secrets actively in motion.

## Clues are Beats with `kind: clue`

A Clue is a Beat whose intent is to reveal (part of) a Secret. Structurally: a Beat with `kind: clue` in frontmatter (see [ADR-0009](./0009-beats-as-gm-authored-lifecycle-object.md) for the kind discriminator added alongside this work) and `linked_secrets:` populated pointing to the Secret it reveals. The agent treats Clues identically to other Beats for surfacing, status, and lifecycle; the Clue label captures GM authorial intent and unlocks per-Secret revelation queries.

A Beat with `linked_secrets:` populated but `kind:` other than `clue` (or unset) is a Beat that *incidentally* touches a Secret — e.g., a scene that happens to drop a fact. Both contribute to `revealed_by` on the linked Secret; only the `kind: clue` ones are *primarily* about revelation.

## Dedup

Dedup is a `secrets/`-only scan — exactly one of the wins of file-per-Secret architecture over the rejected "section in container" alternative.

- **Write-time check.** When `/wrap-session` or `/ingest` proposes a new Secret, the agent normalizes the slug (per `references/dedup-normalization.md`) and checks against existing Secret slugs. Near-match prompts the GM: *"You may already have this Secret at `secrets/<existing-slug>` — merge, separate, or rename?"*
- **Canonical home; cross-reference elsewhere.** Containers other than those in `belongs_to` can wiki-link to the Secret freely without duplicating its content — the same `[[secrets/<slug>]]` linkage that the bidirectional `## Secrets` sections use.

This is a natural fit for the [#24](https://github.com/snlemons/game_manager/issues/24) D-style deterministic helper case: file traversal + slug normalization, no LLM judgment.

## Considered alternatives

- **Section in the Adventure file (no separate file per Secret).** Rejected once multi-container ownership emerged as a requirement. A Secret touching both Maren (NPC) and the Prism (Adventure) would force a single-canonical-home choice plus cross-reference, losing the graph symmetry.
- **GM-only section inside the relevant Reference note (no new object type).** Rejected because Secrets crossing arcs or characters have no single canonical Reference note, and the architecture loses cross-arc dedup.
- **Subtype of Beat (`kind: secret` on Beat).** Rejected because Beats are *deliverables* and Secrets are *facts*. The lifecycle is wrong (Beats `pending → delivered`; Secrets `hidden → revealed`). Conflating them muddies both.
- **Brief-section-only, no persistence.** Rejected — violates the Alexandrian "recycle and reincorporate" principle. A Secret seeded in session 4 that doesn't land until session 9 has no home, and the GM re-invents instead of reusing.
- **Ordered `belongs_to` with a primary container.** Rejected as premature structure. If a primary becomes useful later (e.g., for which container's main file links the Secret most visibly), promote to ordered then.

## Consequences

- `/wrap-session` extracts proposed new Secrets from In-play notes when they hint at hidden facts; GM places them in `belongs_to:` containers during approval.
- `/wrap-session` auto-updates Secret status `hidden → partially-revealed` when Clue Beats flip to `delivered`, and prompts for `partially-revealed → revealed` transitions when relevant Clues land.
- `/wrap-session` and `/ingest` maintain bidirectional Secret↔container links on every Secret write — write to N+1 files (Secret + each container in `belongs_to`).
- `/ingest` extracts Secrets from module "Adventure Background" / "Secrets and Lies" sections into `secrets/` with `belongs_to:` pointing at the ingested Adventure.
- `/prep-session` surfaces relevant Secrets via the **Secret Push** dialogue question (one of seven categories — see [ADR-0015](./0015-conversational-refinement-loop-in-prep-session.md)). Secrets themselves do not appear as a Brief section; Clue Beats (which are Beats) appear in the existing "Beats to weave in" section.
- Skills walk `secrets/` directly to enumerate Secrets and to perform dedup / multi-container backlink lookups. Reference Python in `tests/` mirrors the enumeration and dedup logic for spec-drift detection per the v0.1 convention; a runtime helper is a deferred decision tracked under [#24](https://github.com/snlemons/game_manager/issues/24).
- `references/frontmatter-schemas.md` extends to include the Secret schema.
- `references/dedup-normalization.md` extends to Secrets.
- Bidirectional-link drift is a lint case in `/prep-session` and `/wrap-session` — the agent flags missing `## Secrets` entries or orphaned wiki-links to nonexistent Secrets, asks the GM to reconcile.
