# Reference-note extraction heuristic

When does a name in a source doc or in-play notes warrant creating a Reference note, and what does the proposed file look like? This is the shared spec used by `/ingest` Phase 3 (extracting from GM-authored source docs) and `/wrap-session` Pass 2 (proposing Reference notes from a session's `notes.md`). The orchestration around extraction (cross-doc learning in `/ingest`, session-context dedup in `/wrap-session`) stays in each SKILL.md; this reference is just the heuristic and the default file shape.

The corresponding ADR is [ADR-0003](../docs/adr/0003-per-file-reference-notes.md) (one file per Reference note; default content is a one-liner).

## What counts as a Reference note

A name mentioned in source content becomes a Reference note when:

- It's a **named** NPC, location, faction, or item. Bare descriptors ("the innkeeper", "a guard") without a proper name don't qualify on their own — see "Missing or unclear names" below.
- The source content **introduces or describes the thing substantively** — gives it a role, a place in the world, a fact the agent will plausibly need to retrieve later by name.

A passing mention without role context is **not** a Reference note. Examples of mentions that *don't* warrant extraction:

- A list item in a roster the source doc enumerates for color but doesn't develop ("…among them Orin, Sera, and Maris, none of whom matter to the arc").
- A name dropped once as flavor with no follow-up ("the bard sang about Old Gristle the dragon").
- Generic NPCs the party interacts with mechanically but who aren't characters in the world ("the party haggled with the merchant").

When borderline, prefer to **propose** the Reference note and let the GM reject it at review than to drop it silently. False positives are cheap (one delete in staging); false negatives are invisible.

## Folder by kind

| Kind | Folder |
|---|---|
| NPC | `npcs/` |
| Location | `locations/` |
| Faction | `factions/` |
| Item | `items/` |

PCs live at `pcs/<slug>.md` but are **not** extracted by the Reference-note heuristic — they're established by GM confirmation (per [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md)), either at `/ingest` Phase 2 (Survey) via the PC roster review or at `/ingest` Phase 3 / `/wrap-session` Step 3 via the PC-vs-NPC safety-net ASK. See "PC vs NPC discriminator" below for how the heuristic treats `pcs/` as an exclusion set, not an extraction target.

Don't synthesize new kinds. If something doesn't fit one of these four (or PC, established separately), surface it to the GM rather than inventing a folder.

## Filename — slug rule

Filenames are slugs of the canonical name. Lowercase, ASCII-fold accents, strip leading "the ", collapse whitespace and punctuation to single hyphens, trim leading/trailing hyphens. See `dedup-matching.md` for the full normalization rule — Reference-note slugs use the same normalization as dedup matching so that a candidate slug and an existing filename collide cleanly.

Example: *"The Broken Mines"* → `the-broken-mines.md`. Wait — "the" gets stripped — `broken-mines.md`. *"Sera Stoneforge"* → `sera-stoneforge.md`. *"Café du Monde"* → `cafe-du-monde.md`.

## Default body — the one-liner

The default body is **one line** derived from the source content: who/what the thing is, in short factual prose. ADR-0003: the GM never fills out a form. Do **not** generate an "About" template, a stats block, or empty placeholder sections. One sentence, drawn from the source content, is the artifact.

Use `[[wiki links]]` to other Reference notes that the source content names — those resolve to backlinks the agent uses in later passes.

Example, NPC introduced in a session's notes:

```markdown
# Sera

Blacksmith in [[Phandalin]] who reports the mines were recently closed.
```

Example, location introduced in an ingest doc:

```markdown
# The Broken Mines

A network of half-collapsed tunnels east of [[Phandalin]], rumored to be cursed.
```

## Frontmatter — minimal by default

Reference notes **do not require frontmatter** in v0.1. If the source content gives a clear strong fact — kind, role, status — light frontmatter is allowed:

```yaml
---
kind: npc
---
```

When the entity has more than one name the campaign uses (a pseudonym, a title, a mask, an order name), add an `aliases:` list per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md):

```yaml
---
kind: npc
aliases: [The Shadow, Maren the Dockworker]
---
```

The canonical name (the file slug + H1) is the GM's choice at extraction-time review. The default proposal follows the ADR-0017 canonical-choice heuristic — real identity wins as canonical; pseudonyms, titles, and masks go in `aliases:` — but the GM picks at review and the GM's answer wins. See "Alias detection at extraction time" below for the prose patterns the agent watches for.

But:

- **Do not invent fields the source doesn't supply.** Empty placeholder fields are worse than no frontmatter.
- **Do not invent values.** If the source doesn't say where Sera is or what she does, the one-liner says only what the source said.
- **Do not invent aliases.** A name in the source that the agent suspects might be an alias but the source doesn't connect to the canonical entity is **not** added to `aliases:` silently — it's surfaced at review (see below) and either confirmed by the GM or treated as a separate candidate Reference note.

When a more specific schema is needed for an extracted object (a Thread, a Consequence, an Adventure, a Beat), that's not a Reference note — see `frontmatter-schemas.md`.

## PC vs NPC discriminator

Per [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md), the PC roster is established by GM confirmation — at `/ingest` Phase 2 (Survey), at the Phase 3 per-doc PC-vs-NPC safety-net ASK, or at `/wrap-session` Step 3 ambiguity clarification. The Reference-note extraction heuristic respects the established PC roster as an exclusion set:

- **A named character matching a `pcs/<slug>.md` filename or `aliases:` entry resolves to PC, never proposed as an NPC.** Apply the same matching rule used for NPC dedup (`dedup-matching.md`'s normalization — lowercase, ASCII-fold accents, strip leading "the ", collapse non-alphanumerics to hyphens, trim) against both the file's slug and each entry in its `aliases:` list. A hit means the candidate is the PC and no NPC Reference note is proposed.
- **A named character matching no `pcs/<slug>.md` AND no `npcs/<slug>.md`** is the safety-net case (per [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md)): in `/ingest` Phase 3, the candidate routes to the Step 4a PC-vs-NPC ASK (see `skills/ingest/SKILL.md`); in `/wrap-session`, the candidate routes to Step 3 ambiguity clarification with the same prompt shape. The GM's answer ("PC" or "NPC") determines the file's final location, and `/ingest` records the answer as a carried-forward lesson so subsequent docs in the same run apply silently.
- **The agent does not infer PC status from prose alone.** Frequency-of-mention and party-pronoun proximity are signals the Phase 2 survey uses to *propose* candidates, not to *commit* identities. Outside the survey, the agent always defers to the established roster + safety-net ASK shape.

Reference-note extraction never writes to `pcs/`. PC files are created by the survey roster promotion (`/ingest` Phase 2 Step 5a), by the safety-net ASK promotion (`/ingest` Phase 3 Step 4a, `/wrap-session` Step 3), or by `/prep-session`'s GM Focus Check new-PC disclosure handling (`references/prep-session-questions.md`, "New-PC disclosure handling"). The PC stub shape — `kind: pc` frontmatter, optional `aliases:`, H1, optional one-line body — is documented in `frontmatter-schemas.md` under "Reference note → Worked example: PC stub."

## PC-actor narrative framing as wrap-time discriminator

`/wrap-session` Pass 2 reads narrative prose the GM authored *during play* (the session's `notes.md`). The framing in that prose carries clearer PC-vs-NPC signal than the module-shaped or world-info-shaped prose `/ingest` reads, because the GM was at the table and the in-play voice naturally treats PCs as actors. The wrap-time discriminator leans on this: a named character narrated as the *actor* of party-shaped actions is a PC signal; a named character narrated as the *subject* (a person the party encountered, talked to, fought, helped) is an NPC signal.

This **inverts** the ingest-time discriminator. At ingest time the agent does *not* infer PC identity from prose because module-shaped docs have weak PC signals (the GM hasn't decided who the players are, the doc treats every named character with equal prose weight, and the GM owns the explicit `PC source: <slug>` classification via [ADR-0023](../docs/adr/0023-pc-source-doc-ingestion.md)). At wrap time the GM is the table's narrator and the prose-side signal is reliable enough that the agent can route most candidates without asking.

### PC-actor heuristic for Pass 2

For each named character in `notes.md` whose name doesn't match any existing `pcs/<slug>.md` filename or `aliases:` entry AND doesn't match any existing `npcs/<slug>.md` either (i.e., the standard Reference-note dedup pass would propose a CREATE under `npcs/`), evaluate the prose framing:

**PC-actor signals (route to `pcs/`):**

- **Subject-of-party-action framing.** The character is narrated as the actor performing actions the GM phrases the same way as actions by established PCs: *"Theron drew his sword and charged."* *"Veshenna picked the lock while the others kept watch."* *"Korben rolled to disbelieve and saw through the illusion."* The verb is something a PC does in play (combat, exploration, mechanical decisions) and the GM is narrating the outcome from the player's seat.
- **Party-pronoun grouping.** The character is named alongside the established PCs with shared party pronouns: *"the party (Silas, Rae, and Theron) approached the gate."* *"Theron and Rae searched the back room."* The grouping is the GM's signal that Theron sits in the same role-slot as Rae.
- **Player-attribution shorthand.** The notes name a player when narrating an action: *"Maya described Theron's spell — chains of fire wrapping the cultist."* The player's name on the narrating side and the character's name on the in-fiction side is a strong PC signal.

**NPC signals (route to `npcs/` — the default):**

- **Subject-of-prep framing.** The character is named as someone the party encountered, talked to, fought, or learned about: *"The party met Maren at the docks."* *"Brother Aldric arrived at dawn with the healer."* *"The captain refused to talk."* The verbs land on the character; the actors are the party (or another NPC the GM is narrating).
- **Role-tag framing.** The character is introduced by role first, name second: *"The blacksmith — call her Sera — sold them the daggers."* The role tag is how the GM treats NPCs as functional fixtures of the world.
- **Stance-toward-party framing.** The character has a disposition or stance the GM is recording for future reference: *"Sera is now wary of the party."* *"The duke remained skeptical."* This is what NPCs do in notes; PCs don't have a stance toward themselves.

**Default to NPC if framing is ambiguous.** A named character with weak or mixed signals (a one-line mention in a list, an action described from a distance with no clear subject framing, a name dropped in a quote that could be either) routes to NPC under Pass 2's default. The Step 3 ambiguity clarification then asks PC-or-NPC explicitly so the GM resolves the call. False-positive NPCs are cheap (the GM moves the staged file from `npcs/` to `pcs/` at Step 4); false-positive PCs are *not* cheap (they'd carve out a roster fact the GM didn't intend), so the default leans NPC.

### Step 3 PC-or-NPC ASK shape (wrap time)

When Pass 2's framing read produces an ambiguous candidate, route to Step 3 ambiguity clarification with the PC-or-NPC ASK shape documented in `skills/wrap-session/SKILL.md` Step 3. The phrasing template:

> *"`<Name>` appears in this session's notes — narrated as an actor doing PC-actor things in some sentences and as a subject in others. PC or NPC?"*

For framings the heuristic read as clearly PC-actor (multiple strong signals, no NPC signals), Pass 2 can route directly to `pcs/` *without* a Step 3 ASK — the wrap-time signal is reliable enough to skip the question in the clear-cut case. The GM corrects in the Step 4 proposed-wrap review by deleting the staged `pcs/<slug>.md` (rejecting outright) or by moving it to `npcs/<slug>.md` (the staging pattern's move-to-correct-directory affordance). The Step 4 surfacing is the second-chance reconciliation for confident-but-wrong PC routing.

### Step 4 correction: moving the staged file

The Step 4 proposed-wrap review (per `skills/wrap-session/SKILL.md` Step 4) shows the GM every staged file. If the agent staged `pcs/theron.md` and the GM realizes the framing was misleading (Theron was actually a PC-shaped NPC ally — the bard the party hired — not a player character), the GM moves the staged file: in their IDE, `.ttrpg-staging/wrap/pcs/theron.md` becomes `.ttrpg-staging/wrap/npcs/theron.md`. The Step 5 promotion reads the staged file from its current location and writes to the corresponding final path, so the move-in-staging is the move-on-promote.

The inverse correction works the same way: the agent staged `npcs/marisa.md` based on a default-NPC read of ambiguous framing, the GM clarifies at Step 4 that Marisa is a new PC, and moves `.ttrpg-staging/wrap/npcs/marisa.md` to `.ttrpg-staging/wrap/pcs/marisa.md`. Step 5 promotes from `pcs/`.

When the GM moves a staged file across kinds (npcs ↔ pcs), the agent does **not** auto-rewrite Beat `linked_pcs:` / `linked_npcs:` or Secret `belongs_to:` references that the wrap had drafted using the original kind. The Step 4 review summary should call out the cross-references so the GM knows what else to update — *"You moved `npcs/marisa.md` to `pcs/marisa.md`; the staged Beat `marisa-overheard-in-hall.md` has `linked_npcs: [marisa]`. Should I rewrite to `linked_pcs: [marisa]`?"* — and the agent applies the rewrite on confirm. Single-session scope: no carried-forward lessons (`/wrap-session` runs against one session).

## Alias detection at extraction time

A common case: a single NPC (or location, or faction, or item) is referred to by more than one name in the same source doc. Per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md), one entity gets one Reference note (the canonical), and the other names go in frontmatter `aliases:`. The agent's job at extraction time is to *detect the relationship* and *surface it for GM confirmation*, not to silently pick canonical and merge.

### Prose patterns that signal a dual-name entity

The agent watches for these in source-doc prose:

- **"also known as"** / **"a.k.a."** / **"sometimes called"** — "Maren, also known as The Shadow, runs cartel routes through the docks."
- **"going by the name"** / **"under the name"** — "She enters the city under the name Annika Marra."
- **"posing as"** / **"under the alias"** / **"using the alias"** — "The cult leader poses as Brother Olwen of the Verdant Choir."
- **"whose real name is"** / **"whose true identity is"** — "The masked figure, whose real name is Lord Vael, walked out unchallenged."
- **Parenthetical re-introduction.** Source-doc prose that introduces an entity by one name and re-states another in parentheses: "Brother Olwen (Olwen of the Verdant Choir)" or "Captain Marra (Annika Marra of the City Watch)."
- **Same-paragraph or same-section dual-name pattern.** Two names appear in the same paragraph or section, both referring to the same role or position — the prose makes the equivalence clear via shared pronouns, shared role, or shared location. "Maren works the docks by day. By night, The Shadow clears cartel routes through the same warehouses."
- **Honorific + given name pairing used interchangeably.** "Queen Vael" and "Vael Stormwind" used in the same passage with no role distinction; "Captain Marra" and "Annika" used by different in-fiction speakers for the same person.

When borderline (the agent can't tell if two names refer to the same entity or two different ones), prefer to **surface the question** rather than silently merging or silently splitting. The GM picks; the agent records.

### ASK shape at per-doc review

When the agent detects a possible alias relationship, surface it at the per-doc review (`/ingest` Step 4a) or the ambiguity clarification step (`/wrap-session` Step 3) as a yes/no question:

> *"`The Shadow` in this doc appears to be the same NPC as `npcs/maren.md` (matches a known alias in its `aliases:` list). Confirm merge into `maren.md` with `The Shadow` already covered by the alias list — no schema change needed?"*

Or, if the alias is new and not yet in the existing file's `aliases:`:

> *"`Maren the Dockworker` in this doc appears to be the same NPC as `npcs/maren.md` (same paragraph dual-name pattern). Add `Maren the Dockworker` to `npcs/maren.md`'s `aliases:` list, or create a separate `npcs/maren-the-dockworker.md`?"*

Or, when both names are new and the agent can't tell which should be canonical:

> *"`Brother Olwen` and `Olwen of the Verdant Choir` appear to be the same NPC (parenthetical re-introduction pattern). Pick canonical: `brother-olwen` or `olwen-of-the-verdant-choir`? The other goes in `aliases:`."*

The GM's answer routes the proposal:

- **Confirm merge into existing canonical** → propose an UPDATE on the existing canonical file (append the alias to `aliases:` if not already present; preserve the rest of the file byte-for-byte). The agent's prose-side reference to the alias uses a piped wiki link (e.g., `[[npcs/maren|The Shadow]]`) per ADR-0017's rendering convention.
- **Create separate files** → propose two CREATEs at disambiguated slugs; no `aliases:` linkage.
- **Pick a canonical from two new candidates** → propose one CREATE at the chosen slug with the other name in `aliases:`; future mentions of either route to the canonical file.

### Carried-forward lessons

In `/ingest` (multi-doc runs), confirmed alias relationships join the carried-forward lessons set (per the carried-forward-lessons logic in `skills/ingest/SKILL.md` Step 5b). Subsequent docs in the same run that mention the alias route to the canonical as a silent confident UPDATE (the alias is now in `aliases:`, so the extended dedup-matching rule in `dedup-matching.md` catches it without re-prompting). The agent still surfaces the resulting UPDATE in the per-doc review summary — the lesson skips the ASK, not the review.

`/wrap-session` is single-session; no carried-forward lessons. Each session's alias confirmations are local to that wrap run.

## Missing or unclear names

A common case: source content references "the blacksmith" or "the captain" without ever naming them. **Do not invent a name.** Two correct moves:

- **`/ingest`:** surface the unnamed entity at the per-doc review as an ASK: *"The blacksmith in section 2 is unnamed. Propose a Reference note (with a placeholder name), skip, or wait until the GM names them?"*
- **`/wrap-session`:** route the unnamed entity to ambiguity clarification (Step 3) before staging: *"An unnamed blacksmith appears in the notes. Provide a name, or skip creating a Reference note?"*

If the agent can match the unnamed reference to an existing Reference note via clear context ("the captain" used to refer to `npcs/captain-marra.md` in the prior session's Log), that's a confident UPDATE, not a CREATE — see `dedup-matching.md`.

## Updates to existing Reference notes

When the source content mentions an entity that already has a Reference note and adds new information, propose an UPDATE rather than a CREATE:

- **Append** for accreted facts ("Sera is now wary of the party").
- **Edit** for changes that contradict the existing line ("Sera moved from the village to the city" — replace the location half).
- **Never lose GM-authored prose.** If overwriting would discard content, surface both versions and flag for review.

Dedup matching (slug + first-heading title, normalized) is what routes a candidate to UPDATE vs CREATE — see `dedup-matching.md`.

## What not to do

- **Don't fabricate detail.** If the source doesn't say what kind of blacksmith Sera is, the one-liner doesn't say either.
- **Don't pre-create empty kind folders.** A folder appears when its first file lands.
- **Don't extract Atlas content.** v0.1 is single-repo (ADR-0006); treat everything as campaign-local.
- **Don't fill out a template.** ADR-0003's whole point: capture-now-structure-later. The Reference note's job is to exist and be linkable; the GM enriches it later if needed.
