---
paths: ["sessions/**/*.md"]
---

# Session conventions

A Session is the unit of play. Each session lives in `sessions/YYYY-MM-DD-session-N/` with three documents: `brief.md` (pre-session, agent-drafted), `notes.md` (in-play, GM-written, never modified), `log.md` (post-session, agent-drafted from notes, GM-approved).

`/wrap-session` reads `notes.md` and writes `log.md`. `notes.md` is the source of truth and is preserved unchanged.
