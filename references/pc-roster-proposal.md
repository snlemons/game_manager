# PC roster proposal

Per [ADR-0022](../docs/adr/0022-pc-roster-via-explicit-classification.md) (superseding [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md)), the PC roster is a **Phase 2 (Survey) deliverable** — established by GM confirmation early enough that every downstream extraction (Beat `linked_pcs:`, Secret `belongs_to:` PC containers, Reference-note PC-vs-NPC discrimination, Log narrative voice) can route a named character to a `pcs/<slug>.md` file instead of mis-filing it under `npcs/` or dropping it. This reference is the shared spec used by `/ingest` (Phase 2 PC roster step + Step 5 PC stub promotion) and `/init-campaign` docs mode; the per-skill orchestration around the proposal (where Phase 2 sits in the larger flow, how the result hands off to extraction) stays in each SKILL.md.

ADR-0022 supersedes ADR-0018's skim-inference mechanism. The agent **does not** scan source docs' prose for PC candidates — v0.2 dogfooding showed skim inference produced too many false-positive candidates on every named character and not enough confidence to silently miss PCs the GM expected. The refined mechanism enumerates existing `pcs/<slug>.md` files, leaves a clearly-marked zone for GM-typed adds, and (per slice H2) consumes the `PC source: <slug>` doc-classification path for source-doc-driven PC stubs.

## When to propose

The proposal runs against a campaign repo (with or without source docs in the input directory). It does **not** require the bounded skim to have happened first — the skim is no longer a signal source for this step.

- **0+ markdown docs, existing campaign repo** → propose the roster. An empty staged roster (no existing PCs in `pcs/`, no GM-typed adds, no `PC source:` docs in slice H2) is allowed; the staged file still appears with prose telling the GM the roster is empty and inviting them to type PCs into the "Add other PCs here" zone if they have any.
- **Zero docs (scaffold-only)** in `/ingest` proper → skip. Per ADR-0022 (and ADR-0018), scaffold-only stays minimal — the GM either adds PCs by hand or runs `/ingest` against an input directory later. `/init-campaign` from-scratch mode runs its own PC roster prompt outside this reference's scope.

## Sources of pre-populated roster entries

The staged roster file is pre-populated from two sources (a third lands in slice H2):

1. **Existing `pcs/` enumeration.** List every `pcs/<slug>.md` file in the campaign repo. Read each file's frontmatter `aliases:` (if any) and its H1 (the canonical name). Each existing PC appears in the staged file marked `existing — pcs/<slug>.md` so the GM can see at a glance which entries are already-confirmed PCs versus newly proposed.
2. **GM-typed adds zone.** The staged file carries a clearly-marked "Add other PCs here" zone (a labeled heading with a brief prose contract) where the GM types new PC entries before saying continue. Empty by default.
3. **(Slice H2 — `PC source:` doc classification.)** Source docs the GM classified as `PC source: <slug>` during the description review will auto-add their declared `<slug>` to the staged roster in a dedicated section. **This slice (H1) does not implement that mechanism**; the staged file leaves a placeholder section labeled `Auto-added from PC source: docs` that stays empty until H2 populates it.

The agent does **not** scan source-doc prose for PC candidates. No frequency-of-mention counting, no roster-section heading scan, no party-pronoun proximity scan, no PC-vs-NPC inference labels. The skim-based inference mechanism from ADR-0018 is gone.

## Staged file format: `.ttrpg-staging/survey-pcs.md`

Write the proposed PC roster to `.ttrpg-staging/survey-pcs.md` using the Write tool, so Claude Code's standard file-write diff shows the GM the full proposed roster in their IDE. The file has three labeled sections plus a fixed header explaining the edit contract:

```markdown
# Survey: proposed PC roster

Edit this list — confirm, rename, remove, or add. Existing PCs are pre-seeded
from `pcs/`. Add new PCs by typing them into the "Add other PCs here" zone
below. Empty the entire roster if you have no PCs to confirm yet — you can
add them later by hand-editing `pcs/` or by running `/ingest` against a
PC-roster doc.

To add a PC: type a new line in the "Add other PCs here" zone with the slug
(or a free-form name; the agent slugifies on continue). Optional one-line
description after a tab or two spaces becomes the stub file's body.
Nicknames go in `— alias: <name>` suffixes (multiple aliases
comma-separated).

## Existing PCs

silas         — existing — `pcs/silas.md`
rae           — existing — `pcs/rae.md` — alias: Raelyn
betha         — existing — `pcs/betha.md`

## Auto-added from PC source: docs

(none yet — populated by H2 from docs the GM classifies as `PC source: <slug>`.)

## Add other PCs here

(Type new PC entries below this line, one per line. Optional one-line body
after tab/double-space. Optional `— alias: <name>` suffix.)
```

If the campaign repo has no existing PCs, the "Existing PCs" section renders with a one-line empty-state body instead of a list:

```markdown
## Existing PCs

(No existing PCs in `pcs/`.)
```

The three section headings (`## Existing PCs`, `## Auto-added from PC source: docs`, `## Add other PCs here`) are load-bearing: they label the zones the parser uses to classify each line, and they tell the GM where to type. **Do not remove or rename the section headings.** The GM may delete individual entry lines (to drop a pre-seeded PC from this run's roster) and may add lines inside the "Add other PCs here" zone (to introduce new PCs); the section headings themselves stay.

The staging file is presented alongside `survey-descriptions.md` in the same review batch per ADR-0018 — one continue/cancel prompt covers both files, and a single in-chat verbal refinement loop revises either staged file in place per [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). The orchestration of the dual-file review (the continue/cancel/refinement prompt, the verbal-refinement loop) lives in the consuming skill's SKILL.md; this reference owns the roster file's shape and content.

## Parsing the GM-edited roster

On continue, re-read `.ttrpg-staging/survey-pcs.md` from disk to capture GM edits. Walk the file section by section:

- **Header / prose contract** — skipped (anything before the first `## ` section heading).
- **`## Existing PCs` section** — each non-empty, non-empty-state line is a surviving pre-seeded PC entry. The line shape is `<slug>  — existing — \`pcs/<slug>.md\`[  — alias: <names>]`. If the GM deleted a pre-seeded line, that PC is dropped from this run's roster (the underlying `pcs/<slug>.md` file is **not** deleted from disk — drop-from-this-run is a roster-level signal only; the existing PC file persists). The `(No existing PCs in \`pcs/\`.)` empty-state line is ignored.
- **`## Auto-added from PC source: docs` section** — in slice H1 this section is always empty (placeholder). The parser skips the contents (including the parenthetical empty-state body). Slice H2 will populate this section with entries shaped the same as "Add other PCs here" entries; the parser logic for both sections is the same.
- **`## Add other PCs here` section** — each non-empty, non-empty-state, non-parenthetical line is a GM-typed entry. The parser extracts:
  - The **slug** — the GM-typed first token (slug or free-form name). On any GM addition where the GM supplied a name rather than a slug, slugify per the [`dedup-matching.md`](./dedup-matching.md) normalization rule before recording.
  - The optional **one-line description** — anything after the slug and before any `— alias:` suffix, when the GM added one. Becomes the stub file's body.
  - The **aliases** — any `— alias: <name>` suffix on the line. Multiple aliases are comma-separated.
  - The empty-state instructional parenthetical (`(Type new PC entries below this line, …)`) is ignored.

An empty roster (no surviving pre-seeded entries, no auto-added entries, no GM-typed entries) is allowed and means "no PCs yet" — proceed.

GM-corrected PC roster entries become the campaign's PC roster the moment Phase 2 hands off to Phase 3 — Step 5 stages `pcs/<slug>.md` stubs from any **new** roster entries (GM-typed adds, plus slice-H2 auto-adds when that mechanism lands) and promotes them to the campaign repo. Pre-seeded entries that survived the GM's review do **not** re-stage — they already exist at `pcs/<slug>.md` and the agent leaves them untouched. The roster steers every subsequent Phase 3 extraction: candidate names matching a PC slug or `aliases:` entry resolve to PC (see [`reference-note-extraction.md`](./reference-note-extraction.md) "PC vs NPC discriminator"), and the Phase 3 safety net catches PCs the survey missed.

## Stub staging and promotion to `pcs/<slug>.md`

For each **new** PC roster entry (GM-typed add, or slice-H2 auto-add), draft a stub file per the shape below and stage it at `.ttrpg-staging/pcs/<slug>.md` per [`staging-pattern.md`](./staging-pattern.md) Section 2 (CREATE entries: Write the full proposed content):

```yaml
---
kind: pc
aliases: [<nickname1>, <nickname2>]
---

# <Canonical Name>

<Optional one-line body from the GM-typed description, if any.>
```

Rules:

- The slug is the GM-confirmed slug from `survey-pcs.md` (post-edit, post-refinement, post-slugify for free-form GM names).
- The H1 is the GM-confirmed canonical name. When the staged roster line was `marisa`, the H1 is `Marisa` (the prose-readable form of the slug — title-case each hyphen-separated token); when the GM provided an explicit canonical name in the body (`marisa  Marisa Stoneforge — alias: Mari`) use the body's leading name as the H1.
- `aliases:` carries the `— alias: <name>` entries from the staged line. If there are no aliases, omit the key entirely (per [`frontmatter-schemas.md`](./frontmatter-schemas.md) Reference-note default — absent reads as `[]`).
- Body is the optional one-line description. If the GM didn't supply one, omit the body — leave the file as H1-only after the frontmatter. (Per ADR-0022 + ADR-0018, the stub is intentionally minimal; #57's PC backstory ingestion in slice H2 will extend the body for `PC source:` docs.)

**Pre-seeded entries do not re-stage.** A surviving `## Existing PCs` line points at a file that already exists in `pcs/`; the agent does not stage a stub, does not overwrite, does not no-op-write. Pre-seeded entries flow into the in-memory PC roster handed off to Phase 3 (so Reference-note extraction and Beat `linked_pcs:` see them), but they do not touch disk during Phase 2 Step 5.

### Collision check before promotion

Stage every new PC stub before promoting any. If a new stub's slug collides with an existing `pcs/<slug>.md` file in the campaign repo (rare under the refined mechanism — existing PCs are pre-seeded and the GM sees them in the `## Existing PCs` section before typing adds; a collision here means the GM typed a slug into "Add other PCs here" that matches an existing PC file), **STOP** and surface the collision: *"You added `silas` to the new-PC zone, but `pcs/silas.md` already exists and is in the `## Existing PCs` section. Did you mean to update the existing PC, rename the new one, or skip?"* Don't silently overwrite a GM-authored PC file.

Under ADR-0022's refined mechanism this check fires far less often than under ADR-0018's mechanism (where every confirmed roster entry was a potential collision against pre-existing `pcs/`). The check stays as a safety net for the GM-typed-adds path.

### Promotion

After all new stubs are staged and no collisions remain, promote them to `pcs/<slug>.md` by translating the staging path (strip `.ttrpg-staging/pcs/` prefix → `pcs/<slug>.md`). Create the `pcs/` directory if it doesn't exist. Delete each staged stub after promotion. After all stubs are promoted, remove `.ttrpg-staging/pcs/` if it's now empty.

The promotion happens **inside Phase 2**, before Phase 3 begins, so the new PCs are visible to Phase 3's `pcs/` enumeration (used by Reference-note extraction's PC-vs-NPC discriminator and by Beat `linked_pcs:` population). Pre-seeded entries are already on disk and don't need a promotion step.

If the GM-confirmed roster had no new entries (all pre-seeded entries kept, or all entries dropped), skip stub staging and promotion entirely — no new PCs to write. Note the roster state in the hand-off summary.

## Cancel path

On cancel during the survey review, delete any staged `.ttrpg-staging/pcs/` directory (defensively, in case stubs were written) along with the survey staging files. Write nothing else to the campaign repo. Existing `pcs/<slug>.md` files are **not** touched on cancel — they pre-existed the survey and pre-exist the cancel. The PC roster proposal produces no side effects outside `.ttrpg-staging/` until the GM confirms.

## What this reference does not own

- **The dual-file review prompt** (continue / cancel / verbal refinement covering both `survey-descriptions.md` and `survey-pcs.md`) — orchestration, lives in the consuming skill's SKILL.md per ADR-0018.
- **The per-doc description proposal** (`survey-descriptions.md`) — see the consuming skill's SKILL.md.
- **The processing-order proposal** (`survey-order.md`, multi-doc only) — see the consuming skill's SKILL.md.
- **The `PC source: <slug>` doc-classification mechanism** that populates the `## Auto-added from PC source: docs` section — slice H2's scope; this reference reserves the section but does not specify the recognition rule.
- **The Phase 3 PC-vs-NPC safety-net ASK** for late-addition PCs — see the consuming skill's SKILL.md and [`reference-note-extraction.md`](./reference-note-extraction.md) "PC vs NPC discriminator."
- **The carried-forward "PC identity confirmation" lesson shape** — see the consuming skill's SKILL.md.
