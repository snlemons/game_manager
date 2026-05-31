# /prep-session shifts to a draft-first conversational refinement loop

`/prep-session` changes from **one-shot composition** (draft Brief → terminal review → write) to **draft-first then converse** (draft Brief → multi-turn refinement → write). The agent presents the staged draft, asks rule-based follow-up questions, revises the staged file via Edit (so the IDE shows native diffs per [#16](https://github.com/snlemons/game_manager/issues/16)), and loops until the GM approves.

This is a deliberate change in interaction shape — `/prep-session` becomes a planning workflow, not just a composition command. The change is motivated by source material (Alexandrian's *Smart Prep*, Shea's *15-Minute Prep*, Lange's *SAVE* method) converging on the same principle: **ask the GM what they're prepping around, then prep around it.** A one-shot composition cannot honor that principle.

## Updated flow

| Step | v0.1 | v0.2 |
|---|---|---|
| 0–1: locate, number, date | unchanged | unchanged |
| 2: read state + refresh `campaign.md` | unchanged | unchanged (broad read) |
| 3: draft Brief → stage in `.ttrpg-staging/brief-draft.md` | terminal | becomes the *starting point* for the loop |
| **3.5: conversational refinement loop** | doesn't exist | **NEW** — agent surfaces follow-up questions; GM responds; agent revises staging via Edit; loop until approval or cancel |
| 4: review | terminal yes / no / cancel | **becomes the approval gate inside the loop**: "approve" exits the loop; "cancel" exits without writing |
| 5–6: write final, close | unchanged | unchanged |

The conversation happens *over the staging file*. The GM can mix chat replies and direct IDE edits; the agent re-reads staging on each turn to pick up manual changes.

## Question categories (rule-based)

Seven categories, each with explicit firing rules in a new `references/prep-session-questions.md`. A question fires only when its rule conditions are met; empty categories stay silent.

| Category | Example | Trigger |
|---|---|---|
| **Coverage check** | "I didn't include the goblin-camp Beat because the party's heading away — confirm or override?" | Beat down-tiered with borderline relevance score. |
| **Tiering check** | "3 Beats linked to the Cult Arc are out-of-focus this session because the active Adventure is the Mines arc. Surface any?" | Out-of-focus Beat count > 0 for an Adventure with `status: introduced`. |
| **Secret push** | "Cult Arc has 2 Secrets in `partially-revealed` — push toward either this session?" | `belongs_to` intersects active or in-menu Adventures and status is `hidden` or `partially-revealed`. |
| **Thread decay** | "Thread X has been `open` for 6 sessions without movement — decay, push, or leave?" | Thread open across N+ Logs without `delivered` Beats linked. |
| **Decision request** | "Opening Scene section is empty — propose one from the prior Log's closing state?" | Empty drafted section needing GM input (Opening Scene, name picks, branching prep). |
| **Escalation prep** | "No in-focus Beat is marked `kind: escalation`. Flag one as the back-pocket lever, propose new, or skip?" | No in-focus Beat has `kind: escalation`. Per-campaign opt-out via `.claude/rules/sessions.md`. |
| **GM focus check** | "Anything you're planning this session that's not in the draft?" | Always fires; runs last in the question pass. |

**Why rule-based.** Templated (always-ask-all-7) is too verbose. Heuristic (agent decides per-run) is unpredictable — the GM can't develop a stable mental model. Rules give predictable behavior, are testable, and the rules themselves become a tunable spec.

## Skip semantics

Verbal skip; no flag. The agent's preamble entering Step 3.5 mentions the escape:

> "Brief draft is at `.ttrpg-staging/brief-draft.md`. I have N follow-up questions to help you refine it — or say 'looks good' / 'skip questions' to finalize as-is."

If the GM responds without addressing a question, the agent treats that as "decided not to engage with that one" and moves on. **No re-prompting** — re-prompting feels naggy and breaks the GM's flow.

## Brief section changes paired with this work

Three Brief-shape changes that earn their keep alongside the conversational loop:

- **New `## Opening Scene` section** between "Last time" and "Active adventures." Empty by default; populated via the Decision Request question if the GM wants. Addresses today's past-only framing (Brief has "Last time" recap but no future-facing opener — Shea's "strong opening scene" principle).
- **Locations section reshape** from flat ("party here, heading there") to 3–5 locations with one sensory/evocative detail each. Details come from the Location Reference note's body if authored, or from the dialogue if not. New sensory details gathered via dialogue **write back to the Location Reference note** so future Briefs reuse them — honors Alexandrian "recycle and reincorporate."
- **Clue Beats may appear in the Brief; their Secrets do not.** The Brief shows Clue Beats in the existing "Beats to weave in" section (they're Beats). The Secrets they reveal stay in `secrets/` files, referenced via wiki-link from the Beat body. Avoids creating a "Secrets to leak" checklist that runs against "don't duplicate improvisation."

## Considered alternatives

- **Shape A — single up-front question pass before reading state.** Rejected: a single shot can't support "make decisions" or "gather resources" as the GM described. The Brief is also a better focus-surfacer than a blank-canvas question — GMs react faster to "here's what I see" than to "what do you want?".
- **Shape C — continuous dialogue interleaved throughout (per-section refinement loops).** Rejected as too heavy — turns `/prep-session` from a command into a sustained planning session, and risks dialogue fatigue for GMs who want quick prep. Shape B's bounded loop with verbal skip preserves the option without forcing it.
- **Separate `/plan-session` skill.** Rejected: the conversational work is intrinsic to good prep, not a separate phase. Splitting risks creating two surfaces for the same conceptual thing.
- **Heuristic question selection (agent decides per-run).** Rejected: unpredictable behavior breaks the GM's mental model. Rule-based is testable and tunable.
- **`--quick` flag to bypass the loop.** Rejected as unnecessary mechanism — verbal "skip questions" / "draft is good" achieves the same outcome without adding a flag surface.

## Consequences

- `skills/prep-session/SKILL.md` gains a new Step 3.5; Step 4 becomes the approval gate inside the loop rather than terminal.
- `references/prep-session-questions.md` is new — the rule spec for the 7 question categories (firing conditions, question phrasing, response handling).
- `references/campaign-overview-composer.md` and the Brief section template in `skills/prep-session/SKILL.md` update to include the Opening Scene section and the reshaped Locations section.
- The Locations sensory write-back is a new edit pattern: the agent appends to a Location Reference note's body when the GM authors a sensory hook during dialogue. Honors the existing approval-then-write convention; new content surfaces in the IDE as a normal Edit diff.
- This ADR extends, but does not supersede, [ADR-0010](./0010-prep-session-brief-structure-and-interaction.md): Brief section order is preserved (the Opening Scene addition slots in cleanly); the propose-then-edit interaction generalizes from one-shot to multi-turn. [ADR-0011](./0011-wrap-session-workflow.md) is unaffected — `/wrap-session` continues to read the Log that `/prep-session` enables the GM to feed into during play.
- The seven question categories couple with the Beat `kind:` discriminator and Secret architecture (see [ADR-0014](./0014-secrets-as-multi-container-lifecycle-objects.md)) — several question rules query by `kind` or by Secret `belongs_to`, so the schema changes are prerequisites, not parallel work.
- Per the v0.2 roadmap entry, this work ships alongside the Secret architecture as a single coherent theme: "improve the prep workflow with a richer prep object model."
