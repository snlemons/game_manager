# Packaging: skills directory at `~/.claude/skills/ttrpg-gm/`

The plugin (see [ADR-0002](./0002-plugin-and-per-campaign-repos.md)) ships as a **Claude Code skills directory installed to `~/.claude/skills/ttrpg-gm/`**, not as a formal Claude Code plugin distributed via a plugin install command. Users clone the repo into the skills directory and update via `git pull`.

## Repo layout

```
ttrpg-gm/                              # → ~/.claude/skills/ttrpg-gm/
├── skills/
│   ├── ingest/
│   │   └── SKILL.md                   # /ingest workflow
│   ├── prep-session/
│   │   └── SKILL.md                   # /prep-session workflow
│   └── wrap-session/
│       └── SKILL.md                   # /wrap-session workflow
├── templates/
│   ├── CLAUDE.md.template             # root CLAUDE.md scaffolded into campaigns
│   ├── .claude/
│   │   └── rules/
│   │       ├── sessions.md.template
│   │       └── adventures.md.template
│   └── campaign.md.template
├── CONTEXT.md                         # this project's glossary
├── docs/adr/                          # this project's ADRs
└── README.md
```

Each skill is a directory containing a `SKILL.md` file with frontmatter (`name`, `description`) — the standard Claude Code skill convention. The template path mirror (`templates/.claude/rules/`) reflects the campaign-side layout the templates are scaffolded into.

The plugin's own `CONTEXT.md` and `docs/adr/` stay in the plugin repo. The plugin scaffolds *different* files (the templates above) into campaign repos — scaffolded files contain rules verbatim, not links back to plugin docs, so campaign repos remain self-contained.

## Considered alternatives

- **Formal Claude Code plugin (`claude plugin install`).** Rejected for v0.1: depends on plugin marketplace specifics that may shift; skills directory works today with the mechanisms Claude Code already supports. Migration to the formal plugin system later is mostly repackaging.
- **Standalone repo cloned anywhere, no global registration.** Rejected: would require the GM to run Claude Code from inside the plugin repo to get the skills, which conflicts with [ADR-0002](./0002-plugin-and-per-campaign-repos.md) (campaigns are separate repos the GM works from).

## Consequences

- Slash commands (`/ingest`, `/prep-session`, `/wrap-session`) are globally available regardless of the GM's cwd, because skills install globally.
- Updates flow via `git pull` in `~/.claude/skills/ttrpg-gm/`. Versioning is git tags.
- The plugin doesn't depend on Claude Code's plugin marketplace existing or having a stable API.
- Migration to the formal plugin system later is purely additive — same content, different distribution wrapper.
