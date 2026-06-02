# Conversational refinement loop

A shared workflow pattern for **draft-first-then-converse** skills: the agent drafts a document into staging, then enters a multi-turn loop where it surfaces follow-up questions, the GM responds (or hand-edits the staged file directly), and the agent revises the staged file in place via Edit until the GM explicitly approves or cancels. The loop is consumed by `/prep-session` (per [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md)), `/init-campaign`, and `/init-adventure` (per [ADR-0019](../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md) and [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md)).

This reference documents the **loop mechanics only** — initial-draft staging via Write, multi-turn revision via Edit, verbal-skip exits, mandatory re-read on every turn, GM-paced loop count, no re-prompting within a run, and how mid-loop GM hand-edits are honored as authoritative. The **skill-specific question banks** (what to ask, when each category fires, how each accept-shape revises the staged file) live in each consuming skill's own surface — e.g., `references/prep-session-questions.md` for `/prep-session`. Only the mechanics are shared here.

The loop also depends on [`staging-pattern.md`](./staging-pattern.md) — its "Iterative agent revisions during a review loop" section is the underlying staging-area contract this loop runs on top of. Where this reference and `staging-pattern.md` overlap, `staging-pattern.md` is the deeper invariant (no writes outside `.ttrpg-staging/` between stage-write and approval; deleted staged files are rejections; the GM's edits are the source of truth) and this reference is the loop-shape on top.

## When to use this pattern

A skill should run the conversational refinement loop when **both**:

- The skill produces a single GM-facing document (a Brief, a pitch, an Adventure walkthrough) where the GM is the audience and the agent's draft is a starting point, not a final answer.
- The skill has a meaningful question surface — rule-based follow-ups, decision prompts, or content elicitation — where the GM's answers materially change the staged document.

Skills that produce many independent staged entries (`/ingest` Phase 3's per-doc loop; `/wrap-session`'s wrap directory) use the terminal staging review from `staging-pattern.md` sections 2–4 directly — the conversational loop's question/answer turn shape doesn't add value over the "edit-in-place-then-continue" terminal review when the GM is reviewing a batch of independent files.

## The loop's lifecycle

The loop has five phases that map onto `staging-pattern.md`'s lifecycle. Phases 1, 4, and 5 are the same as the terminal review's stage / re-read / move-to-final. Phases 2 and 3 are the conversational addition.

### Phase 1 — Stage the initial draft via Write

The agent drafts the document from the skill's inputs (campaign state for `/prep-session`; GM-supplied pitch material for `/init-campaign`; Adventure shape for `/init-adventure`) and writes the full draft to a single staging file via the Write tool.

- **Tool: Write.** The initial draft is a new file from the GM's perspective. Write surfaces a new-file diff in the IDE; the GM sees the proposed document in full as a single hunk.
- **Path: a single staging file at the skill's documented sub-path** (e.g., `.ttrpg-staging/brief-draft.md` for `/prep-session`). Create `.ttrpg-staging/` lazily if it doesn't exist; the scaffolder doesn't pre-create it. The exact filename is per-skill; the shape (one file, top-level of `.ttrpg-staging/`) is shared.
- **No writes outside staging.** No final-location files are created at this phase. The session directory / campaign repo / adventure directory only materializes at phase 5 after the loop exits via approve. The staging file's existence is the agent's "I've drafted something"; the final file's existence is the GM's "I approved it."

The Write at this phase is the **only** Write the loop performs against the staged file. Every subsequent revision uses Edit (phase 3).

### Phase 2 — Compute the question queue

The skill evaluates its own question categories against current state and the just-staged draft. Each category whose predicate is true contributes one (or, where the category produces multiple findings, a small batched set of) question(s) to the loop's queue. The categories themselves are skill-specific — `/prep-session` has seven (Coverage Check, Tiering Check, Thread Decay, Decision Request, Secret Push, Escalation Prep, GM Focus Check) per `prep-session-questions.md`; `/init-campaign` and `/init-adventure` have their own banks.

The **only mechanics this reference pins** about the queue:

- **Closely-related questions batch into the same turn.** Multiple findings from one category, or multiple categories whose framings cohere, present as one chat message rather than N separate pings.
- **Unrelated categories surface in separate turns.** Forcing batching across unrelated framings (e.g., a rule-based ask plus an open-ended catch-all) reads as a wall of questions rather than a conversation.
- **An always-fires catch-all category, if the skill has one, runs last.** The rule-based surface has already done its work; the catch-all's "anything else?" framing only lands well after the rules have fired.

If no category's predicate is true (the queue is empty), the loop skips directly to phase 5's approval ask — but still mentions the staging path in the loop preamble so the GM knows where the document is and how to edit it.

### Phase 3 — Run the loop

The loop iterates until the GM explicitly approves or cancels. Each turn has this shape:

1. **Open the turn with the loop preamble.** First turn after staging: *"Draft is at `<staging path>`. I have `N` follow-up question(s) to help you refine it — or say 'looks good' / 'skip questions' to finalize as-is."* Subsequent turns: just present the next queued question. The preamble's mention of the verbal skip (*"looks good"* / *"skip questions"* / *"draft is good"*) is the GM's escape from the loop without writing additional revisions.

2. **Present queued questions one batch at a time.** Per the queue-shape rules in phase 2: closely-related questions in the same turn, unrelated categories in separate turns. The skill-specific reference defines the per-category phrasing template.

3. **Wait for the GM's reply.** Three response shapes the loop accepts at any turn:
   - **Approve / "looks good" / "draft is good" / "continue" / "skip questions"** → exit the loop. Proceed to phase 4's approve branch (re-read staging, then phase 5 writes to final location).
   - **Cancel** → exit the loop. Proceed to phase 4's cancel branch (delete staging, exit without writing).
   - **Anything else** → treat as a turn-level response to the queued question. Continue to step 4.

4. **Re-read the staged file from scratch.** The re-read is **mandatory and unconditional** — the GM may have edited the staged file directly in their IDE between turns and the agent must observe those edits as ground truth before revising. Per `staging-pattern.md`, the re-read happens at the top of every loop turn, not only at exit. The agent never holds a cached view of the staged file across turns; the re-read is always from disk.

5. **Compute revisions from the GM's reply.** The skill-specific question reference defines what kinds of revisions each kind of GM reply implies. This reference only commits to three response-shape semantics that hold for every category:
   - **Accept** → the agent revises the staged file per the category's accept-shape.
   - **Decline / "not this session" / "skip" / "no"** → no revision. The agent does not pre-emptively edit the document to reflect the decline; staging stays byte-identical for this turn.
   - **Defer / non-engagement (the GM replies addressing something else, asks the agent to do an unrelated thing, replies with a partial sentence and moves on)** → **treat as decline**. The question is dropped from the queue. The loop continues. This is the no-re-prompting rule.

6. **Apply revisions via Edit, not Write.** Edit's diff display surfaces the targeted delta against content the GM has already seen once. Rewriting the whole staged file via Write would show the GM a full-file diff instead of the targeted change they're reacting to — the loop reads as confusing churn rather than incremental refinement. If the revision is a whole-section rewrite, Edit can still express it (`old_string` = the section's current bytes, `new_string` = the rewritten section); the targeted diff is still preferable to a full re-stage. Before applying, check whether the intended revision would overwrite GM-authored content the agent did not draft — if so, surface the conflict in chat (*"You edited the [section] after the last turn; my proposed revision would touch a line you changed. Apply anyway, or skip?"*) rather than silently clobbering.

7. **Loop back.** Present the next queued question, or — when the queue is exhausted — drop into phase 4's approval ask. The agent does not need to announce *"all questions covered, asking for approval now"*; the transition from a question turn to phase 4's continue/cancel ask is the signal.

### Phase 4 — Approval gate (loop exit)

The approve / cancel exit follows the shared continue/cancel contract from `staging-pattern.md` — the same shape the v0.1 terminal review used, just reached at the end of the loop's question pass rather than immediately after staging.

When the GM signals approve at any point in the loop, the agent does this:

*"On approve I'll [skill-specific final-location action]. Confirm continue, or cancel to exit cleanly."*

Then accepts two response shapes:

1. **Continue** → re-read the staged file one final time to capture any final GM edits, then proceed to phase 5 to commit it to its final location.
2. **Cancel** → delete the staging file (and remove `.ttrpg-staging/` if it's now empty), leave the rest of the filesystem unchanged, exit.

If the GM's loop-exit signal was already unambiguously a continue (*"approve and write it"*, *"looks good, ship it"*), the agent may proceed directly to phase 5 without a second confirmation — the loop exit already carried the approve semantic. The second ask above is for ambiguous exits (*"that's fine"*, *"yeah ok"*) where confirming the write is worth one more turn.

### Phase 5 — Move from staging to final location

The skill's own SKILL.md owns the final-location move (it knows the target path's shape — `sessions/YYYY-MM-DD-session-N/brief.md` for `/prep-session`, the campaign root for `/init-campaign`, etc.). The mechanics shared here:

- The final-location write happens **only** after phase 4's continue. No partial promotion mid-loop.
- The staging file is removed after the move. If `.ttrpg-staging/` is now empty, it's removed too.
- On cancel at any point in the loop, the same cleanup runs immediately — delete the staging file (and `.ttrpg-staging/` if empty), exit without touching the final location.

## Invariants the loop guarantees

These are the properties downstream skill prose (and the test suite at `tests/test_refinement_loop.py`) relies on:

- **The initial draft uses Write; every subsequent revision uses Edit.** This is the one-Write-then-N-Edits invariant. Re-staging via a fresh Write during the loop would surface a full-file diff and lose the targeted-hunk affordance the loop is designed to give the GM.
- **The agent re-reads the staged file at the top of every loop turn, unconditionally.** No cached view of the staged file is held across turns. Mid-loop GM hand-edits are picked up automatically because of this re-read, not because of any explicit "I edited the file" signal from the GM.
- **No file outside `.ttrpg-staging/` is created or modified between phase 1 and phase 5 continue.** Cancel is byte-safe: the campaign tree is identical before staging and after cleanup.
- **A question dropped because the GM didn't engage with it does not resurface within the same run.** The loop is one-pass through the queue. The GM revisits questions in a future run if they re-prep (or re-pitch, or re-walk-through) the same target.
- **Loop turn count is GM-paced, not agent-paced.** The agent doesn't impose a max-turn limit; the loop runs as long as the GM keeps engaging. A GM who answers every question in detail produces a longer loop than a GM who skips questions verbally on the first turn — both are valid.
- **Mid-loop GM hand-edits to the staged file are authoritative.** The agent treats the post-re-read bytes as ground truth and never silently overwrites GM-authored content. When a proposed revision would touch GM-authored content, the agent surfaces the conflict in chat rather than clobbering.

## What this pattern is not

- **Not a multi-file staging review.** The loop drives a single staged document. Skills that stage many independent files (`/ingest` Phase 3, `/wrap-session`'s wrap directory) use the terminal review from `staging-pattern.md` directly. A skill with a single primary document plus a small number of side-effect stages (e.g., `/prep-session`'s sensory-detail write-back to Location notes) can use the loop for the primary document and stage the side effects per the standard staging contract.
- **Not a planning workspace.** The staged file is the agent's revision surface, not the GM's long-form scratch space. A GM who wants a sustained planning conversation outside the loop's question shape can hand-edit the staged file freely between turns — that's the loop's escape valve — but the loop itself is not the place to host a planning session that lasts hours.
- **Not a substitute for the chat exchange.** The chat preamble and the question phrasing are load-bearing prompts; the staged file alone doesn't tell the GM what's expected of them. Don't stage and stop; always pair phase 1's Write with phase 3's preamble.
- **Not a per-section refinement loop.** The loop iterates over the whole document, not per-section. A skill that needs per-section refinement should still drive it through the single-file loop — the questions can target sections individually, but the staged document is the unified review surface.

## Per-skill nuances live in the SKILL.md and the skill-specific reference

Each consuming skill documents:

- The exact staging file path it uses inside `.ttrpg-staging/`.
- The shape of its initial draft (sections, headings, populated-vs-blank conventions).
- The set of question categories that feed the queue, with predicate / phrasing / response-handling for each. For `/prep-session`, this lives in `prep-session-questions.md`; `/init-campaign` and `/init-adventure` document their own banks similarly.
- The exact phrase the phase 4 approval ask uses to describe the final-location action.
- The final-location write semantics — target path shape, any side-effect writes (e.g., `/prep-session`'s sensory-detail write-back, the auto-commit), and the post-approval closing message.

This reference is the loop shape; the SKILL.md and the skill-specific question reference are the per-skill behavior on top of the shape.
