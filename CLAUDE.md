# Game Manager

A Claude-native plugin for TTRPG GMs to organize campaigns, prep sessions, and track continuity. See [CONTEXT.md](./CONTEXT.md) for the domain glossary and [docs/adr/](./docs/adr/) for architectural decisions.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, accessed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
