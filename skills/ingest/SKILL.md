---
name: ingest
description: Extract structure from existing TTRPG campaign notes into an already-scaffolded campaign repo. Hard-stops if the target directory isn't scaffolded — direct the GM to `/init-campaign` to start a new campaign. The remaining phases are the survey (discover input docs, bounded-skim each, propose one-line descriptions and a PC roster, propose a processing order, confirm with GM), the per-doc extraction loop with multi-doc cross-doc dedup and cross-doc learning (walk docs in confirmed order, extract Reference notes / Adventure / Threads / Consequences / Beats / Secrets per doc; dedup against existing campaign files with confident-update / ambiguous-ask thresholds; carry GM corrections forward as visible lessons applied to subsequent docs), and the wrap-up phase (bulk-prompt the GM for any missing Adventure `order:` values, regenerate `campaign.md` as the agent-maintained Campaign overview per ADR-0007, and make a follow-up git commit capturing the wrap-up's own changes).
---

# /ingest

`/ingest` is the workflow that turns an existing pile of campaign notes into structured, agent-navigable content inside a campaign repo that has already been scaffolded.

`/ingest` no longer scaffolds new campaigns. Per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md), the bootstrap entry for net-new campaigns is `/init-campaign`; `/ingest` requires a pre-scaffolded campaign repo and hard-stops if invoked against an unscaffolded directory.

The workflow has three phases plus an upfront precondition check:

- **Precondition: scaffolded?** — read-only marker check. Hard-stop if the target isn't a scaffolded campaign repo, directing the GM to `/init-campaign`.
1. **Survey** — discover input docs, bounded-skim each, propose a one-line description per doc as an editable diff-style list, propose a PC roster, propose a processing order (world info → adventures → session-shaped), confirm all three with the GM.
2. **Per-doc extraction loop** — for each doc, in the confirmed processing order, extract Reference notes, adventure metadata, Threads, Consequences, Beats, and Secrets; cross-doc dedup against existing campaign files (confident matches propose updates; ambiguous matches surface to the GM); present a per-doc proposed diff; the GM approves; corrections carry forward as visible lessons applied to subsequent docs.
3. **Wrap-up** — bulk-prompt the GM for any missing `order:` values on ingest-era Adventures, regenerate the campaign-root `campaign.md` as the agent-maintained Campaign overview, and make a follow-up git commit capturing the wrap-up's own changes (`campaign.md` regen plus any Adventure `order:` backfill — Phase 3's per-doc commits handle the rest, per issue #61).

Phase 4 runs after the per-doc loop completes (or, if the GM invokes `/ingest` on an already-populated repo just to finalize, runs against current campaign state).

Follow the domain vocabulary defined in the plugin's `CONTEXT.md` and the campaign repo's `CLAUDE.md`: **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Campaign overview**. Don't drift to synonyms the glossary explicitly avoids (no "DM", "module" for non-published adventures, "hook" for Thread, "seed" for Beat, "story"/"game" for Campaign, "world" for Atlas, etc.).

## When to invoke this skill

The GM invokes `/ingest` to add source docs to an already-scaffolded campaign — either a single markdown doc the GM wants extracted into the campaign or a batch of markdown notes from a prior tool that needs ingesting with cross-doc dedup. Both single-doc and multi-doc inputs run through the same Survey → Per-doc loop → Wrap-up pipeline. For a brand-new campaign with no scaffold yet, invoke `/init-campaign` instead — `/ingest` will hard-stop on an unscaffolded directory and direct the GM there.

## Inputs the GM provides

The GM provides:

- **Campaign directory** — the already-scaffolded target campaign repo. Defaults to the current working directory if it is a scaffolded campaign repo. The precondition check below validates this; if it isn't scaffolded, `/ingest` hard-stops and directs the GM to `/init-campaign`.
- **Input directory** — a path containing the source doc(s) to ingest. v0.1 is flat-directory only (no recursion into subdirectories; ADR-0006).

If either is missing, ask the GM for it before doing anything that touches the filesystem.

## Precondition: scaffolded? (run first, before any phase)

Before any other work — before the settings preflight, before Phase 2's survey, before anything that reads or writes campaign state — verify the campaign directory is a scaffolded campaign repo. This is a read-only inspection of the same Step 1 marker set documented in `../../references/scaffolder.md`: presence of `CLAUDE.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, and `campaign.md` at the campaign root. The scaffolder reference owns the canonical marker list; this precondition consumes its Step 1 in read-only mode (no Steps 2–4 writes) per [ADR-0019](../../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md).

If any marker is absent, **hard-stop** with this message verbatim:

> *"This directory isn't a scaffolded campaign repo. Run `/init-campaign` to start a new campaign, or invoke `/ingest` from a campaign that's already scaffolded."*

Do not proceed to the settings preflight. Do not write to the filesystem. Do not offer to scaffold — `/ingest` no longer scaffolds; that's `/init-campaign`'s job.

If every marker is present, continue to the settings preflight below.

## Settings preflight (run once after the precondition passes)

Once the precondition has confirmed the campaign is scaffolded, follow the procedure in `../../references/preflight.md` against the campaign root. The preflight catches the moved-campaign case (absolute paths baked into `.claude/settings.json` no longer match the current location) and offers the GM a regenerate-or-proceed prompt. If the GM declines regeneration, continue with the current settings — do not warn again this run. If the GM accepts, the file is rewritten and `/ingest` continues with no further preflight output.

Run the preflight exactly once per `/ingest` invocation; cache the result across all phases of the run.

## Phase 2: Survey

The survey phase runs **before** the per-doc extraction loop whenever the input directory contains **one or more** markdown docs. Its purpose, per ADR-0008 and [ADR-0018](../../docs/adr/0018-pc-roster-as-survey-deliverable.md), is to pre-label every doc with a GM-confirmed one-line description, propose a **PC roster** the GM corrects inline, and (for multi-doc runs) fix a processing order — all of which steer extraction in Phase 3.

**Run the survey per `../../references/extraction-pipeline.md` § "Phase 2: Survey".** That reference is the canonical spec for the Step 0 pre-flight, the bounded skim discipline (Step 1), the four description classifications (Step 2), the description+roster staging-file format (Step 3), the continue/cancel/refine response shapes (Step 3c), the processing-order proposal (Step 4), and the survey → Phase 3 handoff (Step 5) including survey-staging cleanup. Highlights:

- **Single-doc case is stripped, not skipped** — the bounded skim, the one-description proposal, and the PC roster proposal still run; the ordering step is skipped (one doc, no ordering question).
- **Zero-doc case skips survey entirely** — scaffold-only path.
- **Both staged files are presented in the same review batch** — `.ttrpg-staging/survey-descriptions.md` (descriptions) and `.ttrpg-staging/survey-pcs.md` (PC roster, per the Step 2.5 reference below); one continue/cancel ask covers them both.
- **Verbal refinement uses the Edit tool, one surgical edit per change** per [ADR-0015](../../docs/adr/0015-conversational-refinement-loop-in-prep-session.md) so the IDE shows native hunk diffs. Do not rewrite the whole staging file with Write.

Step 2.5 (PC roster) is the only Phase 2 sub-step whose mechanics SKILL.md still inlines below — the Phase 2 prose in `../../references/extraction-pipeline.md` cites `../../references/pc-roster-proposal.md` for the rest of the PC-roster-proposal spec, and the PC stub staging and promotion at Step 5a/5b also live there. Keep Phase 2 Step 2.5 here in step with `../../references/pc-roster-proposal.md`.

### Step 2.5: Propose a PC roster from skim signals

Per [ADR-0018](../../docs/adr/0018-pc-roster-as-survey-deliverable.md), the survey is the right place to establish who the PCs are — the bounded skim already collected the signals (Step 1), and the GM-confirmed roster is upstream of every Phase 3 extraction that needs PC identity (Beat `linked_pcs:`, Secret `belongs_to:` PC containers, Reference-note PC-vs-NPC discrimination, Log narrative voice).

**Apply `../../references/pc-roster-proposal.md`** for the candidate aggregation rule, the "Likely PC" / "Possible NPC" classification, and the empty-roster default. That reference is the canonical spec — the skim-signal list in Step 1 above and the candidate handling here are mirrors of its content. Hold the resulting candidate list in memory; Step 3 writes it to a staging file alongside the descriptions per the staged file format documented in the same reference.

## Phase 3: Per-doc extraction loop

**Run the per-doc loop per `../../references/extraction-pipeline.md` § "Phase 3: Per-doc extraction loop".** That reference is the canonical spec for the multi-doc loop setup (Step 0b), the recovery pre-flight (Step 0c — detecting the resume-after-crash / resume-after-keep-all-cancel state via `git log --grep '^/ingest doc '`), the bounded skim and proposed description (Step 1), the full read with description and lessons as context (Step 2), the draft per-shape rules (Step 3 — Reference note / Adventure / Thread / Consequence / Beat / Secret with their ingest-specific defaults and `linked_*` / `belongs_to:` population rules), the cross-doc dedup against existing files (Step 3b — applying `../../references/dedup-matching.md`), the per-doc review including the PC-vs-NPC safety net and the Step 4b staging review using `../../references/staging-pattern.md`, the refined cancel-mid-Phase-3 prompt (Keep all / Reset to before doc K / Abandon entirely), the move-to-final-location dispatch with bidi maintenance (Step 5), the per-doc commit with the documented message format `/ingest doc <N>/<total>: <doc-name> (<summary>)` (Step 5.8), the cross-doc learning capture (Step 5b), and the closing summary with the Phase 4 hand-off prompt (Step 6). Highlights of what the reference pins:

- **Per-doc commit subject format** — `/ingest doc <N>/<total>: <doc-name> (<one-line summary of what was extracted>)`. Examples: `/ingest doc 1/12: faerun-gods.md (5 Reference notes, 2 Secrets)`, `/ingest doc 2/12: lost-mines.md (Adventure, 12 Reference notes, 4 Beats)`, `/ingest doc 12/12: session-1-notes.md (3 Threads, 2 Consequences)`. Stage only paths inside the lifecycle/reference folders (`npcs/`, `pcs/`, `locations/`, `factions/`, `items/`, `adventures/`, `threads/`, `consequences/`, `beats/`, `secrets/`); prefer explicit `git add <paths>` over `git add -A` so the scope is auditable — never sweep in unrelated GM edits.
- **Recovery pre-flight (Step 0c)** — `git log --grep '^/ingest doc ' --reverse --format='%H %s'`. Per-doc commits without a subsequent wrap-up commit means the prior run crashed or was Keep-all-cancelled. Surface the resume prompt: *"This campaign has N committed Phase 3 docs from a prior `/ingest` run but no wrap-up. Resume at doc N+1, or abandon and re-scaffold?"*
- **Refined cancel-mid-Phase-3 prompt** — three choices when one or more docs have already committed this run:
  1. **Keep all** — exit; resume later at doc N+1.
  2. **Reset to before doc <K>** — `git reset --hard` to doc K's predecessor; drop carried-forward lessons accumulated by docs ≥ K (lessons 1..K-1 are preserved); re-enter Phase 3 at doc K.
  3. **Abandon entirely** — `git reset --hard` to the Phase 1 scaffold commit; drop all lessons.
- **Pre-approval gate seam** — the per-doc loop crosses a structural boundary before opening any staging file for a given doc (immediately after Step 0c on doc 1, or immediately after Step 5.8's commit for the previous doc). In v0.3 it's a no-op pass-through; a future [#27](https://github.com/snlemons/game_manager/issues/27) implementation slots its preview logic there. See the reference's "Pre-approval gate seam" section for the invariants.
- **PC-vs-NPC safety net** at Step 4a per `../../references/pc-roster-proposal.md` (slice B2 owns the spec) — late-addition PCs the survey missed surface as a Step 4a ASK; on "PC" the proposed `npcs/<slug>.md` CREATE is replaced by a `pcs/<slug>.md` stub CREATE; the confirmation joins Step 5b carried-forward lessons.
- **Carried-forward lessons** accumulate per doc and are tagged with their source-doc index so reset-to-before-doc-K can drop them deterministically (drop every lesson whose source-doc index is ≥ K; lessons 1..K-1 survive because their underlying work is still in the tree).

The reference is the spec; SKILL.md inlines no further Phase 3 prose. The reference's prose and the SKILL.md's "What to avoid" / "Quick reference" sections together carry the full skill behavior.

## Phase 4: Wrap-up

**Run wrap-up per `../../references/extraction-pipeline.md` § "Phase 4: Wrap-up".** That reference is the canonical spec for the Step 0 pre-flight (with the expected/unexpected `git status --porcelain` carve-out), the Step 1 missing-`order:` bulk-prompt (one staging file at `.ttrpg-staging/adventure-order.md`, GM edits in place, validation rules for positive integers and duplicates), the Step 2 `campaign.md` composer (running `../../references/campaign-overview-composer.md` with the **ingest-only variants** — `**Status:** active` + `**Last event:** YYYY-MM-DD (ingest)` header lines, full `## Adventures` history section, no Consequence truncation), the Step 3 wrap-up commit with the narrowed subject format `/ingest wrap-up (<short summary>)` covering **only** the wrap-up's own changes (Phase 3's per-doc commits already cover the lifecycle/reference content), and the Step 4 closing summary including `.ttrpg-staging/` cleanup and bidi link health lint. Highlights:

- **Narrowed wrap-up commit subject format**: `/ingest wrap-up (<short summary>)`. Example: `/ingest wrap-up (campaign.md regen, 3 Adventures backfilled with order: 1/2/3)`. Collapses to `/ingest wrap-up (campaign.md regen)` when no Adventures needed backfilling. When Step 0's pre-flight absorbed stale scaffolder artifacts: `/ingest wrap-up (campaign.md regen, 3 Adventures backfilled, scaffolder artifacts absorbed)`. Keep the subject under ~100 characters; spill detail into the body if needed.
- **Single auto-commit per Phase 4** — Phase 4 makes exactly one follow-up commit. The plugin's commit chain is *the scaffolder's initial commit (Phase 1) + per-doc commits (Phase 3 Step 5.8, one per doc, issue #61) + this wrap-up commit (Phase 4)*. After Phase 4, the GM owns every commit (ADR-0011).
- **No re-run guard** — Phase 4 specifically does **not** include a confirm-before-overwrite guard against a prior Phase 4 output; if the GM bypasses Phase 1 and jumps straight to wrap-up on an already-ingested repo, behavior is undefined.

The reference is the spec; SKILL.md inlines no further Phase 4 prose.

## What to avoid

- Don't use the words "DM", "game", "story" (for campaign), "world" (for Atlas), "hero", "hook" (overloaded), or "module" (reserved for *published* adventures only). Use the glossary in this plugin's `CONTEXT.md`.
- Don't auto-commit anything beyond `/ingest`'s commit chain — the scaffolder's initial commit (Phase 1 Step 3), the per-doc commits during Phase 3 (Step 5.8, one per ingested doc, per issue #61), and the wrap-up commit (Phase 4 Step 3). Ongoing git ownership belongs to the GM thereafter (see ADR-0011). `/wrap-session` and every other workflow downstream of `/ingest` does not auto-commit.
- Don't write to anywhere outside the target campaign directory.
- Don't ask the GM to fill out forms or pick from long lists. Capture-now-structure-later (ADR-0004).
- Don't invent dates, NPC names, or campaign details the source doc didn't provide.
- Don't extract a Thread for content the party isn't aware of in the source doc — that's a Beat (ADR-0009 path #4; the Thread/Beat awareness test). When the source is ambiguous, default to Beat and surface to the GM for re-classification.
- Don't leave a Beat's `linked_adventures` empty when the source doc is itself adventure-shaped — the structural link is unambiguous and skipping it forces a downstream manual backfill (this is the issue-#15 regression). Conversely, don't *guess* a link the source doesn't support: if two Adventures or two Locations are equally near a Beat, surface as ASK at review per the Beat shape rules in `../../references/extraction-pipeline.md` § "Step 3".
- Don't synthesize `sessions/YYYY-MM-DD-session-N/` directories from source docs (ADR-0005 — Sessions are created by `/prep-session`).
- Don't recurse into input subdirectories (ADR-0006 — flat directory only in v0.1).
- Don't silently overwrite an existing Reference note. Confident dedup matches propose **updates** (which the GM approves); ambiguous matches surface as yes/no questions; Adventure name collisions still stop and ask. The agent never picks identity silently.
- Don't carry cross-doc lessons across runs. They are scoped to one ingest invocation; the next `/ingest` starts with an empty lessons set.
- Don't apply a carried-forward rejection lesson to a candidate the GM might still want. When in doubt, surface the carried lesson and ask whether it should apply to this specific candidate — over-application is worse than re-asking.
- Don't ask the GM for `order:` one Adventure at a time when more than one is missing. Phase 4's order prompt is a single bulk question covering the whole missing-order set; one-at-a-time prompting is the form the slice spec explicitly avoids.
- Don't invent a party location in the Phase 4 `campaign.md` regen. If the source docs don't supply one, the section reads as a "GM to update" placeholder.
- Don't truncate the Phase 4 Consequence list. At ingest time, every Consequence is "recent" — truncation belongs to `/wrap-session`'s regen, not `/ingest`'s.
- Don't re-prompt for `order:` on Adventures whose source docs already supplied it (i.e., where Phase 3 wrote a non-null `order:`). The order prompt's whole point is to fill *missing* values, not re-litigate inferred ones.
- Don't extract a Secret with empty `belongs_to:` or only-ephemeral `belongs_to:` paths — the agent refuses to write either (ADR-0014; `tests/test_secret_store.py::TestValidateBelongsTo`). If the source content reads as Secret-bearing but the extractor can't justify any non-ephemeral container, surface as ASK and have the GM pick the container set rather than writing an invalid Secret.
- Don't skip the bidi-link maintenance step when a Secret is written. Every container in a Secret's `belongs_to:` must end up carrying a `## Secrets` section wiki-linking back to the Secret (`../../references/bidi-link-maintenance.md`). The maintenance is idempotent — re-running on an already-linked container is a no-op — so it is safe to run on every Secret write without checking state first.
- Don't auto-create a container from a Secret write. If a Secret's `belongs_to:` names a container file that does not exist (an NPC or Location the agent didn't extract a Reference note for), surface to the GM — the GM owns container creation explicitly, not as a side effect of a Secret write.
- Don't extract surface-plot facts as Secrets. A module's player-facing chapter prose is not Secret-bearing by default (`../../references/secret-extraction.md`); extract Reference notes and Beats from it. Reserve Secret extraction for content under known GM-only section headings ("Secrets and Lies" / "Adventure Background" / "DM-Only" / "Hidden Information") or content the GM-confirmed description identifies as GM-only.
- Don't classify a Beat's `kind:` from body content when a section heading already classifies it (`../../references/beat-kind-classification.md` order of precedence: section heading > body content > unset). The heading is the source author's intent declaration; the body content is the fallback when the heading is unknown.
- Don't pre-populate a Secret's `revealed_by:` from Beats extracted in this same doc. The Beat–Secret pairing is captured on the *Beat's* `linked_secrets:`; the symmetric `revealed_by:` on the Secret is reconciled later by `/wrap-session` when the Beat flips to `delivered`. Pre-populating both sides during ingest creates drift the linter would have to chase.

## Quick reference: which ADR governs what

- **ADR-0003** — Reference notes are one file per entity in `npcs/`, `locations/`, `factions/`, `items/`. Default body is a one-liner.
- **ADR-0004** — Threads and Consequences are per-file. Threads have `status: open | closed | decayed`. Consequences have valid YAML frontmatter and persist (no status).
- **ADR-0006** — v0.1 input is flat-directory local markdown only; non-markdown is skipped, no recursion.
- **ADR-0007** — Adventure frontmatter schema (`status` required, `order` optional/ingest-era, dates optional/nullable, durations free-form prose) and the agent-maintained `campaign.md` Campaign overview shape that Phase 4 Step 2 composes. The agent never invents dates.
- **ADR-0008** — Ingest's full workflow is survey + per-doc + wrap-up; slice 4 implements all four phases (survey, per-doc loop with cross-doc dedup and learning, and wrap-up with the bulk order prompt, `campaign.md` composer, and follow-up commit). Bounded skim plus GM-edited descriptions plus GM-confirmed processing order steer extraction.
- **ADR-0009** — Beats are GM-authored. Ingest is the fourth creation path (source docs are the GM's prior authoring). Extract Beat-shaped content (encounter lists, planned scenes, per-PC hooks, adventure-tagged ideas). Threads vs Beats is the party-awareness test: party knows → Thread; GM prep → Beat. Populate `linked_adventures`, `linked_locations`, `linked_pcs`, `linked_npcs` at extraction time per the proximity rules in the Beat shape subsection of `../../references/extraction-pipeline.md` § "Step 3" — these fields feed `/prep-session`'s tiered surfacing and leaving them empty forces a manual backfill. Phase 4's `campaign.md` lists pending Beats explicitly. Beat `kind:` (open enum) is classified primarily by source-section heading per `../../references/beat-kind-classification.md` (Scenes → set-piece; Lore/Rumors → news; Handouts → handout; Hidden Information for the DM → clue with `linked_secrets:`; Triggers → escalation; PC-attributed hooks → character-moment).
- **ADR-0011** — Plugin doesn't own ongoing git operations beyond `/ingest`'s commit chain: the scaffolder's initial commit (Phase 1 Step 3), the per-doc commits during Phase 3 extraction (Step 5.8 — one per doc, issue #61), and Phase 4's wrap-up commit. `/wrap-session` and every workflow downstream of `/ingest` does not auto-commit (it stays single-skill-invocation = single-commit; `/ingest` is the asymmetric case because it's a multi-doc unbounded workflow where checkpointing each doc is the right primitive).
- **ADR-0013** — Skill packaging (`skills/<name>/SKILL.md`); templates live under `templates/`.
- **ADR-0018** — PC roster is a Phase 2 (Survey) deliverable. The bounded skim collects PC candidates from prose signals; the agent stages a proposed roster (`.ttrpg-staging/survey-pcs.md`) alongside the description list in the same review batch. On approval, each surviving roster line becomes a stub `pcs/<slug>.md` with `kind: pc` and optional `aliases:`. Phase 2 Step 0's single-doc shortcut runs a stripped survey (description + roster) instead of skipping; zero-doc scaffold-only still skips. Phase 3 Step 4a includes a PC-vs-NPC safety-net ASK for late-addition PCs the survey missed; confirmed PC identities join Step 5b carried-forward lessons.
- **ADR-0014** — Secrets are a fourth lifecycle object: GM-only facts the party may not know but could discover. Stored at `secrets/<slug>.md` with required `belongs_to:` (non-empty list of non-ephemeral container paths — Adventure, NPC, PC, Location, Faction, Item). `/ingest` extracts Secrets from module GM-only sections ("Secrets and Lies" / "Adventure Background" / "DM-Only" / "Hidden Information" / equivalents — per `../../references/secret-extraction.md`). The Adventure container is automatic (the ingested doc's slug); additional containers come from named NPCs / Locations / Factions / Items in the Secret's own prose (proximity rule). Every container in `belongs_to:` carries a symmetric `## Secrets` section wiki-linking back to the Secret per `../../references/bidi-link-maintenance.md`. Secret slug dedup is `secrets/`-scoped per `../../references/dedup-matching.md`; the resolution shape for collisions is *merge containers / separate / rename*. Reference Python for the four query operations lives at `tests/test_secret_store.py`; for the bidi maintenance, `tests/test_bidi_link.py`.
- **ADR-0020** — Workflow procedures consumed by ≥2 skills get lifted to shared `references/` documents (not just data/heuristics). The extraction pipeline (Phases 2 + 3 + 4) is one of three v0.3 extractions; the canonical spec lives at `../../references/extraction-pipeline.md` and is cited from this SKILL.md and from `/init-campaign`'s docs-mode branch.
