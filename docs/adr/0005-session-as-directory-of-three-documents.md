# A Session is a directory of three documents

Each session lives in `sessions/YYYY-MM-DD-session-N/` containing **`brief.md`** (pre-session, agent-seeded, GM-editable, preserved), **`notes.md`** (in-play, GM-typed, preserved unchanged), and **`log.md`** (post-session, agent-drafted from notes, GM-approved). We deviate from the brief's literal one-file-per-session recommendation because the three documents have genuinely different lifecycles, audiences, and edit semantics — collapsing them either forces lossy in-place rewrites (and reliance on git history for retrieval, which the GM rejected as too tedious for an everyday workflow) or accumulates mixed-purpose content in one file with no clean lifecycle story.

## Consequences

- **`/prep-session`** writes `brief.md` once at the start of the session's life. It does not regenerate; subsequent edits are the GM's. (Re-running `/prep-session` against the same session is undefined for now — likely an error or a confirm-before-overwrite.)
- **`/wrap-session`** reads `notes.md`, writes `log.md`, and proposes Threads/Consequences/Reference-note changes for GM approval. `notes.md` is not modified.
- Future Briefs read the prior session's `log.md`, never `notes.md`. The log is the durable record; the notes are kept for provenance and re-extraction.
- The directory pattern leaves room for session-scoped artifacts (handouts, maps, recording snippets) without changing the model.
