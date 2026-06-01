# NPC aliases via frontmatter `aliases:` + piped wiki links

A single NPC may have multiple names — a real identity and a pseudonym (Maren / "The Shadow"), a title and a given name (Captain Marra / Annika Marra), an order name and a given name (Brother Olwen / Olwen of the Verdant Choir), or a pre-reveal mask whose true identity is a Secret the party hasn't uncovered yet. Source docs and in-play notes refer to such an NPC by whichever name is in context, and `/ingest` and `/wrap-session` need a consistent way to (a) decide which file the NPC lives in, (b) route alias mentions to that file at dedup time, and (c) render alias mentions in prose without losing in-context naming. v0.2 dogfooding surfaced this gap concretely (issue [#59](https://github.com/snlemons/game_manager/issues/59)): an agent produced two Reference notes for one NPC because no spec told it what to do.

This ADR pins the policy.

## Principle: one file per thing in the world

[ADR-0003](./0003-per-file-reference-notes.md) — "one file per Reference note" — is one file per **thing in the world**, not one file per name the thing goes by. An NPC with two names is still one NPC. Splitting into two files violates ADR-0003 in load-bearing ways:

- **Frontmatter duplicates.** A Secret with `belongs_to: [npcs/maren.md]` would need a sibling entry for `npcs/the-shadow.md` if both files claim the NPC. The two-file shape forces the choice arbitrarily.
- **Queries break.** *"Which Secrets does Maren own?"* via [`~/.claude/skills/ttrpg-gm/references/secret-store.md`](../../references/secret-store.md)'s `find_by_container` returns the wrong count if half live under the alias slug.
- **`linked_*` lists get arbitrary.** Every Beat / Brief / Log mentioning the NPC has to pick one slug; downstream queries can't reconcile two-file split identities.
- **Bidi back-refs bloat.** The container's `## Secrets` section (per [`~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`](../../references/bidi-link-maintenance.md)) is the canonical back-reference site; duplicating it across two NPC files for one entity is per-Secret double-counting.

The decision: **one Reference note per real-world NPC**, period. The slug is the canonical name. Other names the NPC goes by are recorded in frontmatter `aliases:` and rendered in prose via piped wiki links.

## Canonical-choice heuristic

When an NPC has multiple names, the canonical (= the file's slug, the H1 the GM sees, the value `linked_npcs:` lists) is chosen at extraction-time review by the GM. The agent's default proposal follows this heuristic:

1. **Real identity wins.** If one name is the NPC's true identity and the other is a pseudonym, mask, alias, title, or honorific, propose the real identity as canonical. The pseudonym goes in `aliases:`.
2. **Pre-reveal exception.** When the real identity is itself a Secret the party hasn't uncovered, the canonical may transiently be the **pseudonym** — the party-known name. The relationship is recorded as a Secret per [ADR-0014](./0014-secrets-as-multi-container-lifecycle-objects.md): the Secret's body states "<pseudonym> is actually <real identity>," and `belongs_to:` includes the NPC's (currently pseudonym-slugged) file. When the Secret is revealed in play, the GM may choose to rename the file to the real identity (`git mv` + update `aliases:` to include the now-public pseudonym + update `linked_npcs:` references); the agent surfaces the rename as an option but does not perform it silently.
3. **First-encountered wins as a tiebreaker.** When neither is clearly "true identity" (e.g., a title + given name openly used in parallel — Captain Marra ≡ Annika Marra), propose the name the party first encountered as canonical. The GM may override at review.

The v1 cut is **the GM picks canonical at extraction-time review.** The heuristic is the agent's first proposal; the review surfaces it for confirmation, and the GM's answer wins. This keeps the canonical-choice judgment with the human while letting the agent make a defensible default.

## Two-layer composition

The alias policy has two cooperating surfaces:

### Layer 1 — frontmatter `aliases:` is the dedup surface

Canonical Reference notes carry an `aliases:` field in frontmatter:

```yaml
---
kind: npc
aliases: [The Shadow, Maren the Dockworker]
---
```

[`~/.claude/skills/ttrpg-gm/references/dedup-matching.md`](../../references/dedup-matching.md) extends to scan `aliases:` alongside titles and filenames. A source-doc mention of "The Shadow" candidate against `npcs/maren.md` — whose `aliases:` lists "The Shadow" — normalizes to a hit on the alias and routes to a confident UPDATE (not a CREATE of `npcs/the-shadow.md`).

Confident alias matches still surface in the per-doc review summary as UPDATE entries, not silent merges. The GM can catch a wrong match (two distinct NPCs both nicknamed "Hawk" but only one already has "Hawk" in aliases) at review. Ambiguous alias matches (the alias collides with both an existing canonical name and another canonical's alias) route to ASK at the per-doc review per the existing dedup-matching prose.

The `aliases:` schema (optional, list-of-strings, default empty, slug-normalized at match time) is documented in [`~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md`](../../references/frontmatter-schemas.md).

### Layer 2 — piped wiki links are the rendering surface

In-prose mentions of the NPC by alias use piped wiki links so the displayed label matches the in-context name while the link resolves to the canonical file:

```markdown
The cartel's fixer [[npcs/maren|The Shadow]] cleared the route in under an hour.
```

The rendered prose reads naturally ("The Shadow cleared the route"); the link still routes a reader (the GM, the agent on a subsequent read) to `npcs/maren.md`. The piped-link convention is purely about prose readability — it doesn't affect dedup, queries, or bidi back-references, which all key off the canonical slug.

### Why both layers

Each layer covers a different operation, and neither subsumes the other:

| Operation | Surface | Why |
|---|---|---|
| New extraction sees a known alias in a source doc | `aliases:` | Dedup runs at extraction time against existing file frontmatter; the alias mention has to route to the canonical file before any prose is written. |
| Agent writes prose mentioning the NPC by alias | piped wiki link | Once the canonical is known, in-context naming is a prose-rendering concern, and piped links are the established Obsidian-style convention. |
| Bidi back-reference write (`## Secrets`) | canonical slug | Per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`, `## Secrets` lives on the canonical container only; the resolver normalizes alias mentions to canonical before writing. |
| `find_by_container` (Secret store) | canonical slug | Per `~/.claude/skills/ttrpg-gm/references/secret-store.md`, callers normalize alias paths to canonical before the exact-string match. |

The two layers reinforce each other but operate independently. Removing `aliases:` from frontmatter would force every dedup pass to read prose for alias detection (LLM-judgment-heavy, no deterministic check); removing piped links would force prose to use the canonical name everywhere, losing the in-context label readers expect.

## Migration

The migration is **additive — no backfill required.**

- Existing Reference notes without `aliases:` continue to work as canonicals with an implicit empty alias list. The schema in `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md` documents the default-empty behavior.
- The dedup-matching extension treats missing `aliases:` as `[]`: no alias hits, falls back to the existing title-and-filename match.
- The piped-link convention has no migration — it's a prose-rendering convention applied when new prose is written. Existing prose using bare `[[npcs/maren]]` (without a piped label) stays valid.
- The v0.2 dogfooding NPC that surfaced this gap (currently at `npcs/<real-identity>.md` with piped-link mentions in prose) gets its pseudonym added to `aliases:` when the GM next edits the file, or at the next `/ingest` / `/wrap-session` pass that encounters a fresh mention of the pseudonym in a new source doc.

No bulk-rewrite, no schema-validation flag day, no breaking change.

## What this ADR does not commit to

- **Renaming canonical post-creation** when a Secret reveals the real identity (Option D's merge-on-reveal). The clean answer is `git mv` + update `aliases:` + update `linked_npcs:` references across the tree, which is mechanical but not free. The agent surfaces the rename as an option at the `partially-revealed → revealed` prompt; the GM decides whether to perform it. A future ADR may automate the rename if dogfooding shows it's frequent enough.
- **Alias propagation between Atlas and campaign.** Atlas is deferred ([ADR-0006](./0006-single-context-no-atlas-yet.md)); single-repo only.
- **PC aliases / nicknames** (e.g., "Sera" as a nickname for "Seraphina"). The same `aliases:` field is available on PC Reference notes (the schema is at the Reference-note level, not NPC-specific); if PCs need richer treatment — disposition, distinct slugs per identity — file a follow-up. See [#57](https://github.com/snlemons/game_manager/issues/57).
- **Cross-kind aliases** (a Location historically called by an NPC's name, or vice versa). Out of scope; dedup-matching's cross-kind handling continues to route those to ASK.

## Consequences

- `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md` gains a Reference-note section documenting the optional `aliases:` field.
- `~/.claude/skills/ttrpg-gm/references/dedup-matching.md` extends "what to match against" to include each candidate file's frontmatter `aliases:` entries, normalized via the existing slug rule.
- `~/.claude/skills/ttrpg-gm/references/reference-note-extraction.md` documents extraction-time alias detection (the prose patterns that signal a dual-name NPC) and the ASK shape for confirming alias relationships at review.
- `skills/ingest/SKILL.md` Phase 3 per-doc review surfaces alias-detection ASKs; confirmed alias relationships join the carried-forward lessons set so subsequent docs in the run apply them silently as UPDATEs.
- `skills/wrap-session/SKILL.md` Step 3 ambiguity clarification surfaces the same ASK shape for sessions whose notes mention an NPC by alias.
- `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md` confirms that `## Secrets` (and other bidi sections) live on the canonical container only; alias mentions in Secret prose are resolved to canonical before back-references are written. The writer authors the bidi-link bullet in canonical slug-path form (`[[secrets/<slug>]] — <summary>`); the linker accepts either canonical-slug-path or canonical-title for backward compatibility with v0.1/v0.2-era campaigns that wrote display-name wiki-links into `## Secrets` sections. The alias is never the back-reference target in either form — display-name back-references resolve to the canonical Secret's H1 title, not to an alias.
- `~/.claude/skills/ttrpg-gm/references/secret-store.md`'s `find_by_container` normalizes alias slugs to canonical before the exact-string match, so a caller asking *"what Secrets touch The Shadow?"* gets the same answer as *"what Secrets touch Maren?"*.
- No file rewrites, no test-fixture migrations. The 131-test suite as of v0.2 stays green.
