# `/ingest` workflow: survey, then per-doc with learning

`/ingest` operates in **two phases**: a one-shot **survey** where the GM optionally describes each doc and confirms processing order, then a **per-doc loop** where the agent extracts a complete proposal per doc, the GM approves/edits as a batch, and lessons from corrections carry forward to subsequent docs.

## Survey phase

Agent lists discovered docs and does a **bounded skim** of each (first heading and first ~200 words, not full read) to **propose a one-line description per doc**. GM reviews the proposed descriptions as an editable list — corrects what's wrong, leaves the rest as-is, and surfaces ambiguity ("Adventure or world info?") rather than guessing. Agent then proposes a processing order (world info → adventures → session notes if any) and asks the GM to confirm.

Pre-labeling avoids the agent committing to wrong doc-type assumptions before extraction starts and accommodates GMs with idiosyncratic past notetaking styles. Agent-proposed descriptions reduce GM cognitive load vs. asking for descriptions blind.

## Per-doc loop

For each doc, in confirmed order:

1. Agent reads the doc with the GM's description as context.
2. Agent extracts Reference notes (NPCs / locations / factions / items), adventure metadata, Threads, and Consequences.
3. Agent dedups against already-written files (recurring entities update existing notes; ambiguous matches are asked).
4. Agent presents a per-doc proposed diff (all file creates/updates from this doc).
5. GM approves, edits, or rejects.
6. Corrections inform the next doc's extraction prompts ("you don't promote one-off innkeepers — I'll skip those").

## Wrap-up

After the last doc: agent prompts for any missing `order:` values on adventures the GM didn't sequence inline, then generates the campaign-root `campaign.md` snapshot.

## Considered alternatives

- **Batch (all docs in one pass).** Rejected: review at this scale is cognitively unwieldy; errors propagate before correction; context-window pressure on larger corpora.
- **Doc-by-doc with per-entity approval.** Rejected: too many decision points; the cognitive cost is in deciding *the structure of the doc*, not each NPC individually.

## v0.1 boundaries

- One campaign per `/ingest` run; multi-campaign ingest is multiple runs.
- Flat directory; no subdirectory walking.
- Non-markdown files are reported and skipped.
