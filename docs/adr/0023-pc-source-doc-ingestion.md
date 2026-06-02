# PC source-doc ingestion and `pcs/<slug>.md` shape

[ADR-0022](./0022-pc-roster-via-explicit-classification.md) (superseding [ADR-0018](./0018-pc-roster-as-survey-deliverable.md)) refined PC roster proposal to GM-explicit classification + existing-`pcs/` enumeration + a reserved auto-add section for source docs the GM classifies `PC source: <slug>`. That ADR explicitly deferred the `PC source:` classification mechanism, the per-doc routing, and the cross-extraction shape to slice H2 of v0.3 (the v0.3 grilling outcome on [PRD #80](https://github.com/snlemons/game_manager/issues/80) folded [#57](https://github.com/snlemons/game_manager/issues/57) into the grilling scope; H1 landed the roster refinement, H2 lands the source-doc ingestion).

This ADR pins the slice-H2 design: **`PC source: <slug>'s backstory` joins the existing four survey description classifications, Phase 3 routes those docs into a PC-specific extraction branch that appends backstory prose to the PC's body and cross-extracts named NPCs / Locations / Factions / Items into Reference notes pointing back at the PC, those Reference notes carry the PC in `belongs_to:`, the PC file gains symmetric `## NPCs` / `## Locations` / `## Factions` / `## Items` bidi-link sections (and the Reference notes carry `## PCs` sections back), and the PC's frontmatter gains three optional fields (`player:` / `class:` / `level:`) populated only when the source doc supplies them.**

The decision is [#57](https://github.com/snlemons/game_manager/issues/57)'s **Option C** (per-doc PC source classification + PC-as-container cross-extraction with symmetric bidi-links) + **selective B** for the optional frontmatter (player / class / level only, not the full stat schema).

## Why now

Three converging signals:

- **ADR-0022 reserved the slot.** The `## Auto-added from PC source: docs` section in `references/pc-roster-proposal.md`'s staged file format is a placeholder waiting for a recognizer and a routing rule. Leaving it empty indefinitely means the refined roster mechanism remains incomplete — the GM has no way to declare a PC source doc as such, and the agent has no signal to drive PC body enrichment.
- **Dogfooding revealed the GM-typed-adds path is insufficient for backstory.** A GM running `/ingest` against a directory containing PC backstories has to: (a) type the PC's slug into `## Add other PCs here` at the survey, then (b) hand-edit the PC stub later to paste in the backstory, then (c) walk the backstory to extract Reference notes the agent could have surfaced from a full read. Each step is friction the agent could eliminate; the friction compounds with multiple PC source docs in one input directory.
- **PRD #80's grilling consolidated #57 into the v0.3 critical path.** The original #57 ticket targeted a future slice; the grilling outcome moved it into v0.3 H2 alongside the roster refinement so the two interlock cleanly.

The strict reading: v0.3 H1 paid the cost of refining the roster mechanism without delivering the user-visible benefit (PC backstories still required hand-editing). H2 delivers the benefit by composing on top of H1's roster surface.

## The four pieces

H2 lands four things, each independently load-bearing:

### 1. `PC source:` survey classification

The bounded skim that drafts one-line descriptions per doc gains a fifth classification: `PC source: <slug>'s backstory`. The skim *strongly* suggests the classification when the skimmed prose shows backstory-shape signals — single-named-subject narrative, backstory-typical headings (Background / Origin / Family / History), PC-doc structural signals (filename or H1 naming one character). When uncertain, the skim surfaces `Mixed / ambiguous:` so the GM disambiguates at Step 3 review rather than the agent guessing.

The classification's slug is derived from the named-subject's canonical name per `dedup-matching.md` normalization. The GM owns the slug at Step 3 review — the agent's proposal is editable, and the edited slug flows through to both the roster auto-add and the eventual PC stub.

The skim does **not** open a PC source doc fully — bounded skim discipline still applies (~200 words). The classification proposal is from the skim signals only; full extraction is Phase 3's job.

### 2. Phase 3 routing into the PC source extraction branch

Phase 3's Step 2 full-read uses the GM-confirmed classification as a routing input. Docs classified `PC source: <slug>` enter a PC-source-specific extraction branch that composes with the general extraction branch:

- The general branch still runs (Reference notes / Threads / Consequences / Beats / Secrets — all extract by their normal heuristics).
- The PC source branch *adds* body enrichment + cross-extraction with PC-as-container linkage on top.

The two branches do not conflict — the PC source branch's outputs are additive (a PC body append + cross-extracted Reference notes whose `belongs_to:` includes the PC + frontmatter slice fields). The general branch's outputs for the same doc (e.g., a Beat the GM wrote into the backstory file alongside the prose) flow through as usual.

### 3. PC body enrichment + cross-extraction with PC-as-container

The backstory prose appends to `pcs/<slug>.md`'s body. Per the **GM-owned-body / agent-maintained-bidi-sections boundary** below, the agent never overwrites pre-existing GM-authored body content — the append is additive, with pre-existing body prose preserved verbatim above the new content. When the PC file is the minimal H1-only stub Phase 2 produced, the backstory simply becomes the body.

Named NPCs, Locations, Factions, and Items in the backstory become Reference notes by the universal Reference-note extraction heuristic — *with* an extra `belongs_to: [pcs/<slug>.md]` entry on each note's frontmatter. The `belongs_to:` field on Reference notes mirrors the same field on Secrets per ADR-0014's multi-container ownership pattern (the field semantically means "this Reference note is owned by these PC containers as cross-extraction targets" — same field name, same shape, different artifact class).

The bidi-link maintenance per `bidi-link-maintenance.md` § "PC as container" writes symmetric sections on both the PC and the Reference note:

- The PC file gains a `## NPCs` / `## Locations` / `## Factions` / `## Items` section (per the Reference note's kind) wiki-linking the Reference note.
- The Reference note gains a `## PCs` section wiki-linking the PC.

The pattern is the same shape as Secrets per ADR-0014 — bidirectional, content source-of-truth on one side, derived view on the other, idempotent maintenance, lint surfaces drift. The only differences from Secrets are the section names and the content side (Reference note vs Secret).

### 4. Optional frontmatter slice

When the backstory doc supplies them explicitly, populate three optional PC frontmatter fields per `frontmatter-schemas.md` PC schema:

- **`player:`** — string. The player at the table who controls this PC.
- **`class:`** — string. The PC's character class (multi-class composites valid as a single string).
- **`level:`** — positive integer. The PC's character level.

Each field is independently optional. Absent fields are valid and remain the default. The agent never invents values; it populates only when the source supplies the field explicitly (a metadata header, a "Player: …" line, an opening-narration class declaration). Discrepancies between source and pre-existing GM-set values surface as Step 4a ASKs; the GM's value wins by default.

## GM-owned body / agent-maintained bidi sections boundary

The PC file has a structural ownership boundary that ADR-0014's `## Secrets` pattern only implicitly carries (Secret's container files were defined as "the container owns its body; the agent owns the `## Secrets` section"). ADR-0023 makes the boundary explicit for PCs because the PC body is the primary surface where GM-authored content lives (the campaign repo's owner is the GM; PCs are the most-edited files in dogfooding):

- **GM-owned body** — the body prose above the first agent-maintained section heading. Everything from H1 to (but not including) the first `## NPCs` / `## Locations` / `## Factions` / `## Items` / `## Secrets` heading is GM territory. The agent **never** modifies this region except via additive append during Phase 3 PC source extraction. The append is a proposal staged for GM review at Step 4b; the GM may accept, trim, or reject.
- **Agent-maintained bidi sections** — the kind-named sections at the end of the file (`## NPCs` / `## Locations` / `## Factions` / `## Items` / `## Secrets`). Each section is a derived view: bullet lines wiki-linking to Reference notes (or Secrets) that claim this PC as a container via their `belongs_to:`. The agent rewrites these sections on every relevant write per the bidi-link maintenance algorithm. The GM may hand-edit (rare; surfaces as lint findings if it breaks symmetry); the agent reasserts canonical bullets on the next write.

The boundary is structural — placement of agent-maintained sections at end-of-file means the GM's body content is "above" the agent's sections; the agent's section maintenance never bleeds upward. The boundary lets the GM treat the PC file's body as their authoring surface without losing the agent's symmetric-link maintenance benefits.

This boundary applies to PC files specifically because PCs are the most heavily GM-authored containers in the campaign. The same boundary applies *implicitly* to NPC / Location / Faction / Item containers under ADR-0014's Secrets pattern — the body is the GM's one-liner (or longer prose if the GM hand-edited), the `## Secrets` section at end-of-file is agent-maintained. PCs make it explicit because the asymmetry of GM-authored content is greatest there.

## Why selective B frontmatter, not full stats

The original [#57](https://github.com/snlemons/game_manager/issues/57) considered three frontmatter options:

- **Option A**: no frontmatter beyond H2's existing `kind: pc` + optional `aliases:`. Backstory enrichment via body only.
- **Option B**: full stat schema (HP, AC, abilities, proficiencies, equipment, spells, features) — a structured PC stat block.
- **Option C** (combined with body enrichment + cross-extraction, the design adopted here): a *selective* B slice — `player:` / `class:` / `level:` only.

The grilling outcome on PRD #80 picked C+selective-B because:

- **Option A leaves out lightweight metadata the GM would actually populate.** Player name, class, level fit on three lines and surface cleanly in `/prep-session` Brief content, `campaign.md` party section rendering, and per-PC Beat / Secret routing. Leaving them out forces the GM to re-encode the same information in the body prose or hand-edit later.
- **Option B over-commits.** A full stat schema bakes a specific RPG system's mechanics into the campaign repo (D&D 5e? Pathfinder 2e? Powered by the Apocalypse?). v0.3 is system-agnostic; the agent does not run mechanics, does not enforce stat blocks, does not differ behavior by class. A full stat schema becomes maintenance burden without delivering load-bearing capability. v0.3 dogfooding does not justify the cost.
- **Selective B (player / class / level) is the floor that doesn't depend on system.** The three fields are nearly universal across tabletop RPGs (some systems use different vocabulary, but the concepts map); they're descriptive metadata rather than mechanics; they don't bind the agent to system-specific schema evolution. Adding system-specific fields later is a forward-compatible extension — the schema is open.

**Deferred-stats rationale.** A full PC stat schema is out of v0.3 scope. The deferral is intentional, not an oversight. If a future v0.4+ slice introduces system-specific stat blocks (perhaps gated by `system:` declarations in `campaign.md`), the schema extends from this slice's three optional fields rather than replacing them. The deferral allows H2 to land the user-visible improvement (PC body enrichment + cross-extraction) without committing to system-specific design that needs more dogfooding to scope.

## Composition with prior ADRs

ADR-0023 composes with — does not supersede — three prior ADRs:

- **ADR-0022 (refined PC roster mechanism, per slice H1).** The `## Auto-added from PC source: docs` section in `survey-pcs.md` is the integration point. ADR-0022 reserved it; ADR-0023 specifies what populates it (docs classified `PC source: <slug>`). The roster mechanism, the stub shape at Phase 2 promotion, and the Phase 3 PC-vs-NPC safety net all stay as ADR-0022 specifies; this ADR adds the per-doc routing and the per-doc enrichment that the auto-add docs go through in Phase 3.
- **ADR-0018 (PC roster as Phase 2 deliverable, now superseded by ADR-0022).** ADR-0018 explicitly mentioned `#57` as the future composition slice for PC backstory. This ADR is that composition, with the candidate-source change ADR-0022 introduced built in (the auto-add is upstream of the per-doc routing; both are downstream of ADR-0018's roster-as-Phase-2 framing).
- **ADR-0014 (Secrets as multi-container lifecycle objects, with bidirectional `## Secrets` link maintenance).** The PC-as-container bidi-link pattern in `bidi-link-maintenance.md` § "PC as container" mirrors the Secrets pattern exactly. The same maintenance algorithm shape applies (symmetric writes, idempotent re-apply, lint surfaces drift, writer authors canonical slug-path form). The only differences are the section names and the content-side artifact (Reference note vs Secret). The pattern's reuse is deliberate — having two symmetric-link patterns with different shapes would be unnecessary divergence; reusing the Secret pattern's machinery means the lint and maintenance code in `tests/test_bidi_link.py` extends cleanly.

ADR-0023 does **not** supersede any prior ADR. The roster mechanism stays. The Secret pattern stays. The bounded-skim discipline stays. The general extraction branch in Phase 3 stays. This slice composes on top.

## Consequences

- `references/extraction-pipeline.md` adds `PC source: <slug>'s backstory` to Step 2's classification list; adds a "PC source: classification rules" subsection under Step 2; adds a "PC source: extraction branch" subsection under Step 2; updates Step 4b's staging table to include PC body enrichment and PC-as-container back-references; updates Step 5's move-to-final-location ordering to handle the new bidi pattern.
- `references/reference-note-extraction.md` adds a "PC source: cross-extraction" section describing how named NPCs / Locations / Factions / Items in backstory prose become Reference notes with PC `belongs_to:`; adds a "PC source body enrichment" section describing the additive append; adds a "Optional frontmatter slice" section describing player / class / level population.
- `references/bidi-link-maintenance.md` adds a "PC as container" section mirroring the Secrets pattern. The Reference Python at `tests/test_bidi_link.py` extends to cover the PC-as-container case under a `TestPcAsContainer` test class.
- `references/pc-roster-proposal.md` populates the `## Auto-added from PC source: docs` section's mechanics — what populates it (docs classified `PC source: <slug>`), how the parser interprets entries, the empty-state body for when no `PC source:` docs are in the input. The placeholder prose ADR-0022 left behind is replaced with the H2 mechanism.
- `references/frontmatter-schemas.md` adds `belongs_to:` as an optional Reference-note field (for cross-extracted Reference notes pointing back at PCs); adds `player:` / `class:` / `level:` as optional PC-only fields; adds a worked example of a PC after PC source extraction; updates Defaults at creation to cover Phase 3 PC source UPDATE.
- `CONTEXT.md`'s PC entry gains a clarification about the GM-owned-body / agent-maintained-bidi-sections boundary, plus a mention of cross-extracted Reference notes and the optional frontmatter slice.
- `tests/test_reference_note_extraction.py` (new file) covers the PC source cross-extraction heuristic — named entities from backstory get extracted with PC in `belongs_to:`, the PC stays out of NPC extraction, the body append is additive (preserves prior content).
- `tests/test_bidi_link.py` extends with `TestPcAsContainer` covering: bidi sections written symmetrically on PC and Reference note, idempotent re-apply, lint detects drift on PC-as-container pairs.
- `tests/test_frontmatter.py` extends `TestPcStubShape` to cover the optional `player:` / `class:` / `level:` fields: parsed when present, absent when not supplied, do not break validation.
- `tests/test_pc_roster_proposal.py` extends to cover `PC source:` auto-add behavior: a doc classified `PC source: <slug>` auto-adds the slug to the staged roster's `## Auto-added from PC source: docs` section; the parser distinguishes auto-added entries from existing and GM-typed entries.

## What this ADR does not commit to

- **A full PC stat schema** — deferred, per "Why selective B frontmatter" above.
- **A PC `## Threads` / `## Consequences` / `## Beats` bidi pattern** — Threads / Consequences / Beats are ephemeral or per-Adventure objects; they don't fit the multi-container ownership pattern. PCs already surface through Beat `linked_pcs:` and Secret `belongs_to:` PC containers — those existing mechanisms suffice.
- **Re-running `/ingest` against the same PC source doc** — the per-doc commits Phase 3 makes (one per doc) handle re-run as a re-extraction; the body append is additive, so re-runs duplicate content unless the GM has trimmed. v0.3 leaves re-run semantics out of scope per `extraction-pipeline.md`'s v0.1 boundaries inheritance; future work may add a "this doc was already extracted, skip / re-extract / merge?" prompt.
- **Multi-PC backstory docs.** A single source doc whose subject is multiple PCs (a joint origin story) is out of scope. The recommended pattern is one source doc per PC. If a multi-PC backstory appears, the GM classifies it `Mixed / ambiguous:` and trims at Step 4b — the agent does not split a single doc into multiple PCs' branches.
- **Cross-extracted Reference notes inheriting the PC's optional frontmatter fields** — `player:` / `class:` / `level:` are PC-only. A Reference note cross-extracted from a PC source doc does not inherit them; the fields stay on the PC file.
- **Migration of existing campaigns** — none required. The mechanism applies only to future `/ingest` runs. Existing PC files in dogfood campaigns are pre-seeded by ADR-0022's mechanism and continue to work; PC source docs the GM later runs through `/ingest` extend them via the H2 mechanism.
