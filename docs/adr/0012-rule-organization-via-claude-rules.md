# Rule organization via `.claude/rules/`

Per-folder conventions in a campaign repo are expressed as **path-scoped rule files in `.claude/rules/`**, not as nested `CLAUDE.md` files inside subdirectories. The root `CLAUDE.md` holds cross-cutting, always-loaded campaign context; everything else lives in `.claude/rules/*.md` with `paths:` frontmatter scoping each rule to the files it applies to.

## v0.1 scaffolded rule files

`/ingest` writes three files into the campaign repo:

- **`CLAUDE.md`** (root) — cross-cutting context: campaign system, lifecycle-object overview, slash commands, linking syntax, pointer to `campaign.md` for current state.
- **`.claude/rules/sessions.md`** with `paths: ["sessions/**/*.md"]` — brief/notes/log document semantics, "do not edit `log.md` outside `/wrap-session`," session directory naming convention.
- **`.claude/rules/adventures.md`** with `paths: ["adventures/**/*.md"]` — adventure directory structure, frontmatter schema, status transitions.

Other folders (`npcs/`, `locations/`, `factions/`, `items/`, `threads/`, `consequences/`, `beats/`) do not get their own rule files in v0.1 — their conventions are simple enough to live in root `CLAUDE.md`.

## Considered alternatives

- **Nested `sessions/CLAUDE.md` and `adventures/CLAUDE.md`.** Rejected: Claude Code's docs recommend `.claude/rules/` for modular, path-scoped rules; nested CLAUDE.md works but scatters rules across the tree and lacks explicit glob scoping. A single `.claude/rules/` directory is easier for the GM (and any future contributor) to audit.
- **Single root `CLAUDE.md` containing everything.** Rejected: bloats the always-loaded context with session-specific and adventure-specific rules that only apply in subsets of the work. Path-scoped rules load only when Claude reads matching files.

## Consequences

- The GM has one canonical place to look for plugin-shipped rules (`.claude/rules/`) and one for the always-loaded context (`CLAUDE.md`).
- The GM can add their own personal rules to `.claude/rules/` without colliding with plugin files — the plugin owns specific filenames, not the directory.
- Rule drift between scaffolded campaigns and an evolving plugin convention applies here too; `/upgrade-campaign` (future) will need to reconcile.
- Adding new path-scoped rules later is purely additive: new `.claude/rules/*.md` files with appropriate `paths:` frontmatter.
