# /prep-session question categories

`/prep-session`'s Step 3.5 (the conversational refinement loop introduced by [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md)) surfaces rule-based follow-up questions about the drafted Brief. Each question category has a **predicate** the agent evaluates against current campaign state and the just-drafted Brief, a **phrasing template** for asking the GM, and **response-handling notes** for how the agent acts on the answer. A category stays silent when its predicate is false; the GM only sees questions whose conditions are actually met.

The corresponding ADR is [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). The Secret enumeration that the Secret Push predicate walks lives in [`secret-store.md`](./secret-store.md). The staging behavior the agent uses when revising the Brief on a GM response lives in [`staging-pattern.md`](./staging-pattern.md) ("Iterative agent revisions during a review loop"). The Brief section template the agent revises lives in `skills/prep-session/SKILL.md` Step 3.

## How the loop uses these questions

Step 3.5 evaluates every category in order. Each category whose predicate is true contributes one (or, in the case of categories that legitimately produce multiple findings, a small batch of) question(s) to the loop's queue. The agent then presents queued questions to the GM, ideally batching closely-related questions into a single turn so the GM isn't pinged seven separate times.

Per ADR-0015's skip semantics:

- The agent's loop preamble mentions the verbal escape (*"...or say 'looks good' / 'skip questions' to finalize as-is."*).
- If the GM responds without addressing a queued question, that question is dropped — treat the non-response as "decided not to engage." **No re-prompting** within the same run.
- "approve" / "looks good" / "draft is good" exits the loop; "cancel" exits without writing (per the staging pattern's cancel semantics).

When the GM does engage with a question, the agent revises the staged `.ttrpg-staging/brief-draft.md` via the Edit tool so the IDE shows a native diff (per [#16](https://github.com/snlemons/game_manager/issues/16)), then re-presents the loop preamble for the next turn.

## The seven categories

ADR-0015 enumerates seven categories. All seven are documented below. The Step 3.5b enumeration in `skills/prep-session/SKILL.md` walks them in the documented order; the rule the GM should expect is **everything else first, GM Focus Check last** (its phrasing — "Anything you're planning this session that's not in the draft?" — only lands well after the rule-based surface has fired).

The order below is:

1. **Coverage Check** — Beat the agent down-tiered with borderline relevance score; confirm the agent's call or pull the Beat in.
2. **Tiering Check** — Out-of-focus Beats exist on an introduced Adventure; offer to surface any.
3. **Thread Decay** — Threads open for N+ sessions without delivered Beats; mark decayed / push / leave.
4. **Decision Request** — Empty drafted section needing GM input (Opening Scene is the v0.2 starter case).
5. **Secret Push** — Hidden / partially-revealed Secrets on in-focus Adventures; push toward any this session.
6. **Escalation Prep** — No in-focus Beat is `kind: escalation`; flag / propose / skip. Per-campaign opt-out.
7. **GM Focus Check** — Always-fires final catch-all; runs last.

Categories 1–6 are silent-by-predicate (or silent-by-opt-out, for Escalation Prep); only Category 7 fires unconditionally. Each category's section below follows the format established by Secret Push (which historically shipped first): Intent / Predicate / Phrasing template / Response handling / Worked example.

## Coverage Check

**Intent.** Surface Beats the agent's tiered classification (Step 2, per ADR-0009) judged out-of-focus but where the call was close — the Beat's `linked_*` fields name something *adjacent* to an in-focus signal without exact overlap. These are the cases where the agent's automated relevance filter is most likely to misclassify in a way the GM cares about, and where one targeted confirmation per borderline Beat is cheaper than a missed-opportunity in play. The GM either confirms the agent's call (the Beat stays out-of-focus, surfacing only as a count in the Brief) or overrides (the Beat is promoted to "Beats to weave in" for this session).

### Predicate

The question fires **once per borderline-relevance Beat**, capped at a reasonable per-run total to avoid drowning the GM (see "cap" below). Concretely:

1. **Inputs.** Reuse Step 2's tiered surfacing outputs verbatim — `BEATS_IN_FOCUS`, `BEATS_OUT_OF_FOCUS_BY_SCOPE`, the `IN_FOCUS_ADVENTURES` / `IN_FOCUS_PCS` / `NEAR_LOCATIONS` / `ENCOUNTERABLE_NPCS` sets the classifier built. No fresh scan; this predicate is a post-hoc filter on the existing classification.
2. **Walk the out-of-focus *linked* Beats.** Skip in-focus Beats (already surfaced in full) and unlinked Beats (handled by Tiering Check / their own count line — no per-Beat question for them). The candidates are pending Beats with at least one populated `linked_*` field, none of which overlapped any in-focus signal.
3. **Score each candidate for borderline-ness.** A Beat is borderline if **any** of these heuristics holds — judged by the LLM, not by a numeric threshold:
   - `linked_locations` names a location **one step beyond `NEAR_LOCATIONS`** in the Reference-note graph (the location is two steps from the party, not directly adjacent). The party might still reach it this session if they push.
   - `linked_npcs` names an NPC who is **linked from an in-focus Adventure's main file** but did not appear in the prior session's Log — they're scene-adjacent without being in the immediate "encounterable" set.
   - `linked_adventures` names a `status: introduced` Adventure that is **not** in the Brief's menu but **is** referenced from the body of an in-focus Adventure (a cross-arc tie-in the GM may want to surface this session even though the menu didn't promote the introduced arc).
   - `linked_pcs` names a PC who **is** in the campaign but did not appear in the prior session's Log (a PC the GM may want to spotlight after a quiet session).
   - The Beat has a populated `linked_*` field whose value would have hit an in-focus signal **if** the canonical-form match were slightly fuzzier (e.g., a slug typo, an old name the GM has since renamed). Surface as borderline so the GM can either correct the Beat's `linked_*` or accept the out-of-focus call. These are also Tiering Check candidates for the underlying tag fix.
4. **Cap the fired questions.** A campaign with many out-of-focus Beats produces many borderline candidates. To avoid drowning the GM, fire at most **3 Coverage Check questions per `/prep-session` run**. Sort candidates by *score* (Beats that hit more borderline signals rank higher) and take the top 3. The remaining borderline Beats stay counted only — the Brief's out-of-focus count line already surfaces them at scale. The cap is a starting value; if dogfooding shows GMs want more, raise it.
5. **Fire the question for each surviving Beat**, batched into a single turn rather than asking three separate times.

The predicate is **silent** when:

- `BEATS_OUT_OF_FOCUS_BY_SCOPE` is empty (no out-of-focus linked Beats to evaluate).
- No out-of-focus Beat scores as borderline under the heuristics above.
- The Brief's out-of-focus count line already surfaces the same Beats as a count; the per-Beat ask only adds value when a borderline judgement is plausible to override.

### Phrasing template

Single borderline Beat:

> *"`[Beat name]` ([[beats/<slug>]]) is currently out-of-focus — `[one-line why-borderline, e.g., "linked to Old Owl Well, one step from where the party is now"]`. Surface it in `Beats to weave in`, or leave as out-of-focus?"*

Multiple borderline Beats (up to 3), batched in one turn:

> *"Coverage check — 3 Beats are close to in-focus this session but didn't quite hit:*
> *— `[Beat A]` ([[beats/<slug>]]) — `[one-line why-borderline]`.*
> *— `[Beat B]` ([[beats/<slug>]]) — `[one-line why-borderline]`.*
> *— `[Beat C]` ([[beats/<slug>]]) — `[one-line why-borderline]`.*
> *Surface any of these, or leave as out-of-focus?"*

Conventions:

- Use the Beat's H1 title as the human-readable label (same convention as Secret Push).
- The "why-borderline" line is the *signal that almost hit*, not the agent's classification reasoning in general. The GM scans for "is this actually relevant?" — one concrete sentence is enough.
- The closing ask is soft ("leave as out-of-focus" is a valid answer) and never implies the agent's call was wrong. The GM declining is the agent's call standing.

### Response handling

1. **Surface (override the down-tier).** The GM names one or more Beats to pull into the Brief, or says "yes, surface all" / "the Maren one — pull it in." For each accepted Beat:
   - Apply the same in-focus bullet shape Step 3's drafting rules use: `- **<Beat name>** [[beats/<slug>]] — one-line intent. *(scope: <override-reason>)*` where the override-reason names the borderline signal that promoted it (e.g., `*(scope: location-adjacent — one step from Phandalin)*`). The agent does not rewrite the Beat file's `linked_*` fields; the override is Brief-scoped only.
   - Subtract the surfaced Beat from `BEATS_OUT_OF_FOCUS_TOTAL` and update the count line to reflect the new total.
   - Apply via Edit against `.ttrpg-staging/brief-draft.md` per the loop's standing pattern.

2. **Decline (leave as out-of-focus).** The GM says "no, leave them" / "skip" / replies addressing a different question. No revision to the Brief; the out-of-focus count line is unchanged. Loop continues.

3. **Defer / non-engagement.** Per ADR-0015's no-re-prompting rule, treat as decline. The question is dropped; the agent does not re-ask within this run.

### Worked example

Campaign state: in-focus Adventures `{adventures/lost-mines/, adventures/cult-of-the-reborn-flame/}`. Party at `[[Phandalin]]`; `NEAR_LOCATIONS = {Phandalin, Tresendar Manor, Triboar Trail}`. `IN_FOCUS_PCS = {Darius, Sera}`. Out-of-focus linked Beats include:

| Beat slug | `linked_*` |
|---|---|
| `old-owl-well-rumor` | `linked_locations: [old-owl-well]` (one step beyond `NEAR_LOCATIONS` via Triboar Trail) |
| `goblins-in-neverwinter` | `linked_locations: [neverwinter]` (multiple steps away) |
| `maren-overheard-in-hall` | `linked_npcs: [maren]` (Maren is linked from `adventures/cult-of-the-reborn-flame/adventure.md` but didn't appear in the prior Log) |
| `darius-old-rival-card-game` | `linked_pcs: [darius]` (Darius is in-focus already — wait, this is actually in-focus, not borderline) |
| `harken-arrives-with-news` | `linked_npcs: [harken]` (Harken is not linked from any in-focus Adventure — not borderline) |

Filtering for borderline:

- `old-owl-well-rumor` qualifies (location one step beyond `NEAR_LOCATIONS`).
- `goblins-in-neverwinter` does not qualify (location multiple steps away — not borderline, just out-of-focus).
- `maren-overheard-in-hall` qualifies (NPC linked from in-focus Adventure but absent from prior Log).
- `darius-old-rival-card-game` doesn't reach this predicate (already in-focus on the PC signal).
- `harken-arrives-with-news` does not qualify (NPC has no in-focus tie).

Two borderline candidates, both surface. Agent fires one batched turn:

> *"Coverage check — 2 Beats are close to in-focus this session but didn't quite hit:*
> *— Old Owl Well rumor at the inn ([[beats/old-owl-well-rumor]]) — linked to Old Owl Well, one step beyond Triboar Trail from Phandalin.*
> *— Maren overheard in the back hall ([[beats/maren-overheard-in-hall]]) — Maren is linked from the Cult arc but didn't appear last session.*
> *Surface any of these, or leave as out-of-focus?"*

GM replies: *"Surface the Maren one — she's overdue. Leave the well rumor."*

The agent revises `.ttrpg-staging/brief-draft.md` via Edit, adding to "Beats to weave in":

```markdown
- **Maren overheard in the back hall** [[beats/maren-overheard-in-hall]] — one-line intent. *(scope: NPC-adjacent — Maren linked from Cult arc)*
```

And updates the out-of-focus count line from `_Plus 14 more …_` to `_Plus 13 more …_` (one less). The well rumor stays in the count.

## Tiering Check

**Intent.** Out-of-focus Beats linked to a `status: introduced` Adventure are a structurally interesting case: the Adventure is on the GM's radar (introduced, not just hypothetical) but isn't on this session's menu, so its Beats fall through to "counted only." The GM may want to surface a Beat or two to *seed* the introduced arc this session — drop a foreshadowing hook the party will recall when the arc activates later. This is the deliberate-foreshadowing surface that the broad in-focus rule (ADR-0009) doesn't naturally provide.

### Predicate

The question fires **once per `status: introduced` Adventure** that has out-of-focus Beats linked to it. Concretely:

1. **Inputs.** Reuse Step 2's classification outputs: `BEATS_OUT_OF_FOCUS_BY_SCOPE` (the per-scope breakdown of out-of-focus linked Beats), plus the full set of `status: introduced` Adventures (the menu candidates surfaced in Step 3's "Menu of next-session options" — this set is computed even when the menu's curation is selective).
2. **Walk the introduced Adventures NOT on the menu.** Introduced Adventures the Brief is putting on the menu are already in-focus on the Adventure signal; their Beats either landed in `BEATS_IN_FOCUS` or are out-of-focus on other signals (Coverage Check handles those). The Tiering Check candidates are introduced Adventures *not* on the menu — the GM knows about them but isn't elevating them this session.
3. **Filter to introduced Adventures with at least one out-of-focus Beat linked.** For each such Adventure, look up `BEATS_OUT_OF_FOCUS_BY_SCOPE[adventures/<slug>/]` (or the agent's equivalent scope-keyed count). If the count is > 0, the Adventure qualifies.
4. **Fire the question for each qualifying Adventure**, batched into a single turn rather than asking N separate times.

The predicate is **silent** when:

- No Adventure has `status: introduced`.
- Every `status: introduced` Adventure is already on the menu (its Beats are handled by the in-focus tier or Coverage Check).
- No out-of-focus Beat is linked to an off-menu introduced Adventure.

**The cap from Coverage Check does NOT apply here.** Tiering Check is per-Adventure (typically a small number); Coverage Check is per-Beat (potentially many).

### Phrasing template

Single off-menu introduced Adventure with out-of-focus Beats:

> *"`[N]` Beat(s) linked to `[Adventure name]` are out-of-focus this session because the arc isn't on the menu. Surface any as foreshadowing, or leave for when the arc activates?"*

Multiple off-menu introduced Adventures, batched in one turn:

> *"Tiering check:*
> *— `[Adventure A]` (introduced, off-menu): `[N]` Beat(s) out-of-focus.*
> *— `[Adventure B]` (introduced, off-menu): `[M]` Beat(s) out-of-focus.*
> *Surface any as foreshadowing this session, or leave?"*

Conventions:

- Use the Adventure's canonical name (H1 or humanized slug), same as Secret Push.
- The closing phrase frames the surface as *foreshadowing* — "drop one now so the party remembers when the arc starts." That's the legitimate use case; a flat "surface them" ask invites the GM to over-surface arcs they actually meant to defer.
- Don't list individual Beats in this question. The GM picking "yes, foreshadow X" gets a follow-up exchange enumerating the candidates (response handling below). Listing all of them inline would duplicate the out-of-focus count line.

### Response handling

1. **Accept (foreshadow one or more).** The GM says "yes, foreshadow the Strahd arc" / "drop the Curse-of-Strahd intro Beat" / "show me what's there." Two sub-cases:
   - **GM names a specific Beat or asks for a list.** Enumerate the qualifying Beats inline (use [[wiki links]]) and let the GM pick. Once selected, apply the same Brief revision as Coverage Check: add a bullet to "Beats to weave in" with a `*(scope: foreshadowing — <Adventure name>)*` hint, and subtract from the out-of-focus count line.
   - **GM accepts broadly ("surface them all").** Add a bullet for each qualifying Beat to "Beats to weave in." The GM may regret this; that's their call.

2. **Decline (leave for when the arc activates).** The GM says "no, leave them" / "skip" / addresses something else. No revision; Brief unchanged. Loop continues.

3. **Defer / non-engagement.** Treat as decline per ADR-0015. No re-asking this run.

### Worked example

Campaign state: `status: introduced` Adventures `{adventures/curse-of-strahd/, adventures/the-prism/, adventures/blood-of-vol/}`. The Brief's menu surfaces only `curse-of-strahd` this session (the GM wants the party to choose between continuing the Cult arc or jumping to Strahd; The Prism and Blood of Vol are deferred). Out-of-focus by-scope shows:

- `adventures/the-prism/`: 2 Beats linked.
- `adventures/blood-of-vol/`: 1 Beat linked.
- `adventures/curse-of-strahd/`: 0 Beats out-of-focus (in-focus via menu).

Two qualifying Adventures. Agent fires one batched turn:

> *"Tiering check:*
> *— The Prism (introduced, off-menu): 2 Beat(s) out-of-focus.*
> *— Blood of Vol (introduced, off-menu): 1 Beat(s) out-of-focus.*
> *Surface any as foreshadowing this session, or leave?"*

GM replies: *"Show me the Prism ones."*

Agent enumerates inline:

> *"Prism Beats currently out-of-focus:*
> *— [[beats/prism-archivist-arrives]] — Old Master Heron's apprentice shows up looking for help.*
> *— [[beats/prism-core-glows-in-darkness]] — the core flickers when stowed in a dark place.*
> *Foreshadow either?"*

GM replies: *"Drop the archivist Beat — that lands well after the Cult fight."*

Agent revises `.ttrpg-staging/brief-draft.md` via Edit, adding to "Beats to weave in":

```markdown
- **Prism archivist arrives** [[beats/prism-archivist-arrives]] — Old Master Heron's apprentice shows up looking for help. *(scope: foreshadowing — The Prism)*
```

And updates the out-of-focus count line by -1 (was 14, now 13; The Prism scope is now 1 instead of 2). Blood of Vol stays counted only — the GM declined that one by omission.

## Thread Decay

**Intent.** Threads that have been `open` for many sessions without movement are either (a) Threads the GM is letting decay in fact but hasn't formally marked, (b) Threads the party has lost track of and the GM wants to push back into focus, or (c) Threads still legitimately alive but the slow-burning kind. The agent can't distinguish these — only the GM can. Surface stale Threads explicitly with three concrete actions: **decay** (mark `status: decayed`), **push** (commit to surfacing this session), or **leave** (it's still alive, just patient).

### Predicate

The question fires **once per stale-Threads batch**, batching multiple stale Threads into one turn. Concretely:

1. **Inputs.** Walk `threads/` directly. For each `.md` file:
   - Parse frontmatter as YAML; skip silently on parse failure (same as `secret-store.md`'s `list_all`).
   - Keep only Threads with `status: open`. `closed` and `decayed` Threads are not candidates.
2. **Compute "open for N+ sessions without movement"** per Thread:
   - The Thread's `created:` date (per `frontmatter-schemas.md`) is the *opened* anchor. Threads with `created: ~` (ingest-era, date unknown) are skipped from this predicate — the agent has no signal to compute staleness against. (The GM can hand-mark these decayed; the agent doesn't guess for them.)
   - "Without movement" means: no Beat in `beats/` with `status: delivered` AND `delivered:` date >= the Thread's `created:` date AND whose body or `linked_*` fields reference this Thread. The agent uses bidi-link backlinks (per `bidi-link-maintenance.md`) — if any delivered Beat backlinks the Thread, the Thread has movement.
   - "N+ sessions" means: count the number of `sessions/YYYY-MM-DD-session-K/` directories whose date is **after** the Thread's `created:` date. If that count is `>= N`, the Thread is stale.
3. **The N threshold is `5`.** A Thread that's been open for 5 or more sessions without a delivered Beat is stale enough that the question is worth asking. **Rationale:** 5 sessions is roughly two months of weekly play; long enough that "we forgot" is a plausible explanation but short enough that legitimately slow-burn Threads still surface for a confirm-it's-intentional ask. The threshold is a starting value; if dogfooding shows GMs find 5 too aggressive (too many "leave it alone" answers) or too lax (Threads decay before the question fires), the next slice tunes it. Don't make N a per-campaign setting in v0.2 — global threshold first, per-campaign override only if the global one proves unfit.
4. **Sort stale Threads by staleness descending** (oldest-without-movement first), cap at **5 per run** to avoid drowning the GM. Threads above the cap stay open and untouched; they'll re-surface next session if still stale.
5. **Fire one batched question** covering all stale Threads in the batch.

The predicate is **silent** when:

- `threads/` does not exist or is empty.
- No `status: open` Thread meets the 5-session-no-movement threshold.
- Every stale Thread has `created: ~` (can't compute staleness against an unknown date).

### Phrasing template

Single stale Thread:

> *"`[Thread name]` ([[threads/<slug>]]) has been open since session `[K]` (`[N]` sessions ago) with no delivered Beats linked. Decay, push this session, or leave?"*

Multiple stale Threads (up to 5), batched:

> *"Thread decay check — these Threads have been open `[N]`+ sessions without movement:*
> *— `[Thread A]` ([[threads/<slug>]]) — open since session `[K_a]` (`[N_a]` sessions).*
> *— `[Thread B]` ([[threads/<slug>]]) — open since session `[K_b]` (`[N_b]` sessions).*
> *For each, reply: decay (mark status), push (surface this session), or leave (still alive)."*

Conventions:

- Always use the Thread's H1 title for the label, slug for the wiki link.
- The three-action ask (decay / push / leave) is the structural ask. Don't let the GM only choose decay vs. leave — push is the active-handling option and is the whole reason the question is per-Thread rather than a blanket "decay everything stale?" sweep.
- Don't lecture the GM on what each action means inline. They know.

### Response handling

The GM may reply with one action per Thread, or with a single sweep ("decay all of them"). Process each named action:

1. **Decay.** Apply via the same staging pattern Step 4 uses for other UPDATEs: copy the live Thread file into `.ttrpg-staging/threads/<slug>.md`, then Edit the staged copy to change `status: open` → `status: decayed` and set `closed: <session date>` (the upcoming session's date, since the decay is being recorded now). Do **not** also delete the Thread from any "Open threads" section in the Brief — the agent re-renders that section on the next loop turn from the just-edited Thread file's frontmatter, so the change propagates naturally; manual Brief edits would risk getting out of sync with the staged Thread.

   **Important: the actual write to the campaign's `threads/<slug>.md` is gated by the Brief's final approval at Step 5**, not by the GM's decay reply in this turn. If the GM later cancels the Brief, the staged Thread change is also dropped. This matches the staging pattern's cancel semantic.

2. **Push.** No change to the Thread file. Add a bullet to the Brief's "Beats to weave in" section as a Clue / news / handout Beat the GM commits to landing this session (the GM chooses the kind in conversation, or the agent proposes `news` as the default Beat kind for "push this Thread"):

   ```markdown
   - **Push: <Thread title> reminder** — surface [[threads/<slug>]] this session. *(scope: Thread push)*
   ```

   And add a one-line nudge to the GM scratchpad: `- Push [[threads/<slug>]] this session per Thread Decay check.`

3. **Leave.** No revision. The Thread stays `open`; the Brief is unchanged. The Thread is *not* re-surfaced in next session's prep by Thread Decay if the GM said "leave" — but the predicate re-evaluates from scratch each run, so it will fire again if the Thread is still stale next session. (The "no re-prompting within the same run" rule applies inside one `/prep-session` run, not across runs.)

4. **Defer / non-engagement.** Per ADR-0015, treat as leave for every Thread in the batch. No revisions.

If the GM addresses some Threads and not others ("decay A, push B" without naming C), the unnamed ones default to leave (decline). Don't ping the GM to clarify — the per-Thread question is decline-by-omission, same as the other categories.

### Worked example

Campaign state: 12 open Threads in `threads/`. Current session is session 14 (next session date `2026-06-07`). Walking the threads:

| Thread slug | `created` | sessions since | delivered Beats linking? |
|---|---|---|---|
| `find-merrick` | `2026-01-04` (session 5) | 9 | none |
| `silver-prince-rumor` | `2026-02-15` (session 8) | 6 | none |
| `vault-key-question` | `2026-03-22` (session 11) | 3 | none |
| `cult-payment-trail` | `2026-04-12` (session 12) | 2 | yes (last session) |
| `who-killed-jaena` | `2026-01-18` (session 6) | 8 | one in session 10 |
| 7 others | recent | < 5 | varies |

Filtering:

- `find-merrick`: 9 sessions, no movement. Stale.
- `silver-prince-rumor`: 6 sessions, no movement. Stale.
- `vault-key-question`: 3 sessions — not stale (< 5).
- `cult-payment-trail`: 2 sessions and has movement — not stale.
- `who-killed-jaena`: 8 sessions but has a delivered Beat in session 10 — not stale.

Two stale Threads. Agent fires one batched turn:

> *"Thread decay check — these Threads have been open 5+ sessions without movement:*
> *— Find Merrick ([[threads/find-merrick]]) — open since session 5 (9 sessions).*
> *— Silver Prince rumor ([[threads/silver-prince-rumor]]) — open since session 8 (6 sessions).*
> *For each, reply: decay (mark status), push (surface this session), or leave (still alive)."*

GM replies: *"Decay Merrick — that one's dead. Push the Silver Prince — drop news this session."*

Agent does two things:

1. Stage the decay: copy `threads/find-merrick.md` → `.ttrpg-staging/threads/find-merrick.md`, Edit the staged copy to `status: decayed`, `closed: 2026-06-07`.
2. Revise `.ttrpg-staging/brief-draft.md` via Edit, adding to "Beats to weave in":
   ```markdown
   - **Push: Silver Prince rumor reminder** — surface [[threads/silver-prince-rumor]] this session. *(scope: Thread push)*
   ```
   And to the GM scratchpad: `- Push [[threads/silver-prince-rumor]] this session per Thread Decay check.`

Both staged changes are gated by the Brief's final approval at Step 5.

## Decision Request

**Intent.** Some Brief sections are intentionally left empty during Step 3's draft because they require GM input the agent shouldn't fabricate. The Opening Scene (added by ADR-0015 and shipped in #33) is the v0.2 starter case — the agent leaves it blank, and Decision Request offers to propose one from current campaign state when the GM wants help. The category is designed to extend to future drafted-empty sections (NPC name picks, branching prep, etc.) without requiring a new category each time.

### Predicate

The question fires **once per drafted-empty Brief section in the recognized category set**. Concretely:

1. **Recognized empty-section categories.** The category is data-driven, not hardcoded — each recognized section names (a) which Brief section to check, (b) what "empty" means for that section, and (c) what data sources the agent draws from when proposing content. The v0.2 starter set:
   - **Opening Scene** (per [#33](https://github.com/snlemons/game_manager/issues/33) and ADR-0015's "strong opening scene" principle). Section: `## Opening Scene`. Empty means: the body between the section heading and the next heading contains only whitespace, HTML comments, and `_None._`-style markers. Data sources: prior session's `log.md` closing state, in-focus Adventures' main files, the party's current location's Reference note.
   - **(Reserved for future.)** Name picks, branching prep, and other drafted-empty sections will register here as they ship. The agent doesn't fire Decision Request for sections not in this list — an empty Brief section the agent doesn't know how to populate is the GM's to fill manually.
2. **Walk the recognized categories.** For each, re-read `.ttrpg-staging/brief-draft.md` and check whether the named section is empty per the per-category definition. A category fires only if its section is empty.
3. **Fire one question per empty recognized section**, batched if multiple sections are empty in the same run.

The predicate is **silent** when:

- No recognized section is empty (the GM authored Opening Scene during Step 3 by hand-editing the draft, or future categories' sections are populated, etc.).
- The Brief doesn't have the named sections at all (older Brief shapes pre-ADR-0015; this should be rare in v0.2 but the agent should not error).

**Decision Request does NOT fire for sections the agent itself populated.** The predicate is "empty drafted section," meaning the agent's draft left it empty; if the agent populated it, the GM can edit it directly in the staged file (the agent re-reads on every loop turn).

### Phrasing template

Single empty section — Opening Scene:

> *"Opening Scene is empty. Propose one from `[brief context: prior Log's closing state | the active Adventure's main file | the party's current location's Reference note]`? Or skip — you'll fill it in."*

Multiple empty sections (rare in v0.2; expected to grow):

> *"Decision requests:*
> *— Opening Scene is empty. Propose one from `[context]`?*
> *— `[Future section]` is empty. Propose `[per-category ask]`?*
> *Reply per section with propose / specific direction / skip."*

Conventions:

- Always name the section explicitly. The GM may have intentionally left it empty; the ask should be obvious enough that "skip" is an easy answer.
- For Opening Scene, the proposal hint names the data source the agent would draw from — that gives the GM a fast signal whether the proposed opener will land near where they want it (or whether they'd rather hand-author).
- The "skip" option is always implicit but spell it out anyway — Decision Request is a help-on-demand category, not a nudge category like Coverage Check.

### Response handling

1. **Propose.** The GM says "yes propose one" / "go ahead" / "draft it." For Opening Scene:
   - **Read the data sources** per the category definition: the prior session's `log.md` (its closing scene / "where they ended"), the in-focus Adventures' main files (for "what's the natural next scene?"), the party's current location's Reference note (for sensory anchoring).
   - **Draft a 2-4 sentence forward-facing opener** that pairs *where the party is now* with *what's about to happen* — landing the party in motion, not setting a static tableau. Shea's "strong opening scene" principle (per ADR-0015): a question, an interruption, a sensory cue that demands a reaction.
   - **Apply via Edit against `.ttrpg-staging/brief-draft.md`** — replace the section body (between the `## Opening Scene` heading and the next heading) with the drafted opener. Keep the HTML comment hint intact (or replace with one noting the GM can revise in place).

2. **Provide specific direction.** The GM says "the party should be ambushed entering the temple" / "open with Maren waiting at their door" / "start mid-conversation with the Lord Mayor." The agent uses the GM's specifics as the seed, drafts the 2-4 sentence opener around them (filling sensory detail from the Location Reference note where relevant), and applies via Edit.

3. **Skip.** The GM says "skip" / "I'll write it" / addresses something else. No revision; section stays empty. Loop continues.

4. **Defer / non-engagement.** Per ADR-0015, treat as skip. No re-asking this run.

**The Step 4 sensory-detail write-back rule applies if the GM authored a sensory detail tied to a Location in the opener.** That's a cross-category interaction with the existing write-back surface — it just works because the write-back rule looks at the final staged Brief, not at which category produced the content.

### Worked example

Campaign state: Step 3's draft produced an empty `## Opening Scene` section (default per ADR-0015). The prior session's `log.md` ended with: *"The party retreated to the inn after Sera's collapse. Brother Aldric promised to come at dawn with a healer. As they slept, the bell at the cult's chapel rang once, late."* In-focus Adventures: `[[Cult of the Reborn Flame]]`. Current location: `[[Phandalin]]` (Reference note body: *"frontier town, two streets crossing at the inn; the night smells of cold smoke and wet pine"*).

Agent fires:

> *"Opening Scene is empty. Propose one from the prior Log's closing (Sera's collapse, the bell at the chapel) and Phandalin's current sensory hooks? Or skip — you'll fill it in."*

GM replies: *"Yes propose. Land them at the chapel."*

Agent drafts the opener and revises the staged Brief via Edit. The new `## Opening Scene` body:

```markdown
The bell at the chapel of the Reborn Flame rings a second time before dawn — long, deliberate, not the morning hour. Sera is still on the cot, Brother Aldric not yet arrived. Across the empty common-room, the innkeeper meets the party's eyes and slowly shakes her head. The night smells of cold smoke and wet pine, and the cult's bell is still tolling.
```

Note: the opener pulls (a) prior-Log closing state (Sera on the cot, Aldric not yet, the bell from the cult's chapel), (b) the GM-supplied direction (land them at the chapel), and (c) Phandalin's sensory hook (cold smoke and wet pine) — recycling the Reference-note detail per ADR-0015's "recycle and reincorporate" principle. The GM can edit further in the staged file before approval.

## Secret Push

**Intent.** Surface Secrets that are partially or fully hidden but tied to an Adventure the party is likely to engage with this session, so the GM can decide whether to push the revelation forward this session. A `partially-revealed` Secret with no Clue Beat planned is a story payoff actively waiting on the GM; a `hidden` Secret on the in-focus arc is one the GM may have been waiting to drop. The Brief shouldn't list Secrets directly (per ADR-0015: "Clue Beats may appear in the Brief; their Secrets do not"), but the prep-time question is the right surface to nudge the GM toward authoring a Clue Beat or otherwise advancing the Secret this session.

### Predicate

The question fires once per **(Adventure, Secret-status) pair** whose enumeration is non-empty. Concretely:

1. **Compute the in-focus Adventure set**, identical to the `IN_FOCUS_ADVENTURES` set Step 2's tiered Beat surfacing computes: the union of every `status: active` Adventure and every `status: introduced` Adventure surfaced in the Brief's "Menu of next-session options" section. `completed` and `abandoned` Adventures are never in focus. Introduced Adventures the GM is *not* putting on the menu this session are not in focus on the Adventure signal.
2. **Walk `secrets/` directly** per the enumeration algorithm in [`secret-store.md`](./secret-store.md) (`list_all`). For each `.md` file under `secrets/`:
   - Parse frontmatter as YAML; skip silently if it doesn't parse or doesn't start with `---\n`.
   - Read the `status:` and `belongs_to:` fields. (The schema is in `frontmatter-schemas.md`; `belongs_to:` is a non-empty list of non-ephemeral container paths.)
3. **Filter by status.** Keep only Secrets whose `status:` is `hidden` or `partially-revealed`. `revealed` Secrets have already landed for the party and need no nudge.
4. **Filter by `belongs_to:` intersection with the in-focus Adventure set.** A Secret qualifies if **any** entry in its `belongs_to:` list matches an in-focus Adventure's container path. Adventure containers are exact-string matched in their canonical directory form (`adventures/<slug>/` with trailing slash) per [`secret-store.md`](./secret-store.md)'s `find_by_container` semantics. A Secret whose `belongs_to:` only names NPC / location / faction / item containers is not in scope of *this* question — Secret Push is the Adventure-scoped surfacing; per-container surfacing of NPC / location Secrets is a different question category (deferred to #40 or beyond).
5. **Group the matches by in-focus Adventure.** A Secret that lists two in-focus Adventures in its `belongs_to:` counts under each — but the agent should phrase a combined question rather than asking twice (see response handling below).
6. **Fire the question for each (in-focus Adventure, status) bucket with non-empty membership.** If the Cult Arc has 2 `partially-revealed` Secrets and 0 `hidden`, fire one question for the `partially-revealed` bucket. If it has 1 of each, fire two — but batch them in the same turn.

The predicate is **silent** when:

- `secrets/` does not exist or is empty.
- No Secret has both an in-scope status (`hidden` or `partially-revealed`) and an in-focus Adventure in its `belongs_to:`.
- Every qualifying Secret is already going to be advanced this session via a `kind: clue` Beat the Brief is surfacing in "Beats to weave in" whose `linked_secrets:` names it. The Beat already represents the GM's intent to push; the question would be redundant. (Implementation note: cross-check `BEATS_IN_FOCUS` from Step 2's classification — if every qualifying Secret's slug is named in some in-focus `kind: clue` Beat's `linked_secrets:`, suppress the question for that Secret. Don't suppress if the Beat is only `linked_secrets:`-tagged but isn't `kind: clue` — the incidental link doesn't represent the GM choosing to push.)

### Phrasing template

Single-bucket case (one Adventure, one status):

> *"`[Adventure name]` has `[count]` Secret(s) in `[status]` (`[Secret title, Secret title…]`) — push toward any this session?"*

Multi-bucket case for the same Adventure (both statuses non-empty), one turn:

> *"`[Adventure name]` has `[count_partial]` Secret(s) in `partially-revealed` (`[partial titles…]`) and `[count_hidden]` in `hidden` (`[hidden titles…]`) — push toward any this session?"*

Multi-Adventure case, batched in one turn:

> *"Secret-Push check:*
> *— `[Adventure A]`: `[count]` `partially-revealed` (`[titles]`).*
> *— `[Adventure B]`: `[count]` `hidden` (`[titles]`).*
> *Want to push any of these this session?"*

Conventions for the phrasing:

- Use the Secret's H1 title (the first `# <text>` line in the Secret's body) as the human-readable label, not the slug. The slug is the agent's index; the title is what the GM remembers.
- Use the Adventure's canonical name (the Adventure's H1 or the slug humanized) rather than the directory path. `adventures/the-prism/` becomes `The Prism` (or whatever the H1 says).
- Quote at most three titles per bucket inline. If there are more, append "… and `N` more" and let the GM ask for the full list if they want it.
- The closing phrase is always a soft push, not a hard ask: "push toward any this session?", not "which Secret are you advancing?" The GM should feel free to say "no, all of these need more time" without explanation.

### Response handling

The agent interprets the GM's reply against three shapes:

1. **Accept (push one or more).** The GM names one or more Secrets they want to push this session, or says "yes, push `[Secret title]`" / "the Maren one — set that up" / "all of them, draft a Clue Beat for each." Two sub-cases for the Brief revision:
   - **Add a Clue Beat to the Brief's "Beats to weave in" section.** Draft a new bullet for each accepted Secret describing the Clue's intent in one line. The Brief is the prep doc, not the wrap doc — the Brief surfaces "weave this Clue in if the opportunity lands"; the actual `beats/<slug>.md` file is authored after the session via `/wrap-session` Pass 7 when the GM scratches it into `notes.md`. Don't create a `beats/` file from `/prep-session`. The bullet shape: `- **<Clue intent one-liner>** — push toward `[[secrets/<slug>]]` (currently `<status>`). *(scope: Adventure — <Adventure name>)*`.
   - **Add a one-line nudge to the GM scratchpad** if the GM phrased the push as "remind me to look for an opening" rather than "I'm landing a Clue this session." The scratchpad is the GM-owned forward planning surface; the agent appends a single bullet under the scratchpad heading. The bullet shape: `- Watch for an opening to push `[[secrets/<slug>]]` (`<Adventure name>`).`
   - The agent decides between the two shapes by how the GM phrased the push. Hard commitments ("I'm dropping this") → Beats section. Soft intents ("keep my eye on it") → scratchpad. If the phrasing is ambiguous, default to the scratchpad — it's the lower-commitment surface and the GM can promote it in `/wrap-session` later if the moment lands.
   - Apply the revision via Edit against `.ttrpg-staging/brief-draft.md` so the IDE diff surfaces the change. Re-read the file after editing per the loop's standing re-read-on-each-turn semantic.

2. **Decline (skip this push).** The GM says "no, those need more time" / "not this session" / "skip" / replies addressing a different question. No revision to the Brief; no `_None_` marker, no comment. The agent does not pre-emptively reorder the Brief to reflect the decline; the Brief's content is unchanged. Loop continues to the next queued question.

3. **Defer / non-engagement.** The GM responds without addressing the question (replies to a different topic, asks the agent to do something else, types a partial sentence and moves on). Per ADR-0015's no-re-prompting rule, treat as decline: no revision, no re-asking. Loop continues to the next queued question or the approval ask.

### Worked example

Campaign state: two Adventures `status: active` (`adventures/lost-mines/`, `adventures/cult-of-the-reborn-flame/`). One Adventure `status: introduced` surfaced in the Brief's menu (`adventures/curse-of-strahd/`). `secrets/` contains 6 Secrets:

| Secret slug | `status` | `belongs_to` |
|---|---|---|
| `maren-is-the-spy` | `partially-revealed` | `npcs/maren.md`, `adventures/cult-of-the-reborn-flame/` |
| `prism-core-is-cursed` | `hidden` | `items/the-prism-core.md`, `adventures/cult-of-the-reborn-flame/` |
| `jhera-survived` | `hidden` | `npcs/jhera.md`, `factions/silent-court.md` |
| `strahd-watched-the-funeral` | `partially-revealed` | `npcs/strahd.md`, `adventures/curse-of-strahd/` |
| `vault-key-in-temple` | `hidden` | `locations/old-temple.md` |
| `barovian-mist-is-sentient` | `partially-revealed` | `adventures/curse-of-strahd/` |

The in-focus Adventure set is `{adventures/lost-mines/, adventures/cult-of-the-reborn-flame/, adventures/curse-of-strahd/}` (two active + one menu introduced).

Filtering:

- `maren-is-the-spy` qualifies (Cult arc, `partially-revealed`).
- `prism-core-is-cursed` qualifies (Cult arc, `hidden`).
- `jhera-survived` does not — `belongs_to:` has no in-focus Adventure.
- `strahd-watched-the-funeral` qualifies (Strahd menu, `partially-revealed`).
- `vault-key-in-temple` does not — no Adventure in `belongs_to:`.
- `barovian-mist-is-sentient` qualifies (Strahd menu, `partially-revealed`).

(Lost Mines has zero in-scope Secrets — silent on that Adventure.)

Suppose the Brief's "Beats to weave in" already contains an in-focus `kind: clue` Beat with `linked_secrets: [prism-core-is-cursed]`. That suppresses `prism-core-is-cursed` from the question (the GM's already pushing it via a Clue this session).

The agent fires one batched turn:

> *"Secret-Push check:*
> *— Cult of the Reborn Flame: 1 `partially-revealed` (Maren is the spy).*
> *— Curse of Strahd: 2 `partially-revealed` (Strahd watched the funeral, Barovian mist is sentient).*
> *Want to push any of these this session?"*

GM replies: *"Yes — set up the Maren reveal. Drop a Clue this session."*

The agent revises `.ttrpg-staging/brief-draft.md` via Edit, adding to the "Beats to weave in" section:

```markdown
- **Maren's cover slips at the warehouse** — push toward [[secrets/maren-is-the-spy]] (currently partially-revealed). *(scope: Adventure — Cult of the Reborn Flame)*
```

The Strahd Secrets weren't named in the GM's accept; they fall through as declines per the no-re-prompting rule. The loop continues to the next queued question (or the approval ask if Secret Push was the last one).

## Escalation Prep

**Intent.** Per the Beat `kind:` enum and ADR-0014, `escalation` is the back-pocket lever kind: a held-back Beat the GM lands mid-session when stakes need to rise (the timer expires, reinforcements arrive, the cult succeeds at the ritual the party didn't stop). A session without *any* in-focus `kind: escalation` Beat is a session where the GM has nothing on the bench — the party drifts, the pacing flattens, and the GM has to improvise when stakes need to escalate. Escalation Prep nudges the GM to flag an existing Beat as `escalation`, propose a new one, or explicitly skip ("this session doesn't need one"). Per ADR-0015 this is the category most likely to be opt-out per campaign; improvisation-heavy GMs and low-stakes campaigns may legitimately disable it.

### Predicate

The question fires **at most once per `/prep-session` run** — there's only ever one "no escalation in focus" condition. Concretely:

1. **Check the per-campaign opt-out.** Read `.claude/rules/sessions.md` from the campaign root. If the file contains the literal line `prep-session escalation-prep: off` (whitespace-tolerant; case-sensitive on the keyword `off`), the predicate is silent for the entire run — Escalation Prep is disabled for this campaign. The opt-out is documented in `templates/.claude/rules/sessions.md.template`'s "Per-campaign prep options" section.
2. **Inputs.** Reuse Step 2's `BEATS_IN_FOCUS` (the list of pending Beats the Brief surfaces in full).
3. **Walk `BEATS_IN_FOCUS` for `kind: escalation`.** For each in-focus Beat, read its frontmatter's `kind:` field. If any Beat has `kind: escalation`, the predicate is silent — the session already has at least one escalation lever in focus.
4. **Fire the question if no in-focus Beat is `kind: escalation`.** Single question; no batching needed (only one condition fires).

The predicate is **silent** when:

- `.claude/rules/sessions.md` opts out (per step 1 above).
- At least one Beat in `BEATS_IN_FOCUS` has `kind: escalation`.
- `BEATS_IN_FOCUS` is empty AND `BEATS_OUT_OF_FOCUS_TOTAL == 0` AND `BEATS_UNLINKED_TOTAL == 0` (the campaign has zero pending Beats at all — likely a freshly-scaffolded campaign or early session). The question would be too aspirational; the GM has nothing to flag and the "propose new" option requires more campaign context than the agent has.

### Phrasing template

```
*"No in-focus Beat is `kind: escalation` this session. Flag an existing in-focus Beat as the back-pocket lever, propose a new escalation Beat, or skip (this session doesn't need one)?"*
```

If proposing a new Beat is plausible (in-focus Adventures are non-empty), append the propose-new option as concrete:

> *"… If proposing: I'll seed a Beat from `[active Adventure name]` — likely shape: `[short hint, e.g., "reinforcements from the Cult arrive if the party stalls"]`."*

Conventions:

- **Three-action ask** (flag / propose / skip), same shape as Thread Decay's three-action ask. The structural parallel matters — both categories have a "do nothing" option that's a legitimate answer, not a default-to-decline.
- **Don't enumerate every in-focus Beat in the question.** If the GM says "flag one," the follow-up exchange lists candidates. Inline enumeration would bloat the question for a category that often gets "skip" as the answer.
- The propose-hint sentence is optional but valuable when present — it gives the GM a fast read on whether the propose option is worth the conversation.

### Response handling

1. **Flag (existing Beat becomes the escalation).** The GM names an in-focus Beat (or asks for the list, then picks). Two sub-cases:
   - **GM asks for the list.** Enumerate `BEATS_IN_FOCUS` with wiki links; let the GM pick.
   - **GM names the Beat directly.** Stage an UPDATE to `beats/<slug>.md`: copy the live file into `.ttrpg-staging/beats/<slug>.md`, then Edit the staged copy to set `kind: escalation`. Per the staging pattern, the actual write to the campaign's `beats/<slug>.md` is gated by the Brief's final approval at Step 5.

   Also update the Brief: the bullet for that Beat in "Beats to weave in" gets its `*(scope: ...)*` hint expanded to `*(scope: <prior-scope>; kind: escalation — back-pocket lever)*`. The visual marker is the GM-facing signal that the Beat is now the session's escalation.

2. **Propose (new Beat).** The GM says "yes, propose one" / "draft an escalation from the Cult arc." Three steps:
   - **Draft the Beat content** from the in-focus Adventure(s) the GM named (or, if the GM didn't name one, the primary active Adventure): a one-line description of the escalation, with `linked_adventures:` populated and other `linked_*` lists empty-or-populated per proximity to the source material.
   - **Stage a CREATE** under `.ttrpg-staging/beats/<slug>.md` with `status: pending`, `created: <session date>`, `delivered: ~`, `kind: escalation`, `linked_*` populated.
   - **Add to the Brief's "Beats to weave in"** as a new bullet: `- **<Beat name>** [[beats/<slug>]] — one-line intent. *(scope: Adventure — <name>; kind: escalation — back-pocket lever)*`.

   Both writes are gated by the Brief's final approval at Step 5.

3. **Skip ("this session doesn't need one").** No revision; no Beat change. Loop continues. Skip is a perfectly normal answer — not every session has stakes that benefit from a planned escalation, and the GM is the authority.

4. **Defer / non-engagement.** Per ADR-0015, treat as skip. No re-asking this run.

### Worked example

Campaign state: `.claude/rules/sessions.md` does **not** contain `prep-session escalation-prep: off` (opt-out absent). `BEATS_IN_FOCUS` has 5 Beats, none with `kind: escalation`:

| Beat slug | `kind` |
|---|---|
| `old-owl-well-rumor` | `news` |
| `sera-locket-reveal` | `character-moment` |
| `goblin-ambush-south-road` | `set-piece` |
| `cult-sigil-on-door` | `clue` |
| `darius-old-commander` | `character-moment` |

In-focus Adventures: `[[Lost Mines of Phandelver]]`, `[[Cult of the Reborn Flame]]`.

Agent fires:

> *"No in-focus Beat is `kind: escalation` this session. Flag an existing in-focus Beat as the back-pocket lever, propose a new escalation Beat, or skip (this session doesn't need one)? If proposing: I'll seed a Beat from Cult of the Reborn Flame — likely shape: 'the cult completes the ritual the party isn't stopping in time.'"*

GM replies: *"Yes propose. Cult ritual completes if they don't reach the chapel by midnight in-game."*

Agent stages `.ttrpg-staging/beats/cult-ritual-completes.md`:

```yaml
---
status: pending
created: 2026-06-07
delivered: ~
kind: escalation
linked_pcs: []
linked_npcs: []
linked_adventures: [cult-of-the-reborn-flame]
linked_locations: [phandalin]
linked_secrets: []
---

# The cult ritual completes

If the party doesn't reach the chapel by midnight in-game, the cult finishes the binding ritual. The party arrives to a sealed sanctum and the first signs of the Reborn Flame on the horizon.
```

And revises `.ttrpg-staging/brief-draft.md` via Edit, adding to "Beats to weave in":

```markdown
- **The cult ritual completes** [[beats/cult-ritual-completes]] — back-pocket if the party stalls past midnight in-game. *(scope: Adventure — Cult of the Reborn Flame; kind: escalation — back-pocket lever)*
```

Both writes are gated by the Brief's final approval.

## GM Focus Check

**Intent.** Always-fires catch-all final question. Every rule-based category before this one fires only when its predicate hits, which means a session whose drafted Brief perfectly matches the rules will see *zero* questions. That's a failure mode: even a perfect Brief may miss something the GM has been thinking about (a side-conversation with a player, an idea from this morning's commute, a planned NPC reveal that doesn't fit any category yet). GM Focus Check is the explicit invitation to surface it. It runs **last** in the question pass so the rule-based categories have already done their work — the GM's "anything else" answer is informed by what the agent already asked.

### Predicate

The question fires **unconditionally**, every run, regardless of campaign state. There is no opt-out; the question is short, the answer is fast, and the always-fires guarantee is the value (per ADR-0015's "the GM can develop a stable mental model" criterion — they know one question always comes at the end).

The question fires **last** in the question pass. After the other six categories (Coverage Check, Tiering Check, Thread Decay, Decision Request, Secret Push, Escalation Prep) have queued their questions or stayed silent, GM Focus Check appends one final question to the loop's queue. If the queue is otherwise empty, GM Focus Check is the *only* question the GM sees — and that's intentional.

The predicate is **silent** when:

- Never. GM Focus Check is the one category that fires for every run.

### Phrasing template

```
*"Anything you're planning this session that's not in the draft? (Side conversations, surprise NPC, a scene you've been waiting to land, anything from your head that isn't on the page.)"*
```

When the GM has been actively engaging with prior questions this run (the loop has had at least one accept response from a prior category), soften the framing:

> *"Last one — anything else you're planning that isn't in the draft yet? (Skip if everything's covered.)"*

Conventions:

- **Open-ended.** The question isn't scoped to a category, a section, or a kind of thing. The GM may answer with a Beat shape, a Thread reminder, a name pick, an NPC motivation note, or a session-opener twist — any of those is a valid answer.
- The parenthetical is examples, not a constraint. Don't replace it with a list of specific category targets ("anything Beat-shaped? Thread-shaped?") — that turns the catch-all back into a rule-shaped question and defeats the purpose.
- "Skip if everything's covered" framing is essential. The question must be cheap to dismiss; a GM who feels obligated to answer something every time will start dreading the question.

### Response handling

The agent classifies the GM's free-form answer into one of three Brief revision shapes, the same way Secret Push routes accept-shapes:

1. **Concrete forward-facing content.** The GM names a planned scene, an NPC reveal, an item drop, a piece of news. Two sub-cases:
   - **The content fits a known Brief section.** Route to that section. A planned Beat → add to "Beats to weave in" (with a `*(scope: GM focus)*` hint). A surprise NPC the party will meet → add to "NPCs the party may encounter" with a one-line stance note. A planned consequence the agent didn't surface → add to "Recent significant consequences." A new location → add to "Locations" (and apply the Step 4 sensory-detail write-back rule if the GM authored a sensory hook).
   - **The content is forward-planning the GM wants to remember but isn't section-bound.** Add a one-line nudge to the GM scratchpad: `- <GM's note, lightly tidied>.`
2. **Direction for a section the agent already drafted.** The GM says "rewrite Opening Scene to start with the bell tolling" or "drop the goblin ambush — the party went the other way." Apply via Edit to the named section. For a drop, replace the bullet with `_None._` or remove it cleanly per the section's rendering rules.
3. **"No, all covered" / "skip" / "nothing."** No revision. Loop exits to Step 4's approval ask (this is the last question by construction).

Per ADR-0015's no-re-prompting rule, a non-engagement reply (the GM addresses something else or moves on without answering) is treated as "all covered." The agent does not re-ping.

**Multiple things in one answer.** GMs commonly dump several thoughts at once ("the goblin ambush should be a chase now, and add a Beat for Maren overhearing them at the door, and remind me to figure out the name of the temple priest"). Process each part:
- Chase the goblin ambush → revise the existing Beat bullet via Edit.
- Maren Beat → add to "Beats to weave in".
- Name-the-priest → scratchpad nudge.

Apply all revisions in one Edit batch (one or several Edit calls in sequence; the loop turn doesn't return to chat between them).

### Worked example

Campaign state: this is the last question of the loop. Prior categories produced 2 Secret Push asks (one accepted, one declined) and one Decision Request (Opening Scene proposed and accepted). Brief is otherwise final.

Agent fires:

> *"Last one — anything else you're planning that isn't in the draft yet? (Skip if everything's covered.)"*

GM replies: *"Yeah, two things. The party's going to find a kid hiding in the chapel — name her Tessa, she's the deacon's daughter. And remind me to roll on the wandering encounter table if they take more than an hour to reach the chapel."*

Agent processes:

1. Tessa-the-deacon's-daughter → add to "NPCs the party may encounter":
   ```markdown
   - **Tessa** — deacon's daughter, hiding in the chapel. Surprise NPC the party may find this session.
   ```
2. Wandering-encounter reminder → add to GM scratchpad:
   ```markdown
   - Roll on the wandering encounter table if the party takes >1 hour to reach the chapel.
   ```

Both via Edit against `.ttrpg-staging/brief-draft.md`. The agent does **not** also create `npcs/tessa.md` — that's a Reference-note CREATE the GM authors after the session if Tessa lands as a recurring NPC. The Brief is forward-planning prep; the Reference-note tree grows from `/wrap-session` notes.

Loop exits to Step 4's approval ask.

## Format conventions for future categories

The seven ADR-0015 categories are all documented above. If a future slice adds a new category (the ADR allows new kinds to surface dedicated questions — see ADR-0014's `kind:` open-enum reasoning), follow the same five subsections used by every category above:

- **Intent.** One-paragraph statement of why the question exists and what GM behavior it's nudging toward.
- **Predicate.** A numbered prose walkthrough of what state the agent reads and what condition fires the question. Reference the canonical query in `secret-store.md` / `bidi-link-maintenance.md` / `frontmatter-schemas.md` where applicable rather than re-deriving algorithms inline. Call out the silent-cases explicitly.
- **Phrasing template.** One or more concrete templates with placeholders. Document conventions for label choice (titles vs slugs vs names), inline truncation rules, and the soft-vs-hard ask tone the question should carry.
- **Response handling.** The accept / decline / defer shapes (or the category-specific shape set, e.g., Thread Decay's decay/push/leave triple) and what the agent does on each. Where accept produces a Brief revision, specify which section is revised, the exact bullet/line shape, and which staging surface the revision lands on.
- **Worked example.** A concrete fixture-shaped scenario showing predicate filtering, batched phrasing, GM reply, and resulting Brief revision (or no-op for decline). Keep examples small but realistic — drawn from `tests/fixtures/` where possible so the same fixture exercises multiple references.

When inserting a new category, place it in the file in the same order it fires in the loop, and update the "## The seven categories" list at the top with the new entry. Categories that should fire **last** belong after GM Focus Check semantically only if there's a compelling reason — the always-fires final question is normally the closer. Per-campaign opt-outs follow the Escalation Prep precedent: literal-line match in `.claude/rules/sessions.md` documented in `templates/.claude/rules/sessions.md.template`.

Keep per-category prose tight; this reference grows linearly with the category count and stays readable only if each category's section stays focused.
