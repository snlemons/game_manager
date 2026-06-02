# `/init-campaign` as the bootstrapping front door; standalone `/init-adventure` produces a campaign-shaped repo

`/ingest` in v0.1–v0.2 covered two user intents under one verb: *"scaffold a fresh campaign repo"* (with or without source docs) and *"ingest existing markdown notes into a campaign"* (per `skills/ingest/SKILL.md` line 23 — the *"to ingest additional source docs into an already-scaffolded campaign"* path). The conflation was tolerable when `/ingest` was the only entry point; v0.3's introduction of net-new authoring skills makes it actively confusing — a GM coming in fresh with no notes shouldn't have to discover that the verb for *"start a campaign"* is the same as the verb for *"extract structure from existing docs."*

This ADR pins the split: **`/init-campaign` is the bootstrap entry point** for net-new campaigns (dual-mode: from existing docs or guided from scratch). **`/ingest` shrinks to extraction-only** against an already-scaffolded campaign; it hard-stops if invoked against an unscaffolded directory. **`/init-adventure` covers net-new adventure authoring**, in-campaign or standalone — where standalone scaffolds a full campaign-shaped repo with one Adventure pre-populated (a one-shot is a single-Adventure campaign, structurally identical to a regular campaign).

## Why standalone `/init-adventure` produces a campaign-shaped repo (not a separate "module" shape)

A one-shot has PCs (the GM may know them up front), will be *run* (it has at least one Session), generates a Log, and may surface Threads / Consequences / Beats / Secrets during play. All the campaign-shaped affordances apply. The thing it *doesn't* have is multiple Adventures and an open-ended timeline.

The structural answer: a standalone `/init-adventure` invocation produces the same shape as `/init-campaign` — `CLAUDE.md`, `campaign.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, `pcs/`, `npcs/`, etc. — with `adventures/<slug>/adventure.md` pre-populated as the one Adventure the GM is authoring. `/prep-session` and `/wrap-session` then Just Work on a one-shot without any special-casing because the file layout is campaign-shaped.

Considered alternatives (rejected):

- **Standalone adventure as a single folder, no git, no scaffolding overhead.** Loses CLAUDE.md context and git history; loses all campaign-shaped affordances. The cost-of-rigor is low enough that the loss-of-affordances dominates.
- **Standalone adventure as a "module workshop" repo with multiple adventures.** Atlas-without-world-content shape. Premature — Sofia's stated use case is one-shots she runs herself, not a portfolio of published modules. Defer to a future Atlas-adjacent decision if the use case materializes.
- **Standalone adventure as a separate "publishable module" shape, distinct from a campaign.** Export of a campaign-shaped one-shot into a shareable module is a v0.4+ concern (strip PCs, package the adventure-specific content). Keeping the repo shape unified during authoring makes the export a transformation, not a different starting point.

## CONTEXT.md remains stable

`CONTEXT.md`'s Adventure entry — *"A story arc the party runs **inside** a campaign. … Lives under `adventures/<name>/` in a campaign repo"* — applies to both in-campaign and standalone adventures, because standalone is just a campaign that happens to contain one Adventure. No new repo shape, no new term needed yet. *One-shot* stays informal; if it hardens into something the agent needs to reason about beyond rendering, it gets promoted to a glossary entry then.

## Why this is hard to reverse

- **User-visible flow change.** README's "First run" section currently says *"invoke `/ingest`"* to start a campaign; this ADR moves the front door to `/init-campaign`. Dogfooders' muscle memory shifts.
- **`/ingest`'s prose contracts shrink.** Phase 1's scaffold step moves into a shared reference (per ADR-0020) and `/ingest`'s SKILL.md prose shrinks to the "campaign-must-already-be-scaffolded" precondition + the extraction pipeline. Undoing means restoring the scaffold path inline.
- **The standalone-as-campaign-shape commitment.** What an `/init-adventure --standalone` output structurally *is* gets pinned here. Future skills (`/prep-session`, `/wrap-session`) lean on the shape being campaign-shaped without branching.

## Composition with ADR-0020

This ADR commits to the *user-facing skill split*. [ADR-0020](./0020-modularization-via-shared-references.md) commits to the *internal modularization* that makes the split feasible without duplicating prose: the scaffolder, extraction pipeline, and conversational-refinement-loop become shared `references/` consumed by both `/init-campaign` and `/ingest` (and `/init-adventure` consumes the scaffolder + the conversational-refinement-loop). The two ADRs land together; neither is independently coherent.

## What this ADR does not commit to

- **Export of standalone adventures as shareable modules.** That's a v0.4+ concern (Atlas-adjacent). The current scope ends at "GM authors a one-shot they will run themselves."
- **Migration of v0.1/v0.2-scaffolded campaigns.** Existing campaigns are already scaffolded; `/ingest` running against them continues to work. The change only affects the *front door* for new campaigns.
- **Removal of `/ingest`.** `/ingest` keeps doing the same extraction work it does today, against scaffolded campaigns. Only the no-source-docs / scaffold-from-zero branch moves out.
- **A separate `/init-pc` skill.** PC creation is covered by `/init-campaign`'s roster step, `/ingest`'s extraction pipeline (for PC backstory docs), and the prep/wrap-time surfaces (see [#57](https://github.com/snlemons/game_manager/issues/57) work).

## Consequences

- New `skills/init-campaign/SKILL.md` — the bootstrap entry. Dual-mode question flow (docs or guided from scratch). Consumes the shared scaffolder, the shared extraction pipeline, and the shared conversational-refinement-loop (per ADR-0020).
- New `skills/init-adventure/SKILL.md` — net-new adventure authoring. In-campaign mode adds `adventures/<slug>/` to an existing campaign; standalone mode invokes the shared scaffolder + a single first-adventure sub-flow, producing a campaign-shaped repo with one Adventure.
- `skills/ingest/SKILL.md` Phase 1 prose moves out (into the shared scaffolder reference); `/ingest` SKILL.md adds an upfront "campaign-must-be-scaffolded" check that hard-stops if invoked against an unscaffolded directory, directing the GM to `/init-campaign`.
- README "First run" section updates to point at `/init-campaign` for new campaigns; existing `/ingest` documentation reshapes around the extension-of-existing-campaign use case.
- `CONTEXT.md` Adventure glossary entry unchanged. *One-shot* not added.
- Plugin manifest (`.claude-plugin/plugin.json`) gains the two new skills; test coverage extends to cover the new skills' question flows and the `/ingest` precondition check.
