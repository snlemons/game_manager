# Threads and Consequences are per-file, created via post-session extraction

Threads and Consequences are tracked as their own markdown files (`threads/`, `consequences/`) with status frontmatter — not as inline sentences inside session notes, and not created by the GM during play. **During** a session, the GM takes free-form in-play notes; **after** the session, the agent proposes Threads and Consequences for the GM to approve in bulk. This resolves the brief's internal tension between "first-class objects with lifecycle behavior" and "no schemas, no friction at capture": capture stays unstructured, structure emerges in a single agent-driven moment.

## Considered options

- **Inline-only.** Sentences inside session notes; agent greps semantically when needed. Rejected: no stable identity across sessions, no lifecycle (decay/status), no clean way to answer "what's open?" without semantic guessing.
- **Per-file from creation, GM-declared during play.** Rejected: forces the GM to decide mid-session whether something is "a thread" and create a file — exactly the upfront-structure friction the brief calls out as the dominant failure mode of GM tools.

## Why Threads and Consequences are distinct kinds

- A Thread is *future-facing* — the agent surfaces it in pre-session briefs and decays it if not addressed.
- A Consequence is *past-facing* — the agent consults it when describing the things it affects; it persists, doesn't close.

They share a creation moment (post-session extraction) but have different surfacing rules, so they're separate file types rather than one kind with a `type:` field.
