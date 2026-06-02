# PC roster proposal

Per [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md), the PC roster is a **Phase 2 (Survey) deliverable** — established by GM confirmation early enough that every downstream extraction (Beat `linked_pcs:`, Secret `belongs_to:` PC containers, Reference-note PC-vs-NPC discrimination, Log narrative voice) can route a named character to a `pcs/<slug>.md` file instead of mis-filing it under `npcs/` or dropping it. This reference is the shared spec used by `/ingest` (Phase 2 Step 2.5 + Step 5 PC stub promotion) and `/init-campaign` docs mode; the per-skill orchestration around the proposal (where Phase 2 sits in the larger flow, how the result hands off to extraction) stays in each SKILL.md.

The corresponding ADR is [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md) (PC roster as a Phase 2 survey deliverable).

## When to propose

The proposal runs against a corpus of source docs in an input directory. It requires the bounded skim of every doc to have already happened — the skim text is the signal source for candidate detection, and re-skimming for PC discovery is wasted work.

- **1+ markdown doc** → propose the roster. Empty roster is allowed (a bestiary-only corpus, a pure world-info corpus); the staged file still appears with prose telling the GM the agent found no PC candidates and inviting them to add any the skim missed.
- **Zero docs (scaffold-only)** → skip. Per ADR-0018, scaffold-only stays minimal — no skim signal to drive the candidate set means no roster prompt. The GM either adds PCs by hand or runs `/ingest` against a PC-roster source doc later.

## Skim signals for PC candidate collection

While the bounded skim runs (the first heading and the first ~200 words per doc), **also collect PC candidates from prose signals**. The same ~200 words drives this; do not full-read for PC discovery. Watch for these signals across the corpus:

- **Frequency of mention.** A name that recurs across multiple docs (especially across session logs) is a stronger PC candidate than a name mentioned once. Track per-doc counts in memory; aggregate across all skimmed docs before proposing the roster.
- **Explicit roster sections.** Session-zero packets and party-overview docs commonly have headings like `## Party`, `## The PCs`, `## Player Characters`, `## Cast`. Names listed under those headings are very strong PC candidates.
- **Party / pronoun patterns.** Prose using "the party", "the PCs", "the players" in proximity to a named character is a PC signal (e.g., *"the party — Silas, Rae, and Betha — entered the citadel"*).
- **Session-log narrator voice.** Session logs that narrate a named character as the *actor* ("Silas opened the door, Rae cast detect magic") rather than the *subject* of the GM's prep ("Mayor Brennan asks them to investigate") are PC signals. The "named character does things" pattern reads differently from the "named character is described" pattern.
- **Nicknames in proximity to a canonical name.** "Helerel ('Helly' to her friends)" or "Helly (short for Helerel)" — both names refer to the same PC, captured as canonical + `aliases:` per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md).

Be conservative: false positives are cheap (the GM removes them at review); false negatives are caught by the Phase 3 safety net per ADR-0018, but adding the candidate at survey time is the lower-friction path. When borderline, propose with a "Possible NPC" label rather than dropping silently.

If a doc has no heading or is shorter than ~200 words, work with what's there. Don't pad. Don't infer content beyond what's visible in the skim.

## Aggregation and candidate classification

Aggregate the per-doc PC candidates collected during the skim across the whole input directory. For each candidate name:

- Sum the doc count where the candidate appeared.
- Note any explicit-roster-section hits (these promote the candidate to "Likely PC" regardless of frequency).
- Note any nickname / canonical-name pairings captured during the skim (these become `aliases:` on the stub).
- Classify the candidate:
  - **"Likely PC"** — appears in multiple docs as an actor, named under an explicit roster heading, or named in proximity to "the party" / "the PCs" patterns.
  - **"Possible NPC"** — appears once, in a one-off mention, or in a pattern that reads more like NPC framing than PC framing. The candidate is still surfaced; the label tells the GM where the agent leaned.

Hold the candidate list in memory until the staging step writes it to disk for GM review.

If no PC candidates surfaced from the skim (a bestiary-only input, a pure world-info input), the roster proposal is empty — the staged file still appears, with prose telling the GM the agent found no PC candidates and inviting them to add any the skim missed. Empty is the honest default.

## Staged file format: `.ttrpg-staging/survey-pcs.md`

Write the proposed PC roster to `.ttrpg-staging/survey-pcs.md` using the Write tool, so Claude Code's standard file-write diff shows the GM the full proposed roster in their IDE. Format the file as a short header explaining the edit contract, followed by one line per candidate — the candidate's proposed slug, a frequency annotation, and the agent's "Likely PC" / "Possible NPC" classification. Capture any nickname / canonical pairings the skim caught as an `— alias: <nickname>` suffix:

```markdown
# Survey: proposed PC roster

Edit this list — confirm, rename, remove, or add. Names not in this list will
be treated as NPC candidates in Phase 3 (with a safety-net ASK at per-doc
review for any unknown named character). Empty the list if you have no PCs to
add yet — you can add them later by re-running `/ingest` against a PC-roster
doc or by hand-editing `pcs/`.

To add a PC: add a new line with the slug. Optional one-line description
after a tab or two spaces becomes the stub file's body. Nicknames go in
`— alias: <name>` suffixes (multiple aliases comma-separated).

silas         — appears in 5 docs (session logs 1, 3, 5, 7, 9). Likely PC.
rae           — appears in 5 docs. Likely PC.
betha         — appears in 4 docs. Likely PC.
gaelan        — appears in 5 docs. Likely PC.
helerel       — appears in 3 docs, often as "Helly". Likely PC. — alias: Helly
maren         — appears in 1 doc. Possible NPC (one-off mention).
the-shadow    — appears in 1 doc. Possible NPC alias.
```

If the skim found no PC candidates, write a roster file with the same header and a single line below it explaining the empty state:

```markdown
# Survey: proposed PC roster

(No PC candidates surfaced from the skim. Add PC slugs here as needed — one
per line, optional `— alias: <nickname>` suffix — or leave empty and add PCs
later by hand-editing `pcs/` or running `/ingest` against a PC-roster doc.)
```

The staging file is presented alongside `survey-descriptions.md` in the same review batch per ADR-0018 — one continue/cancel prompt covers both files, and a single in-chat verbal refinement loop revises either staged file in place per [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). The orchestration of the dual-file review (the continue/cancel/refinement prompt, the verbal-refinement loop) lives in the consuming skill's SKILL.md; this reference owns the roster file's shape and content.

## Parsing the GM-edited roster

On continue, re-read `.ttrpg-staging/survey-pcs.md` from disk to capture GM edits. Each non-comment, non-header line is a surviving PC entry. Extract:

- The **slug** — the GM-confirmed slug from the line (post-edit, post-refinement). On any GM addition where the GM supplied a name rather than a slug, slugify per the `dedup-matching.md` normalization rule before recording.
- The optional **one-line description** — anything after the slug and before the dash-separated frequency/classification annotation, when the GM added or kept one. Becomes the stub file's body.
- The **aliases** — any `— alias: <name>` suffix on the line. Multiple aliases are comma-separated.

An empty roster (no entries) is allowed and means "no PCs yet" — proceed.

GM-corrected PC roster entries become the campaign's PC roster the moment Phase 2 hands off to Phase 3 — Step 5 stages `pcs/<slug>.md` stubs from the surviving roster lines and promotes them to the campaign repo. The roster steers every subsequent Phase 3 extraction: candidate names matching a PC slug or `aliases:` entry resolve to PC (see `reference-note-extraction.md` "PC vs NPC discriminator"), and the Phase 3 safety net catches PCs the survey missed.

## Stub staging and promotion to `pcs/<slug>.md`

For each surviving PC roster entry, draft a stub file per the shape below and stage it at `.ttrpg-staging/pcs/<slug>.md` per `staging-pattern.md` Section 2 (CREATE entries: Write the full proposed content):

```yaml
---
kind: pc
aliases: [<nickname1>, <nickname2>]
---

# <Canonical Name>

<Optional one-line body from the GM-enriched annotation, if any.>
```

Rules:

- The slug is the GM-confirmed slug from `survey-pcs.md` (post-edit, post-refinement).
- The H1 is the GM-confirmed canonical name. When the staged roster line was `silas — appears in 5 docs…`, the H1 is `Silas` (the prose-readable form of the slug); when the GM provided an explicit canonical name (`silas Silas Stoneforge — appears…`) use that.
- `aliases:` carries the `— alias: <name>` entries from the staged line. If there are no aliases, omit the key entirely (per `frontmatter-schemas.md` Reference-note default — absent reads as `[]`).
- Body is the optional one-line description from the GM-enriched annotation. If the GM didn't enrich the annotation, omit the body — leave the file as H1-only after the frontmatter. (Per ADR-0018, the stub is intentionally minimal; #57's PC backstory ingestion will extend the body later.)

### Collision check before promotion

Stage every PC stub before promoting any. If a stub's slug collides with an existing `pcs/<slug>.md` file in the campaign repo (which would only happen if the GM is running `/ingest` against an already-populated campaign — uncommon for fresh ingest), **STOP** and surface the collision: *"PC roster includes `silas`, but `pcs/silas.md` already exists. Update existing, rename, or skip?"* Don't silently overwrite a GM-authored PC file.

### Promotion

After all stubs are staged and no collisions remain, promote them to `pcs/<slug>.md` by translating the staging path (strip `.ttrpg-staging/pcs/` prefix → `pcs/<slug>.md`). Create the `pcs/` directory if it doesn't exist. Delete each staged stub after promotion. After all stubs are promoted, remove `.ttrpg-staging/pcs/` if it's now empty.

The promotion happens **inside Phase 2**, before Phase 3 begins, so the PCs are visible to Phase 3's `pcs/` enumeration (used by Reference-note extraction's PC-vs-NPC discriminator and by Beat `linked_pcs:` population).

If the GM-confirmed roster was empty, skip stub staging and promotion entirely — no PCs to write. Note the empty roster in the hand-off summary.

## Cancel path

On cancel during the survey review, delete any staged `.ttrpg-staging/pcs/` directory (defensively, in case stubs were written) along with the survey staging files. Write nothing else to the campaign repo. The PC roster proposal produces no side effects outside `.ttrpg-staging/` until the GM confirms.

## What this reference does not own

- **The dual-file review prompt** (continue / cancel / verbal refinement covering both `survey-descriptions.md` and `survey-pcs.md`) — orchestration, lives in the consuming skill's SKILL.md per ADR-0018.
- **The per-doc description proposal** (`survey-descriptions.md`) — see the consuming skill's SKILL.md.
- **The processing-order proposal** (`survey-order.md`, multi-doc only) — see the consuming skill's SKILL.md.
- **The Phase 3 PC-vs-NPC safety-net ASK** for late-addition PCs — see the consuming skill's SKILL.md and `reference-note-extraction.md` "PC vs NPC discriminator."
- **The carried-forward "PC identity confirmation" lesson shape** — see the consuming skill's SKILL.md.
