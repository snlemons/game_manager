# Temporal model and campaign overview

The campaign tracks time on **two axes** (real-world and in-fiction), **neither required**, with **different reliability between ingest-era and session-tracked data**. State is exposed through two surfaces: structured frontmatter on adventures (queryable, machine-readable) and an agent-maintained `campaign.md` (human-readable snapshot).

> **Live spec:** the canonical `campaign.md` composer is `references/campaign-overview-composer.md`. The Adventure frontmatter schema is `references/frontmatter-schemas.md`. This ADR is the historical decision record; the references are the live specs the skills run.

## Adventure frontmatter

```yaml
status: completed                       # required: introduced | active | completed | abandoned
order: 3                                # ingest-era only — reliable GM-supplied sequence
introduced: ~                           # real-world date; null when unknown
started: ~                              # real-world date; null when unknown
completed: ~                            # real-world date; null when unknown
in_world_duration: "3 in-game months"   # optional, free-form prose
real_world_duration: "~6 sessions"      # optional, free-form prose
```

- `status` is the only universally-required field.
- For **ingest-era adventures**, `order` provides reliable sequence; dates are null because the GM doesn't know them.
- For **session-tracked adventures**, dates get filled precisely by `/wrap-session`; `order` is unnecessary (derivable from `started`).
- Durations are narrative annotations the GM can supply when known, in any form. The agent treats them as prose, not structured time.

## Why both real-world and in-fiction time

The first user has campaigns running across multiple years where in-fiction durations are more memorable than real-world dates ("the Lost Mines arc took about 3 in-game months"). A real-world-only model couldn't honestly represent ingest-era history. Both axes optional and free-form means we capture what the GM actually has, no fabrication.

## Campaign overview file

`campaign.md` at the campaign root is **agent-generated**, rewritten by `/wrap-session` (and `/ingest`). It shows the campaign's *current* state in glance-readable form. Frontmatter and per-file storage power the agent's queries; `campaign.md` powers the GM's "open the repo and orient myself" need.

The composer leads with **"Where the party might go next session"** — the forward-looking *menu* the GM is actually orienting against when they reopen the repo. The menu is a bulleted set:

- `status: active` Adventures (if any), framed as "could continue any of these."
- `status: introduced` Adventures the party could pick up next session, one line each — the open-world menu of next-session options.
- Recent open Threads that could plausibly become a session focus, one line each.
- Party location as a separate line when known (a piece of context, not the framing).

After the menu, the file continues with the full **Open threads** list (every `status: open` Thread), **Recent significant consequences**, and **Pending beats** as glance-readable state sections. Older revisions of this ADR led with separate "Active adventures" and "Party location" sections that implicitly assumed one focused arc at a time; that framing didn't survive contact with open-world / sandbox campaigns, where multiple Adventures are available and none is currently active. The menu-led shape handles single-arc, multi-arc, and no-active cases without a new mode flag.

Manual GM edits to `campaign.md` are reconciled (or overwritten with warning) at next regeneration. GM-editorial campaign notes (themes, pitch, house rules) live in a separate file the agent doesn't touch.

## Timeline is generated on demand

`/timeline` produces a historical view by combining ingest-era adventure ordering (from `order:` and frontmatter status) with session-tracked precise dates. Ingest-era items appear in an undated ordered bucket; session-tracked items appear with dates. No maintained `timeline.md` file exists.

## Consequences

- The agent never asks the GM to invent dates it doesn't have.
- Adding new adventure metadata (e.g., system-specific fields) is additive; existing files don't need migration.
- `campaign.md` drift is possible if `/wrap-session` fails or the GM hand-edits. Mitigation: regenerate-with-confirmation pattern in `/wrap-session`.
- **Open-world / sandbox campaigns are first-class.** The "Where the party might go next session" framing supports zero, one, or many `status: active` Adventures equally — multi-active and no-active states render naturally instead of being edge cases the composer has to apologise for. The Adventure status enum (`introduced | active | completed | abandoned`) and the rest of the frontmatter schema are unchanged; only the composer's surface and the Brief's forward-looking section absorb the open-world case (see ADR-0009 surfacing, ADR-0010 Brief structure, ADR-0011 wrap-session status detection).
