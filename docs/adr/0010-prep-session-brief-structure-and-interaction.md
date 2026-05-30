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
(Empty / `_None._` is normal in open-world campaigns between arcs —
see "Menu of next-session options" below.)

## Menu of next-session options
The forward-looking menu of arcs and threads the party could pick up
next session. Three sub-buckets:
  - `status: introduced` Adventures the party could plausibly start,
    one line each.
  - Open Threads that could become a session focus (a curated subset
    of the full Open threads list — the ones substantial enough to
    drive a session), one line each.
  - A pointer back to active arcs if any exist ("any of the active
    adventures above could continue") so the GM sees the full menu
    in one place.
Empty buckets render `_None._` under their sub-heading. This section
is the open-world surface — single-arc campaigns will often show
"continue [active arc]" plus a short list; sandbox campaigns will
show a wider menu.

## Open threads (likely to surface)
Threads with `status: open` whose context is likely relevant.

## Beats to weave in (optional)
Pending Beats relevant to in-focus Adventures (active OR introduced
and in the menu above) or campaign-wide. Explicitly framed as
optional — land 0–N this session. Surfacing is tiered (ADR-0009).

## NPCs the party may encounter
Filtered by relevance: in-focus adventure's NPCs + locally-relevant recurring NPCs.

## Locations
Where the party is now and where they're likely heading.

## Items in play that might matter
PCs' inventory items that interact with in-focus adventures or open threads.

## Recent significant consequences
Consequences likely to come up given current location/adventure.

## GM scratchpad
Empty section. GM-owned. Foreshadowing reminders, NPC name picks,
"if they go north, then…" branches.
```

The "Menu of next-session options" section was added after dogfooding hit the open-world case (issue #13): a campaign with several `introduced` Adventures available and none currently `active` had nothing forward-looking in the Brief beyond "Last time" and an empty "Active adventures" section. The menu makes available Adventures and session-driver Threads first-class without adding a campaign-mode flag or new Adventure status values — the same Brief shape serves single-arc, multi-arc, and no-active-arc campaigns.

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
