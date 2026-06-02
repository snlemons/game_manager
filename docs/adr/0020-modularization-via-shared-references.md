# Modularization of workflow behavior via shared `references/`

v0.1 and v0.2 established the `references/` directory as the home for content the agent reads at skill-run time — `dedup-matching.md`, `frontmatter-schemas.md`, `campaign-overview-composer.md`, `staging-pattern.md`, `preflight.md`, `prep-session-questions.md`, `secret-extraction.md`, `secret-store.md`, `beat-kind-classification.md`, `reference-note-extraction.md`, `bidi-link-maintenance.md`. The convention was: when two skills need the same data/heuristic, lift it to `references/` and have both cite it.

v0.3 extends the pattern from *"data the agent consults"* to *"workflow behavior the agent executes."* The scaffolder, the extraction pipeline, and the conversational-refinement-loop are not lookups — they are substantive multi-step procedures with their own staging surfaces, error paths, and review gates. This ADR pins the discipline: **when a workflow procedure is consumed by ≥2 skills, lift it to a shared `references/` document and have the skills cite it. Don't re-inline.**

## What v0.3 extracts

Three workflow procedures move out of skill SKILL.md prose into shared references:

- **Scaffolder.** Currently `skills/ingest/SKILL.md` Phase 1 (template enumeration, write order with `.claude/settings.json` first, `git init` + initial commit, the `{{CAMPAIGN_NAME}}` / `{{CAMPAIGN_SYSTEM}}` / `{{CAMPAIGN_PATH}}` substitution rules). Consumed by `/init-campaign` and `/init-adventure` (standalone mode) per [ADR-0019](./0019-init-campaign-as-bootstrapping-front-door.md), and by `/ingest`'s remaining "scaffolded?" precondition check (read-only — to detect the absence of scaffolding and direct the GM to `/init-campaign`).
- **Extraction pipeline.** Currently `skills/ingest/SKILL.md` Phases 2 + 3 + 4 (survey with description-classification and PC-roster review, per-doc loop with cross-doc dedup and carried-forward lessons, per-doc commits, wrap-up regen of `campaign.md`, recovery pre-flight). Consumed by `/ingest` (its primary job) and `/init-campaign`'s docs-mode branch.
- **Conversational-refinement-loop.** Currently `skills/prep-session/SKILL.md` Step 3.5 + `references/prep-session-questions.md`'s response-handling machinery (initial draft via Write, multi-turn revision via Edit so diffs are native IDE hunks, verbal-skip exits cleanly, mid-loop GM hand-edits picked up via mandatory re-read). Consumed by `/init-campaign` (pitch elicitation, optional first-Adventure sub-flow), `/init-adventure` (adventure-shaped content walkthroughs), and `/prep-session` (its existing 7 question categories).

The skill-specific layers stay in skill SKILL.md prose: `/prep-session`'s 7 question categories are skill-specific *content*, even though the loop *mechanics* move out; `/init-adventure`'s content surface (premise, hook, 3–5 locations, key NPCs, secrets+clues, set-pieces, escalations) is skill-specific even though the conversational loop driving it is shared.

## Why this is hard to reverse

- **Single source of truth becomes the value.** Once two skills cite a shared reference, divergent re-inlining produces drift. The whole point of the abstraction is that one update propagates everywhere; backing out means making the update in every consuming skill.
- **New skills are designed against the abstractions.** `/init-campaign` and `/init-adventure` SKILL.md prose assumes the shared scaffolder and conversational-refinement-loop exist. Backing out the modularization means rewriting both skills to inline the procedures, and re-bloating `/ingest` and `/prep-session` to absorb the inlining.
- **The discipline is the architectural commitment.** v0.3 is not just *"extract three things";* it's *"adopt the lift-when-shared rule going forward."* Future workflow procedures consumed by multiple skills follow the same pattern. Reversing the discipline means consciously re-adopting the duplicate-and-drift pattern, which is the failure mode v0.2 dogfooding repeatedly diagnosed.

## Considered alternatives

- **Skip modularization in v0.3; ship `/init-campaign` and `/init-adventure` with their own copies of the scaffolder and extraction-pipeline prose.** Rejected: this is exactly the duplicate-and-drift pattern that PR #79's path-resolution-direction fix (and several earlier v0.2 dogfooding fixes) were correcting. Doing it deliberately would burn the budget for one more version's worth of drift before paying the cost anyway.
- **Modularize per-feature on a slice-by-slice basis instead of as a versionwide commitment.** Rejected: ad-hoc per-slice modularization decisions produce inconsistent abstractions (some pieces lifted, others not, no shared rule for when). Committing to the discipline as a v0.3 theme produces consistent decisions.
- **Modularize via Python helper scripts (D-style per [#24](https://github.com/snlemons/game_manager/issues/24)).** Rejected: per [ADR-0016](./0016-lib-helper-script-convention.md), `lib/` helpers were explored and rolled back in v0.2. Shared references stay markdown-prose-only at runtime. Reference-implementation Python lives in `tests/` per the v0.1 pattern, used for spec-drift detection rather than runtime execution.
- **Modularize only the scaffolder; defer extraction-pipeline and conversational-refinement-loop modularization.** Rejected: the scaffolder is the easiest extraction but the conversational-refinement-loop is the highest-leverage one (consumed by *three* skills, including the new ones, including the v0.2-shipped `/prep-session`). Half-modularization would leave the highest-overlap pieces inlined.

## Design seams for future composability

The shared references are designed with explicit forward-compatibility seams for two trigger-gated post-v0.3 items:

- **[#27](https://github.com/snlemons/game_manager/issues/27) pre-approval staging gate.** The extraction-pipeline reference has a documented "before opening any staging file" boundary that a pre-approval gate can slot into without restructuring the per-doc loop. No design work for the gate itself in v0.3; the seam is just visible.
- **[#11](https://github.com/snlemons/game_manager/issues/11) context management.** The references are bounded in length (a few hundred lines each), so they don't worsen the campaign-content-loading side of #11. The extraction pipeline's per-doc commit pattern (PR #76) already keeps per-iteration agent context bounded; the modularized reference preserves that property.

These seams are documentation-level — no code or spec work to add the gates/heuristics — but they're called out in the references so future work has a clear hook.

## What this ADR does not commit to

- **A specific filename per reference.** Names settled during implementation; this ADR commits to the *what* (three procedures lifted) and the *why* (the discipline), not to whether the conversational-refinement-loop reference is named `conversational-authoring.md` vs. `refinement-loop.md` vs. `dialogue-pattern.md`.
- **Test reorganization.** The existing `tests/test_*.py` convention (reference impls in pytest) carries forward unchanged. Reference impls for the modularized behaviors land in new `tests/test_*.py` files following the v0.1 pattern.
- **A full audit of every shareable piece in v0.3.** The PC-roster-proposal logic is also modularized (per the ADR-0018 refinement in [#57](https://github.com/snlemons/game_manager/issues/57)-adjacent work), but smaller utility patterns lifted opportunistically during implementation don't each need their own ADR.
- **Future versions' modularization scope.** v0.4 will surface its own shareable workflow pieces (e.g., the bigger-than-session prep arc may share planning patterns across skills); those are scoped by their own PRDs.

## Composition with ADR-0019

This ADR commits to the internal restructuring; [ADR-0019](./0019-init-campaign-as-bootstrapping-front-door.md) commits to the user-visible skill split that the restructuring enables. Neither is independently coherent — without modularization, the skill split duplicates prose; without the skill split, the modularization has no second consumer to share with. The two land together.

## Consequences

- Three new files under `references/` — scaffolder, extraction-pipeline, conversational-refinement-loop (exact names settled during implementation).
- `skills/ingest/SKILL.md` shrinks substantially as scaffolder (Phase 1) and pipeline (Phases 2–4) prose moves out; the remaining `/ingest` SKILL.md is mostly orchestration plus the "scaffolded?" precondition.
- `skills/prep-session/SKILL.md` Step 3.5 shrinks: the loop mechanics move to the shared reference, the 7 question categories stay skill-specific.
- New `skills/init-campaign/SKILL.md` and `skills/init-adventure/SKILL.md` cite the shared references via relative paths per PR #79's discipline.
- Test coverage extends: each shared reference gets a `tests/test_*.py` mirror with reference-impl Python for the deterministic algorithms (scaffolder file enumeration + write order, extraction-pipeline dedup boundaries, conversational-refinement-loop turn structure). Spec-drift detection on every change.
- The plugin manifest test (`tests/test_plugin_manifest.py`) continues to enforce relative-path-only references in SKILL.md and references/ prose.
