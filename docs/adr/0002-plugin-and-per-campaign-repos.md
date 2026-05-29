# Plugin distribution; campaign data in GM-owned repos

The system ships as a **Claude Code plugin** (skills, slash commands, templates). The GM's campaign data lives in **a separate git repo per campaign**, owned by the GM. A shared **Atlas** repo holds cross-campaign setting content; campaigns reference it and may override it locally (see [[CONTEXT#campaign-local-override]]).

## Considered options

- **One mono-repo containing tool + all campaigns as subdirectories.** Rejected: entangles tool-update history with campaign-evolution history, makes single-campaign sharing impossible, and ties campaign portability to the tool's continued existence — directly against the brief's "GMs have been burned by tools that disappeared" concern.
- **One GM-owned vault repo with multiple campaigns as subdirectories.** Rejected: Atlas-vs-campaign overrides are messier when both live in the same repo, can't share one campaign without sharing all of them, and git history mixes campaigns.

## Consequences

- The plugin scaffolds a root `CLAUDE.md` and a `.claude/rules/` directory into the campaign on `/ingest` (see [ADR-0012](./0012-rule-organization-via-claude-rules.md)); those files are owned by the campaign repo from that point on. When the plugin's conventions evolve, scaffolded campaigns drift — an `/upgrade-campaign` workflow is implied but not yet designed.
- Cross-repo linking (a campaign session note pointing into the Atlas) needs a resolution mechanism. The brief mandates `[[wiki link]]` syntax, so disambiguation between "campaign-local Waterdeep" and "Atlas Waterdeep" has to happen without inventing new syntax. Decision deferred.
