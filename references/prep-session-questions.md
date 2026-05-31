# /prep-session question categories

`/prep-session`'s Step 3.5 (the conversational refinement loop introduced by [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md)) surfaces rule-based follow-up questions about the drafted Brief. Each question category has a **predicate** the agent evaluates against current campaign state and the just-drafted Brief, a **phrasing template** for asking the GM, and **response-handling notes** for how the agent acts on the answer. A category stays silent when its predicate is false; the GM only sees questions whose conditions are actually met.

The corresponding ADR is [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md). The Secret enumeration that the Secret Push predicate walks lives in [`references/secret-store.md`](./secret-store.md). The staging behavior the agent uses when revising the Brief on a GM response lives in [`references/staging-pattern.md`](./staging-pattern.md) ("Iterative agent revisions during a review loop"). The Brief section template the agent revises lives in `skills/prep-session/SKILL.md` Step 3.

## How the loop uses these questions

Step 3.5 evaluates every category in order. Each category whose predicate is true contributes one (or, in the case of categories that legitimately produce multiple findings, a small batch of) question(s) to the loop's queue. The agent then presents queued questions to the GM, ideally batching closely-related questions into a single turn so the GM isn't pinged seven separate times.

Per ADR-0015's skip semantics:

- The agent's loop preamble mentions the verbal escape (*"...or say 'looks good' / 'skip questions' to finalize as-is."*).
- If the GM responds without addressing a queued question, that question is dropped — treat the non-response as "decided not to engage." **No re-prompting** within the same run.
- "approve" / "looks good" / "draft is good" exits the loop; "cancel" exits without writing (per the staging pattern's cancel semantics).

When the GM does engage with a question, the agent revises the staged `.ttrpg-staging/brief-draft.md` via the Edit tool so the IDE shows a native diff (per [#16](https://github.com/snlemons/game_manager/issues/16)), then re-presents the loop preamble for the next turn.

## The seven categories (one implemented in this slice)

ADR-0015 enumerates seven categories. **This reference currently documents one**: Secret Push. The other six (Coverage check, Tiering check, Thread decay, Decision request, Escalation prep, GM focus check) will be added in [#40](https://github.com/snlemons/game_manager/issues/40) following the same per-category format below.

## Secret Push

**Intent.** Surface Secrets that are partially or fully hidden but tied to an Adventure the party is likely to engage with this session, so the GM can decide whether to push the revelation forward this session. A `partially-revealed` Secret with no Clue Beat planned is a story payoff actively waiting on the GM; a `hidden` Secret on the in-focus arc is one the GM may have been waiting to drop. The Brief shouldn't list Secrets directly (per ADR-0015: "Clue Beats may appear in the Brief; their Secrets do not"), but the prep-time question is the right surface to nudge the GM toward authoring a Clue Beat or otherwise advancing the Secret this session.

### Predicate

The question fires once per **(Adventure, Secret-status) pair** whose enumeration is non-empty. Concretely:

1. **Compute the in-focus Adventure set**, identical to the `IN_FOCUS_ADVENTURES` set Step 2's tiered Beat surfacing computes: the union of every `status: active` Adventure and every `status: introduced` Adventure surfaced in the Brief's "Menu of next-session options" section. `completed` and `abandoned` Adventures are never in focus. Introduced Adventures the GM is *not* putting on the menu this session are not in focus on the Adventure signal.
2. **Walk `secrets/` directly** per the enumeration algorithm in [`references/secret-store.md`](./secret-store.md) (`list_all`). For each `.md` file under `secrets/`:
   - Parse frontmatter as YAML; skip silently if it doesn't parse or doesn't start with `---\n`.
   - Read the `status:` and `belongs_to:` fields. (The schema is in `references/frontmatter-schemas.md`; `belongs_to:` is a non-empty list of non-ephemeral container paths.)
3. **Filter by status.** Keep only Secrets whose `status:` is `hidden` or `partially-revealed`. `revealed` Secrets have already landed for the party and need no nudge.
4. **Filter by `belongs_to:` intersection with the in-focus Adventure set.** A Secret qualifies if **any** entry in its `belongs_to:` list matches an in-focus Adventure's container path. Adventure containers are exact-string matched in their canonical directory form (`adventures/<slug>/` with trailing slash) per [`references/secret-store.md`](./secret-store.md)'s `find_by_container` semantics. A Secret whose `belongs_to:` only names NPC / location / faction / item containers is not in scope of *this* question — Secret Push is the Adventure-scoped surfacing; per-container surfacing of NPC / location Secrets is a different question category (deferred to #40 or beyond).
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

## Format conventions for future categories

When [#40](https://github.com/snlemons/game_manager/issues/40) adds the other six categories (Coverage check, Tiering check, Thread decay, Decision request, Escalation prep, GM focus check), each follows the same three subsections used above:

- **Intent.** One-paragraph statement of why the question exists and what GM behavior it's nudging toward.
- **Predicate.** A numbered prose walkthrough of what state the agent reads and what condition fires the question. Reference the canonical query in `references/secret-store.md` / `references/bidi-link-maintenance.md` / `references/frontmatter-schemas.md` where applicable rather than re-deriving algorithms inline. Call out the silent-cases explicitly.
- **Phrasing template.** One or more concrete templates with placeholders. Document conventions for label choice (titles vs slugs vs names), inline truncation rules, and the soft-vs-hard ask tone the question should carry.
- **Response handling.** The three shapes (accept / decline / defer) and what the agent does on each. Where accept produces a Brief revision, specify which section is revised, the exact bullet/line shape, and which staging surface the revision lands on.
- **Worked example.** A concrete fixture-shaped scenario showing predicate filtering, batched phrasing, GM reply, and resulting Brief revision (or no-op for decline). Keep examples small but realistic — drawn from `tests/fixtures/secrets/` where possible so the same fixture exercises multiple references.

Keep per-category prose tight; this reference grows linearly with the category count and stays readable only if each category's section stays focused.
