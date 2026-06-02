"""Behavioral tests for `/ingest`'s upfront "scaffolded?" precondition check.

Per [ADR-0019](../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md)
and v0.3 slice G (#88), `/ingest` no longer scaffolds new campaigns —
the bootstrap front door is `/init-campaign`. `/ingest` requires a
pre-scaffolded campaign repo and hard-stops if invoked against an
unscaffolded directory.

The precondition check inspects the same Step 1 marker set documented
in `references/scaffolder.md` (read-only — no Steps 2–4 writes):

- `CLAUDE.md`
- `.claude/rules/sessions.md`
- `.claude/rules/adventures.md`
- `campaign.md`

If any are absent, the precondition fails with the verbatim hard-stop
message specified in `skills/ingest/SKILL.md`:

> "This directory isn't a scaffolded campaign repo. Run `/init-campaign`
> to start a new campaign, or invoke `/ingest` from a campaign that's
> already scaffolded."

These tests embed a small **reference precondition checker** in Python —
a faithful translation of the SKILL.md "Precondition: scaffolded?"
section — and exercise it against `tmp_path` directories that mirror
each of the relevant cases: every marker present (passes), each marker
individually missing (fails), no markers at all (fails), empty
directory (fails). The hard-stop message text is also pinned so a
SKILL.md prose change without a test update surfaces as a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest


# The four marker files the precondition inspects. Mirrors
# `references/scaffolder.md` Step 1 and `skills/ingest/SKILL.md`
# "Precondition: scaffolded?".
PRECONDITION_MARKERS: tuple[str, ...] = (
    "CLAUDE.md",
    ".claude/rules/sessions.md",
    ".claude/rules/adventures.md",
    "campaign.md",
)

# The verbatim hard-stop message specified by `skills/ingest/SKILL.md`.
# Kept here so any drift between the test and the SKILL.md prose
# surfaces as a failure. The trailing period and the literal backticks
# around `/init-campaign` and `/ingest` are part of the message.
HARD_STOP_MESSAGE: str = (
    "This directory isn't a scaffolded campaign repo. "
    "Run `/init-campaign` to start a new campaign, "
    "or invoke `/ingest` from a campaign that's already scaffolded."
)


# --------------------------------------------------------------------------
# Reference precondition checker — encodes SKILL.md's "Precondition:
# scaffolded?" section in test code.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PreconditionResult:
    """Outcome of running the precondition check against a target.

    `passes` is True iff every marker in `PRECONDITION_MARKERS` is
    present. `missing` lists the markers that were absent — empty
    when `passes` is True. `message` is the GM-facing hard-stop
    message when `passes` is False; empty string when True (the
    precondition passes silently — there is no "all good" surface).
    """

    passes: bool
    missing: tuple[str, ...]
    message: str


def check_scaffolded_precondition(target: Path) -> PreconditionResult:
    """Run the SKILL.md "Precondition: scaffolded?" check against `target`.

    Read-only inspection of the same Step 1 marker set documented in
    `references/scaffolder.md`. No writes. No git inspection (the
    `.git/` marker the scaffolder consults at Step 1 is about
    refusing to re-scaffold; the `/ingest` precondition consults the
    content markers only, since `/ingest` requires those to do
    extraction).

    Returns a `PreconditionResult`:

    - `passes=True, missing=(), message=""` when every marker is
      present.
    - `passes=False, missing=(...), message=HARD_STOP_MESSAGE`
      otherwise.
    """
    missing = tuple(
        marker for marker in PRECONDITION_MARKERS
        if not (target / marker).is_file()
    )
    if not missing:
        return PreconditionResult(passes=True, missing=(), message="")
    return PreconditionResult(
        passes=False, missing=missing, message=HARD_STOP_MESSAGE
    )


# --------------------------------------------------------------------------
# Fixture: a tmp directory containing every precondition marker as an
# empty (but present) file. Tests then selectively unlink markers to
# exercise the failure cases.
# --------------------------------------------------------------------------


@pytest.fixture
def scaffolded_target(tmp_path: Path) -> Path:
    """Create a target directory with all four precondition markers present.

    The markers are touched as empty files — the precondition only
    inspects presence, not content (the SKILL.md prose specifies
    `is_file()`-equivalent presence; content validation is the
    scaffolder's job at write time, not the precondition's at read
    time).
    """
    target = tmp_path / "scaffolded-campaign"
    target.mkdir()
    for marker in PRECONDITION_MARKERS:
        marker_path = target / marker
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.touch()
    return target


# --------------------------------------------------------------------------
# Tests — external behavior only.
# --------------------------------------------------------------------------


class TestPreconditionPasses:
    """The precondition passes when every marker is present."""

    def test_all_markers_present_returns_passes_true(
        self,
        scaffolded_target: Path,
    ) -> None:
        result = check_scaffolded_precondition(scaffolded_target)
        assert result.passes, (
            "Precondition should pass when every marker is present; "
            f"missing reported: {result.missing}"
        )

    def test_passes_means_no_missing_markers(
        self,
        scaffolded_target: Path,
    ) -> None:
        result = check_scaffolded_precondition(scaffolded_target)
        assert result.missing == (), (
            "Passing precondition must report empty `missing`; "
            f"got {result.missing}"
        )

    def test_passes_means_empty_message(
        self,
        scaffolded_target: Path,
    ) -> None:
        """Passing precondition surfaces no GM-facing message.

        SKILL.md describes the precondition as silent on success:
        proceed to the settings preflight without saying anything.
        A passing precondition that nonetheless surfaces a message
        would be a UX regression.
        """
        result = check_scaffolded_precondition(scaffolded_target)
        assert result.message == "", (
            "Passing precondition must produce an empty message; "
            f"got {result.message!r}"
        )


class TestPreconditionFailsWhenMarkerMissing:
    """The precondition fails when any single marker is missing."""

    @pytest.mark.parametrize("missing_marker", PRECONDITION_MARKERS)
    def test_single_missing_marker_fails(
        self,
        scaffolded_target: Path,
        missing_marker: str,
    ) -> None:
        """Deleting any one marker makes the precondition fail.

        Parametrized over every marker individually so the test
        surfaces *which* marker the precondition treats as
        load-bearing — every one of them. A precondition that
        ignored any single marker would let `/ingest` proceed
        against a half-scaffolded directory.
        """
        (scaffolded_target / missing_marker).unlink()
        result = check_scaffolded_precondition(scaffolded_target)
        assert not result.passes, (
            f"Precondition should fail when {missing_marker} is "
            "missing; passed instead."
        )
        assert missing_marker in result.missing, (
            f"Precondition reported missing markers {result.missing} "
            f"but did not include {missing_marker} (the one we "
            "deleted). The marker reporter is wrong."
        )

    def test_empty_directory_fails(self, tmp_path: Path) -> None:
        """An empty directory is the canonical unscaffolded case."""
        target = tmp_path / "empty-dir"
        target.mkdir()
        result = check_scaffolded_precondition(target)
        assert not result.passes, (
            "Precondition should fail on an empty directory; passed."
        )
        # Every marker should be reported missing.
        assert set(result.missing) == set(PRECONDITION_MARKERS), (
            "Empty directory should report all four markers missing; "
            f"got {result.missing}"
        )

    def test_directory_with_unrelated_content_fails(
        self,
        tmp_path: Path,
    ) -> None:
        """A directory of source-doc markdown is not a scaffolded campaign.

        This is the v0.1/v0.2 path the GM would have used to invoke
        `/ingest` against — drop markdown notes in a directory, point
        `/ingest` at it. Per ADR-0019 that path is now `/init-campaign`'s
        job; `/ingest` hard-stops here.
        """
        target = tmp_path / "source-docs"
        target.mkdir()
        (target / "lost-mines.md").write_text(
            "# Lost Mines\n\nA published-module-shaped adventure.\n",
            encoding="utf-8",
        )
        (target / "faerun-gods.md").write_text(
            "# Gods of Faerun\n\nWorld info notes.\n", encoding="utf-8"
        )
        result = check_scaffolded_precondition(target)
        assert not result.passes, (
            "Precondition should fail when only source-doc markdown is "
            "present; passed instead."
        )
        assert set(result.missing) == set(PRECONDITION_MARKERS), (
            "Source-doc-only directory should report all four markers "
            f"missing; got {result.missing}"
        )


class TestPreconditionHardStopMessage:
    """The hard-stop message is pinned to SKILL.md verbatim.

    Per slice G (#88), the precondition surfaces a specific verbatim
    message when it fails. The message names both replacement entry
    points — `/init-campaign` for net-new campaigns, `/ingest` for
    pre-scaffolded campaigns — so the GM can route themselves
    correctly. A drift between this test and the SKILL.md prose
    means the GM-facing UX changed without coordinated updates.
    """

    def test_failing_precondition_surfaces_hard_stop_message(
        self,
        tmp_path: Path,
    ) -> None:
        target = tmp_path / "no-scaffold"
        target.mkdir()
        result = check_scaffolded_precondition(target)
        assert result.message == HARD_STOP_MESSAGE, (
            "Hard-stop message drifted from SKILL.md.\n"
            f"  expected: {HARD_STOP_MESSAGE!r}\n"
            f"  actual:   {result.message!r}"
        )

    def test_hard_stop_message_mentions_init_campaign(self) -> None:
        """The message directs the GM at `/init-campaign`.

        ADR-0019 hinges on this routing — without the explicit
        `/init-campaign` pointer the GM has no idea what to do next.
        """
        assert "/init-campaign" in HARD_STOP_MESSAGE, (
            "Hard-stop message does not mention `/init-campaign`; the "
            "GM has no replacement bootstrap entry pointed at."
        )

    def test_hard_stop_message_mentions_ingest_against_scaffolded(self) -> None:
        """The message names the other valid path for `/ingest`.

        A GM who is in fact at a scaffolded campaign that's missing a
        marker (file deletion, half-recovery) needs to know `/ingest`
        is the right verb once the scaffold is restored.
        """
        # Loose check: the message names `/ingest` somewhere after
        # mentioning that the directory isn't scaffolded.
        assert "/ingest" in HARD_STOP_MESSAGE, (
            "Hard-stop message does not mention `/ingest`; GMs at a "
            "broken scaffold have no surface telling them which verb "
            "to retry once the scaffold is restored."
        )


class TestPreconditionSurfacedInSkillMd:
    """The precondition's SKILL.md surface is load-bearing.

    Per slice G (#88), `skills/ingest/SKILL.md` adds an upfront
    "Precondition: scaffolded?" section that runs before any phase
    logic. The section's presence and the hard-stop message are part
    of the GM-facing contract; this test pins both.
    """

    def test_skill_md_has_precondition_section(
        self,
        repo_root: Path,
    ) -> None:
        skill_text = (
            repo_root / "skills" / "ingest" / "SKILL.md"
        ).read_text(encoding="utf-8")
        # The exact heading; SKILL.md prose uses this verbatim.
        assert "## Precondition: scaffolded?" in skill_text, (
            "`skills/ingest/SKILL.md` does not contain the "
            "'## Precondition: scaffolded?' section heading. Slice G "
            "(#88) added this section; a missing heading means the "
            "precondition is not surfaced in the SKILL.md the agent "
            "loads at invocation time."
        )

    def test_skill_md_hard_stop_message_matches_reference(
        self,
        repo_root: Path,
    ) -> None:
        """The SKILL.md prose carries the same verbatim hard-stop message.

        Slice G (#88) specifies the message verbatim; if SKILL.md
        drifts, the GM-facing UX changes without a coordinated test
        update. This is the canonical drift detector.
        """
        skill_text = (
            repo_root / "skills" / "ingest" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert HARD_STOP_MESSAGE in skill_text, (
            "`skills/ingest/SKILL.md` does not contain the verbatim "
            "precondition hard-stop message specified by slice G "
            "(#88).\n"
            f"  expected to find: {HARD_STOP_MESSAGE!r}\n"
            "Verify the message in SKILL.md matches this test's "
            "`HARD_STOP_MESSAGE` constant."
        )

    def test_skill_md_no_longer_documents_scaffold_phase(
        self,
        repo_root: Path,
    ) -> None:
        """Slice G removes the scaffold-only branch from `/ingest`.

        Per ADR-0019 and slice G (#88), `/ingest` no longer scaffolds —
        the scaffold phase moved into `references/scaffolder.md`
        consumed by `/init-campaign`. The SKILL.md prose should no
        longer document a Phase 1 scaffold step; verifying this
        catches regressions where someone re-inlines the scaffolder
        into `/ingest`.

        We check structurally — SKILL.md must not have a "Phase 1:
        Scaffold" heading.
        """
        skill_text = (
            repo_root / "skills" / "ingest" / "SKILL.md"
        ).read_text(encoding="utf-8")
        # Match Phase 1 headings that name the scaffold (case-insensitive)
        # — the "Phase 1: Scaffold (implemented)" heading the v0.2-era
        # SKILL.md carried.
        scaffold_phase_heading = re.compile(
            r"^##\s+Phase\s+1\s*:\s*Scaffold",
            re.IGNORECASE | re.MULTILINE,
        )
        assert not scaffold_phase_heading.search(skill_text), (
            "`skills/ingest/SKILL.md` still contains a 'Phase 1: "
            "Scaffold' heading. Per ADR-0019 and slice G (#88), the "
            "scaffold phase moved out of `/ingest` — it lives in "
            "`references/scaffolder.md` and is consumed by "
            "`/init-campaign`. Restore the slim shape per slice G."
        )


class TestPreconditionOrdersBeforePhases:
    """The precondition runs before any phase logic.

    SKILL.md specifies the precondition runs first — before the
    settings preflight, before Phase 2's survey, before anything
    that reads or writes campaign state. This is structurally
    enforced by the section ordering in SKILL.md: the precondition
    section appears before the settings preflight section, which
    appears before the Phase 2 section.

    We pin the ordering so a future SKILL.md restructure that
    accidentally moves the precondition into Phase 2 (or after the
    preflight) surfaces as a test failure.
    """

    def test_precondition_section_precedes_settings_preflight(
        self,
        repo_root: Path,
    ) -> None:
        skill_text = (
            repo_root / "skills" / "ingest" / "SKILL.md"
        ).read_text(encoding="utf-8")
        precondition_idx = skill_text.find("## Precondition: scaffolded?")
        preflight_idx = skill_text.find("## Settings preflight")
        assert precondition_idx != -1, (
            "Precondition section heading missing from SKILL.md."
        )
        assert preflight_idx != -1, (
            "Settings preflight section heading missing from SKILL.md."
        )
        assert precondition_idx < preflight_idx, (
            "Precondition section must precede the settings preflight; "
            f"precondition at offset {precondition_idx}, preflight at "
            f"{preflight_idx}. The precondition is the load-bearing "
            "first check per ADR-0019 — it has to run before the "
            "preflight touches anything."
        )

    def test_precondition_section_precedes_phase_2(
        self,
        repo_root: Path,
    ) -> None:
        skill_text = (
            repo_root / "skills" / "ingest" / "SKILL.md"
        ).read_text(encoding="utf-8")
        precondition_idx = skill_text.find("## Precondition: scaffolded?")
        phase_2_idx = skill_text.find("## Phase 2: Survey")
        assert precondition_idx != -1, (
            "Precondition section heading missing from SKILL.md."
        )
        assert phase_2_idx != -1, (
            "Phase 2 section heading missing from SKILL.md."
        )
        assert precondition_idx < phase_2_idx, (
            "Precondition section must precede Phase 2 (Survey); "
            f"precondition at offset {precondition_idx}, Phase 2 at "
            f"{phase_2_idx}. A precondition running after Phase 2 "
            "starts would let the survey read source docs against an "
            "unscaffolded directory."
        )
