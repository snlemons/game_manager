# `/prep-session` brief structure and v0.1 interaction shape

`/prep-session` creates a session directory and writes a structured `brief.md` for the GM. v0.1 uses **propose-then-edit**: the agent drafts the brief from current state, presents it as a diff-style review, the GM accepts/edits, and `brief.md` is written. Later versions may move toward more interactive prep (guiding new GMs, brainstorming dialogues), but v0.1 keeps it transactional.

## Brief sections (in order)

```markdown
# Session N Brief

## Last time
3-5 sentence recap from prior session's log.md
(or, for first session, the most recently active adventure's history).

## Active adventures
Bulleted list of `status: active` adventures with one-line state.

## Open threads (likely to surface)
Threads with `status: open` whose context is likely relevant.

## Beats to weave in (optional)
Pending Beats relevant to active adventures or campaign-wide.
Explicitly framed as optional — land 0–N this session.

## NPCs the party may encounter
Filtered by relevance: active adventure's NPCs + locally-relevant recurring NPCs.

## Locations
Where the party is now and where they're likely heading.

## Items in play that might matter
PCs' inventory items that interact with active adventures or open threads.

## Recent significant consequences
Consequences likely to come up given current location/adventure.

## GM scratchpad
Empty section. GM-owned. Foreshadowing reminders, NPC name picks,
"if they go north, then…" branches.
```

## Interaction shape in v0.1

1. Agent determines next session number and date; creates `sessions/YYYY-MM-DD-session-N/`.
2. Agent reads relevant state (prior log or recent adventure history, active adventures, open threads, pending beats, recent consequences, relevant NPCs/locations).
3. Agent drafts the brief and presents it for review (diff-style edit if substantial; full preview otherwise).
4. GM approves or edits.
5. Brief is written. `notes.md` is created empty. No `log.md` yet.

## Future direction (not v0.1)

The brief notes a desire for richer interaction in later versions:
- Guided prep for new GMs (walk through "what do you want to happen if X?").
- Brainstorming mode ("help me think of three ways this NPC could escalate").
- Iterative refinement ("re-draft with more focus on Strahd").

v0.1 establishes the shape; future versions add depth on top.

## Re-running `/prep-session`

If `brief.md` already exists for a session: confirm-before-overwrite. GM may have hand-edited; we don't stomp without consent.
