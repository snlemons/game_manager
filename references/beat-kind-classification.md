# Beat `kind:` classification heuristic

When a skill proposes a new Beat (`/wrap-session` Pass 7 from scratchpad / notes; `/ingest` Phase 3 from a source doc's beat-shaped content), it also drafts a `kind:` value from the Beat's description so the GM has a concrete classification to confirm or override rather than a blank field. This reference is the shared heuristic both skills consult.

The corresponding ADR is [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md) (introduced `kind` alongside `linked_secrets` to support Clue-vs-Beat queries). The full Beat schema, including the open-enum nature of `kind:`, lives in [`references/frontmatter-schemas.md`](./frontmatter-schemas.md) ("Beat" section). The Secret extraction heuristic that pairs with `kind: clue` lives in [`references/secret-extraction.md`](./secret-extraction.md).

## Why classify at extraction time

`kind:` is optional — an unclassified Beat (`kind: ~` or absent) surfaces normally in `/prep-session` and behaves identically to a kind-classified Beat for every other lifecycle operation. Classification exists to unlock **kind-specific surfacing** in `/prep-session` (the Clue / Escalation prep questions in ADR-0015) and to let queries like "all Clues that reveal Secret X" return the right rows.

If the extracting skill leaves every Beat unclassified, the system still works — the per-kind questions just never surface. The win from classifying at extraction time is that the GM gets the question they care about ("is this Clue revealing partial or full picture?") without having to retroactively label every Beat after `/prep-session` already drafted the Brief.

The cost of misclassification is small: the GM corrects at the staging review, the same way they correct a misjudged Thread vs Consequence. **A wrong classification the GM corrects is cheaper than no classification at all.**

## The starter enum

Per `references/frontmatter-schemas.md` and CONTEXT.md, the starter values for `kind:` are:

- `news` — an information drop. A messenger arrives with word from another city; a contact passes along a rumor; the party reads a poster. The party hears something they didn't know.
- `handout` — an item transfer or physical handout. A magic item is given; a letter changes hands; a map is unfolded. The party gains something tangible.
- `character-moment` — a PC-arc payoff. A scene scoped to one PC's backstory or arc — their parent reappears, their old rival corners them, their patron calls in a debt. Generic party-wide moments are not character-moments.
- `set-piece` — a planned scene with structural prep. A chase, an ambush, a ritual, a heist. Has its own choreography and the GM wants to land the scene as designed.
- `clue` — a Beat whose intent is to reveal (part of) a Secret. Conventionally paired with `linked_secrets:` populated pointing to the Secret it reveals (see `references/secret-extraction.md` for the pairing).
- `escalation` — held back as a back-pocket lever for raising stakes mid-session. The reinforcements arrive, the timer runs out, the cult succeeds at the ritual the party didn't stop. Surfaced separately via `/prep-session`'s Escalation Prep question, not in the main "Beats to weave in" list.

The enum is **open**. Any string is accepted at schema-validation time. New kinds may be added as dogfooding reveals distinct prep-surfacing needs without a schema change — but the extracting skills should **not** invent new kinds during a wrap or ingest. If a Beat doesn't fit one of the six starter values, classify it as `~` (unclassified) and let the GM hand-edit a new kind if they want to track it. The agent inventing kinds would scatter the campaign with one-off labels nothing queries.

## Heuristic by prose shape

For each proposed Beat, classify by matching the Beat's description against these signals. Apply in order — the first match wins:

| Prose signal | `kind:` |
|---|---|
| Words: "reveal", "discover", "find out", "the party learns that…", "Clue that…", explicit mention of a Secret-shaped fact | `clue` |
| Words: "escalation", "if things go badly", "if the timer runs out", "back-pocket", "raise the stakes", "if the party isn't doing X by Y, then…" | `escalation` |
| Names a specific PC and only that PC ("for Darius:", "Darius's hook:", "Sera-specific moment") | `character-moment` |
| Words: "set up", "set-piece", "ambush", "chase", "ritual", "heist", names a choreographed scene with multiple beats / stages | `set-piece` |
| Words: "give them", "hand the party", "they receive", "physical item", names a specific item or document | `handout` |
| Words: "drop the news", "they hear", "messenger arrives", "rumor", "word reaches them", "poster" | `news` |
| None of the above clearly apply | `~` (unclassified) |

When two signals conflict (e.g., "for Darius: messenger arrives with news that his parent is dead" — both `character-moment` and `news`), prefer the **outer** framing — the GM's scoping note ("for Darius:") wins over the inner event shape. `character-moment` here. If the framing is co-equal ("news about Darius" with no GM scoping cue), classify as the inner shape (`news`) and surface the alternative at ambiguity clarification.

## Pairing `clue` with `linked_secrets:`

A Beat classified `kind: clue` should also have `linked_secrets:` populated naming the Secret(s) it reveals. The two fields are conventionally paired:

- **At extraction time**, if the Beat's description names a Secret the campaign already has (via `references/secret-store.md`'s `find_dedup_candidates` or `find_by_container`), draft `linked_secrets:` with that Secret's slug.
- **If the Beat's description names a new Secret** (e.g., the scratchpad says "Clue: drop that Maren is the spy" and there's no `secrets/maren-is-the-spy.md` yet), the extracting skill should also propose the Secret per `references/secret-extraction.md`. The Beat and the Secret are co-proposed at the same staging review; the GM approves both together.
- **If `kind: clue` but no Secret is named**, surface as ambiguity: *"This Beat is classified Clue but doesn't name the Secret it reveals. Which Secret? Or reclassify as `news` / `set-piece`?"*

A Beat with `linked_secrets:` populated but `kind:` other than `clue` is a Beat that **incidentally** touches a Secret — e.g., a `set-piece` whose choreography happens to reveal a fact. Both contribute to `revealed_by` on the linked Secret when delivered (see `skills/wrap-session/SKILL.md` for the delivery-time auto-flip). The Clue/incidental distinction captures GM authorial intent: a Clue is **primarily** about revelation; an incidental link is "this Beat also happens to touch the Secret."

## Pairing `linked_*` lists with classification

The classification often co-occurs with specific `linked_*` populations:

- `character-moment` → `linked_pcs:` populated (otherwise it's a generic Beat, not a character moment). If no PC is named, reclassify as `news` / `set-piece` and surface at ambiguity.
- `clue` → `linked_secrets:` populated (per above).
- `set-piece` → `linked_locations:` and/or `linked_adventures:` often populated (the scene has a setting).
- `handout` → may carry an item slug; v0.1 has no formal item-slug field on Beats, so use the body to name the item and ensure the item's Reference note exists (or surface as ambiguity).
- `news`, `escalation` → `linked_*` lists populated only when the source clearly justifies (per the proximity rules in `skills/ingest/SKILL.md` Step 3 Beat-shape subsection).

The `linked_*` proximity heuristic itself (which slugs to populate, how close in the source the name has to be) lives in `skills/ingest/SKILL.md` — this reference doesn't restate it.

## What this heuristic does not handle

- **The lifecycle status (`pending | delivered | dropped`).** That's a separate field driven by Pass 6 of `/wrap-session`, not extraction-time classification.
- **The Clue → Secret revelation flow.** When a Clue Beat flips to `delivered`, the linked Secret auto-flips `hidden → partially-revealed`, and `/wrap-session` may prompt for `partially-revealed → revealed`. That orchestration lives in `skills/wrap-session/SKILL.md`, not here.
- **GM overrides.** The classification is a draft; the GM corrects at staging review. If the GM consistently overrides a particular shape ("I never want a `news` Beat to be auto-classified — they're all `handout` in my campaign"), the heuristic doesn't track that as a campaign-local override. The agent classifies fresh each time.
- **Multi-Beat scenes.** A complex scene that breaks into multiple Beats (set-piece intro, character-moment beat inside, escalation if it goes badly) gets classified per Beat. The relationship between Beats is the GM's to track in body prose; the classification is per-file.

## Why an open enum (rather than a hardcoded one)

If new prep-time questions emerge that need their own kind (the SKILL spec calls out `clue` and `escalation` as the kinds that unlock dedicated `/prep-session` questions today; future kinds might add a `prophecy` question or a `betrayal` question), they can be added to the enum incrementally without a schema migration. The extracting skills stick to the documented starter set; the GM adds new kinds as the campaign reveals the need.

The cost is that a typo (`kind: clu`) doesn't fail validation — the schema accepts it. That's a known tradeoff: kind-specific queries silently miss the typo'd Beats. The mitigation is the heuristic above: the extracting skill only ever writes one of the six starter values, so typos are GM-introduced and the GM owns the fix.
