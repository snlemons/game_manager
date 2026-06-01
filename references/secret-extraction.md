# Secret extraction heuristic

When does a hint in source content (a session's `notes.md` for `/wrap-session`, a GM-authored source doc for `/ingest`) warrant proposing a new Secret, and what does the proposed file look like? This is the shared spec used by `/wrap-session` (Secret extraction pass) and `/ingest` (Phase 3 extraction over module-shaped or world-shaped source docs). The orchestration around extraction (cross-doc learning in `/ingest`, session-context dedup in `/wrap-session`) stays in each SKILL.md; this reference is just the heuristic and the default file shape.

The corresponding ADR is [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md) (Secret as the fourth lifecycle object). The Secret frontmatter schema lives in [`frontmatter-schemas.md`](./frontmatter-schemas.md). The dedup rule (slug normalization, `secrets/`-only scan, near-match prompt) lives in [`dedup-matching.md`](./dedup-matching.md). The bidirectional `## Secrets` link writes live in [`bidi-link-maintenance.md`](./bidi-link-maintenance.md). The store enumeration / query operations live in [`secret-store.md`](./secret-store.md).

## What counts as a Secret

A fragment of prose becomes a candidate Secret when:

- It states a **fact about the world** (not a future intention, not a past completed event the party caused) that the party may not yet know in full.
- The fact has a **non-ephemeral home** — at least one Adventure, NPC, PC, Location, Faction, or Item the fact attaches to. If the only plausible "container" is a Thread, a Beat, a Consequence, or the session itself, it is **not** a Secret per ADR-0014.
- The fact is **revelation-shaped**: there is something to learn that would change the party's understanding when they learn it. Color details that simply enrich a scene (a tavern's smell, an NPC's accent) are not Secrets even if the party doesn't notice them.
- The GM (or the source doc) is treating it as latent — phrased as a backstory note, a "what's really going on", a "secretly", a "the GM knows that…", a "behind the scenes". The shape of the prose is the strongest signal.

The defining test versus the other lifecycle objects:

| If the fragment is… | …it's a |
|---|---|
| A future obligation, question, or foreshadowed danger the party is aware of and may act on | **Thread** |
| A past fact resulting from the party's actions, now part of the world | **Consequence** |
| GM intent to deliver a scene / news / handout / character moment in play | **Beat** (and possibly `kind: clue` with `linked_secrets:` pointing at the Secret it reveals) |
| A latent fact about the world the party may not know, attached to ≥1 non-ephemeral container | **Secret** |

A single fragment may legitimately produce both a Beat and a Secret (the Beat is the planned delivery of a Clue; the Secret is the underlying fact). When that's the right read, propose both and explain the split to the GM at the review step — the same posture as the Thread-vs-Consequence split documented under `/wrap-session` Pass 5.

## Prose shapes that suggest a Secret

In a session's `notes.md`:

- *"The party doesn't know yet that Maren is the cult's contact."*
- *"GM note: the vault key is hidden in the temple's apse."*
- *"Behind the scenes, Jhera survived the purge — she's underground in the Silent Court."*
- *"Set up: the Prism core is cursed. Reveal slowly."*
- *"Save for later — the duke has a half-dragon son."*

In a GM-authored source doc (module-shaped):

- A `## Secrets and Lies` / `## Adventure Background` / `## What's Really Going On` section. Every distinct fact in such a section is a candidate Secret.
- A villain motivation paragraph that says, in effect, "what the antagonist actually wants" as distinct from "what the antagonist appears to want."
- An NPC entry that includes a "Secret:" or "Hidden:" or "Behind the scenes:" labelled fact.
- A location description that includes a "Hidden feature:" or "The party can discover that…" fragment.

When borderline, prefer to **propose** the Secret and let the GM reject or rename it at review than to drop it silently. False positives are cheap (one delete in staging or one "no, that's just narrative color" answer in ambiguity clarification); false negatives are invisible.

## Prose shapes that are NOT Secrets

Reject these even if they look plausible at a glance:

- **Already a Consequence.** "The bridge is destroyed." The party caused it; the party knows; it's a past fact, not a latent one.
- **Already a Thread.** "The party promised the captain they'd look into the missing caravan." Future-facing, party-aware, party-driven — Thread.
- **Just a Beat.** "Land the warfront news next session." That's GM intent to deliver, not a latent fact the world contains. (If the news *itself* is a latent fact — e.g., "the duke is dead and the regent is hiding it" — propose the Beat AND the underlying Secret.)
- **Color without revelation shape.** A tavern's smell, a banner's color, an NPC's accent. Adds flavor; nothing changes when the party "discovers" it.
- **Player-secret rather than world-secret.** "Darius's player hasn't told the rest of the table that his PC is the duke's bastard." That's a PC secret the GM is tracking out-of-character; it doesn't live in the campaign world model and isn't a Secret in this sense. (If the GM wants to track it, that's their call — but `/wrap-session` and `/ingest` don't propose it.)

## Container set (`belongs_to`)

Per ADR-0014 and the Secret schema in `frontmatter-schemas.md`, every Secret's `belongs_to:` is a non-empty unordered list of paths to non-ephemeral containers. The canonical set:

- `adventures/<slug>/` — Adventure container (directory form, trailing slash)
- `npcs/<slug>.md` — NPC
- `pcs/<slug>.md` — PC
- `locations/<slug>.md` — Location
- `factions/<slug>.md` — Faction
- `items/<slug>.md` — Item

Ephemeral paths (`threads/`, `beats/`, `consequences/`, `sessions/`, `.ttrpg-staging/`) are rejected — the validation algorithm in `secret-store.md` (`validate_belongs_to`) refuses to write a Secret whose `belongs_to:` is empty or contains only ephemeral paths.

### Drafting `belongs_to` at extraction time

The extracting skill drafts a `belongs_to:` list as part of the proposal so the GM has something concrete to confirm or correct, not a blank field to fill from scratch. The draft uses these signals in order:

1. **Named entities in the same sentence / paragraph.** "Maren is the cult's contact" mentions Maren → draft `npcs/maren.md`. "The vault key is hidden in the old temple's apse" mentions the temple → draft `locations/old-temple.md`.
2. **Enclosing structural context.** In a source doc, the heading the fragment lives under names the container — a fact in the `## Curse of the Prism Core` section of an Adventure doc drafts `adventures/curse-of-the-prism-core/`. In session notes, the Adventure the party is running this session (if exactly one is in clear focus) is a reasonable draft for facts that don't name a specific NPC / location.
3. **Backreferences in the prose.** "Behind the scenes for the Prism arc, Jhera survived" names both the Adventure (`adventures/the-prism/`) and Jhera (`npcs/jhera.md`); multi-container draft.
4. **Don't invent containers.** If the draft would require creating a Reference-note file (or an Adventure directory) that doesn't exist yet, surface the dependency to the GM at ambiguity clarification — don't silently scaffold a new container from a Secret write. The GM names the entity (or confirms the slug) first; then the Secret write proceeds.

When in doubt between one container and several, draft **all** the plausible ones — the GM trims at approval. Over-attribution is a one-keystroke fix; under-attribution surfaces only when a later query misses the Secret it should have found.

### Validation

Run the candidate `belongs_to:` list through the validator from `secret-store.md` (`validate_belongs_to`) before staging the Secret file. The validator rejects:

- empty lists (no containers proposed),
- all-ephemeral lists (only `threads/`, `beats/`, `consequences/`, `sessions/`, `.ttrpg-staging/` entries),
- unknown folder roots (typos like `npc/maren.md` — missing the `s`).

If validation fails, surface the failure to the GM at ambiguity clarification rather than writing an invalid Secret.

## Filename — slug rule

Filenames are slugs of the canonical Secret name, normalized by the rule in `dedup-matching.md`. The Secret's canonical name is the H1 in the file body — usually a short factual statement: *"Maren is the spy"*, *"The Prism core is cursed"*, *"Vault key in the temple"*, *"Jhera survived the purge"*.

Files live at `secrets/<slug>.md`. One file per Secret.

## Default body — fact-shaped

The body opens with the H1 (the canonical name) and is one or two sentences stating the fact for the GM. The Secret file is for the GM, not for the players — write the fact plainly. Use `[[wiki links]]` to the containers in `belongs_to:` and to any other Reference notes the fact touches, so backlinks resolve.

Example:

```markdown
---
status: hidden
belongs_to:
  - npcs/maren.md
  - adventures/the-prism/
revealed_by: []
---

# Maren is the spy

[[Maren]] has been feeding caravan-route intelligence to the cult for two seasons. She's the inside contact the party has been trying to identify since the [[the-prism|Prism arc]] opened. Her cover is impeccable — she sells the party rumors that almost implicate Joran, the obvious red herring.
```

Length scales with how much the source supplies. A one-sentence Secret is fine; do not pad. Do not invent backstory the source doesn't give.

## Dedup at extraction time

**Before staging any new Secret, apply the dedup rule from `dedup-matching.md`** scoped to the `secrets/` folder (the rule is `secrets/`-only per ADR-0014). The query operation lives in `secret-store.md` (`find_dedup_candidates`); it returns Secrets whose slug or first-heading title normalizes to the same form as the candidate name.

The three buckets:

- **CREATE — no match.** Proceed with a new Secret file at the candidate's slug.
- **Confident UPDATE — same slug, same kind, no contradicting context.** The candidate is the same Secret as an existing one. Two sub-cases:
  - Same `belongs_to:` set. UPDATE the existing Secret's body (append the new fact or merge the prose) — never lose GM-authored prose.
  - **New container in `belongs_to:`.** The candidate extends an existing Secret's ownership. Propose adding the new container to `belongs_to:` rather than creating a duplicate Secret file. The bidi-link maintenance pass then writes the `## Secrets` section into the new container.
- **ASK — near-match or ambiguous.** Surface to the GM with the prompt shape from `dedup-matching.md`: *"You may already have this Secret at `secrets/<existing-slug>` — merge, separate, or rename?"* The merge response converts to UPDATE; separate converts to CREATE at a disambiguated slug the GM names; rename converts to UPDATE with the existing file renamed.

The dedup check is what makes `/wrap-session` re-runs and `/ingest` cross-doc passes idempotent against the same Secret material. Skipping it produces duplicate `secrets/` files that drift on subsequent writes.


## Module-source extraction (ingest-specific)

This section is the `/ingest`-specific extension of the universal heuristic above. It applies during Phase 3 (per-doc extraction loop) when the source doc has been classified as Adventure-shaped (per the survey description or the GM's Step 1 override) and has explicit Secret-bearing sections.

### Section-heading signals

Module-shaped source docs commonly partition GM-only content from player-facing content via section headings. Treat these headings as **strong** signals that the prose underneath is Secret-bearing:

- **"Secrets and Lies"** (or "Secrets & Lies") — the canonical module convention. Every fact under this heading is a Secret candidate. Most modules write the section as a bulleted list of one-line facts; extract one Secret per bullet.
- **"Adventure Background"** (or "Background" inside an Adventure section) — typically a prose section establishing the hidden truth behind the surface plot. Extract Secrets from the load-bearing facts (who is really behind it, what really happened, what the party is being lied to about). Skip framing prose ("centuries ago, the kingdom was at peace…") — that's setting context, not a hidden fact.
- **"DM-Only"** / **"For the DM"** / **"GM Notes"** — explicitly GM-eyes-only sections. Treat as Secret-bearing by default; extract per-fact. Watch for the substitution: some published material uses "DM" while the campaign repo's vocabulary uses "GM." Translate when extracting (the extracted Secret's body should use "GM" — or, more typically, no role label at all since the body is the fact, not GM instructions).
- **"Hidden Information"** / **"Hidden Truth"** — analogous to "Secrets and Lies"; one Secret per fact.
- **"What's Really Going On"** / **"The Truth"** / **"Behind the Scenes"** — narrative-shaped reveals; extract the load-bearing facts as Secrets.
- **Subsections under any of the above** — e.g., "Secrets and Lies → About the Mayor" — the subsection heading often names the container the Secret belongs to (here, the mayor's NPC). See "Multi-container `belongs_to` population" below for how that signal flows into the `belongs_to:` set.

A section heading whose **content** is GM-eyes-only but whose **name** doesn't match the patterns above (e.g., the writer used "Notes for the GM" or just "Notes") is still Secret-bearing — the heading-name signal is a *positive* trigger; absence of a known heading doesn't mean the content is player-facing. When the agent has uncertainty about whether a section is GM-only, surface it at the per-doc review as an ASK alongside any candidate Secrets extracted from it: *"Section 'Notes' in chapter 2 reads as GM-only background — extract its facts as Secrets, or treat it as Reference-note content?"*

### Multi-container `belongs_to` population

The ingest case has more structural signal than wrap-session: the source doc is itself adventure-shaped (so the Adventure container is automatic), and the Secret's prose often names specific NPCs, Locations, Factions, or Items the Secret is *about*. Use both signals:

1. **Adventure container is automatic.** Every Secret extracted from an adventure-shaped source doc gets `belongs_to:` containing **at minimum** the slug of the Adventure being ingested, in the form `adventures/<slug>/`. This is the structural link — the Secret was found *inside* the Adventure's source doc, so the Adventure is its container by construction. Do not skip this entry even when the Secret's own prose doesn't name the Adventure.

2. **Named-entity expansion — proximity rule.** Scan the Secret's prose (the body the extractor would write) for **named** NPCs, Locations, Factions, and Items. For each named entity that resolves to:
   - A Reference note already present in the campaign repo (under `npcs/`, `locations/`, `factions/`, or `items/`), **or**
   - A Reference note being CREATEd from earlier docs in this same `/ingest` run, **or**
   - A Reference note being CREATEd from this same doc (i.e., named in this same Adventure's prose),

   add that entity's container path to `belongs_to:`. The matching uses the same slugification rule as `dedup-matching.md`. The proximity radius is *the Secret's own body* — the prose the extractor is writing for the Secret file, not the surrounding section. If an entity is named in the same section but not in the Secret's own fact, it's adjacent context, not a container.

   Worked example. The source doc has:

   ```markdown
   ## Secrets and Lies

   - **The mayor secretly funds the cult.** Mayor Brennan diverts town
     funds to the [[Silent Court]] through a shell merchant in the
     [[Old Temple]] district.
   ```

   Extract one Secret with body *"Mayor Brennan diverts town funds to the [[Silent Court]] through a shell merchant in the [[Old Temple]] district."* and `belongs_to:`:

   ```yaml
   belongs_to:
     - adventures/the-prism/        # the ingested Adventure (automatic)
     - npcs/mayor-brennan.md        # named in the Secret's prose
     - factions/silent-court.md     # named in the Secret's prose
     - locations/old-temple.md      # named in the Secret's prose
   ```

3. **Subsection-heading expansion.** When a Secret is found under a subsection whose heading names a container (e.g., `### About the Mayor` under `## Secrets and Lies`), add that container to `belongs_to:` even if the Secret's own body doesn't repeat the name. The enclosing heading is the GM's implicit scope tag for the Secrets underneath, analogous to the Beat shape's "heading rule" for `linked_locations` in `skills/ingest/SKILL.md` Step 3.

4. **PC containers — explicit attribution only.** A Secret may belong to a PC (`pcs/<slug>.md`) if the source material *explicitly* names the PC as the subject ("Darius's hidden parentage", "the truth about Sera's brother"). Generic mentions ("one of the party"; "a PC who carries the medallion") do not justify a PC container. PCs are author-collaborative; the GM resolves PC-tied Secrets at review rather than the agent guessing.

5. **Cross-kind ambiguity.** A name that matches Reference notes in multiple kind folders (e.g., "Veil" matches both `npcs/veil.md` and `factions/the-veil.md`) surfaces as an ASK at Step 4a inline-dedup resolution, the same shape as cross-kind dedup ASKs.

6. **Default to a smaller set on doubt.** If the proximity rule would expand `belongs_to:` to many containers and the extractor is uncertain about the structural justification for one or more, surface those as an ASK alongside the Secret in the per-doc review: *"Secret 'Mayor secretly funds the cult' was extracted near mentions of the Silent Court (faction), the Old Temple (location), and the council chambers (location). Include any/all in `belongs_to:`?"* Don't guess; the GM has the campaign-shape context.

### Per-doc dedup against earlier docs in the same run

Cross-doc dedup against already-extracted Secrets matters: a module commonly **restates the same Secret across multiple chapters** ("Chapter 1: the mayor is secretly funding the cult." "Chapter 4: as established in chapter 1, the mayor funds the cult.").

Apply `dedup-matching.md` against the `secrets/` files written by earlier docs in this same `/ingest` run. A confident match proposes the merge action specific to Secrets (add the new container(s) to the existing Secret's `belongs_to:` rather than creating a duplicate). A near-match surfaces the multi-container reconciliation prompt at Step 4a, the same shape as the universal dedup prompt.

Lessons from the prior doc's dedup decisions carry forward via the same carried-forward-lessons mechanism Phase 3 already uses for Reference notes (see `skills/ingest/SKILL.md` Step 0b / Step 5b). A confirmed identity ("the mayor's funding Secret in chapter 4 is the same as the one in chapter 1") consolidates without re-asking on chapter 7.

### Extraction-time partial-reveal handling

`/ingest` runs against historical notes: source docs commonly describe past sessions where the party already learned part of a Secret. There is no in-flight Beat delivery to drive the `hidden → partially-revealed` status flip the way `/wrap-session` does, so the agent has to recognize the partial-reveal shape at extraction time and emit the right structure directly.

**Signals that a Secret is already partially revealed in the source.** Prose shapes to watch for:

- "The party learned in session 3 that the mayor's involved, but they don't yet know which faction."
- "By the end of chapter 2, the PCs have figured out the curse but not its source."
- "After the Whitebridge interlude, the players know Maren is a spy. They still don't know who she reports to."
- GM commentary on a Secret-bearing fact that says, in effect, "this much is out; this much isn't."

When the GM (in the source doc or at the per-doc review) confirms a candidate Secret has already been partly revealed in play, extract the four-piece structure below — **do not** restructure the Secret itself.

**The four-piece shape.**

1. **Extract the Secret with its body intact** — the full GM-known fact, written exactly as you would for a still-hidden Secret. The body is the underlying truth, not "the part the party doesn't yet know." Keeping the body whole preserves the auditable boundary: the Secret file always describes the complete fact, and the partial-reveal state is carried in frontmatter and linked Beats, not by editing the body.
2. **Extract the past scene that revealed part of it as a `kind: clue` Beat with `status: delivered`.** The Beat's body describes what the party learned in that scene — that is the auditable record of which portion is now out. The Beat's `linked_secrets:` points at the Secret. See `beat-extraction.md` for the Beat file shape and the `status:` field.
3. **Populate `revealed_by:` on the Secret** pointing at that delivered Beat (and any other prior Beats whose delivery contributed to the partial reveal). `revealed_by:` is the back-link from the Secret to the Clues that have landed against it.
4. **Set the Secret's `status: partially-revealed`** in frontmatter (instead of the default `hidden`).

This shape keeps the Secret surfacing through `/prep-session`'s Secret Push question (which filters on `status: partially-revealed`), keeps the GM-known fact intact for future Clue authoring, and gives the Beat-body description of what's out the same shape every other delivered Clue has. When the next partial reveal lands in play, `/wrap-session` adds another Beat to `revealed_by:` without needing to reconcile a fragmented Secret.

**Anti-pattern: do not split the Secret into a Consequence + tightened Secret.** It can feel auditable to extract the revealed portion as a Consequence ("the party knows the mayor is involved") and rewrite the Secret body to cover only the still-hidden portion ("the mayor funds the Silent Court"). **Do not do this.** Per ADR-0014, a Secret becomes a Consequence only when **fully revealed and acted upon** — a partial reveal is a *status*, not a structural decomposition. The split breaks four things at once:

- The Secret body no longer describes the full GM-known fact, so subsequent Clue authoring has to reconstruct what's still hidden from what's already out across two files.
- `/prep-session`'s Secret Push filter (`status: partially-revealed`) no longer surfaces the Secret, because the split Secret got rewritten as still `hidden`.
- The Consequence file carries a fact about the world that arrived through *party discovery*, not through *party action* — which is what Consequences are for (ADR-0014 line 18, ADR-0003).
- The bidirectional `## Secrets` back-references on the containers in `belongs_to:` now point at a Secret whose body has been narrowed; the symmetry the dedup rule depends on drifts.

If the source notes describe a past *action the party took* whose downstream world-state effect happens to also resolve part of a Secret (the party burned the mayor's records, so the funding link is now public knowledge in-world), that **action's outcome** is a Consequence on its own merits — extract it as a Consequence per `consequence-extraction.md`, and *separately* mark the underlying Secret partially revealed with the four-piece shape above. Two artifacts for two different facts, not one Secret cut in half.

**Carried-forward lesson capture.** A GM correction during per-doc review that confirms a Secret as partially revealed is a Step 5b lesson worth recording for the rest of the run — *not* the anti-pattern split, but the recognition signal: *"Doc 3: the GM treats 'the party learned X in session Y' commentary as a partial-reveal flag; extract the past scene as a delivered Clue Beat with linked_secrets, not as a Consequence."* The carried-forward-lessons surface in `skills/ingest/SKILL.md` Step 5b must never canonize the Consequence-split as a learned pattern; if a prior review accidentally landed on the split, drop it at the next review and reconstruct the four-piece shape.

### What not to extract from module sources

- **Surface plot.** A module's player-facing chapter prose is *not* Secret-bearing by default. Extract Reference notes and Beats from it; don't extract its public statements as Secrets even when they're load-bearing.
- **Stat blocks / monster details.** Mechanical content (HP, AC, attacks) is not Secret content even when it lives in a GM-only section. The agent extracts Reference notes for named monsters / NPCs as usual; stat blocks live in those notes' bodies (or in the source the GM keeps separately), not as Secrets.
- **Read-aloud / boxed text.** Player-facing prose, by construction.
- **Encounter design notes** (tactical advice, scaling guidance). GM-eyes-only but not *fact about the world*; these are about how to *run* the Adventure, not what is *true*. Skip.
- **Pre-existing Consequences.** If a module's "Adventure Background" section states a past event the party will encounter the aftermath of and the GM-confirmed description has the party already in the world post-event, that's a Consequence (past-facing world fact), not a Secret. The agent's classifier defaults to Secret when uncertain; the GM can re-classify at review.

## What this heuristic does not handle

- **Per-skill orchestration.** When the dedup ASK lands (Step 3 ambiguity clarification in `/wrap-session`, Step 4a inline resolution in `/ingest`), how the response feeds back into the staging set, how cross-doc lessons carry forward in `/ingest` — those stay in each SKILL.md.
- **In-play Secret status transitions.** `hidden → partially-revealed` and the `partially-revealed → revealed` prompt as **side effects of in-play Beat delivery** are `/wrap-session`'s job, not extraction-time decisions. See `skills/wrap-session/SKILL.md`. The separate case — `/ingest` discovering that a Secret in the source notes is *already* partially revealed because past sessions are baked into the source — *is* an extraction-time concern and is handled by the "Extraction-time partial-reveal handling" section above.
- **Bidirectional link writes.** Once the Secret is approved, writing the `## Secrets` section into every container in `belongs_to:` is the bidi-link maintenance algorithm in `bidi-link-maintenance.md`. The extraction heuristic stops at the file shape; the link maintenance is its own concern.
- **Cross-Secret queries.** "Which Secrets does this NPC own?" / "Which Secrets are partially revealed?" — those queries live in `secret-store.md` and are consumed by `/prep-session` (the Secret Push question) and `/wrap-session` (the Clue-delivery status flip).
