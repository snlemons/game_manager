# PC roster as a Phase 2 survey deliverable

`/ingest` needs to establish who the **PCs** are early enough that every downstream extraction (Beat `linked_pcs:`, Secret `belongs_to:` PC containers, Reference-note PC-vs-NPC discrimination, Log narrative voice) can route a named character to a `pcs/<slug>.md` file instead of mis-filing it under `npcs/` or dropping it. v0.2 dogfooding surfaced the gap concretely (issue [#73](https://github.com/snlemons/game_manager/issues/73)): the v0.1 `/ingest` of the Greyhawk campaign produced **zero** files under `pcs/`, with one PC mis-extracted as an NPC under `npcs/`. The strict reading: `/ingest` has no phase that asks the GM who their PCs are or proposes a PC roster from the docs, so PCs surface inconsistently — sometimes as `pcs/<slug>.md` (when the source doc was explicitly labelled), sometimes as `npcs/<slug>.md` (when the source treated them as named characters without role context), sometimes not at all (when the source only referenced them by first name).

This ADR pins the policy: **the PC roster is a Phase 2 (Survey) deliverable**, folded into the same review batch that already presents the per-doc descriptions, with a Phase 3 safety-net ASK for late-addition PCs.

## Why the agent can't infer reliably

Named character → NPC by default. The extraction heuristic in `~/.claude/skills/ttrpg-gm/references/reference-note-extraction.md` is intentionally permissive about Reference-note creation — it favors *proposing* a candidate the GM can reject at review over silently dropping it (the "false positives are cheap, false negatives are invisible" framing). That heuristic is correct for NPCs but produces the wrong default for PCs: a PC who appears in five session logs as an actor reads to the agent the same way as a recurring NPC, and there's no prose-shape signal that reliably disambiguates the two for a single character without round-tripping with the GM. Frequency-of-mention is a leading indicator — a focus PC with one session of spotlight is statistically rare — but not a reliable one: a recurring NPC ally with regular spotlight reads identically.

The agent's bounded skim during Phase 2 *can* surface PC candidates from prose signals (explicit roster sections, party-pronoun patterns, session-log narrators referring to a name as an actor rather than a subject), but the load-bearing confirmation is the GM's. The agent's job is to *propose* a roster the GM corrects; the agent's job is not to *commit* a roster the GM didn't review.

## Mechanism: skim-discovery + GM-confirmation, folded into the survey

The Phase 2 bounded skim already runs against every source doc. The same skim that drafts a one-line description per doc also collects PC candidates from prose signals across all docs. The agent then stages the proposed roster alongside the description list in **the same review batch** — one continue/cancel prompt covers both files, and a single in-chat verbal refinement loop revises either staged file in place (matching the [ADR-0015](./0015-conversational-refinement-loop-in-prep-session.md) refinement pattern that `/prep-session` already uses).

Two staging surfaces in one review batch:

- `.ttrpg-staging/survey-descriptions.md` — unchanged.
- `.ttrpg-staging/survey-pcs.md` — new. Lists candidate PCs with frequency-of-mention annotations and "Likely PC" / "Possible NPC" classifications. GM edits inline (add missed PCs, remove false positives, fix names, capture nicknames as `aliases:`), or empties the roster for "no PCs / I'll add them later."

The GM responds **once** with continue / cancel / verbal-refinement and both staged files are consumed together. Stopping points stay at 2 for multi-doc runs (descriptions+PCs combined, then order) — same count as today, with the PC roster added.

On approval, each surviving roster line becomes a stub `pcs/<slug>.md` file with `kind: pc`, optional `aliases:` for nicknames captured in the annotation, and an optional one-line body if the GM enriched the annotation. The stub is staged at `.ttrpg-staging/pcs/<slug>.md` as part of the same Phase 2 hand-off and promoted to `pcs/<slug>.md` on approval. The body is intentionally minimal — the GM owns the longer-form PC content via hand-edit or via a future [#57](https://github.com/snlemons/game_manager/issues/57) backstory ingest.

## Why fold into the survey rather than add a Phase 1.5 step

An earlier draft routed the PC roster ask through its own pre-survey step. Folding into Phase 2 is strictly better:

- **Stopping-point parity.** The current Phase 2 has two stopping points: descriptions, then order. Adding a third stopping point for the PC roster would interrupt the same skim-then-review flow with three GM hand-offs instead of two. Folding the PC roster into the descriptions review keeps the count at two and reuses the same continue/cancel/verbal-refinement loop.
- **Skim-time discovery is free.** The bounded skim already runs against every doc for description-drafting. The PC-candidate detection is the same read, the same in-memory text. A Phase 1.5 step would either re-skim (wasted work) or read the docs blind (low-signal proposal).
- **Same review surface, same affordances.** GM edits the staged file in their IDE the same way they edit `survey-descriptions.md`. No new staging-pattern variant; no new ASK shape.

## Scaffold-only deferral

`/ingest` invoked in scaffold-only mode (no source docs in the input directory) currently skips Phase 2 entirely — there is nothing to survey. The PC roster step inherits that constraint: **scaffold-only stays minimal; no PC roster prompt fires.** The GM either adds PCs by hand or runs `/ingest` against a PC-roster source doc later (per [#57](https://github.com/snlemons/game_manager/issues/57) + this ADR's stub creation).

Considered alternatives:

- *Run a stripped survey for scaffold-only* — just the PC roster portion, no descriptions, no order. Rejected: a survey without docs has no skim signal to drive the candidate set, so the agent would have to ask the GM to type in PC names blind. That's a worse experience than letting the GM hand-edit `pcs/` directly.
- *Add the PC roster ask outside Phase 2 for scaffold-only* — asymmetric branch in the workflow. Rejected: complexity without payoff.

Recommended (and adopted): scaffold-only skips the PC roster ask. The GM has two ergonomic paths to add PCs later — hand-edit, or `/ingest` against a PC-shaped source doc — both of which compose with the rest of the workflow.

## Single-doc shortcut

The current Phase 2 Step 0 routes single-doc runs (exactly one markdown file in the input directory) directly to Phase 3, skipping the survey. Under this ADR, the PC roster review is load-bearing enough that single-doc runs need it too: a session-log doc has PCs; a single bestiary doc has none and the GM empties the roster.

Implementation choice: keep Step 0's "single-doc shortcut" framing for descriptions and order (one description, no ordering question), but extend it so the PC roster review still runs when 1+ doc is present. The single-doc path now runs a stripped survey — one description, one order entry implied, and the PC roster review — then hands off to Phase 3. A zero-doc scaffold-only run still skips survey entirely (no docs, no skim).

The trade-off is that survey becomes non-optional for all 1+ doc runs. Acceptable cost: the PC roster review is fast (a single staged file, often a few lines), and PCs are usually relevant even for one-doc ingest.

## Phase 3 safety net for late-addition PCs

The Phase 2 PC roster proposal can miss PCs: the skim's signal isn't strong enough, a late-introduced PC first appears in session logs the GM ingests later, or the GM dropped the candidate at survey review intending to add later. The Phase 3 per-doc extraction loop handles late-addition PCs via an ASK at per-doc review:

When per-doc extraction surfaces a named character whose name doesn't match any existing `pcs/<slug>.md` filename or `aliases:` entry **and** matches no existing `npcs/<slug>.md` either (so the dedup pass would otherwise propose a CREATE under `npcs/`), the per-doc review surfaces a PC-vs-NPC ASK. GM confirmation:

- *"PC"* — the agent stages a `pcs/<slug>.md` stub for that doc's promotion (same shape as the survey stub) instead of the proposed NPC CREATE, and records the confirmation as a carried-forward lesson (Step 5b) so subsequent docs in the run apply the PC identity silently via the extended dedup-matching rule.
- *"NPC"* — the proposed NPC CREATE stands.

This catches PCs the GM didn't enumerate at survey time without forcing the GM into a per-doc decision every time a known PC name appears. The carried-forward lesson is the load-bearing piece: once the GM confirms PC identity on doc N, doc N+1 routes the same name to PC without re-asking.

## Composition with #57

These compose cleanly:

- This ADR establishes the PC roster upfront — the stub `pcs/<slug>.md` files exist with `kind: pc` frontmatter, optional `aliases:` for nicknames, and an optional one-line body.
- [#57](https://github.com/snlemons/game_manager/issues/57) handles PC-shaped source docs (character sheets, backstory). When the GM later runs `/ingest` against a backstory doc, the stub already exists; #57's logic extends the file with the backstory body and extracts named NPCs / Locations / Factions from the backstory prose with the PC in their `belongs_to:`.

The "GM-owned PC file" framing is preserved — the survey roster ask only writes a one-line stub; #57 handles longer-form backstory ingestion with cross-extraction.

## What this ADR does not commit to

- **Renaming PCs post-creation** (e.g., a PC whose true name reveals later in play) — same renaming concern as ADR-0017's alias machinery. File follow-up if dogfooding hits it.
- **Inactive / retired / dead PCs** — they stay in `pcs/` with a `status:` field if needed; covered by general lifecycle, not this ADR.
- **PC ownership transfer** (a player leaves, another player picks up the PC) — out of scope; the GM hand-edits the file.
- **Migration for existing v0.1-ingested campaigns** — the v0.2-dogfooding "convert v0.1 → v0.2" path is doing this manually; the spec change here applies to future `/ingest` runs.

## Consequences

- `skills/ingest/SKILL.md` Phase 2 (Survey) extends the bounded skim to collect PC candidates from prose signals, adds a new staged file `.ttrpg-staging/survey-pcs.md` presented in the same review batch as `survey-descriptions.md`, and on approval stages `pcs/<slug>.md` stubs alongside the description hand-off.
- `skills/ingest/SKILL.md` Phase 2 Step 0 scopes the "single-doc shortcut" so the PC roster review still runs when 1+ doc is present; a zero-doc scaffold-only run still skips survey entirely.
- `skills/ingest/SKILL.md` Phase 3 per-doc review surfaces the PC-vs-NPC safety-net ASK shape for unknown named characters whose dedup pass would propose an NPC CREATE.
- `skills/ingest/SKILL.md` Step 5b carried-forward lessons gains a "PC identity confirmation" lesson shape mirroring the existing Reference-note dedup and Secret merge lessons.
- `references/reference-note-extraction.md` extraction heuristic respects the PC roster: a named character matching a `pcs/<slug>.md` filename or `aliases:` entry resolves to PC and is never proposed as an NPC.
- `references/frontmatter-schemas.md` confirms `kind: pc` is covered by the Reference-note schema (already documented under ADR-0017 + the [#59](https://github.com/snlemons/game_manager/issues/59) work) and adds a worked example of the stub PC file shape.
- `skills/wrap-session/SKILL.md` Step 3 ambiguity clarification gains the same PC-vs-NPC ASK shape for the case where a brand-new PC first appears in a session's `notes.md`. Less load-bearing because `/wrap-session` runs against an established campaign where the roster usually exists, but coherent with the Phase 3 safety net.
- No file rewrites, no test-fixture migrations. The 137-test suite as of v0.2 stays green; one new test exercises the PC stub shape.
