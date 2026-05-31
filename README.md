# ttrpg-gm

A Claude Code skills plugin for TTRPG GMs. Helps you organize a campaign, prep sessions, and track continuity, with your campaign data living in a GM-owned git repo on disk.

The plugin is the workflow surface (`/ingest`, `/prep-session`, `/wrap-session`). Each of your campaigns is its own git repo, scaffolded by `/ingest`. See [`CONTEXT.md`](./CONTEXT.md) for the domain glossary the plugin uses and [`docs/adr/`](./docs/adr/) for the architectural decisions.

## What v0.1 ships

v0.1 is the ingest workflow plus the minimum session loop:

- **`/ingest`** — scaffold a fresh campaign repo (slice 1, shipped here) and import existing notes via survey + per-doc extraction (later slices).
- **`/prep-session`** — create a session directory and draft a structured pre-session brief (later slice).
- **`/wrap-session`** — read the session's in-play notes, draft the log, propose Threads, Consequences, Reference notes, and Beat updates for GM approval, and regenerate `campaign.md` (later slice).

In this slice, `/prep-session` and `/wrap-session` respond "not yet implemented". `/ingest` runs only its scaffolder phase; survey, per-doc extraction, and wrap-up are stubs.

## Roadmap

Rough cross-version horizon. Scope shifts based on dogfooding; per-version PRDs in GitHub Issues are the source of truth for committed work.

- **v0.1** *(shipped 2026-05-30)* — ingest workflow + session loop. Three skills (`/ingest`, `/prep-session`, `/wrap-session`).
- **v0.2** *(planned)* — richer prep workflow + Secret architecture. Conversational prep-session dialogue with rule-based question categories; Secret as a new multi-container lifecycle object; Beat `kind:` discriminator (`news | handout | character-moment | set-piece | clue | escalation`); Brief Opening Scene section + evocative Locations.
- **v0.3** *(planned)* — campaign and adventure scaffolding. `/init-campaign` and `/init-adventure` skills for net-new content (vs. `/ingest` for existing notes).
- **Post-v0.3 candidates** *(not committed)* — Atlas + cross-repo linking, context-management for large campaigns ([#11](https://github.com/snlemons/game_manager/issues/11)), deterministic spec helpers ([#24](https://github.com/snlemons/game_manager/issues/24)), pre-approval stage for large batches ([#27](https://github.com/snlemons/game_manager/issues/27)), continuity catching.

## Install

The plugin installs as a Claude Code skills directory at `~/.claude/skills/ttrpg-gm/`.

```sh
git clone https://github.com/snlemons/game_manager.git ~/.claude/skills/ttrpg-gm
```

Updates flow via `git pull` in `~/.claude/skills/ttrpg-gm/`. Versioning is git tags.

After cloning, the three slash commands (`/ingest`, `/prep-session`, `/wrap-session`) resolve globally in Claude Code — you can invoke them from any working directory.

## First run

Start a fresh campaign repo:

1. Decide where the campaign repo should live, e.g. `~/campaigns/my-faerun/`.
2. From a Claude Code session, invoke `/ingest`.
3. When prompted, give the campaign name (e.g. `Faerûn Campaign`) and the system (e.g. `D&D 5e`).
4. Confirm the target directory.

The scaffolder writes:

- `CLAUDE.md` — root campaign context: metadata, slash commands available, lifecycle-object overview, linking syntax, pointer to `campaign.md`.
- `.claude/rules/sessions.md` — session document conventions (`brief.md`, `notes.md`, `log.md` semantics, edit rules, directory naming).
- `.claude/rules/adventures.md` — adventure directory structure, frontmatter schema, status transitions.
- `campaign.md` — placeholder campaign overview (agent-maintained; regenerated later by `/wrap-session` and `/ingest`'s wrap-up).

Then it runs `git init` and commits those four files as the campaign repo's first commit. After that, the repo is yours — make your own commits, push it wherever you like.

In this slice, the scaffolder stops there. The survey and per-doc extraction phases of `/ingest`, plus `/prep-session` and `/wrap-session`, ship in later slices.

## Slash commands

| Command | Status in slice 1 | What it does (eventually) |
|---|---|---|
| `/ingest` | Scaffolder phase shipped; later phases stubbed | Scaffold a campaign repo, then ingest existing markdown notes into structured Reference notes, Adventures, Threads, and Consequences. |
| `/prep-session` | Stub | Create a session directory and draft a structured pre-session Brief from the campaign's current state. |
| `/wrap-session` | Stub | Read the session's in-play notes, draft the Log, propose new Threads / Consequences / Reference notes / Beat updates / Adventure status changes, and regenerate `campaign.md`. |

## Repo layout

```
ttrpg-gm/                              # → ~/.claude/skills/ttrpg-gm/
├── skills/
│   ├── ingest/SKILL.md                # /ingest workflow
│   ├── prep-session/SKILL.md          # /prep-session workflow
│   └── wrap-session/SKILL.md          # /wrap-session workflow
├── templates/
│   ├── CLAUDE.md.template             # root CLAUDE.md scaffolded into campaigns
│   ├── .claude/rules/
│   │   ├── sessions.md.template
│   │   └── adventures.md.template
│   └── campaign.md.template
├── CONTEXT.md                         # this project's glossary
├── docs/adr/                          # this project's architectural decisions
└── README.md                          # this file
```

Templates carry a `.template` suffix in the plugin repo so they're easy to spot. The scaffolder strips the suffix when it writes them into a campaign repo.

## Vocabulary

This plugin uses the domain language defined in [`CONTEXT.md`](./CONTEXT.md): **GM**, **PC**, **NPC**, **Campaign**, **Adventure**, **Atlas**, **Reference note**, **Session**, **Brief**, **In-play notes**, **Log**, **Thread**, **Consequence**, **Beat**, **Campaign overview**. Files the plugin writes (its own and the templates it scaffolds) stick to this vocabulary consistently — synonyms the glossary calls out as "avoid" are off-limits.

## License

See [LICENSE](./LICENSE).
