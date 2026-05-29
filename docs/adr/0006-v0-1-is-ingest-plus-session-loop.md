# v0.1 is ingest plus the minimum session loop

v0.1 ships **`/ingest`** (extract structure from existing campaign notes into a scaffolded repo) plus **`/prep-session`** and **`/wrap-session`** (the minimum operational loop). Single campaign at a time, no Atlas, no continuity catching, no proactive features.

The first user (Sofia) has several active campaigns in other tools; ingest is required for the tool to be usable at all. But ingest alone produces a half-product — imported campaigns sit unused if there's no way to actually run a session through the tool — so the loop ships with it. The loop on imported state is also the strongest test of whether ingest did its job (a useful brief generated from an imported log proves the import).

## Considered options

- **v0.1 = session loop only (no ingest).** Rejected: assumes a first user starting fresh, which this user isn't. Forces hand-porting that a Claude-native tool should be doing.
- **v0.1 = ingest only.** Rejected: imported campaigns go stale before any session can run through the tool, breaking dogfooding.
- **v0.1 = lazy entity creation only.** Rejected: too narrow without `/wrap-session` to give Threads and Consequences a creation moment.

## Ingest input mechanism in v0.1

`/ingest` reads **local markdown files only** (the GM exports their Google Docs as Markdown and points ingest at the directory). Drive MCP, URL fetch, paste-into-conversation, and other input mechanisms are deferred to future versions. The migration is a one-time event per campaign, so the manual export step is an acceptable cost for v0.1.

## Out of scope for v0.1

- **Atlas** and cross-repo linking. v0.1 campaigns are standalone. Override granularity ([[CONTEXT#campaign-local-override]]) and `[[wiki link]]` resolution into a separate Atlas repo are deferred.
- **Continuity catching.** Proactive contradiction-detection is a v0.2+ concern.
- **Multi-campaign workflows.** Each campaign is its own repo, but the tool only operates on one at a time.
- **Player-facing exports** (redacted views).
- **Adventure ingestion as distinct from campaign ingestion** — published-module import gets the same treatment as any other input in v0.1.
- **`/init-campaign`** (fresh-start without source docs) — fast-follow after v0.1.
- **`/init-adventure`** (scaffold a new adventure within a campaign, or as a standalone adventure repo) — fast-follow after v0.1. Implies a future decision about whether standalone adventures live in adventure-as-root repos or campaign-of-one-adventure repos.
