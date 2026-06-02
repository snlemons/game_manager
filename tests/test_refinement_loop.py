"""Reference-impl coverage of the conversational refinement loop spec.

This file follows the v0.1 test convention (see `test_secret_store.py`,
`test_wrap_session_idempotency.py`, `test_ingest_per_doc_commits.py`):
the reference Python below is a thin near-translation of the loop
mechanics documented in `references/conversational-refinement-loop.md`
(extracted from `skills/prep-session/SKILL.md` Step 3.5 in slice C of
v0.3, per [ADR-0015](../docs/adr/0015-conversational-refinement-loop-in-prep-session.md)
and [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md)).

The reference impl is **not** a runtime helper — the loop is driven by
the agent reading the prose at skill-run time. The tests exist so the
spec and the consuming skills' prose can't silently drift apart: any
change to the documented loop mechanics must land in both the reference
file and this file, and the tests catch mismatches.

What is asserted (per the acceptance criteria on issue #83):

  1. **Initial-draft Write surface.** The first time the loop touches
     the staged file, it uses the Write tool — a fresh full-file
     surface the IDE shows as a new-file diff. No Edit is permitted
     before the initial Write because Edit requires a prior Read of
     the file.
  2. **Revision via Edit produces targeted hunks, not full-file
     rewrites.** Once the initial draft is staged, every subsequent
     revision flows through Edit with a non-trivially-smaller
     `old_string` than the whole staged file, so the IDE diff is a
     targeted hunk rather than a full re-stage. The one-Write-then-N-
     Edits invariant from the reference is enforced.
  3. **Verbal-skip exits cleanly.** Replies matching "looks good" /
     "skip questions" / "draft is good" / "continue" exit the loop on
     the approve branch without any further Edit; the staging file
     stays byte-identical from the moment of the exit signal to the
     phase 4 re-read.
  4. **Mid-loop GM hand-edits are picked up via re-read.** A GM who
     edits the staged file directly between turns has those edits
     present in the agent's view at the top of the next turn because
     the re-read is unconditional. The reference impl exercises that
     by mutating the staged file out-of-band and asserting the agent
     observes the mutation on the next turn's re-read.

What is **not** tested here is the LLM agent's free-form question
phrasing or category-specific predicate evaluation — those are
skill-specific layers documented in `references/prep-session-questions.md`
and exercised against fixtures only behaviorally (per the gap noted in
`tests/README.md`). This file pins the *loop mechanics*, not the
question banks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest


# ---------------------------------------------------------------------------
# Reference implementation of the conversational refinement loop.
#
# Mirrors `references/conversational-refinement-loop.md`:
#
#   - Phase 1: initial draft via Write (one and only one Write per run).
#   - Phase 2: question queue (skill-specific; passed in as a list here
#     since this file pins mechanics, not the seven `/prep-session`
#     categories).
#   - Phase 3: per-turn loop — preamble, present question, re-read,
#     compute revision, apply via Edit, loop back.
#   - Phase 4: approve / cancel exit.
#   - Phase 5: move from staging to final location.
#
# Tool calls are modeled as instances of a `ToolCall` dataclass so the
# tests can assert the exact tool, path, and arguments used at each
# step — the surface-shape invariant the loop reference pins.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCall:
    """One agent tool invocation against the staged file or its target.

    The `tool` is the literal Claude Code tool name (`Write`, `Edit`,
    `Read`, `Delete`). `path` is the absolute path acted on. For Edit
    calls, `old_string` and `new_string` are the patch payload; for
    Write, `new_string` is the full file content; for Read and Delete,
    both are None.
    """

    tool: str
    path: Path
    old_string: str | None = None
    new_string: str | None = None


@dataclass
class LoopRecorder:
    """Captures the loop's tool calls in order for test assertions.

    The recorder is the test's view into the agent's behavior — every
    Write / Edit / Read / Delete the reference loop performs against
    the staged file lands here, and tests assert against the recorded
    sequence (e.g., "the first tool call is a Write," "every
    subsequent tool call against the staged file is an Edit," "the
    re-read happens before each Edit").
    """

    calls: list[ToolCall] = field(default_factory=list)

    def write(self, path: Path, content: str) -> None:
        self.calls.append(ToolCall(tool="Write", path=path, new_string=content))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read(self, path: Path) -> str:
        self.calls.append(ToolCall(tool="Read", path=path))
        return path.read_text(encoding="utf-8")

    def edit(self, path: Path, old_string: str, new_string: str) -> None:
        self.calls.append(
            ToolCall(
                tool="Edit",
                path=path,
                old_string=old_string,
                new_string=new_string,
            )
        )
        live = path.read_text(encoding="utf-8")
        if old_string not in live:
            raise AssertionError(
                f"Edit's old_string not found in {path.name}: "
                "loop reference contract requires Edit's old_string to "
                "match live bytes (post-re-read), per the no-clobber "
                "invariant in conversational-refinement-loop.md."
            )
        path.write_text(live.replace(old_string, new_string, 1), encoding="utf-8")

    def delete(self, path: Path) -> None:
        self.calls.append(ToolCall(tool="Delete", path=path))
        if path.exists():
            path.unlink()


# Verbal-skip phrases the loop accepts as the approve exit signal. Mirrors
# the reference's phase 3 step 3 enumeration ("looks good" / "skip
# questions" / "draft is good" / "continue" / "approve").
VERBAL_APPROVE = frozenset(
    {
        "approve",
        "continue",
        "looks good",
        "draft is good",
        "skip questions",
        "looks good, ship it",
        "approve and write it",
    }
)


# Verbal cancel signals — exits without writing to the final location.
VERBAL_CANCEL = frozenset({"cancel", "nope", "abort"})


@dataclass
class GMReply:
    """One reply the GM gives during a loop turn.

    `text` is the verbatim reply. `pre_edit` is an optional callable
    the GM applies to the staged file *before* the next turn's
    re-read, modeling the "GM hand-edits the staged file in their
    IDE between turns" case the reference reference calls out
    explicitly.
    """

    text: str
    pre_edit: Callable[[Path], None] | None = None


@dataclass
class QueuedQuestion:
    """One question in the loop's queue.

    `category` is the question category name (skill-specific — e.g.,
    "Secret Push" for `/prep-session`); used only for diagnostics.
    `phrasing` is the question text the agent would surface (also
    only for diagnostics — the loop mechanics don't depend on the
    content of the phrasing).

    `apply_accept` is the per-category accept handler: given the
    GM's reply and the current staged bytes, it returns the
    `(old_string, new_string)` pair the loop will pass to Edit. If
    the category's accept-shape doesn't fire on this reply, the
    handler returns None and the loop treats the reply as decline.
    """

    category: str
    phrasing: str
    apply_accept: Callable[
        [GMReply, str], tuple[str, str] | None
    ]


def normalize_reply(text: str) -> str:
    """Match the loop's case-insensitive, whitespace-tolerant reply
    parsing for verbal approve / cancel signals."""
    return text.strip().lower()


def classify_reply(reply: GMReply) -> str:
    """Classify a GM reply into one of {approve, cancel, engage}.

    Mirrors phase 3 step 3 of the loop reference: the three response
    shapes the loop accepts at any turn. "Engage" covers both
    accept-shape (the per-category handler runs and may produce an
    Edit) and decline-shape (the handler returns None and the loop
    no-ops for this turn).
    """
    norm = normalize_reply(reply.text)
    if norm in VERBAL_APPROVE:
        return "approve"
    if norm in VERBAL_CANCEL:
        return "cancel"
    return "engage"


def run_loop(
    recorder: LoopRecorder,
    staging_path: Path,
    initial_draft: str,
    question_queue: list[QueuedQuestion],
    gm_replies: list[GMReply],
    final_path: Path,
) -> str:
    """Drive the conversational refinement loop end-to-end.

    Returns one of {"approved", "cancelled"}. On approve, the staged
    file is moved to `final_path` and removed from staging. On cancel,
    the staged file is deleted and the final path is untouched.

    The reference impl mirrors phases 1–5 of
    `references/conversational-refinement-loop.md`:

      - Phase 1: write `initial_draft` to `staging_path` via the Write
        tool.
      - Phase 2: the queue is passed in (skill-specific concern).
      - Phase 3: iterate over `gm_replies`, one per turn. Each turn:
        re-read the staged file, classify the reply, either exit
        (approve/cancel) or apply the category's accept-shape via
        Edit.
      - Phase 4: on approve, re-read once more before moving.
      - Phase 5: write to `final_path`, delete the staging file.

    Mid-loop GM hand-edits are modeled via `GMReply.pre_edit` — a
    callable that mutates the staged file before the next turn's
    re-read fires. The loop never holds a cached view across turns;
    the re-read is unconditional.
    """
    # --- Phase 1: initial draft via Write -------------------------------
    recorder.write(staging_path, initial_draft)

    # --- Phase 3: per-turn loop -----------------------------------------
    queue: list[QueuedQuestion] = list(question_queue)
    for reply in gm_replies:
        # Phase 3 step 4: mandatory unconditional re-read at top of turn.
        # The GM may have hand-edited between turns; re-read picks that up.
        if reply.pre_edit is not None:
            reply.pre_edit(staging_path)
        live_bytes = recorder.read(staging_path)

        # Phase 3 step 3: classify the reply.
        kind = classify_reply(reply)
        if kind == "approve":
            # Phase 4 approve branch: final re-read, move to final.
            final_bytes = recorder.read(staging_path)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            recorder.write(final_path, final_bytes)
            recorder.delete(staging_path)
            return "approved"
        if kind == "cancel":
            # Phase 4 cancel branch: delete staging, don't touch final.
            recorder.delete(staging_path)
            return "cancelled"

        # kind == "engage": run the head-of-queue question's accept handler.
        # If the queue is empty, the GM is presumably refining without a
        # specific question on the table — treat as decline (no Edit).
        if not queue:
            continue
        question = queue.pop(0)
        patch = question.apply_accept(reply, live_bytes)
        if patch is None:
            # Decline (or non-engagement-treated-as-decline). The
            # no-re-prompting rule means we drop the question from the
            # queue regardless of which reason it didn't fire.
            continue
        old_string, new_string = patch
        # Phase 3 step 6: revision via Edit, not Write. Edit's
        # old_string must be present in live_bytes (the re-read above
        # is the source of truth).
        recorder.edit(staging_path, old_string, new_string)

    # Ran out of GM replies without an approve/cancel signal. The loop
    # would normally keep going (GM-paced); for the reference impl we
    # treat this as an unfinished run and surface it explicitly.
    raise AssertionError(
        "Loop exhausted GM replies without an approve or cancel signal. "
        "The loop is GM-paced and only exits on an explicit terminal "
        "reply — the test fixture should provide one as the final reply."
    )


# ---------------------------------------------------------------------------
# Test fixtures: small, hand-rolled question categories and replies
# exercising each acceptance criterion. The fixtures are tiny so the
# tests can assert tool-call sequences at the byte level without
# fixture noise.
# ---------------------------------------------------------------------------


# A toy initial draft modeling a `/prep-session` Brief with a couple of
# sections the test's accept-handlers will revise. The exact content
# doesn't matter — only that it has distinct sections an Edit can
# target without rewriting the whole file.
INITIAL_DRAFT = """# Session 5 Brief

## Last time

The party retreated to the inn after Sera's collapse.

## Opening Scene

<!-- Forward-facing opener; the GM may author this directly. -->

## Active adventures

- Cult of the Reborn Flame — bell tolling at the chapel.

## Beats to weave in (optional, weave in if possible)

- Old Owl Well rumor — bard drops the name at the inn.

## GM scratchpad

<!-- GM-owned. -->
"""


def make_question_appends_beat() -> QueuedQuestion:
    """A Secret-Push-shaped question that appends a Clue Beat bullet."""

    def accept(reply: GMReply, live: str) -> tuple[str, str] | None:
        if "push" not in normalize_reply(reply.text):
            return None
        section_anchor = "- Old Owl Well rumor — bard drops the name at the inn.\n"
        if section_anchor not in live:
            return None
        new_bullet = (
            section_anchor
            + "- **Maren's cover slips at the warehouse** — push toward [[secrets/maren-is-the-spy]] (currently partially-revealed). *(scope: Adventure — Cult of the Reborn Flame)*\n"
        )
        return section_anchor, new_bullet

    return QueuedQuestion(
        category="Secret Push",
        phrasing="Cult arc has 1 partially-revealed Secret — push this session?",
        apply_accept=accept,
    )


def make_question_fills_opening_scene() -> QueuedQuestion:
    """A Decision-Request-shaped question that populates Opening Scene."""

    def accept(reply: GMReply, live: str) -> tuple[str, str] | None:
        if "propose" not in normalize_reply(reply.text):
            return None
        anchor = (
            "## Opening Scene\n\n"
            "<!-- Forward-facing opener; the GM may author this directly. -->\n"
        )
        if anchor not in live:
            return None
        proposed = (
            "## Opening Scene\n\n"
            "<!-- Forward-facing opener; the GM may author this directly. -->\n"
            "The bell at the chapel rings a second time before dawn — "
            "long, deliberate, not the morning hour.\n"
        )
        return anchor, proposed

    return QueuedQuestion(
        category="Decision Request",
        phrasing="Opening Scene is empty. Propose one?",
        apply_accept=accept,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def staged_paths(tmp_path: Path) -> tuple[Path, Path]:
    """A campaign-root-shaped tmp_path with staging and final paths."""
    campaign_root = tmp_path / "campaign"
    campaign_root.mkdir()
    staging_path = campaign_root / ".ttrpg-staging" / "brief-draft.md"
    final_path = campaign_root / "sessions" / "2026-06-07-session-5" / "brief.md"
    return staging_path, final_path


class TestInitialDraftViaWrite:
    """Phase 1: the loop's first tool call against the staged file is Write.

    Per the reference's "the initial draft uses Write; every subsequent
    revision uses Edit" invariant. The IDE shows a full-file new-file
    diff for the GM's first view of the proposed document; no Edit is
    permitted before the initial Write because Edit requires a prior
    Read of the file to satisfy its own contract.
    """

    def test_first_tool_call_is_write_to_staging_path(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()
        run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[],
            gm_replies=[GMReply(text="looks good")],
            final_path=final_path,
        )
        assert recorder.calls, "loop produced no tool calls"
        first = recorder.calls[0]
        assert first.tool == "Write", (
            f"loop's first tool call was {first.tool!r}; the reference "
            "requires Write for the initial draft so the IDE shows a "
            "new-file diff."
        )
        assert first.path == staging_path, (
            f"loop's initial Write targeted {first.path}, expected "
            f"the staging path {staging_path}."
        )
        assert first.new_string == INITIAL_DRAFT, (
            "loop's initial Write payload did not match the drafted "
            "content — the reference contract is that the full draft "
            "is written verbatim in one shot."
        )

    def test_only_one_write_to_staging_in_the_run(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        """One-Write-then-N-Edits invariant: re-staging the file via a
        second Write during the loop would surface a full-file diff
        instead of the targeted hunk the GM is reacting to. Forbidden."""
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()
        run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[
                make_question_appends_beat(),
                make_question_fills_opening_scene(),
            ],
            gm_replies=[
                GMReply(text="push the Maren one"),
                GMReply(text="propose an opener"),
                GMReply(text="looks good"),
            ],
            final_path=final_path,
        )
        writes_to_staging = [
            c
            for c in recorder.calls
            if c.tool == "Write" and c.path == staging_path
        ]
        assert len(writes_to_staging) == 1, (
            f"loop performed {len(writes_to_staging)} Writes against the "
            "staging file; the one-Write-then-N-Edits invariant in "
            "conversational-refinement-loop.md requires exactly one."
        )


class TestRevisionViaEditProducesTargetedHunks:
    """Phase 3 step 6: revisions flow through Edit, and the patch is
    materially smaller than the whole staged file (a targeted hunk,
    not a full-file rewrite expressed via Edit). Mirrors the
    reference's "If the revision is a whole-section rewrite, Edit can
    still express it ... the targeted diff is still preferable to a
    full re-stage" guidance."""

    def test_every_post_initial_revision_uses_edit(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()
        run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[
                make_question_appends_beat(),
                make_question_fills_opening_scene(),
            ],
            gm_replies=[
                GMReply(text="push the Maren one"),
                GMReply(text="propose an opener"),
                GMReply(text="looks good"),
            ],
            final_path=final_path,
        )
        # Skip the initial Write (call 0). Every subsequent tool call
        # against the staging file should be Read or Edit — never a
        # second Write.
        staging_calls_after_initial = [
            c
            for c in recorder.calls[1:]
            if c.path == staging_path
        ]
        offenders = [
            c.tool for c in staging_calls_after_initial if c.tool == "Write"
        ]
        assert not offenders, (
            "after the initial Write, the loop must use Edit (or Read) "
            f"against the staging file; saw {offenders} instead."
        )
        # There should be at least one Edit (the two accept-replies
        # both fire their accept handlers).
        edits = [c for c in staging_calls_after_initial if c.tool == "Edit"]
        assert len(edits) >= 1, (
            "loop produced no Edit calls despite GM replies accepting "
            "two queued questions; the accept-shape revisions must "
            "land via Edit."
        )

    def test_edit_patches_are_strictly_smaller_than_full_file(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        """The whole point of Edit is the targeted hunk. If an Edit's
        old_string is the entire file body, the diff degenerates to a
        full re-stage — equivalent to a Write surface from the GM's
        perspective. The reference contract is that targeted hunks
        are preferable; this test pins the contract by requiring
        every Edit's old_string to be strictly smaller than the
        current staged bytes at the moment of the Edit."""
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()
        run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[
                make_question_appends_beat(),
                make_question_fills_opening_scene(),
            ],
            gm_replies=[
                GMReply(text="push the Maren one"),
                GMReply(text="propose an opener"),
                GMReply(text="looks good"),
            ],
            final_path=final_path,
        )
        # Walk the recorded calls and, for each Edit against staging,
        # check that the old_string is strictly shorter than the
        # bytes-at-time-of-Edit. We reconstruct the byte-at-time-of-
        # Edit by walking the calls in order and applying each Write/
        # Edit to a shadow buffer.
        shadow = ""
        for call in recorder.calls:
            if call.tool == "Write" and call.path == staging_path:
                shadow = call.new_string or ""
                continue
            if call.tool == "Edit" and call.path == staging_path:
                assert call.old_string is not None
                assert len(call.old_string) < len(shadow), (
                    f"Edit's old_string ({len(call.old_string)} bytes) "
                    f"is not strictly smaller than the staged file "
                    f"({len(shadow)} bytes) at the moment of Edit. The "
                    "loop reference requires targeted hunks — a "
                    "whole-file old_string is a re-stage, not a "
                    "revision."
                )
                shadow = shadow.replace(
                    call.old_string, call.new_string or "", 1
                )


class TestVerbalSkipExitsCleanly:
    """Phase 3 step 3 + phase 4 approve branch: verbal-skip phrases
    exit the loop cleanly without any further Edit. The staging file
    stays byte-identical from the moment of the exit signal to the
    final-location move."""

    @pytest.mark.parametrize(
        "skip_phrase",
        ["looks good", "skip questions", "draft is good", "continue", "approve"],
    )
    def test_verbal_skip_phrase_exits_without_edit(
        self,
        staged_paths: tuple[Path, Path],
        skip_phrase: str,
    ) -> None:
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()
        result = run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[
                make_question_appends_beat(),
                make_question_fills_opening_scene(),
            ],
            gm_replies=[GMReply(text=skip_phrase)],
            final_path=final_path,
        )
        assert result == "approved", (
            f"verbal-skip phrase {skip_phrase!r} did not exit on the "
            f"approve branch; got {result!r}."
        )
        # No Edit calls against the staging file should appear; the
        # only mutations are the initial Write and the move-to-final
        # (Write + Delete).
        edits = [
            c
            for c in recorder.calls
            if c.tool == "Edit" and c.path == staging_path
        ]
        assert not edits, (
            f"verbal-skip phrase {skip_phrase!r} produced {len(edits)} "
            "Edit calls; the reference requires zero Edits on a "
            "skip-on-first-turn exit."
        )
        # The final location should now hold the initial draft
        # verbatim — no revisions were applied.
        assert final_path.read_text(encoding="utf-8") == INITIAL_DRAFT, (
            "verbal-skip exit did not preserve the initial draft "
            "byte-for-byte at the final location."
        )

    def test_cancel_does_not_write_final_location(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        """Phase 4 cancel branch: delete staging, never touch final."""
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()
        result = run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[make_question_appends_beat()],
            gm_replies=[GMReply(text="cancel")],
            final_path=final_path,
        )
        assert result == "cancelled"
        assert not final_path.exists(), (
            "cancel branch wrote to the final location; the reference "
            "requires the campaign tree to be byte-identical before "
            "staging and after cleanup."
        )
        assert not staging_path.exists(), (
            "cancel branch left the staging file behind; cleanup "
            "should delete it."
        )


class TestMidLoopGMHandEditsPickedUpViaReRead:
    """Phase 3 step 4: the re-read at the top of every turn picks up
    GM hand-edits to the staged file made between turns. The agent
    observes the edits as ground truth before computing any revision
    for the current turn."""

    def test_hand_edit_between_turns_appears_in_next_read(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()

        hand_edited_marker = (
            "## Opening Scene\n\n"
            "<!-- Forward-facing opener; the GM may author this directly. -->\n"
            "GM-AUTHORED OPENER: the bell tolls twice.\n"
        )

        def gm_hand_edits_opening_scene(path: Path) -> None:
            """Simulate the GM editing the staged file in their IDE
            between loop turns. The agent's re-read at the top of the
            next turn must observe this content."""
            current = path.read_text(encoding="utf-8")
            anchor = (
                "## Opening Scene\n\n"
                "<!-- Forward-facing opener; the GM may author this directly. -->\n"
            )
            path.write_text(
                current.replace(anchor, hand_edited_marker, 1),
                encoding="utf-8",
            )

        run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[make_question_appends_beat()],
            gm_replies=[
                # First reply: the GM hand-edits Opening Scene in
                # their IDE before sending this reply. The agent's
                # re-read at the top of this turn must see the edit.
                GMReply(
                    text="push the Maren one",
                    pre_edit=gm_hand_edits_opening_scene,
                ),
                GMReply(text="looks good"),
            ],
            final_path=final_path,
        )

        # The first Read call against the staging file should reflect
        # the GM's hand-edit. (Calls: 0=Write, 1=Read, then the
        # accept-shape Edit, etc.)
        reads_of_staging = [
            c
            for c in recorder.calls
            if c.tool == "Read" and c.path == staging_path
        ]
        assert reads_of_staging, "loop produced no Reads of the staging file"
        # We can't directly assert the Read's *return value* via the
        # recorder (Read isn't recording its result), so we assert
        # against the live file state at the time the Read happened,
        # which the recorder mirrors: the Read call's path is the live
        # path, and the next Edit's old_string must be present in the
        # post-hand-edit bytes. The simpler observable: the final
        # written file at the final-location must contain the GM's
        # hand-edited content, because nothing in the loop ever
        # overwrote it.
        final_content = final_path.read_text(encoding="utf-8")
        assert "GM-AUTHORED OPENER: the bell tolls twice." in final_content, (
            "the GM's mid-loop hand-edit to Opening Scene was lost "
            "between turns; the unconditional re-read in phase 3 step "
            "4 should have made the agent observe and preserve it."
        )

    def test_agent_does_not_clobber_gm_hand_edits(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        """The no-clobber invariant: if the GM hand-edits the staged
        file in a way that removes the anchor a queued question's
        accept handler would have targeted, the accept handler must
        no-op rather than silently fabricating the anchor back. The
        reference's "surface the conflict in chat ... rather than
        silently clobbering" prose is what this test pins."""
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()

        def gm_deletes_beats_section_anchor(path: Path) -> None:
            current = path.read_text(encoding="utf-8")
            # GM removes the bullet the Secret-Push accept handler
            # would target. After this edit, the handler has no
            # anchor to append to.
            path.write_text(
                current.replace(
                    "- Old Owl Well rumor — bard drops the name at the inn.\n",
                    "",
                    1,
                ),
                encoding="utf-8",
            )

        run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[make_question_appends_beat()],
            gm_replies=[
                GMReply(
                    text="push the Maren one",
                    pre_edit=gm_deletes_beats_section_anchor,
                ),
                GMReply(text="looks good"),
            ],
            final_path=final_path,
        )

        # No Edit should have fired (the accept handler's old_string
        # anchor was deleted by the GM; handler returns None; loop
        # no-ops for that turn).
        edits = [
            c
            for c in recorder.calls
            if c.tool == "Edit" and c.path == staging_path
        ]
        assert not edits, (
            "agent applied an Edit despite the GM hand-edit removing "
            "the anchor the Edit would have targeted. The no-clobber "
            "rule from conversational-refinement-loop.md requires the "
            "agent to no-op (or surface the conflict in chat), not "
            "silently fabricate the anchor back."
        )


class TestNoReprompting:
    """Phase 3 step 5: a question dropped because the GM didn't engage
    with it does not resurface within the same run. The loop is
    one-pass through the queue."""

    def test_declined_question_is_not_re_asked(
        self, staged_paths: tuple[Path, Path]
    ) -> None:
        staging_path, final_path = staged_paths
        recorder = LoopRecorder()

        # The accept handler only fires when the reply contains the
        # word "push". A reply addressing something else ("skip" / a
        # different topic) returns None and the question is dropped.
        run_loop(
            recorder=recorder,
            staging_path=staging_path,
            initial_draft=INITIAL_DRAFT,
            question_queue=[
                make_question_appends_beat(),
                make_question_fills_opening_scene(),
            ],
            gm_replies=[
                # GM addresses something else — accept handler returns
                # None — question is dropped from the queue.
                GMReply(text="not this session"),
                # Second turn: the Decision Request question is at the
                # head of the queue now (Secret Push was dropped, not
                # re-queued).
                GMReply(text="propose an opener"),
                GMReply(text="looks good"),
            ],
            final_path=final_path,
        )

        # Only ONE Edit should have fired (the Decision Request
        # accept). If the Secret Push question had been re-asked, the
        # subsequent "propose" reply might or might not have
        # accidentally matched, but we'd see different Edit count or
        # ordering. The cleanest assertion: exactly one Edit against
        # the staging file.
        edits = [
            c
            for c in recorder.calls
            if c.tool == "Edit" and c.path == staging_path
        ]
        assert len(edits) == 1, (
            f"expected exactly one Edit (Decision Request accept); got "
            f"{len(edits)}. The Secret Push question was declined on "
            "turn 1 and should not have been re-asked."
        )
        # And the Edit should be the Decision Request one (Opening
        # Scene content), not the Secret Push one (Maren bullet).
        the_edit = edits[0]
        assert "Maren" not in (the_edit.new_string or ""), (
            "the Edit was Secret-Push-shaped, suggesting the declined "
            "Secret Push question was re-asked — re-prompting is "
            "forbidden by phase 3 step 5."
        )
        assert "bell" in (the_edit.new_string or "").lower(), (
            "the Edit didn't apply the Decision Request accept-shape; "
            "the queue may not have advanced past the declined "
            "question correctly."
        )
