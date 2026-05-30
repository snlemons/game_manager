# `campaign.md` composer

Canonical spec for the agent-maintained Campaign overview file. `/wrap-session`, `/prep-session`, and `/ingest` all regenerate `campaign.md` from current campaign state using this composer. They differ only in two well-bounded ways (called out under "Skill-specific variants" below); the section shape, ordering, and rendering rules are otherwise identical.

The corresponding ADR is [ADR-0007](../docs/adr/0007-temporal-model-and-campaign-overview.md) — this reference is the live spec; the ADR is the historical decision.

The campaign-root `campaign.md` is **agent-generated**. Manual GM edits are reconciled (or overwritten with warning) at next regeneration (ADR-0007). GM-editorial content (themes, pitch, house rules) lives in a separate file the agent doesn't touch.

## When this composer runs

- **`/wrap-session`** runs it at Step 5 #7 — after writing the Log and the session's new/updated lifecycle objects, so the rendered state reflects this session's effects.
- **`/prep-session`** runs it at Step 2.5 (the `campaign.md` refresh) — before drafting the Brief, so the Brief reads from a current overview. This regen is independent of Brief approval: even if the GM cancels at Step 4, the refresh stays on disk because it reflects state the GM already changed.
- **`/ingest`** runs it at Phase 4 Step 2 — after the per-doc extraction loop, replacing the scaffolder's placeholder with the populated campaign's first overview.

In every case the composer is a deterministic function of current campaign state. Given identical state, two runs produce byte-identical content.

## Section ordering

Render exactly these sections in this exact order:

1. Header (campaign name + system, optional Status / Last event lines — see "Skill-specific variants")
2. `## Where the party might go next session` — the forward-looking menu
3. `## Adventures` — **ingest-only**, skipped by `/wrap-session` and `/prep-session`
4. `## Open threads`
5. `## Recent significant consequences`
6. `## Pending beats`

The header preserves verbatim the italic agent-maintained header paragraph from `templates/campaign.md.template`. Do not paraphrase that paragraph — it tells the GM the file is agent-managed.

## Header

```markdown
# {{CAMPAIGN_NAME}} — Campaign Overview

*This file is agent-maintained. It snapshots the campaign's current state in glance-readable form and is rewritten by `/wrap-session` and `/ingest`. Manual edits will be reconciled (or overwritten with warning) at the next regeneration. For editorial campaign notes (themes, pitch, house rules), use a separate file the agent doesn't touch.*

- **Campaign:** {{CAMPAIGN_NAME}}
- **System:** {{CAMPAIGN_SYSTEM}}
```

- `{{CAMPAIGN_NAME}}` — read from the existing `campaign.md`'s H1 or `**Campaign:**` line (whichever is present). Don't re-prompt the GM. If neither is parseable, surface the path and ask before continuing — do not invent a name.
- `{{CAMPAIGN_SYSTEM}}` — read from the existing `**System:**` line.

## `## Where the party might go next session`

This menu-led section is the file's lead surface. It replaces older standalone "Active adventures" + "Party location" framings and handles zero, one, or many `status: active` Adventures equally (issue #13, ADR-0007). Render its sub-buckets in this order:

### 1. Active arcs — conditional sub-bucket

If any `adventures/<slug>/adventure.md` has frontmatter `status: active`, render:

```markdown
**Active arcs — could continue any of these:**

- **[[<Adventure title>]]** — one-line current state.
- ...
```

If **no** Adventures have `status: active`, **omit this sub-bucket entirely** — no heading, no empty bullet list. The menu falls straight through to "Introduced Adventures." This is the open-world / no-active case rendering correctly (issue #13).

### 2. Introduced Adventures the party could pick up — always rendered

Always render the bold sub-heading. For every Adventure with `status: introduced`, render one bullet:

```markdown
**Introduced Adventures the party could pick up:**

- **[[<Adventure title>]]** — one-line hook/state. *(order N)*
- ...
```

- `*(order N)*` parenthetical is shown only if `order:` is set; omit it otherwise.
- Sort by `order:` ascending. Null-`order:` Adventures sort alphabetically by slug after numbered ones.
- If the campaign has zero `status: introduced` Adventures, render `_None._` under the sub-heading so the GM sees the agent looked.

### 3. Recent open Threads that could become a session focus

```markdown
**Recent open Threads that could become a session focus:**

- **[[<Thread title>]]** — one-line body excerpt.
- ...
```

This is a **curated subset** of `status: open` Threads — the ones substantial enough to drive a session, not every flavor reminder. Heuristic: include Threads whose body suggests an arc-in-waiting (a place to investigate, a person to confront, an obligation big enough to organize a session around); exclude flavor-only reminders. When uncertain, lean toward including — the GM scans the menu and ignores misses cheaply.

Order: descending by `created:` (most recent first; slug asc as tiebreak when dates tie or are null). If no Threads qualify, render `_None._`.

The full open-Threads list still appears below in the `## Open threads` section; this curated subset is a menu cue.

### 4. Party location

A single line at the end of the menu (not a sub-heading — just a line of context):

```markdown
**Party location:** <prose>
```

Derive in this order:

1. **`/wrap-session` path:** pull from the just-written Log's closing state, with `[[wiki link]]` to the location's Reference note.
2. **`/ingest` path:** among `status: active` Adventures, pick the one with the highest `order:` (most recently started, per ADR-0007's ingest-era ordering). If multiple tie or none are active, fall back to the highest-`order:` Adventure overall regardless of status. If `order:` is null across the board, fall back to the alphabetically-last Adventure slug and explicitly call this out in the prose. Then read that Adventure's `adventure.md` body for a wiki link to a `locations/<slug>.md` or a clearly-named place in prose. If a location is identifiable, write: *"The party is at [[<Location>]], most recently engaged with [[<Adventure>]]."* If not but an Adventure is, write: *"The party's most recent activity is [[<Adventure>]]; current location not stated in source docs — GM to update."* If neither is identifiable, write: *"Party location not yet established — GM to update."*

In **every** path, if the location is unclear, say so plainly — *"Party location not stated in this session's Log."* (or the `/ingest` equivalent). **Never invent a location.** ADR-0007: the agent never asks the GM to invent facts it doesn't have.

## `## Adventures` (ingest-only)

`/ingest` Phase 4 renders this full-history section after the menu. `/wrap-session` and `/prep-session` **do not render this section** — they skip from the menu straight to `## Open threads`.

Rationale: at ingest time the GM is finalizing the campaign's entire history through today; the full Adventures list is load-bearing context. Session-to-session, the menu-led "Where the party might go" surface plus the Log captures recency; repeating the whole Adventure history every wrap would be noise.

```markdown
## Adventures

- **[[<Adventure title>]]** (order N) — <status>. <lifecycle annotations from frontmatter>.
- ...
```

- List **every** Adventure in the campaign, sorted by `order:` ascending. Null-order Adventures (those the GM skipped at the Phase 4 order prompt) appear after numbered ones, in alphabetical slug order.
- `<Adventure title>` is the H1 from `adventure.md`.
- `(order N)` is shown only if `order:` is set; omit the parenthetical otherwise.
- `<status>` is the literal frontmatter `status` value: `introduced`, `active`, `completed`, or `abandoned`.
- **Lifecycle annotations** are the optional frontmatter fields, joined as a short comma-separated phrase:
  - `in_world_duration` rendered verbatim if set (e.g., "~3 in-game months").
  - `real_world_duration` rendered verbatim if set (e.g., "~6 sessions").
  - `started` rendered as "started YYYY-MM-DD" if set; ingest-era usually null.
  - `completed` rendered as "completed YYYY-MM-DD" if set; ingest-era usually null.

  If all four are null, omit the annotations clause entirely — don't write a trailing period after nothing.

Example bullets:

```markdown
- **[[Lost Mines of Phandelver]]** (order 1) — completed. ~6 sessions, ~3 in-game months.
- **[[Cragmaw Castle]]** (order 2) — completed. ~4 sessions.
- **[[Wave Echo Cave]]** (order 3) — active.
- **[[Side Mystery: The Veiled Court]]** — introduced.
```

If there are zero Adventures, render `*None yet.*` under the heading. (Possible but unusual at end of ingest — would mean the source corpus was world-info-only.)

## `## Open threads`

For every `threads/<slug>.md` with frontmatter `status: open`, render a bullet:

```markdown
- **[[<Thread title>]]** — <one-line body excerpt>.
```

- `<Thread title>` is the file's H1.
- `<one-line body excerpt>` is the first sentence of the Thread's body (after the H1 and blank line). Truncate at the first period for terseness if the body is multi-sentence. Preserve wiki links inside the excerpt verbatim (don't strip `[[...]]`).
- Order: descending by `created:` if `created:` is set (most recent first); for ingest-era Threads where `created:` may be absent, fall back to lexicographic slug order. Don't invent a `created:` value.

If there are zero open Threads, render `*None.*` under the heading.

This is the **full list** of open Threads; the menu above is a curated subset.

## `## Recent significant consequences`

For every `consequences/<slug>.md`, render a bullet:

```markdown
- **[[<Consequence title>]]** — <one-line body excerpt>.
```

Same excerpt rules as Threads. Order: descending by `created:` when set; for ingest-era Consequences where `created:` is null (the agent honors the date-honesty rule and doesn't fabricate ingest-day dates), fall back to lexicographic slug order.

### Recency filter — skill-specific

- **`/wrap-session` and `/prep-session`:** truncate to the top 5–10 (whatever fits on a glance-readable screen). Don't dump the entire history.
- **`/ingest` Phase 4:** show **every** Consequence. Do not truncate. At ingest time, everything just landed; truncation would hide the just-ingested history the GM is about to commit. Once `/wrap-session` runs and `created:` dates start being precise, normal truncation applies.

If there are zero Consequences, render `*None.*` under the heading.

## `## Pending beats`

Render one bullet per `status: pending` Beat in `beats/`, sorted by `created:` ascending (oldest first, so freshly-ingested Beats appear in source-doc order). Format:

```markdown
- **[[<Beat title>]]** — <one-line summary from frontmatter or body opening>
```

If a Beat has `linked_adventures`, `linked_pcs`, or `linked_locations` populated, optionally append a short scope hint: `(linked: <names>)`.

If `beats/` has no `status: pending` files, render `*None yet.*` under the heading.

Note on scale: when there are many pending Beats (common after ingesting a long-running campaign with prepped encounter content), this section gets long. ADR-0009's surfacing-at-scale design (relevance-filtered tiered display) is a **Brief-time** concern only; `campaign.md` is the state snapshot and shows everything. Filtering belongs in the Brief, not here.

## Skill-specific variants

Two surface-level differences from the base spec are intentional, both flowing from what's true at the time each skill runs:

### `/ingest` Phase 4 additions

- Adds two header lines below `**System:**`:
  - `- **Status:** active` (the campaign as a whole is active at end of ingest; future regens overwrite if the GM doesn't manually maintain it).
  - `- **Last event:** YYYY-MM-DD (ingest)` — today's date suffixed `(ingest)`. After `/wrap-session` runs, that workflow may replace this line with the wrapped session's date.
- Renders the full `## Adventures` history section between the menu and `## Open threads` (see above).
- Shows **every** Consequence in `## Recent significant consequences` (no top-N truncation).

### `/wrap-session` and `/prep-session` shape

- No Status / Last event header lines.
- **No `## Adventures` section.** Skip from the menu straight to `## Open threads`.
- Truncate Consequences to top 5–10 by recency.

## Determinism contract

Given identical campaign state, two composer runs must produce byte-identical output. Impose deterministic ordering everywhere — never rely on filesystem enumeration order. The test suite at `tests/test_wrap_session_idempotency.py` (`TestCampaignMdRegenerationIsDeterministic`) pins this property.

## Why this composer is shared

The composer's job is to read campaign state and produce the same human-readable snapshot. Whether the entry point is `/wrap-session`, `/prep-session`, or `/ingest`, the state is what it is and the rendering should match. Skills don't share code; consistency comes from this single specification. If a skill's behavior drifts from this reference, the divergence is a documentation bug to fix here, not a per-skill variation to preserve.
