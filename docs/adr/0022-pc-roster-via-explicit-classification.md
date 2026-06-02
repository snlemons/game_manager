# PC roster proposal mechanism: GM-explicit classification + existing pcs/ enumeration

[ADR-0018](./0018-pc-roster-as-survey-deliverable.md) established the PC roster as a Phase 2 (Survey) deliverable and gave it a skim-inference mechanism: the bounded skim that drafts per-doc descriptions also scans prose for PC candidates (frequency of mention, explicit roster sections, party-pronoun patterns, session-log narrator voice, nickname proximity), aggregates the signals, and proposes a roster with "Likely PC" / "Possible NPC" classification labels. v0.3 dogfooding and the [v0.3 grilling outcome on PRD #80](https://github.com/snlemons/game_manager/issues/80) surfaced the mechanism's failure mode concretely enough to step back from it.

This ADR pins the refined mechanism: **the PC roster is established by reading existing `pcs/<slug>.md` files, accepting GM-typed adds in a labeled zone of the staged file, and (per slice H2) auto-adding slugs the GM declared via `PC source: <slug>` doc classification.** Skim-based PC candidate inference is dropped entirely.

ADR-0018's broader policy (PC roster as a Phase 2 deliverable, dual-file review batch with descriptions, single-doc-stripped-survey scope, scaffold-only-skip scope, Phase 3 safety net for late-addition PCs, composition with #57) stays in force. This ADR refines only the **candidate-source** layer; the staging surface, hand-off contract, and Phase 3 safety net are unchanged.

## Why skim inference is stepped back

Three problems showed up under dogfooding:

- **False positives at scale.** The skim's prose signals (frequency of mention, party-pronoun proximity, narrator-as-actor framing) genuinely do correlate with PC identity, but the correlation is weak in the wrong direction: in a module-shaped or world-info-shaped corpus, frequently-mentioned named NPCs read *identically* to PCs under skim heuristics. The "Possible NPC" classification label was supposed to absorb this — flag the uncertainty, let the GM decide — but in practice every named character ended up with a "Possible NPC" label, turning the GM's review into a long list of false candidates to delete. The signal-to-noise ratio was too low to be useful as a proposal.
- **Silent-miss risk for the cases skim couldn't see.** The mechanism's other failure mode is the inverse: a PC the skim *didn't* surface (because their introduction lives deeper than the 200-word bounded skim, or because the PC's name happens not to appear in the skimmed window of any doc) silently misses the roster. The Phase 3 safety net catches this eventually — per-doc review surfaces unknown named characters as PC-or-NPC ASKs — but the silent-miss-then-correct-late workflow is more friction than the GM-explicit upfront workflow.
- **Inference quality is its own design problem.** The set of "signals" ADR-0018 specified isn't axiomatic — it was a v0.2 best-guess that needed empirical tuning, and the tuning loop required a working corpus of dogfood campaigns to evaluate against. v0.3 dogfooding gave us that corpus and the answer: the tuning isn't there, and pursuing it competes with shipping the rest of v0.3's modularization and bootstrapping work.

The strict reading of dogfooding: a GM who *wants* to declare their PCs has lower-friction paths than "let the agent guess and then correct"; a GM who doesn't yet know their PCs has no useful signal for the agent to infer from.

## The refined mechanism

Three sources pre-populate the staged `survey-pcs.md` file:

1. **Existing `pcs/<slug>.md` enumeration.** The agent lists every PC file in the campaign repo and pre-seeds the staged roster with one line per existing PC, marked `existing — pcs/<slug>.md`. The GM can drop a pre-seeded entry (delete the line) to exclude that PC from *this run's* roster (the underlying file persists), but the default is "keep all existing PCs." This is the dominant path for `/ingest` against an established campaign — the v0.2 dogfooding case where PCs are already declared no longer requires the GM to re-confirm them.
2. **GM-typed adds zone.** The staged file carries a clearly-marked `## Add other PCs here` section where the GM types new PC entries before saying continue. Slug normalization rules from [`references/dedup-matching.md`](../../references/dedup-matching.md) apply to GM-typed entries on parse — the GM may type a free-form name and the agent slugifies. Aliases and optional one-line description bodies are supported the same way as ADR-0018's mechanism.
3. **`PC source: <slug>` doc classification (slice H2 scope).** Source docs the GM classifies as `PC source: <slug>` during the description review auto-add their declared `<slug>` to a dedicated section of the staged roster. The recognition mechanism and the cross-extraction routing live in slice H2 of v0.3; this ADR reserves the staged-file section (`## Auto-added from PC source: docs`) and the auto-add behavior contract but does not specify the routing.

Skim-based candidate inference is removed. The bounded skim still runs (for the per-doc description proposal — ADR-0008's load-bearing use of the skim is untouched), but the skim text is no longer read for PC discovery. The skim's PC-signal heuristics from ADR-0018 are dropped from `references/pc-roster-proposal.md` entirely.

## What's preserved from ADR-0018

The supersession is narrow. Everything ADR-0018 established that isn't candidate-detection survives:

- **PC roster as a Phase 2 deliverable** — unchanged. The roster is established before Phase 3 starts so downstream extraction can route PC identity.
- **Dual-file review batch with `survey-descriptions.md`** — unchanged. One continue/cancel prompt covers both files; one verbal-refinement loop revises either file in place.
- **Single-doc stripped-survey scope** — unchanged. Single-doc input still runs the PC roster review (now reading existing `pcs/` instead of inferring from skim signals); zero-doc scaffold-only still skips.
- **Stub shape** (`kind: pc`, optional `aliases:`, optional one-line body) — unchanged. The shape promotion to `pcs/<slug>.md` is the same.
- **Phase 3 safety net for late-addition PCs** — unchanged. The per-doc PC-vs-NPC ASK still fires when an unknown named character whose dedup pass would propose an NPC CREATE surfaces. The carried-forward "PC identity confirmation" lesson shape is unchanged.
- **Composition with [#57](https://github.com/snlemons/game_manager/issues/57)** — unchanged in shape, refined in routing. The PC backstory extraction path now triggers off the GM-explicit `PC source: <slug>` classification (slice H2) rather than off any inferred PC-shape signal.

The mechanism step-back is at the candidate-source layer only. The Phase 3 safety net continues to be the lower-friction late-addition path; this ADR strengthens it by removing the upstream noise from skim inference that was crowding the safety net's job.

## Why GM-explicit beats agent-inferred

Two framings that converged on the same answer during the v0.3 grilling:

- **The agent can't reliably infer PC identity from prose signals.** PC-vs-NPC at the prose level is a role disambiguation that depends on out-of-band context (which character does the *player* control), not on a textual pattern. ADR-0018 acknowledged this in its "Why the agent can't infer reliably" section — the skim-inference mechanism was an attempt to *narrow* the GM's review work rather than to *decide* PC identity. v0.3 dogfooding showed the narrowing didn't work well enough to justify the mechanism's complexity.
- **The GM is the cheapest source of ground truth.** Two clicks of friction (read the pre-seeded list of existing PCs; type any adds in the labeled zone) deliver the load-bearing roster directly from the GM, with no inference layer that can drift. For new campaigns where no `pcs/` files exist yet, the GM-typed-adds path is the *primary* path — the same path `/init-campaign` from-scratch mode uses (per ADR-0019).

The framing matches the project-wide pattern from [ADR-0007](./0007-temporal-model-and-campaign-overview.md) (GM-editorial unread files) and [ADR-0021](./0021-gm-writing-style-via-claude-rules-style.md) (GM-authored steering file): where the GM is the source of truth, the agent's job is to surface the steering surface clearly and read it on consumption — not to reconstruct it from signals.

## Consequences

- `references/pc-roster-proposal.md` rewritten to document the existing-`pcs/` enumeration + GM-typed-adds + (slice-H2-placeholder) `PC source:` auto-add mechanism. All skim-signal prose (frequency, explicit roster sections, party-pronoun proximity, narrator voice, nickname proximity) and all "Likely PC" / "Possible NPC" classification prose is removed. The staged file shape gains three labeled sections (`## Existing PCs`, `## Auto-added from PC source: docs`, `## Add other PCs here`). The parser updates to walk the file section by section.
- `docs/adr/0018-pc-roster-as-survey-deliverable.md` gains a `Status: superseded by ADR-0022` line at the top. The body content stays intact as the historical record of the v0.2 mechanism — the supersession is by candidate-source layer, not a full revocation.
- `tests/test_pc_roster_proposal.py` reference-impl Python updated to match: drop the `classify_candidates` skim-signal aggregator; add `enumerate_existing_pcs` for the pre-seeding source; update `render_survey_pcs_md` to render the three-section shape; update `parse_survey_pcs_md` to walk by section and route pre-seeded vs. GM-typed entries differently. New tests assert the negative (no skim-based candidate inference) and assert the GM-typed-adds zone survives across staging file edits.
- `skills/ingest/SKILL.md` Phase 2 Step 1 (bounded skim), Step 2.5 (PC roster proposal), Step 3b (stage roster), and Step 3c (parse on continue) prose gets updated to match the refined reference. This ADR commits to the design; the skill-prose update lands as a follow-up slice (likely H2 alongside the `PC source:` mechanism, or earlier as a paired touch — the slice-H1 scope is the reference and the ADR, not the skill prose).
- `references/reference-note-extraction.md` "PC vs NPC discriminator" prose stays accurate (the `pcs/` set still drives discrimination); the upstream description of how `pcs/` got populated updates to cite ADR-0022 alongside ADR-0018.
- `references/frontmatter-schemas.md` PC stub shape is unchanged (frontmatter `kind: pc`, optional `aliases:`, optional one-line body). The schema doesn't depend on which source produced the entry.

## What this ADR does not commit to

- **The `PC source: <slug>` doc classification mechanism** — slice H2's scope. This ADR reserves the staged-file section and the auto-add behavior contract; H2 specifies the recognition rule, the description-line shape, and the cross-extraction routing for the doc's body.
- **Migration for existing v0.2 / v0.3-pre-H1 ingested campaigns** — none required. The mechanism change affects only future `/ingest` and `/init-campaign` runs. Existing `pcs/<slug>.md` files in dogfood campaigns become the pre-seeding source the moment H1 lands.
- **Removing the Phase 3 PC-vs-NPC safety net** — explicitly kept. The safety net is the load-bearing late-addition path under the refined mechanism, not optional.
- **An `/extract-pcs` skill** that re-derives PC identity from a corpus retroactively — out of scope. The GM-explicit mechanism makes this less interesting; a GM running `/ingest` against PC source docs uses the slice-H2 routing instead.
- **Renaming PCs post-creation** — same scope as ADR-0018; not addressed here.
