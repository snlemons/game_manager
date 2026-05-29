# Temporal model and campaign overview

The campaign tracks time on **two axes** (real-world and in-fiction), **neither required**, with **different reliability between ingest-era and session-tracked data**. State is exposed through two surfaces: structured frontmatter on adventures (queryable, machine-readable) and an agent-maintained `campaign.md` (human-readable snapshot).

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

`campaign.md` at the campaign root is **agent-generated**, rewritten by `/wrap-session` (and `/ingest`). It shows the campaign's *current* state in glance-readable form: active adventures, open threads, recent significant consequences, party location. Frontmatter and per-file storage power the agent's queries; `campaign.md` powers the GM's "open the repo and orient myself" need.

Manual GM edits to `campaign.md` are reconciled (or overwritten with warning) at next regeneration. GM-editorial campaign notes (themes, pitch, house rules) live in a separate file the agent doesn't touch.

## Timeline is generated on demand

`/timeline` produces a historical view by combining ingest-era adventure ordering (from `order:` and frontmatter status) with session-tracked precise dates. Ingest-era items appear in an undated ordered bucket; session-tracked items appear with dates. No maintained `timeline.md` file exists.

## Consequences

- The agent never asks the GM to invent dates it doesn't have.
- Adding new adventure metadata (e.g., system-specific fields) is additive; existing files don't need migration.
- `campaign.md` drift is possible if `/wrap-session` fails or the GM hand-edits. Mitigation: regenerate-with-confirmation pattern in `/wrap-session`.
